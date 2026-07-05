#!/usr/bin/env python3
"""Export a reviewed skill trace into the existing assignment pipeline shape."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    from .db import get_review
except ImportError:  # pragma: no cover - supports direct script execution.
    from db import get_review


REVIEWED_TRACE_FILENAME = "01-skill-trace.reviewed.json"
STRUCTURE_ANALYSIS_FILENAME = "01-structure-analysis.md"
THREAD_HANDOFF_FILENAME = "thread_handoff.json"


def export_for_pipeline(
    *,
    reviewed_trace_id: str,
    out_dir: str | Path,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    review = get_review(reviewed_trace_id, db_path=db_path)
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reviewed_payload = _reviewed_trace_payload(review)
    structure_analysis = _structure_analysis_markdown(reviewed_payload)
    handoff_payload = _thread_handoff_payload(review, output_dir)

    reviewed_path = output_dir / REVIEWED_TRACE_FILENAME
    structure_path = output_dir / STRUCTURE_ANALYSIS_FILENAME
    handoff_path = output_dir / THREAD_HANDOFF_FILENAME

    _write_json(reviewed_path, reviewed_payload)
    structure_path.write_text(structure_analysis, encoding="utf-8")
    _write_json(handoff_path, handoff_payload)

    return {
        "status": "exported",
        "reviewed_trace_id": review["reviewed_trace_id"],
        "codex_thread_id": review["codex_thread_id"],
        "problem_case_id": review["problem_case_id"],
        "artifact_dir": str(output_dir),
        "files": {
            "reviewed_trace": str(reviewed_path),
            "structure_analysis": str(structure_path),
            "thread_handoff": str(handoff_path),
        },
    }


def _reviewed_trace_payload(review: dict[str, Any]) -> dict[str, Any]:
    reviewed_json = dict(review["reviewed_json"])
    reviewed_json["reviewed_trace_id"] = review["reviewed_trace_id"]
    reviewed_json["codex_thread_id"] = review["codex_thread_id"]
    reviewed_json["problem_case_id"] = review["problem_case_id"]
    return reviewed_json


def _thread_handoff_payload(review: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    return {
        "codex_thread_id": review["codex_thread_id"],
        "problem_case_id": review["problem_case_id"],
        "reviewed_trace_id": review["reviewed_trace_id"],
        "artifact_dir": str(output_dir),
        "next": {
            "explanation": "generate 02-student-explanation.assignment.yaml from reviewed trace",
            "assignment": "generate 03-adaptive-practice.*.assignment.yaml from reviewed trace",
        },
    }


def _structure_analysis_markdown(reviewed_trace: dict[str, Any]) -> str:
    problem = reviewed_trace["problem_case"]
    steps = reviewed_trace.get("steps", [])
    core_steps = [step for step in steps if step.get("is_core_step", True)]
    if not core_steps:
        core_steps = steps

    lines = [
        "# 结构分析",
        "",
        "## 题目",
        _text_or_placeholder(problem.get("raw_problem")),
        "",
        "## 用户预期解题思路",
        _text_or_placeholder(problem.get("expected_thinking")),
        "",
        "## 已审阅技能 Trace 摘要",
        "",
        "### 核心路径",
    ]
    if core_steps:
        lines.extend(_format_core_steps(core_steps))
    else:
        lines.append("暂无核心路径。")

    lines.extend(
        [
            "",
            "## 学生主要卡点",
        ]
    )
    lines.extend(_format_student_blockers(steps, reviewed_trace.get("validation", {})))

    lines.extend(
        [
            "",
            "## 讲解生成约束",
            "- 必须沿用 reviewed trace 的 core steps。",
            "- 必须先引导学生确认题目要求什么，再进入关系选择或列式。",
            "- 先给学生动作，再给算式或计算过程。",
            "",
            "## 练习生成约束",
            "- 练习应围绕 reviewed trace 的 core steps。",
            "- 每道题至少绑定一个 target step。",
            "- 变式不要只换数，要改变一个主维度。",
        ]
    )

    provided_solution = str(problem.get("provided_solution") or "").strip()
    if provided_solution:
        lines.extend(["", "## 参考解答", provided_solution])

    return "\n".join(lines).rstrip() + "\n"


def _format_core_steps(steps: list[dict[str, Any]]) -> list[str]:
    formatted = []
    for index, step in enumerate(steps, start=1):
        layer = _short_layer(str(step.get("cognitive_layer", "")))
        action = step.get("student_action_norm") or step.get("name") or "未命名动作"
        formatted.append(f"{index}. {layer}: {action}")
    return formatted


def _format_student_blockers(steps: list[dict[str, Any]], validation: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for step in steps:
        for item in step.get("common_errors") or []:
            text = str(item).strip()
            if text and text not in blockers:
                blockers.append(text)

    for key in ("warnings", "unresolved_questions"):
        values = validation.get(key, []) if isinstance(validation, dict) else []
        for item in values or []:
            text = str(item).strip()
            if text and text not in blockers:
                blockers.append(text)

    if not blockers:
        return ["- 暂无已审阅卡点。"]
    return [f"- {item}" for item in blockers]


def _short_layer(layer: str) -> str:
    return layer.split("_", 1)[0] if "_" in layer else layer or "step"


def _text_or_placeholder(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "（未提供）"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-trace-id", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path; defaults to SKILL_TRACE_DB or artifacts/skill_trace.db")
    args = parser.parse_args(argv)

    try:
        result = export_for_pipeline(
            reviewed_trace_id=args.reviewed_trace_id,
            out_dir=args.out_dir,
            db_path=args.db,
        )
    except (KeyError, ValueError, sqlite3.Error, OSError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
