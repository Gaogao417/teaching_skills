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
    find_sequence_gaps,
    image_to_data_url,
    is_role_leak_response,
    looks_truncated,
    stitch_band_texts,
    strip_code_fences,
)


ADAPTER_ID = "qwen"

# 条带降级的横带几何：5 个约 25% 页高的小带，相邻重叠约 5% 页高。
# 45% 高条带在密集评分点页上仍会生成上千个 ``\cdots`` 后截断；缩短条带
# 才能真正降低单次视觉输出预算，同时重叠区保证边界公式能由相邻带补全。
_BAND_RATIOS = (
    (0.0, 0.25),
    (0.20, 0.45),
    (0.40, 0.65),
    (0.60, 0.85),
    (0.80, 1.0),
)
_BAND_UPSCALE = 2
_BAND_MAX_ATTEMPTS = 3

# 伪结构标记:忠实抄录的页文本不会出现这些排版命令——命中说明模型在
# 「重新排版」而不是「抄录」,该次输出不可用于拼接(2026-08-19 黄浦答案页
# 实测:同一带一次返回 338 字符 \section/\textbf 排版垃圾,重试即正常)。
_PSEUDO_STRUCTURE_MARKERS = (
    "\\section",
    "\\textbf",
    "\\includegraphics",
    "\\begin{figure}",
    "\\caption",
    "\\textwidth",
)


