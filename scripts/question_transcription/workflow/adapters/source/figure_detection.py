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

The provider contract is deliberately fail-closed.  A calibration probe against
the current qwen-vl compatible endpoint established that grounding uses an
isotropic scale whose page width is 1000 units (so a portrait page's y maximum
is greater than 1000).  The prompt and parser pin that exact convention, and
every candidate must carry the matching question-number anchor and pass a
second crop-only visual check.  Invalid or ambiguous candidates are reported
to the staging adapter; they are never attached as prompt crops.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from ..page_text.bailian_ocr_client import BailianOcrClient

__all__ = [
    "FIGURE_DETECTION_PROMPT_VERSION",
    "FigureDetectionResult",
    "FigureDetector",
    "detect_page_figures",
]

FIGURE_DETECTION_PROMPT_VERSION = "figure-detection-v7-validated-edge-growth"
_LOCALIZATION_PROMPT_VERSION = "figure-detection-v5-width-normalized-complete"
_VALIDATION_PROMPT_VERSION = "figure-crop-validation-v2-refined-box"
DETECTION_MODEL = "qwen-vl-max"
_RETRYABLE_PROVIDER_ERRORS = {
    "ConnectError",
    "ConnectTimeout",
    "ConnectionError",
    "ReadTimeout",
    "RemoteProtocolError",
}

_PROMPT_TEMPLATE = """\
你是数学试卷页的插图定位器。下面给出一张试卷页图片和若干题号。请为每个题号\
定位它的配图插图（几何图形、函数图象、统计图、实物示意图等；不包括纯文字题\
干本身）的紧密边界框。

只输出 JSON，格式：
{{"coordinate_system":"width_normalized_1000","figures":[{{"question_number":N,\
"nearest_question_anchor":"第N题","box_w1000":[x0,y0,x1,y1]}}]}}

规则：
- 本页原图尺寸是 {page_width}×{page_height} 像素。坐标必须使用\
width_normalized_1000 等比例坐标：x_u=x_px/{page_width}×1000，\
y_u=y_px/{page_width}×1000；左上角为 (0,0)，右下角约为\
(1000,{page_y_max})，x 向右、y 向下；
- x/y 必须使用同一个基于图片宽度的比例。绝对禁止输出像素坐标，也禁止把 y\
独立缩放到 0–1000；
- nearest_question_anchor 必须抄写插图旁最近的题号或“第N题图”图注；
- box_w1000 只包围独立插图，保留图内所有点名、刻度、坐标轴和题号图注，\
不要包含题干、选项、答题线或相邻题；
- 一题有多张彼此独立的图时输出多条（同题号多条）；
- 同一个框不得分配给两个题号；
- 某题号在页面上没有插图时，不要输出该题号；
- 不要输出 JSON 以外的任何内容。

需要定位的题号：
{question_list}
"""

_VALIDATION_PROMPT_TEMPLATE = """\
你是数学试卷插图裁片校验器。裁片来自第{question_number}题，定位器回报的最近锚点是\
“{anchor}”。题干摘要：{stem}

只判断并精定位该题的目标插图，不要依据猜测补全裁片外内容。裁片尺寸是\
{crop_width}×{crop_height} 像素。

只输出 JSON：
{{"is_math_figure":true或false,\
"dominant_content":"math_figure|text|formula|answer_option|blank|other",\
"figure_box_w1000":[x0,y0,x1,y1],\
"confidence":"high|medium|low","reason":"一句短说明"}}

math_figure 包括几何图、函数图象、坐标图、统计图、表格和实物示意图；图中的少量\
字母、数字和图注不算文字主体。若主体是题干、选项、公式、答题线或空白，\
is_math_figure 必须为 false。

figure_box_w1000 使用以裁片宽度为 1000 的等比例坐标：x_u=x_px/{crop_width}×1000，\
y_u=y_px/{crop_width}×1000，裁片右下角约为 (1000,{crop_y_max})。它必须紧密包围\
第{question_number}题的目标插图，保留图内点名、刻度、坐标轴和自身图注，排除题干、\
选项、答题线、表格边框和相邻题插图。若裁片内无法唯一确认目标图，\
is_math_figure 必须为 false。不要输出 JSON 以外的内容。
"""


