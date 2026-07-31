"""MiMo v2.5 page-text adapter (OpenAI-compatible).

MiMo's existing :class:`MimoClient` only offers ``complete_json`` (forces
``response_format=json_object``). The design calls for a plain-text OCR transport
that keeps ``complete_json`` behaviour intact. Rather than mutate the shared client
(and risk the existing transcription tests), this adapter adds a self-contained
plain-text call to the MiMo endpoint, reusing the same content-addressed disk-cache
pattern as :class:`BailianOcrClient`.

Bound by the composition root; the node never sees "mimo".
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from scripts.utilities.files.atomic_write import atomic_write_text
from scripts.utilities.files.hashing import stable_json_sha256

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap)
from ...contracts import PageTextFailure, PageTextJob
from ._common import (
    PAGE_TEXT_PROMPT_VERSION,
    build_messages,
    commit_extract,
    image_to_data_url,
)


ADAPTER_ID = "mimo"

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"


class MimoPageTextExtractor:
    """:class:`PageTextExtractor` backed by the MiMo v2.5 plain-text transport."""

    def __init__(self, *, model: str, store, api_key: str | None = None,
                 base_url: str | None = None, timeout_s: float = 120.0,
                 cache_dir: Path | None = None, http_client=None) -> None:
        import os

        self.model = model
        self.store = store
        self.cache_dir = cache_dir or (store.layout.cache_dir)
        self.api_key = api_key or os.environ.get("MIMO_API_KEY")
        self.base_url = (base_url or MIMO_BASE_URL).rstrip("/")
        self.timeout_s = timeout_s
        self.http_client = http_client

    def _cache_key(self, cache_material: dict) -> str:
        return stable_json_sha256(
            {
                "mode": "text",
                "request": cache_material,
                "model": self.model,
                "base_url": self.base_url,
            }
        )

    def _call_text(self, messages: list[dict], cache_material: dict) -> tuple[str, bool]:
        """Plain-text MiMo call with content-addressed disk cache (mirrors BailianOcrClient)."""

        cache_key = self._cache_key(cache_material)
        cache_path = self.cache_dir / f"{cache_key}.json" if self.cache_dir else None
        if cache_path and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("mode") == "text":
                return cached["raw_text"], True
        if not self.api_key:
            raise RuntimeError("MIMO_API_KEY is required for a live MiMo call")
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.01,
            "max_completion_tokens": 8192,
        }
        client = self.http_client or httpx.Client(timeout=self.timeout_s)
        close = self.http_client is None
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if response.is_error:
                raise RuntimeError(
                    f"MiMo HTTP {response.status_code}: {response.text[:2000]}"
                )
            raw = response.json()["choices"][0]["message"]["content"]
        finally:
            if close:
                client.close()
        if cache_path:
            atomic_write_text(
                cache_path,
                json.dumps(
                    {"cache_key": cache_key, "mode": "text", "raw_text": raw},
                    ensure_ascii=False,
                ),
            )
        return raw, False

    def extract(self, job: PageTextJob):
        image_path = self.store.layout.root / job.image.path
        if not image_path.exists():
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="source_hash_mismatch", attempts=1,
                detail=f"page image missing: {image_path}",
            )
        try:
            data_url, _ = image_to_data_url(image_path)
            messages = build_messages(data_url)
            text, cache_hit = self._call_text(
                messages,
                cache_material={
                    "task": "page_text_ocr",
                    "prompt_version": PAGE_TEXT_PROMPT_VERSION,
                    "page_sha256": job.image.sha256,
                },
            )
        except RuntimeError as exc:
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID,
                kind=_classify(str(exc)),
                attempts=1,
                detail=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="invalid_response", attempts=1,
                detail=f"{type(exc).__name__}: {exc}",
            )
        if text is None or not text.strip():
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="empty_text", attempts=1,
                detail="provider returned blank page text",
            )
        extract = commit_extract(
            job=job, text=text, store=self.store, model=self.model,
            adapter_id=ADAPTER_ID, prompt_version=PAGE_TEXT_PROMPT_VERSION,
            cache_hit=cache_hit,
        )
        return extract, None


def _classify(detail: str) -> str:
    low = detail.lower()
    if "429" in low or "rate" in low:
        return "rate_limited"
    if "timeout" in low or "timed out" in low:
        return "request_timed_out"
    if "api key" in low or "401" in low or "403" in low:
        return "authentication_failure"
    if "502" in low or "503" in low or "504" in low:
        return "provider_unavailable"
    return "invalid_response"
