#!/usr/bin/env python3
"""Concatenate reviewed sampled assignments into one student/teacher pair."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
from typing import Any

import yaml


QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def rebase_assets(value: Any, source_dir: Path, output_dir: Path) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"image_path", "tikz_path"} and isinstance(child, str):
                source = Path(child)
                if not source.is_absolute():
                    source = (source_dir / source).resolve()
                result[key] = Path(os.path.relpath(source, output_dir)).as_posix()
            else:
                result[key] = rebase_assets(child, source_dir, output_dir)
        return result
    if isinstance(value, list):
        return [rebase_assets(child, source_dir, output_dir) for child in value]
    return copy.deepcopy(value)


def practice_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for section in payload.get("sections", [])
        if isinstance(section, dict) and section.get("type") == "practice"
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") in QUESTION_TYPES
    ]


def build_combined(
    part_paths: list[Path],
    section_titles: list[str],
    version: str,
    output_dir: Path,
    title: str,
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    combined_blocks: list[dict[str, Any]] = []
    source_parts: list[str] = []
    next_number = 1
    grade = ""
    subject = "数学"

    for part_index, (part_path, section_title) in enumerate(
        zip(part_paths, section_titles, strict=True), start=1
    ):
        payload = load_yaml(part_path)
        meta = payload.get("meta", {})
        if meta.get("version") != version:
            raise ValueError(f"{part_path}: expected meta.version={version}")
        grade = grade or str(meta.get("grade", ""))
        subject = subject or str(meta.get("subject", "数学"))
        section_blocks: list[dict[str, Any]] = []
        for source_block in practice_blocks(payload):
            block = rebase_assets(source_block, part_path.parent, output_dir)
            block["id"] = f"H{next_number:03d}"
            if block.get("type") in {"problem", "short_answer"}:
                block["label"] = f"第 {next_number} 题"
            section_blocks.append(block)
            combined_blocks.append(block)
            next_number += 1
        section: dict[str, Any] = {
            "id": f"homework-part-{part_index}",
            "title": section_title,
            "type": "practice",
            "visibility": "student" if version == "student" else "both",
            "blocks": section_blocks,
        }
        sections.append(section)
        source_parts.append(Path(os.path.relpath(part_path, output_dir)).as_posix())

    if version == "teacher":
        missing_answers = [block["id"] for block in combined_blocks if not block.get("answer")]
        if missing_answers:
            raise ValueError(f"teacher blocks missing answers: {', '.join(missing_answers)}")
        sections.append(
            {
                "id": "answer-key",
                "title": "答案",
                "type": "answer_key",
                "visibility": "teacher",
                "blocks": [
                    {
                        "type": "answer",
                        "id": "combined-answers",
                        "title": "答案速查",
                        "items": [
                            {"latex": f"第 {index} 题：{block.get('answer', '')}"}
                            for index, block in enumerate(combined_blocks, start=1)
                        ],
                    }
                ],
            }
        )

    return {
        "meta": {
            "title": f"{title} · {'学生版' if version == 'student' else '教师版'}",
            "grade": grade,
            "subject": subject,
            "total_points": sum(int(block.get("points") or 0) for block in combined_blocks),
            "version": version,
            "show_answers": version == "teacher",
            "source_artifacts": {"assignment_parts": source_parts},
        },
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "after_page_break",
        },
        "sections": sections,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student-part", action="append", type=Path, required=True)
    parser.add_argument("--teacher-part", action="append", type=Path, required=True)
    parser.add_argument("--section-title", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    if not (
        len(args.student_part) == len(args.teacher_part) == len(args.section_title)
    ):
        parser.error("student parts, teacher parts, and section titles must have equal counts")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for version, part_paths in (
        ("student", args.student_part),
        ("teacher", args.teacher_part),
    ):
        resolved_paths = [path.resolve() for path in part_paths]
        combined = build_combined(
            resolved_paths,
            args.section_title,
            version,
            output_dir,
            args.title,
        )
        output_path = output_dir / f"combined.{version}.assignment.yaml"
        output_path.write_text(
            yaml.safe_dump(combined, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
