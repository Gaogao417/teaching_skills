"""qwen3.5-ocr page-text adapter (DashScope, OpenAI-compatible).

Wraps the existing :class:`BailianOcrClient` (``complete_text`` — already a mature
plain-text OCR transport with content-addressed disk caching keyed on
``task + prompt_version + page_sha + model``). We point the model at
``qwen3.5-ocr`` (the dedicated OCR model) and reuse the OCR prompt so page output is
pure text + LaTeX with no question structure.

The adapter is bound by the composition root; the node never sees "qwen".
"""

from __future__ import annotations

import os
from pathlib import Path

from .._common_paths import repo_root  # noqa: F401  (ensures sys.path bootstrap)
from ...contracts import PageTextFailure, PageTextJob
from ._common import (
    PAGE_TEXT_PROMPT_VERSION,
    build_messages,
    commit_extract,
    image_to_data_url,
    is_role_leak_response,
)


ADAPTER_ID = "qwen"


class QwenPageTextExtractor:
    """:class:`PageTextExtractor` backed by BailianOcrClient (qwen3.5-ocr)."""

    def __init__(self, *, model: str, store, api_key: str | None = None,
                 base_url: str | None = None, timeout_s: float = 180.0,
                 cache_dir: Path | None = None, client=None) -> None:
        self.model = model
        self.store = store
        self.cache_dir = cache_dir or (store.layout.cache_dir)
        self._client = client  # injectable for tests; lazy-created otherwise
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_s = timeout_s

    def _get_client(self):
        if self._client is not None:
            return self._client
        from .bailian_ocr_client import BailianOcrClient

        self._client = BailianOcrClient(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self.model,
            timeout_s=self._timeout_s,
            cache_dir=self.cache_dir,
        )
        return self._client

    def extract(self, job: PageTextJob):
        image_path = self.store.layout.root / job.image.path
        if not image_path.exists():
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID,
                kind="source_hash_mismatch",
                attempts=1,
                detail=f"page image missing: {image_path}",
            )
        # Observability: a real model call is recorded as a ``generation``; a
        # cache-served result is recorded as a ``span`` (NOT a generation, so it
        # does not pollute model-call count/latency/token/cost metrics). We only
        # learn which path applied after ``complete_text`` returns, so we record
        # after the call rather than wrapping it. No-op when Langfuse is off.
        from ...observability import langfuse as _lf

        try:
            data_url, _ = image_to_data_url(image_path)
            messages = build_messages(data_url)
        except RuntimeError as exc:
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="invalid_response", attempts=1,
                detail=f"image read failed: {exc}",
            )
        prompt_shape = _lf.sanitize(_prompt_shape(messages))
        gen_input = {"page_number": job.page_number, "prompt": prompt_shape}
        gen_meta = {"adapter": ADAPTER_ID, "page_number": job.page_number}
        try:
            client = self._get_client()
            text, cache_hit = client.complete_text(
                messages=messages,
                cache_material={
                    "task": "page_text_ocr",
                    "prompt_version": PAGE_TEXT_PROMPT_VERSION,
                    "page_sha256": job.image.sha256,
                },
            )
        except RuntimeError as exc:
            # Mark the generation ERROR before the context exits so a failed OCR
            # is not displayed as a successful model call.
            with _lf.generation(
                "qwen-ocr",
                model=self.model,
                input=gen_input,
                metadata=gen_meta,
            ) as obs:
                obs.update(
                    level="ERROR",
                    status_message=f"{type(exc).__name__}: {exc}",
                )
            kind = _classify_runtime(str(exc))
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind=kind, attempts=1, detail=str(exc)
            )
        except Exception as exc:  # pragma: no cover - defensive
            with _lf.generation(
                "qwen-ocr",
                model=self.model,
                input=gen_input,
                metadata=gen_meta,
            ) as obs:
                obs.update(
                    level="ERROR",
                    status_message=f"{type(exc).__name__}: {exc}",
                )
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID,
                kind="invalid_response",
                attempts=1,
                detail=f"{type(exc).__name__}: {exc}",
            )
        # Success path: record cache hit as a span, cache miss as a generation.
        if cache_hit:
            with _lf.cache_span(
                "qwen-ocr.cache",
                metadata={**gen_meta, "page_text_chars": len(text) if text else 0},
            ) as obs:
                obs.update(output=text[:4000] if text else None)
        else:
            with _lf.generation(
                "qwen-ocr",
                model=self.model,
                input=gen_input,
                metadata=gen_meta,
            ) as obs:
                obs.update(
                    output=text[:4000] if text else None,
                    metadata={"cache_hit": False},
                )
        if text is None or not text.strip():
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="empty_text", attempts=1,
                detail="provider returned blank page text",
            )
        if is_role_leak_response(text):
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="invalid_response", attempts=1,
                detail="provider echoed the OCR persona / asked for the image instead of transcribing the page",
            )
        extract = commit_extract(
            job=job, text=text, store=self.store, model=self.model,
            adapter_id=ADAPTER_ID, prompt_version=PAGE_TEXT_PROMPT_VERSION,
            cache_hit=cache_hit,
        )
        return extract, None


def _prompt_shape(messages: list) -> list:
    """Return the OCR prompt structure with image bytes replaced by a size marker.

    Keeps the role/text structure visible in the trace without uploading
    megabytes of base64 page images. The result is JSON-safe and is passed
    through ``sanitize`` by the caller before reaching Langfuse.
    """

    redacted = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = str(part.get("image_url", {}).get("url", ""))
                    parts.append({"type": "image_url", "image_url": {"url": f"<base64 {len(url)} chars>"}})
                else:
                    parts.append(part)
            redacted.append({"role": m.get("role"), "content": parts})
        else:
            redacted.append({"role": m.get("role"), "content": content})
    return redacted


def _classify_runtime(detail: str) -> str:
    low = detail.lower()
    if "429" in low or "rate" in low:
        return "rate_limited"
    if "timeout" in low or "timed out" in low:
        return "request_timed_out"
    if "401" in low or "403" in low or "api key" in low:
        return "authentication_failure"
    if "5" in low[:1] or "502" in low or "503" in low or "504" in low:
        return "provider_unavailable"
    return "invalid_response"
