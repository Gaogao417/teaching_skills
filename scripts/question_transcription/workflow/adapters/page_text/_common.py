"""Shared OCR prompt + helpers for page-text adapters (architecture §5.1).

The prompt is the single source of truth for what the page-text contract allows:
visible words in reading order, LaTeX formulae, necessary line breaks — and nothing
else. Both qwen and MiMo adapters feed the same prompt so cache keys and provenance
are comparable.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from ...contracts import (
    ArtifactRef,
    ExecutionProvenance,
    PageTextArtifact,
    PageTextExtract,
    PageTextJob,
)


PAGE_TEXT_PROMPT_VERSION = "page-text-ocr-v1"

# --- OCR 截断守卫（2026-08-19 闵行 Q23(2) 根因）-------------------------------
# qwen3.5-ocr 对长而密的公式页（官方解答页）会在输出中段悄悄截断：观测特征是
# 1) 行内公式定界符 ``$`` 计数为奇数（有一个 ``$`` 没闭合）；2) 输出尾部悬在
# 「分值点虚线」的 \cdot/… 串上，没有任何收尾文字；3) 代码围栏或 \begin/\end
# 环境不闭合。截断的页文本会让整卷转写模型把真实存在的内容标成
# 「未出现在所给逐页文本中」，因此必须在页文本层确定性检出。
_DANGLING_TAIL_RE = re.compile(
    r"(?:\\cdot|\\cdots|\\ldots|\\dots|\.{3,}|…|・|⋯|\s)+$"
)


def looks_truncated(text: str) -> bool:
    """页文本是否带有 OCR 输出截断的确定性特征。

    空白文本不算（空文本由 ``empty_text`` 契约处理）。误报的代价只是多跑
    一次条带降级，漏报的代价是解答内容静默丢失，所以判定从严。
    """
    if not text or not text.strip():
        return False
    if text.count("```") % 2 == 1:
        return True
    if text.count("\\begin{") != text.count("\\end{"):
        return True
    # 行内公式定界：去掉代码围栏内容后 ``$`` 必须成对。
    outside_fence = re.sub(r"```.*?```", "", text, flags=re.S)
    if outside_fence.count("$") % 2 == 1:
        return True
    return bool(_DANGLING_TAIL_RE.search(text.rstrip()))


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", "", line)


def stitch_band_texts(bands: list[str]) -> str:
    """把同一页的多个横条带 OCR 输出按顺序拼接，重叠行只保留一份。

    条带两两有 ~15% 高度重叠，同一段内容会在相邻条带各出现一次。按
    「空白归一后整行相等」在接缝处做尾部/头部最长匹配（最多回看 12 行）去
    重；匹配不上就原样接上——宁可保留重复行，也不能丢内容（整卷转写对
    重复行不敏感，对缺行敏感）。
    """
    merged: list[str] = []
    for band in bands:
        lines = [line for line in band.splitlines() if line.strip()]
        if not merged:
            merged.extend(lines)
            continue
        head = [line for line in lines]
        max_overlap = min(12, len(merged), len(head))
        overlap = 0
        for k in range(max_overlap, 0, -1):
            if [_normalize_line(x) for x in merged[-k:]] == [
                _normalize_line(x) for x in head[:k]
            ]:
                overlap = k
                break
        merged.extend(head[overlap:])
    return "\n".join(merged) + "\n"

PAGE_TEXT_PROMPT = (
    "你是数学试卷逐页 OCR 抄录器。只按视觉阅读顺序忠实抄录本页全部可见文字。\n"
    "要求:\n"
    "1. 数学公式写成 LaTeX。\n"
    "2. 保留必要的换行。\n"
    "3. 题号保持原样(如 `1．`、`2.`、`(1)`),不要识别题目边界。\n"
    "4. 不要识别 bbox、不要判断题型、不要生成答案字段、不要解释或纠错。\n"
    "5. 不要补全、不要合并多页。\n"
    "6. 直接输出该页的纯文本,不要 JSON、不要 Markdown 代码围栏、不要任何前言或结论。\n"
)


_SHA_PREFIX_RE = re.compile(r"^sha256:")

# Markers of a "role leak": the model echoed the OCR persona / asked for the image
# instead of transcribing it (observed with MiMo vision on some pages). These short
# strings are the persona the prompt assigns ("你是数学试卷逐页 OCR 抄录器"), reflected
# back as "我是…", plus the canonical "please provide the image" refusal. A real page
# transcript never contains them, so a hit means the provider produced no usable text.
_ROLE_LEAK_MARKERS = (
    "我是数学试卷逐页 OCR 抄录器",
    "我是数学试卷逐页OCR抄录器",
    "请提供图片",
    "请提供需要处理的图片",
    "请提供试卷图片",
)


def is_role_leak_response(text: str | None) -> bool:
    """True when ``text`` is a persona echo / image request, not a page transcript.

    Vision OCR models occasionally reply with the assistant persona assigned by the
    prompt ("我是数学试卷逐页 OCR 抄录器…请提供图片") instead of reading the page. Such a
    reply is non-empty (so it bypasses the blank-text guard) but carries zero page
    content; treating it as ``invalid_response`` lets the workflow fail the page loudly
    rather than silently dropping its coverage.
    """

    if not text:
        return False
    return any(marker in text for marker in _ROLE_LEAK_MARKERS)


def image_to_data_url(path: Path) -> tuple[str, str]:
    """Return ``(data_url, media_type)`` for a page image (PNG default)."""

    suffix = path.suffix.lower()
    media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    data = path.read_bytes()
    url = f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
    return url, media_type


def build_messages(image_data_url: str) -> list[dict]:
    """OpenAI-style multimodal chat messages for one page image + OCR prompt."""

    return [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": PAGE_TEXT_PROMPT},
            ],
        }
    ]


def commit_extract(
    *,
    job: PageTextJob,
    text: str,
    store,
    model: str,
    adapter_id: str,
    prompt_version: str,
    cache_hit: bool,
    ocr_enhancement: str | None = None,
) -> PageTextExtract:
    """Commit ``page-NNN.txt`` + sidecar and return the typed extract."""

    text_ref = store.commit_text(
        f"pages/page-{job.page_number:03d}.txt", text, "text/plain"
    )
    sidecar = {
        "page_number": job.page_number,
        "run_id": job.run_id,
        "paper_id": job.paper_id,
        "source_image": job.image.model_dump(mode="json"),
        "input_fingerprint": job.input_fingerprint,
        "model": model,
        "adapter_id": adapter_id,
        "prompt_version": prompt_version,
        "cache_hit": cache_hit,
    }
    if ocr_enhancement is not None:
        sidecar["ocr_enhancement"] = ocr_enhancement
    side_ref = store.commit_yaml(
        f"pages/page-{job.page_number:03d}.extract.yaml",
        sidecar,
        "page-text-extract/v1",
    )
    return PageTextExtract(
        artifact=PageTextArtifact(
            page_number=job.page_number,
            text=text_ref,
            metadata=side_ref,
            provenance=ExecutionProvenance(
                adapter_id=adapter_id, model=model, prompt_version=prompt_version
            ),
        )
    )
