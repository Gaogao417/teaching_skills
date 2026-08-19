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
import yaml

from ._common import (
    PAGE_TEXT_PROMPT_VERSION,
    build_messages,
    commit_extract,
    find_sequence_gaps,
    image_to_data_url,
    is_role_leak_response,
    looks_truncated,
    strip_code_fences,
)


ADAPTER_ID = "qwen"

# 人工页文本补丁(page-text-overrides.yaml,放在原始源文件旁,与
# non-question-pages.yaml / missing-questions.yaml 同一约定)。OCR 守卫发现
# 可疑页时不再自动修复(2026-08-19 用户裁定:自动拼接/重试机器拆除,检测→
# 上报→人工补):人工在此声明整页文本(手抄/从原生 docx 复制),或提供一张
# 手工截取的局部图片由工作流只对这张小图 OCR——小图输出短,不触发截断。
PAGE_TEXT_OVERRIDES_SCHEMA = "math_page_text_overrides/v1"
PAGE_TEXT_OVERRIDES_FILENAME = "page-text-overrides.yaml"


def load_page_text_overrides(payload, *, label: str) -> dict[int, dict]:
    """Parse and validate a page-text-overrides.yaml payload → {page_number: claim}."""
    if not isinstance(payload, dict):
        raise ValueError(f"{label}: YAML root must be a mapping")
    if payload.get("schema") != PAGE_TEXT_OVERRIDES_SCHEMA:
        raise ValueError(f"{label}: schema must be {PAGE_TEXT_OVERRIDES_SCHEMA}")
    if not isinstance(payload.get("paper_id"), str) or not payload["paper_id"].strip():
        raise ValueError(f"{label}: paper_id must be a non-empty string")
    raw = payload.get("overrides")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{label}: overrides must be a non-empty list")
    claims: dict[int, dict] = {}
    for index, claim in enumerate(raw):
        where = f"{label}.overrides[{index}]"
        if not isinstance(claim, dict):
            raise ValueError(f"{where} must be a mapping")
        page = claim.get("page_number")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError(f"{where}.page_number must be a positive integer")
        if page in claims:
            raise ValueError(f"{where}: duplicate override for page {page}")
        mode = claim.get("mode")
        if mode not in ("text", "image"):
            raise ValueError(f"{where}.mode must be one of text, image")
        if mode == "text" and (
            not isinstance(claim.get("text"), str) or not claim["text"].strip()
        ):
            raise ValueError(f"{where}.text must be a non-empty string")
        if mode == "image" and (
            not isinstance(claim.get("image"), str) or not claim["image"].strip()
        ):
            raise ValueError(f"{where}.image must be a non-empty path string")
        if not isinstance(claim.get("note"), str) or not claim["note"].strip():
            raise ValueError(f"{where}.note must be a non-empty string")
        if not isinstance(claim.get("verified_at"), str) or not claim["verified_at"].strip():
            raise ValueError(f"{where}.verified_at must be a non-empty string")
        claims[page] = claim
    return claims


