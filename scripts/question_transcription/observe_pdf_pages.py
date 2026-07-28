#!/usr/bin/env python3
"""Observe PDF page windows with one joint MiMo transcription+bbox request."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import PaperMeta, Provider
from scripts.question_transcription.mimo_client import MimoClient
from scripts.question_transcription.pdf_observation_contracts import (
    PdfPage,
    PdfPageObservation,
    PdfSourceManifest,
)

PROMPT_VERSION = "pdf-joint-observation-v3"
SYSTEM_PROMPT = r"""
你是数学试卷视觉转录器。对给定的连续页面一次完成文字/公式忠实转录和独立题图 bbox 识别。
只返回 JSON 对象 {"questions": [...]}。每题字段必须符合：
question_ref(数字字符串), question_number, section_ref, section_title,
question_type(choice|fillin|problem|short_answer), points,
content 或 null；content 含 stem_latex, choices, answer, clue, solution_steps, solution_notes；
question_evidence/solution_evidence 数组元素为 {page_number, box_norm:[left,top,right,bottom]}；
solution_start_anchor/solution_end_anchor；figures 数组元素为
{local_id,page_number,role:prompt|solution,order,box_norm,whiteout_norm,confidence,state,
note,needs_human_crop}；confidence 字典；continues_from_previous/continues_to_next；notes。
所有 *_norm 坐标必须是相对页面宽高的 0–1000 整数坐标，不要使用模型内部缩放图的像素。
question_evidence 是整题审计框，figure 是独立视觉对象，两者可重叠。
medium confidence 默认 state=needs_review；只有题号、角色、主体和标签都明确才 accepted。
看不到答案时允许 content=null 或 solution_evidence 为空，不得编造。公式用 LaTeX，保留原解答步骤数量与顺序。
不得返回 null：未知分值用 0，未知数组用 []，未知 clue 用“依据题目条件推导”，末题
solution_end_anchor 用 <END_OF_SOURCE>。figure confidence 必须是 high/medium/low 字符串。
每道已识别题必须显式返回 question_evidence 和 solution_evidence；如果当前页同时有题目与
“参考答案/解”文字，两类框都不能遗漏。figure bbox 必须完整包含全部线条、顶点字母、角度
或坐标标注，并在四边各留约页面宽高 1% 的安全边距，禁止裁掉标签。
""".strip()


def make_windows(
    pages: list[PdfPage], *, window_size: int = 3, overlap: int = 1
) -> list[list[PdfPage]]:
    if window_size < 1:
        raise ValueError("window_size must be positive")
    if not 0 <= overlap < window_size:
        raise ValueError("overlap must satisfy 0 <= overlap < window_size")
    step = window_size - overlap
    return [pages[start : start + window_size] for start in range(0, len(pages), step)]


def _page_path(manifest: PdfSourceManifest, page: PdfPage) -> Path:
    path = Path(page.source)
    if path.is_absolute():
        return path
    return Path(manifest.source_archive) / path


def _data_url(path: Path) -> str:
    media_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def observe_windows(
    manifest: PdfSourceManifest,
    *,
    paper: PaperMeta,
    client: MimoClient,
    window_size: int = 3,
    overlap: int = 1,
    document_role: str = "mixed",
) -> list[PdfPageObservation]:
    provider = Provider(
        kind="vision_api", name="xiaomi-mimo", version=f"{client.model}/{PROMPT_VERSION}"
    )
    observations = []
    for window in make_windows(
        manifest.pages, window_size=window_size, overlap=overlap
    ):
        window_id = f"p{window[0].page_number:03d}-p{window[-1].page_number:03d}"
        metadata = [
            {
                "page_number": page.page_number,
                "width_px": page.width_px,
                "height_px": page.height_px,
                "sha256": page.sha256,
            }
            for page in window
        ]
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"文档角色：{document_role}。页面元数据："
                    + json.dumps(metadata, ensure_ascii=False)
                ),
            }
        ]
        for page in window:
            content.extend(
                [
                    {"type": "text", "text": f"PAGE_NUMBER={page.page_number}"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _data_url(_page_path(manifest, page)),
                            "detail": "high",
                        },
                    },
                ]
            )
        result, _cache_hit = client.complete_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            cache_material={
                "page_sha256": [page.sha256 for page in window],
                "prompt_version": PROMPT_VERSION,
                "observation_schema": "math_pdf_page_observation/v1",
                "document_role": document_role,
            },
        )
        payload = {
            "schema": "math_pdf_page_observation/v1",
            "paper": paper.model_dump(by_alias=True, exclude_none=True),
            "provider": provider.model_dump(),
            "prompt_version": PROMPT_VERSION,
            "window_id": window_id,
            "pages": [page.model_dump() for page in window],
            "questions": _normalize_provider_questions(
                result.get("questions", []), window
            ),
        }
        observations.append(PdfPageObservation.model_validate(payload))
    return observations


def _normalize_provider_questions(
    questions: Any, pages: list[PdfPage]
) -> list[dict[str, Any]]:
    """Normalize provider quirks and convert normalized boxes to source pixels."""
    if not isinstance(questions, list):
        raise ValueError("provider questions must be a list")
    page_by_number = {page.page_number: page for page in pages}
    normalized = deepcopy(questions)
    for question in normalized:
        if not isinstance(question, dict):
            raise ValueError("each provider question must be an object")
        question["points"] = question.get("points") or 0
        question["notes"] = question.get("notes") or []
        question["confidence"] = question.get("confidence") or {}
        content = question.get("content")
        if isinstance(content, dict):
            content["choices"] = content.get("choices") or []
            content["clue"] = content.get("clue") or "依据题目条件推导。"
            content["solution_steps"] = content.get("solution_steps") or []
            content["solution_notes"] = content.get("solution_notes") or []
        question["question_evidence"] = question.get("question_evidence") or []
        question["solution_evidence"] = question.get("solution_evidence") or []
        question["figures"] = question.get("figures") or []
        if not question.get("solution_end_anchor"):
            question["solution_end_anchor"] = "<END_OF_SOURCE>"
        for evidence_name in ("question_evidence", "solution_evidence"):
            for evidence in question[evidence_name]:
                _convert_box(evidence, page_by_number, "box_norm", "box_px")
        for figure in question["figures"]:
            _convert_box(figure, page_by_number, "box_norm", "box_px")
            if "whiteout_norm" in figure:
                figure["whiteout_px"] = [
                    _norm_box_to_px(
                        box, page_by_number[int(figure["page_number"])]
                    )
                    for box in (figure.pop("whiteout_norm") or [])
                ]
            else:
                figure["whiteout_px"] = figure.get("whiteout_px") or []
            confidence = figure.get("confidence") or "low"
            if isinstance(confidence, dict):
                rank = {"low": 0, "medium": 1, "high": 2}
                values = [value for value in confidence.values() if value in rank]
                confidence = min(values, key=rank.get) if values else "low"
            figure["confidence"] = confidence
            if confidence == "medium" and figure.get("state") == "accepted":
                figure["state"] = "needs_review"
            figure["state"] = figure.get("state") or "needs_review"
            figure["needs_human_crop"] = bool(
                figure.get("needs_human_crop", False)
            )
    return normalized


def _convert_box(
    item: dict[str, Any],
    pages: dict[int, PdfPage],
    normalized_name: str,
    pixel_name: str,
) -> None:
    page_number = int(item["page_number"])
    if normalized_name in item:
        item[pixel_name] = _norm_box_to_px(
            item.pop(normalized_name), pages[page_number]
        )
    if pixel_name not in item:
        raise ValueError(f"provider region missing {normalized_name}")


def _norm_box_to_px(box: Any, page: PdfPage) -> list[int]:
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(type(value) is not int for value in box)
        or any(value < 0 or value > 1000 for value in box)
    ):
        raise ValueError("normalized bbox must be four integers in [0, 1000]")
    left, top, right, bottom = box
    return [
        round(left * page.width_px / 1000),
        round(top * page.height_px / 1000),
        round(right * page.width_px / 1000),
        round(bottom * page.height_px / 1000),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--paper-meta", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--window-size", type=int, default=3)
    parser.add_argument("--overlap", type=int, default=1)
    parser.add_argument(
        "--document-role", choices=["question", "solution", "mixed"], default="mixed"
    )
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    manifest = PdfSourceManifest.model_validate(
        yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    )
    paper = PaperMeta.model_validate(
        yaml.safe_load(args.paper_meta.read_text(encoding="utf-8"))
    )
    client = MimoClient(timeout_s=args.timeout, cache_dir=args.cache_dir)
    observations = observe_windows(
        manifest,
        paper=paper,
        client=client,
        window_size=args.window_size,
        overlap=args.overlap,
        document_role=args.document_role,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for observation in observations:
        output = args.output_dir / f"{observation.window_id}.observation.yaml"
        output.write_text(
            yaml.safe_dump(
                observation.model_dump(by_alias=True, exclude_none=True),
                allow_unicode=True,
                sort_keys=False,
                width=1000,
            ),
            encoding="utf-8",
        )
    print(f"PDF OBSERVED: windows={len(observations)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