@dataclass
class FigureDetectionResult:
    """Validated per-question boxes plus human-readable rejection reasons."""

    boxes: dict[int, list[list[int]]] = field(default_factory=dict)
    review_notes: dict[int, list[str]] = field(default_factory=dict)

    def add_note(self, question_number: int, note: str) -> None:
        notes = self.review_notes.setdefault(question_number, [])
        if note not in notes:
            notes.append(note)


@dataclass(frozen=True)
class _Candidate:
    question_number: int
    box_px: list[int]
    anchor: str


class FigureDetector:
    """Detect per-question figure boxes on one rendered page (cached)."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ):
        self._client = client or BailianOcrClient(
            model=DETECTION_MODEL, cache_dir=cache_dir, api_key=api_key
        )

    def detect(
        self,
        page_path: Path,
        *,
        page_sha256: str,
        questions: list[dict[str, Any]],
        page_size: tuple[int, int],
    ) -> FigureDetectionResult:
        """Return only candidates that pass grounding and crop validation.

        ``questions`` carries ``question_number`` plus a short stem snippet per
        question so the detector can anchor boxes to the right item. Boxes are
        validated against the page dimensions; anything malformed drops that
        question rather than emitting a bad crop (fail closed per item).
        """
        if not questions:
            return FigureDetectionResult()
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
                        "text": _PROMPT_TEMPLATE.format(
                            question_list=question_list,
                            page_width=page_size[0],
                            page_height=page_size[1],
                            page_y_max=round(page_size[1] / page_size[0] * 1000),
                        ),
                    },
                ],
            }
        ]
        payload, _cache_hit = _complete_json_with_retry(
            self._client,
            messages=messages,
            cache_material={
                "task": "figure_detection",
                "prompt_version": _LOCALIZATION_PROMPT_VERSION,
                "page_sha256": page_sha256,
                "page_size": list(page_size),
                "questions": [
                    [q["question_number"], str(q.get("stem", ""))[:40]]
                    for q in questions
                ],
            },
            max_tokens=2048,
        )
        result, candidates = _parse_candidates(payload, page_size, questions)
        for candidate in candidates:
            validation_box = _pad_box(candidate.box_px, page_size)
            if not _sane_box(validation_box, page_size):
                result.add_note(
                    candidate.question_number,
                    "候选框补足安全留白后尺寸不合理",
                )
                continue
            try:
                validation, _cache_hit = _complete_json_with_retry(
                    self._client,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": _crop_data_url(
                                            page_path, validation_box
                                        )
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": _VALIDATION_PROMPT_TEMPLATE.format(
                                        question_number=candidate.question_number,
                                        anchor=candidate.anchor,
                                        stem=next(
                                            str(question.get("stem") or "")[:120]
                                            for question in questions
                                            if int(question["question_number"])
                                            == candidate.question_number
                                        ),
                                        crop_width=validation_box[2]
                                        - validation_box[0],
                                        crop_height=validation_box[3]
                                        - validation_box[1],
                                        crop_y_max=round(
                                            (validation_box[3] - validation_box[1])
                                            / (validation_box[2] - validation_box[0])
                                            * 1000
                                        ),
                                    ),
                                },
                            ],
                        }
                    ],
                    cache_material={
                        "task": "figure_crop_validation",
                        "prompt_version": _VALIDATION_PROMPT_VERSION,
                        "page_sha256": page_sha256,
                        "question_number": candidate.question_number,
                        "box_px": validation_box,
                    },
                    max_tokens=256,
                )
            except Exception as exc:
                result.add_note(
                    candidate.question_number,
                    f"插图裁片二次校验失败：{type(exc).__name__}",
                )
                continue
            refined_box = _refine_validated_box(
                validation, validation_box, page_size
            )
            if refined_box is None:
                reason = (
                    str(
                        validation.get("reason")
                        or "裁片主体或精定位子框不是可确认的数学插图"
                    )
                    if isinstance(validation, dict)
                    else "裁片校验返回格式无效"
                )
                result.add_note(
                    candidate.question_number,
                    f"候选框未通过插图内容校验：{reason}",
                )
                continue
            # The first pass and crop validator provide independent grounding
            # evidence.  Keep their union before pixel edge growth: some
            # qwen-vl responses correctly classify the crop but return a
            # sub-box covering only the visually salient half of the figure.
            refined_box = _box_union(refined_box, candidate.box_px)
            refined_box = _expand_clipped_ink(
                page_path, refined_box, validation_box, page_size
            )
            result.boxes.setdefault(candidate.question_number, []).append(
                refined_box
            )
        return result


def detect_page_figures(
    detector: FigureDetector,
    page_path: Path,
    *,
    page_sha256: str,
    questions: list[dict[str, Any]],
    page_size: tuple[int, int],
) -> FigureDetectionResult:
    """Convenience wrapper; provider failures become per-question review notes."""
    try:
        detected = detector.detect(
            page_path,
            page_sha256=page_sha256,
            questions=questions,
            page_size=page_size,
        )
        if isinstance(detected, FigureDetectionResult):
            return detected
        # Keep fake/legacy detector injection small and deterministic in tests.
        if isinstance(detected, dict):
            return FigureDetectionResult(boxes=detected)
        raise TypeError("figure detector returned an unsupported result")
    except Exception as exc:
        result = FigureDetectionResult()
        for question in questions:
            try:
                number = int(question["question_number"])
            except (KeyError, TypeError, ValueError):
                continue
            result.add_note(number, f"插图定位服务失败：{type(exc).__name__}")
        return result


def _image_data_url(path: Path) -> str:
    raw = Path(path).read_bytes()
    suffix = Path(path).suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else "png"
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _complete_json_with_retry(client: Any, **kwargs: Any) -> tuple[Any, bool]:
    """Retry bounded transport failures without changing fail-closed parsing."""

    for attempt in range(1, 4):
        try:
            return client.complete_json(**kwargs)
        except Exception as exc:
            retryable = type(exc).__name__ in _RETRYABLE_PROVIDER_ERRORS
            if not retryable or attempt == 3:
                raise
            time.sleep(0.25 * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def _crop_data_url(path: Path, box_px: list[int]) -> str:
    with Image.open(path) as image:
        crop = image.convert("RGB").crop(tuple(box_px))
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _parse_candidates(
    payload: Any, page_size: tuple[int, int], questions: list[dict[str, Any]]
) -> tuple[FigureDetectionResult, list[_Candidate]]:
    width, height = page_size
    stems = {
        int(question["question_number"]): str(question.get("stem") or "")
        for question in questions
    }
    wanted = set(stems)
    result = FigureDetectionResult()
    if (
        not isinstance(payload, dict)
        or payload.get("coordinate_system") != "width_normalized_1000"
    ):
        for number in wanted:
            result.add_note(
                number, "插图定位返回未声明 width_normalized_1000 坐标系"
            )
        return result, []
    figures = payload.get("figures") if isinstance(payload, dict) else None
    if not isinstance(figures, list):
        for number in wanted:
            result.add_note(number, "插图定位返回缺少 figures 列表")
        return result, []
    candidates: list[_Candidate] = []
    for entry in figures:
        if not isinstance(entry, dict):
            continue
        number = entry.get("question_number")
        if not isinstance(number, int) or number not in wanted:
            continue
        anchor = str(entry.get("nearest_question_anchor") or "").strip()
        if not _anchor_matches(number, anchor, stems[number]):
            result.add_note(number, "候选框旁的题号锚点与目标题号不一致")
            continue
        box = entry.get("box_w1000")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            result.add_note(number, "候选框缺少四元 box_w1000")
            continue
        try:
            normalized = [float(value) for value in box]
        except (TypeError, ValueError):
            result.add_note(number, "候选框 box_w1000 含非数值坐标")
            continue
        y_max = height / width * 1000
        if not (
            -25 <= normalized[0] <= 1025
            and -25 <= normalized[2] <= 1025
            and -25 <= normalized[1] <= y_max + 25
            and -25 <= normalized[3] <= y_max + 25
        ):
            result.add_note(number, "候选框超出 width_normalized_1000 可钳制范围")
            continue
        nx0 = min(1000.0, max(0.0, normalized[0]))
        ny0 = min(y_max, max(0.0, normalized[1]))
        nx1 = min(1000.0, max(0.0, normalized[2]))
        ny1 = min(y_max, max(0.0, normalized[3]))
        x0 = round(nx0 * width / 1000)
        y0 = round(ny0 * width / 1000)
        x1 = round(nx1 * width / 1000)
        y1 = round(ny1 * width / 1000)
        if not _sane_box([x0, y0, x1, y1], page_size):
            result.add_note(number, "候选框钳制并换算为像素后尺寸不合理")
            continue
        candidates.append(_Candidate(number, [x0, y0, x1, y1], anchor))

    # De-duplicate repeated rows for one question, then reject any box (or
    # practically identical box) assigned across different questions.
    deduplicated: list[_Candidate] = []
    for candidate in candidates:
        if any(
            existing.question_number == candidate.question_number
            and _intersection_over_union(existing.box_px, candidate.box_px) >= 0.9
            for existing in deduplicated
        ):
            continue
        deduplicated.append(candidate)
    candidates = deduplicated

    conflicted: set[int] = set()
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            if (
                left.question_number != right.question_number
                and _intersection_over_union(left.box_px, right.box_px) >= 0.9
            ):
                conflicted.update((left.question_number, right.question_number))
    if conflicted:
        for number in conflicted:
            result.add_note(number, "候选框与相邻题高度重合，无法唯一配对")
        candidates = [
            candidate
            for candidate in candidates
            if candidate.question_number not in conflicted
        ]
    return result, candidates


def _anchor_matches(question_number: int, anchor: str, stem: str) -> bool:
    if re.search(rf"第\s*{question_number}\s*题", anchor):
        return True
    subfigure = re.fullmatch(r"[（(]?\s*图\s*(\d+)\s*[）)]?", anchor)
    if subfigure is None:
        return False
    figure_number = int(subfigure.group(1))
    return bool(re.search(rf"图\s*{figure_number}(?!\d)", stem))


def _sane_box(box: list[int], page_size: tuple[int, int]) -> bool:
    width, height = page_size
    x0, y0, x1, y1 = box
    box_width, box_height = x1 - x0, y1 - y0
    if box_width < 24 or box_height < 24:
        return False
    area = box_width * box_height
    return area <= 0.65 * width * height


def _pad_box(box: list[int], page_size: tuple[int, int]) -> list[int]:
    """Add pixel-domain safety margin so labels/lines are not edge-clipped."""

    page_width, page_height = page_size
    x0, y0, x1, y1 = box
    padding = max(16, round(max(x1 - x0, y1 - y0) * 0.5))
    return [
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(page_width, x1 + padding),
        min(page_height, y1 + padding),
    ]


def _intersection_over_union(left: list[int], right: list[int]) -> float:
    lx0, ly0, lx1, ly1 = left
    rx0, ry0, rx1, ry1 = right
    intersection_width = max(0, min(lx1, rx1) - max(lx0, rx0))
    intersection_height = max(0, min(ly1, ry1) - max(ly0, ry0))
    intersection = intersection_width * intersection_height
    left_area = max(0, lx1 - lx0) * max(0, ly1 - ly0)
    right_area = max(0, rx1 - rx0) * max(0, ry1 - ry0)
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def _box_union(left: list[int], right: list[int]) -> list[int]:
    return [
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    ]


def _is_figure_content(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("is_math_figure") is True
        and payload.get("dominant_content") == "math_figure"
        and payload.get("confidence") in {"high", "medium"}
    )


def _refine_validated_box(
    payload: Any, outer_box: list[int], page_size: tuple[int, int]
) -> list[int] | None:
    """Convert the validator's crop-relative tight box back to page pixels."""

    if not _is_figure_content(payload) or not isinstance(payload, dict):
        return None
    box = payload.get("figure_box_w1000")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        normalized = [float(value) for value in box]
    except (TypeError, ValueError):
        return None
    ox0, oy0, ox1, oy1 = outer_box
    outer_width, outer_height = ox1 - ox0, oy1 - oy0
    y_max = outer_height / outer_width * 1000
    if not (
        -25 <= normalized[0] <= 1025
        and -25 <= normalized[2] <= 1025
        and -25 <= normalized[1] <= y_max + 25
        and -25 <= normalized[3] <= y_max + 25
    ):
        return None
    nx0 = min(1000.0, max(0.0, normalized[0]))
    ny0 = min(y_max, max(0.0, normalized[1]))
    nx1 = min(1000.0, max(0.0, normalized[2]))
    ny1 = min(y_max, max(0.0, normalized[3]))
    x0 = ox0 + round(nx0 * outer_width / 1000)
    y0 = oy0 + round(ny0 * outer_width / 1000)
    x1 = ox0 + round(nx1 * outer_width / 1000)
    y1 = oy0 + round(ny1 * outer_width / 1000)
    padding = max(6, round(outer_width * 0.015))
    refined = [
        max(ox0, x0 - padding),
        max(oy0, y0 - padding),
        min(ox1, x1 + padding),
        min(oy1, y1 + padding),
    ]
    return refined if _sane_box(refined, page_size) else None