class QwenPageTextExtractor:
    """:class:`PageTextExtractor` backed by BailianOcrClient (qwen3.5-ocr).

    OCR 守卫(截断特征 + 枚举序列跳号)发现可疑页时:查人工补丁文件
    (构造参数 ``overrides_path``)——有则用人工声明的整页文本(或对手工截取
    图做一次 OCR);无则照常提交 OCR 文本并在 sidecar 记 ``ocr_suspect``
    上报人工,由人在 Review UI / 补丁文件里补,不在适配器里自动修复。
    """

    def __init__(self, *, model: str, store, api_key: str | None = None,
                 base_url: str | None = None, timeout_s: float = 180.0,
                 cache_dir: Path | None = None, client=None,
                 overrides_path: Path | None = None) -> None:
        self.model = model
        self.store = store
        self.cache_dir = cache_dir or (store.layout.cache_dir)
        self._client = client  # injectable for tests; lazy-created otherwise
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._overrides_path = Path(overrides_path) if overrides_path else None
        self._overrides_cache: dict[int, dict] | None = None

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

    def _overrides_for(self, paper_id: str) -> dict[int, dict]:
        """Load human page-text overrides (empty when the file is absent)."""
        if self._overrides_cache is not None:
            return self._overrides_cache
        if self._overrides_path is None or not self._overrides_path.is_file():
            self._overrides_cache = {}
            return self._overrides_cache
        payload = yaml.safe_load(self._overrides_path.read_text(encoding="utf-8"))
        claims = load_page_text_overrides(payload, label=str(self._overrides_path))
        if payload.get("paper_id") != paper_id:
            raise ValueError(
                f"{self._overrides_path}: declares paper_id {payload.get('paper_id')!r} "
                f"but run is {paper_id!r}"
            )
        self._overrides_cache = claims
        return claims

    def _apply_override(self, claim: dict, job: PageTextJob):
        """Return the human-supplied page text (``text`` mode) or OCR the
        human-cropped image once (``image`` mode; a small crop's output budget
        cannot trigger the dense-page truncation)."""
        mode = claim.get("mode")
        if mode == "text":
            return str(claim["text"]), None
        image_path = Path(str(claim["image"]))
        if not image_path.is_absolute():
            image_path = (self._overrides_path.parent / image_path).resolve()
        if not image_path.is_file():
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="invalid_response", attempts=1,
                detail=f"override image missing for page {job.page_number}: {image_path}",
            )
        data_url, _ = image_to_data_url(image_path)
        try:
            text, _ = self._get_client().complete_text(
                messages=build_messages(data_url),
                cache_material={
                    "task": "page_text_ocr",
                    "prompt_version": PAGE_TEXT_PROMPT_VERSION,
                    "page_sha256": f"override:{image_path.name}",
                },
            )
        except RuntimeError as exc:
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="invalid_response", attempts=1,
                detail=f"override image OCR failed for page {job.page_number}: {exc}",
            )
        if not text or not text.strip():
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID, kind="empty_text", attempts=1,
                detail=f"override image OCR returned blank text for page {job.page_number}",
            )
        return strip_code_fences(text), None

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
        # 守卫前先剥离模型违反提示词加的 ```latex 围栏:围栏不是页面内容,
        # 未配对围栏会让 looks_truncated 误判。
        text = strip_code_fences(text)
        # 检测 → 上报/人工补,不自动修复(2026-08-19 用户裁定):
        # - 截断特征(未闭合 $/围栏/环境)或枚举序列跳号(选项字母/题号)→ 可疑;
        # - 有人工补丁(整页文本或手工截图)→ 用补丁,provenance 记 manual-override;
        # - 无补丁 → 照常提交 OCR 文本,sidecar 记 ocr_suspect 原因上报人工,
        #   由人在 Review UI / 补丁文件补,run 不因此失败。
        suspect_reasons = []
        if looks_truncated(text):
            suspect_reasons.append("truncated")
        suspect_reasons.extend(find_sequence_gaps(text))
        enhancement = None
        if suspect_reasons:
            try:
                overrides = self._overrides_for(job.paper_id)
            except ValueError as exc:
                return None, PageTextFailure(
                    adapter_id=ADAPTER_ID, kind="invalid_response", attempts=1,
                    detail=str(exc),
                )
            claim = overrides.get(job.page_number)
            if claim is not None:
                overridden, override_failure = self._apply_override(claim, job)
                if override_failure is not None:
                    return None, override_failure
                text = overridden
                enhancement = "manual-override"
                suspect_reasons = []
        extract = commit_extract(
            job=job, text=text, store=self.store, model=self.model,
            adapter_id=ADAPTER_ID, prompt_version=PAGE_TEXT_PROMPT_VERSION,
            cache_hit=cache_hit,
            ocr_enhancement=enhancement,
            ocr_suspect=suspect_reasons or None,
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
