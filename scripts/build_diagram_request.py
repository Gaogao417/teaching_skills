#!/usr/bin/env python3
"""Build a teaching-side diagram request from 01-structure-analysis.md.

The script is intentionally deterministic.  It does not ask a model to invent
diagram details; it consumes the optional `diagram_request_packet` emitted by
math-structure-analysis and wraps it in the JSON contract used by the local
GeometricScene-Builder adapter.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


GEOMETRY_HINTS = (
    "三角形",
    "圆",
    "垂直",
    "平行",
    "角平分线",
    "中线",
    "高",
    "等腰",
    "相似",
    "全等",
    "弦",
    "切线",
)

COORDINATE_HINTS = (
    "坐标",
    "x 轴",
    "y 轴",
    "函数",
    "图像",
    "直线",
    "抛物线",
    "一次函数",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_first_json_object(text: str) -> dict[str, Any]:
    for match in re.finditer(r"```json\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def infer_packet(problem_text: str) -> dict[str, Any]:
    normalized = problem_text.replace("\u3000", " ")
    has_geometry = any(token in normalized for token in GEOMETRY_HINTS)
    has_coordinate = any(token in normalized for token in COORDINATE_HINTS)
    if not has_geometry and not has_coordinate:
        return {
            "needs_diagram": False,
            "fallback": "结构分析未提供 diagram_request_packet，且未检测到稳定图形触发词。",
        }
    if has_coordinate and not has_geometry:
        diagram_type = "coordinate_geometry"
    elif has_coordinate and has_geometry:
        diagram_type = "auto"
    else:
        diagram_type = "synthetic_geometry"
    return {
        "needs_diagram": True,
        "diagram_type": diagram_type,
        "diagram_intent": "student_explanation",
        "objects_hint": {"points": [], "segments": [], "curves": [], "constraints": []},
        "teaching_focus": [],
        "must_not_imply": [],
        "fallback": "使用题干文字描述或教师手动画图建议。",
    }


def compact_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in ("", None, [])]
    if value in ("", None):
        return []
    return [value]


def build_request(
    structure_path: Path,
    infer_if_missing: bool,
    diagram_variant: str,
    disclosure_policy: str,
    diagram_job_id: str,
    problem_text_override: str,
) -> dict[str, Any]:
    text = read_text(structure_path)
    problem_text = problem_text_override or extract_section(text, "原题")
    summary = extract_first_json_object(text)
    packet = summary.get("diagram_request_packet")

    if not isinstance(packet, dict):
        packet = infer_packet(problem_text) if infer_if_missing else {
            "needs_diagram": False,
            "fallback": "结构分析 JSON 中没有 diagram_request_packet。",
        }

    diagram_type = packet.get("diagram_type") or "auto"
    teaching_focus = compact_list(packet.get("teaching_focus"))
    if not teaching_focus:
        teaching_focus = compact_list(summary.get("explanation_task_packet", {}).get("teaching_sequence"))
    objects_hint = packet.get("objects_hint", {})
    must_not_imply = compact_list(packet.get("must_not_imply"))
    if disclosure_policy == "clean":
        # Prompt diagrams are source-side figures.  They must not inherit
        # solution-side teaching cues such as midpoint/equality annotations.
        derived_tokens = ("BH=HD", "中点", "midpoint", "作高", "两次勾股", "看中点")
        teaching_focus = [
            item for item in teaching_focus
            if not any(token in str(item) for token in derived_tokens)
        ]
        if not teaching_focus:
            teaching_focus = ["读清点序", "标出题干给定对象"]
        if isinstance(objects_hint, dict):
            filtered_constraints = [
                item for item in compact_list(objects_hint.get("constraints"))
                if not any(token in str(item) for token in ("BH=HD", "Midpoint", "midpoint", "中点"))
            ]
            objects_hint = {**objects_hint, "constraints": filtered_constraints}
        must_not_imply.extend([
            "不要标注 BH=HD 或 H 为中点",
            "不要给 BH 与 HD 加相等刻痕",
            "不要写解题提示或推理结论",
        ])

    request = {
        "schema_version": "teaching-diagram-request/v1",
        "source_artifact": str(structure_path),
        "created_date": date.today().isoformat(),
        "needs_diagram": bool(packet.get("needs_diagram", False)),
        "diagram_type": diagram_type,
        "diagram_intent": packet.get("diagram_intent", "student_explanation"),
        "diagram_variant": diagram_variant,
        "disclosure_policy": disclosure_policy,
        "diagram_job_id": diagram_job_id,
        "problem_text": problem_text,
        "grade_or_topic": summary.get("problem_pattern", ""),
        "objects_hint": objects_hint,
        "teaching_focus": teaching_focus,
        "must_not_imply": must_not_imply,
        "fallback": packet.get("fallback", "textual_diagram_description"),
    }

    for key in ("max_retries", "seed", "wolfram_timeout_s", "wolfram_hard_timeout_s", "model_config"):
        if key in packet:
            request[key] = packet[key]

    return request


def main() -> None:
    parser = argparse.ArgumentParser(description="Build diagram-request.json from a structure analysis artifact")
    parser.add_argument("structure_analysis", type=Path, help="Path to 01-structure-analysis.md")
    parser.add_argument("--out", type=Path, help="Output JSON path; defaults beside structure analysis")
    parser.add_argument(
        "--infer-if-missing",
        action="store_true",
        help="Infer a minimal request from the problem text when diagram_request_packet is absent",
    )
    parser.add_argument(
        "--variant",
        choices=("prompt", "solution"),
        default="prompt",
        help="Diagram variant to request: prompt is clean source-side, solution may be annotated",
    )
    parser.add_argument(
        "--disclosure-policy",
        choices=("clean", "annotated"),
        help="Override disclosure policy; defaults to clean for prompt and annotated for solution",
    )
    parser.add_argument("--job-id", default="", help="Question-level diagram job id")
    parser.add_argument("--problem-text", default="", help="Override problem text for this diagram job")
    args = parser.parse_args()

    structure_path = args.structure_analysis.resolve()
    if not structure_path.exists():
        raise FileNotFoundError(structure_path)
    out_path = args.out or (structure_path.parent / "diagram-request.json")
    disclosure_policy = args.disclosure_policy or ("clean" if args.variant == "prompt" else "annotated")
    request = build_request(
        structure_path,
        args.infer_if_missing,
        args.variant,
        disclosure_policy,
        args.job_id,
        args.problem_text,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
