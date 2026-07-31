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
        from scripts.question_transcription.bailian_ocr_client import BailianOcrClient

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
        # OTel span so the OCR prompt/result is visible in Langfuse. No-op when the
        # driver has not initialized a TracerProvider (offline tests).
        from opentelemetry import trace

        tracer = trace.get_tracer("question-ingestion.page-text")
        with tracer.start_as_current_span(
            "llm.qwen_ocr", attributes={"adapter": ADAPTER_ID, "model": self.model}
        ) as span:
            try:
                data_url, _ = image_to_data_url(image_path)
                messages = build_messages(data_url)
                # Record the prompt shape without the raw base64 image (too large);
                # keep the role/text structure for observability.
                span.set_attribute(
                    "gen_ai.prompt.messages",
                    _redact_messages(messages),
                )
                span.set_attribute("page.number", job.page_number)
                client = self._get_client()
                text, cache_hit = client.complete_text(
                    messages=messages,
                    cache_material={
                        "task": "page_text_ocr",
                        "prompt_version": PAGE_TEXT_PROMPT_VERSION,
                        "page_sha256": job.image.sha256,
                    },
                )
                if text:
                    span.set_attribute("gen_ai.response.text", text[:4000])
                span.set_attribute("cache_hit", bool(cache_hit))
            except RuntimeError as exc:
                # BailianOcrClient raises RuntimeError for HTTP errors / missing key.
                kind = _classify_runtime(str(exc))
                span.record_exception(exc)
                return None, PageTextFailure(
                    adapter_id=ADAPTER_ID, kind=kind, attempts=1, detail=str(exc)
                )
            except Exception as exc:  # pragma: no cover - defensive
                span.record_exception(exc)
                return None, PageTextFailure(
                    adapter_id=ADAPTER_ID,
                    kind="invalid_response",
                    attempts=1,
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


def _redact_messages(messages: list) -> str:
    """Render the OCR prompt as compact JSON with image bytes replaced by a marker.

    Langfuse should show the prompt *structure* (roles, text instructions) without
    uploading megabytes of base64 page images.
    """

    import json

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
    return json.dumps(redacted, ensure_ascii=False)


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
