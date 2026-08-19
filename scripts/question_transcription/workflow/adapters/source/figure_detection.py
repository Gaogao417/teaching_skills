#!/usr/bin/env python3
"""Vision figure detection for pages without media-backed figures (Phase 2).

Two real source shapes have figures that exist only on the rendered page —
scan packs (2025-HUANGPU-YIMO) and DOCX volumes whose figures are VML shape
groups rather than media assets (2020-MINHANG-YIMO, where all 41 media are
formula WMFs and zero are diagrams). The architecture's prescribed answer
(docs/question-transcription-architecture.md §8.2) is a vision detection
provider emitting ``math_pdf_detection/v1``-style region boxes; this adapter
is that provider, backed by BaiLian ``qwen-vl-max`` (grounding-capable — the
OCR-dedicated ``qwen3.5-ocr`` returns malformed boxes in probes).

Detected crops are attached with ``attribution_review: needs_review`` so the
Review UI surfaces them as pending human confirmation: the reviewer verifies
or paste-replaces a precise crop. Detection failures degrade to a full-page
crop (also ``needs_review``) rather than blocking ingestion — the audit's
figure rule (figure stems must carry a visual) stays intact either way.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from ..page_text.bailian_ocr_client import BailianOcrClient

__all__ = [
    "FIGURE_DETECTION_PROMPT_VERSION",
    "FigureDetector",
    "detect_page_figures",
]

FIGURE_DETECTION_PROMPT_VERSION = "figure-detection-v1"
DETECTION_MODEL = "qwen-vl-max"

_PROMPT_TEMPLATE = """\
你是数学试卷页的插图定位器。下面给出一张试卷页图片和若干题号。请为每个题号\
定位它的配图插图（几何图形、函数图象、统计图、实物示意图等；不包括纯文字题\
干本身）在整页像素坐标系中的紧密边界框。

只输出 JSON，格式：
{{"figures":[{{"question_number":N,"box_px":[x0,y0,x1,y1]}}]}}

规则：
- 坐标为像素，原点在图片左上角，x 向右、y 向下；
- 一题有多张图时输出多行（同题号多条），box 取各图最紧的外接矩形；
- 某题号在页面上没有插图时，不要输出该题号；
- 不要输出 JSON 以外的任何内容。

需要定位的题号：
{question_list}
"""


class FigureDetector:
    """Detect per-question figure boxes on one rendered page (cached)."""

    def __init__(self, *, cache_dir: Path | None = None, api_key: str | None = None):
        self._client = BailianOcrClient(
            model=DETECTION_MODEL,
            cache_dir=cache_dir,
            api_key=api_key,
        )

    def detect(
        self,
        page_path: Path,
        *,
        page_sha256: str,
        questions: list[dict[str, Any]],
        page_size: tuple[int, int],
    ) -> dict[int, list[list[int]]]:
        """Return ``{question_number: [box_px, …]}`` for one page.

        ``questions`` carries ``question_number`` plus a short stem snippet per
        question so the detector can anchor boxes to the right item. Boxes are
        validated against the page dimensions; anything malformed drops that
        question rather than emitting a bad crop (fail closed per item).
        """
        if not questions:
            return {}
        question_list = "\n".join(
            f"- 第{q['question_number']}题：{str(q.get('stem', ''))[:40]}"
            for q in questions
        )
        data_url = _image_data_url(page_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {
                        "type": "text",
                        "text": _PROMPT_TEMPLATE.format(question_list=question_list),
                    },
                ],
            }
        ]
        payload, _cache_hit = self._client.complete_json(
            messages=messages,
            cache_material={
                "task": "figure_detection",
                "prompt_version": FIGURE_DETECTION_PROMPT_VERSION,
                "page_sha256": page_sha256,
                "questions": [
                    [q["question_number"], str(q.get("stem", ""))[:40]]
                    for q in questions
                ],
            },
            max_tokens=2048,
        )
        return _parse_boxes(payload, page_size, questions)


def detect_page_figures(
    detector: FigureDetector,
    page_path: Path,
    *,
    page_sha256: str,
    questions: list[dict[str, Any]],
    page_size: tuple[int, int],
) -> dict[int, list[list[int]]]:
    """Convenience wrapper; returns ``{}`` on any provider/parse failure."""
    try:
        return detector.detect(
            page_path,
            page_sha256=page_sha256,
            questions=questions,
            page_size=page_size,
        )
    except Exception:
        return {}


def _image_data_url(path: Path) -> str:
    raw = Path(path).read_bytes()
    suffix = Path(path).suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else "png"
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _parse_boxes(
    payload: Any, page_size: tuple[int, int], questions: list[dict[str, Any]]
) -> dict[int, list[list[int]]]:
    width, height = page_size
    wanted = {int(q["question_number"]) for q in questions}
    figures = payload.get("figures") if isinstance(payload, dict) else None
    if not isinstance(figures, list):
        figures = payload if isinstance(payload, list) else []
    boxes: dict[int, list[list[int]]] = {}
    for entry in figures:
        if not isinstance(entry, dict):
            continue
        number = entry.get("question_number")
        if not isinstance(number, int) or number not in wanted:
            continue
        box = entry.get("box_px")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            x0, y0, x1, y1 = (int(value) for value in box)
        except (TypeError, ValueError):
            continue
        # Clamp to the page and require a positive-area, sane-size rectangle
        # (a figure smaller than 24px or covering >95% of the page is not a
        # figure crop — treat as malformed).
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 - x0 < 24 or y1 - y0 < 24:
            continue
        if (x1 - x0) * (y1 - y0) > 0.95 * width * height:
            continue
        boxes.setdefault(number, []).append([x0, y0, x1, y1])
    return boxes
