"""Shared OCR prompt + helpers for page-text adapters (ports-design §2.1 / §4).

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