def _expand_clipped_ink(
    page_path: Path,
    box: list[int],
    outer_box: list[int],
    page_size: tuple[int, int],
) -> list[int]:
    """Grow a model sub-box while visible ink is cut by one of its edges.

    Grounding models are useful at identifying the right figure but often put
    a tight edge through a long graph/triangle line.  Starting from the
    validated sub-box, follow only ink that actually reaches an edge.  Growth
    is bounded by the first-pass safety crop, so neighbouring questions cannot
    make this turn into a full-page fallback.
    """

    with Image.open(page_path) as image:
        grayscale = image.convert("L")
        x0, y0, x1, y1 = box
        ox0, oy0, ox1, oy1 = outer_box
        step = max(8, round(page_size[0] * 0.015))
        band = max(3, round(page_size[0] * 0.002))
        grew_any = False

        for _ in range(64):
            changed = False
            if x0 > ox0 and _edge_has_ink(
                grayscale, [x0, y0, min(x1, x0 + band), y1]
            ):
                x0 = max(ox0, x0 - step)
                changed = True
                grew_any = True
            if x1 < ox1 and _edge_has_ink(
                grayscale, [max(x0, x1 - band), y0, x1, y1]
            ):
                x1 = min(ox1, x1 + step)
                changed = True
                grew_any = True
            if y0 > oy0 and _edge_has_ink(
                grayscale, [x0, y0, x1, min(y1, y0 + band)]
            ):
                y0 = max(oy0, y0 - step)
                changed = True
                grew_any = True
            if y1 < oy1 and _edge_has_ink(
                grayscale, [x0, max(y0, y1 - band), x1, y1]
            ):
                y1 = min(oy1, y1 + step)
                changed = True
                grew_any = True
            if not changed:
                break

    # Keep a small white border for labels and a caption immediately outside
    # the last connected line, still never exceeding the validated outer crop.
    if not grew_any:
        return box
    clearance = max(8, round(page_size[0] * 0.025))
    expanded = [
        max(ox0, x0 - clearance),
        max(oy0, y0 - clearance),
        min(ox1, x1 + clearance),
        min(oy1, y1 + clearance),
    ]
    return expanded if _sane_box(expanded, page_size) else box


def _edge_has_ink(image: Image.Image, box: list[int]) -> bool:
    """Return whether a narrow edge band contains non-background pixels."""

    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return False
    histogram = image.crop((x0, y0, x1, y1)).histogram()
    dark_pixels = sum(histogram[:225])
    # Two dark pixels catches antialiased one-pixel graph lines while ignoring
    # isolated compression speckles on scanned pages.
    return dark_pixels >= 2