def _band_acceptable(text: str) -> bool:
    """条带输出是否可用于拼接。

    - 命中伪结构标记 → 废(模型在排版,不是抄录);
    - 无未闭合结构 → 可用;
    - 未闭合结构只出现在最后一行 → 可用(底边物理切断,相邻重叠带的完整
      重读 + stitch 的残行清除会补齐);出现在中部 → 废。
    """
    if any(marker in text for marker in _PSEUDO_STRUCTURE_MARKERS):
        return False
    if not looks_truncated(text):
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    return not looks_truncated("\n".join(lines[:-1]))


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

    def _stripe_fallback(self, image_path, job: PageTextJob):
        """整页输出被判定截断后的条带降级：横切 3 带、各 2x 放大重 OCR、
        按重叠去重拼接。任何条带仍呈现截断特征 → 结构化失败（fail-closed，
        由 barrier 拦下整个 run），绝不提交已知不完整的页文本。"""
        from PIL import Image

        sha = job.image.sha256.removeprefix("sha256:")[:16]
        band_dir = self.cache_dir / "bands" / sha
        band_dir.mkdir(parents=True, exist_ok=True)
        client = self._get_client()
        texts: list[str] = []
        for index, (top, bottom) in enumerate(_BAND_RATIOS):
            band_path = band_dir / f"band-{index}.png"
            with Image.open(image_path) as page:
                width, height = page.size
                crop = page.crop((0, int(height * top), width, int(height * bottom)))
                band = crop.resize(
                    (crop.width * _BAND_UPSCALE, crop.height * _BAND_UPSCALE),
                    Image.LANCZOS,
                )
                band.save(band_path)
            data_url, _ = image_to_data_url(band_path)
            try:
                text, _ = client.complete_text(
                    messages=build_messages(data_url),
                    cache_material={
                        "task": "page_text_ocr",
                        "prompt_version": PAGE_TEXT_PROMPT_VERSION,
                        "page_sha256": f"{job.image.sha256}#stripe{index}",
                        "stripe_geometry": [top, bottom, _BAND_UPSCALE],
                    },
                )
            except RuntimeError as exc:
                return None, PageTextFailure(
                    adapter_id=ADAPTER_ID,
                    kind="invalid_response",
                    attempts=1 + index,
                    detail=f"stripe band {index} request failed: {exc}",
                )
            if not text or not text.strip():
                return None, PageTextFailure(
                    adapter_id=ADAPTER_ID,
                    kind="truncated_page_text",
                    attempts=1 + index,
                    detail=f"stripe band {index} returned blank text",
                )
            text = strip_code_fences(text)
            if not text.strip():
                return None, PageTextFailure(
                    adapter_id=ADAPTER_ID,
                    kind="truncated_page_text",
                    attempts=1 + index,
                    detail=f"stripe band {index} was only a code fence",
                )
            # A band may legitimately cut through a formula/environment at its
            # physical lower edge — unclosed structure confined to the LAST line
            # is acceptable (the overlap re-read of the next band completes it,
            # and stitch_band_texts drops the covered fragment). Anything else —
            # pseudo-structure (\section/\textbf/\begin{figure}: the model is
            # typesetting, not transcribing) or unclosed structure mid-band —
            # marks the attempt garbage: retry with a cache-busting key, since
            # qwen sampling variance is high (2026-08-19 黄浦答案页实测:同一
            # 条带一次返回 338 字符排版垃圾、重试即得正常抄录).
            for attempt in range(1, _BAND_MAX_ATTEMPTS + 1):
                if _band_acceptable(text):
                    break
                if attempt == _BAND_MAX_ATTEMPTS:
                    return None, PageTextFailure(
                        adapter_id=ADAPTER_ID,
                        kind="truncated_page_text",
                        attempts=1 + index + attempt,
                        detail=(
                            f"stripe band {index} keeps producing pseudo-structure "
                            "or mid-band unclosed content after retries"
                        ),
                    )
                retry_text, _ = client.complete_text(
                    messages=build_messages(data_url),
                    cache_material={
                        "task": "page_text_ocr",
                        "prompt_version": PAGE_TEXT_PROMPT_VERSION,
                        "page_sha256": f"{job.image.sha256}#stripe{index}a{attempt}",
                        "stripe_geometry": [top, bottom, _BAND_UPSCALE],
                    },
                )
                retry_text = strip_code_fences(retry_text or "")
                if retry_text.strip():
                    text = retry_text
            texts.append(text)
        stitched = stitch_band_texts(texts)
        if looks_truncated(stitched):
            return None, PageTextFailure(
                adapter_id=ADAPTER_ID,
                kind="truncated_page_text",
                attempts=1 + len(texts),
                detail="stitched stripe text still looks truncated",
            )
        return stitched, None

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
        # 未配对围栏会让 looks_truncated 误判、围栏行也会污染拼接。
        text = strip_code_fences(text)
        # 截断守卫 + 枚举序列守卫:整页输出带截断特征(未闭合 $/围栏/环境),
        # 或选项字母/题号跳号(行内内容被悄悄丢掉、结构仍闭合——黄浦 002.png
        # 第 5 题只剩 (A)(B)(D) 即此类)时,降级到条带重 OCR。守卫对缓存命中
        # 同样生效——缓存里的坏文本也会触发降级并被拼接结果替换。
        enhancement = None
        gaps = find_sequence_gaps(text)
        if looks_truncated(text) or gaps:
            stitched, stripe_failure = self._stripe_fallback(image_path, job)
            if stripe_failure is not None:
                with _lf.generation(
                    "qwen-ocr",
                    model=self.model,
                    input={"page_number": job.page_number, "prompt": "stripe-fallback"},
                    metadata={"adapter": ADAPTER_ID, "page_number": job.page_number},
                ) as obs:
                    obs.update(
                        level="ERROR",
                        status_message=f"stripe fallback failed: {stripe_failure.detail}",
                    )
                return None, stripe_failure
            # 序列跳号触发时源材料真缺(如声明过的缺题)可能拼不回来——
            # 只要拼接结果没有新的截断特征就接受,缺题豁免由 staging 层
            # missing-questions.yaml 声明机制兜底。
            text = stitched
            enhancement = "stripe-fallback"
        extract = commit_extract(
            job=job, text=text, store=self.store, model=self.model,
            adapter_id=ADAPTER_ID, prompt_version=PAGE_TEXT_PROMPT_VERSION,
            cache_hit=cache_hit,
            ocr_enhancement=enhancement,
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
