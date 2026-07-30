#!/usr/bin/env python3
"""Normalize imported staged exam items and refresh their content hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}


def read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def normalize_assignment(
    payload: dict[str, Any], *, item_id: str, is_teacher: bool
) -> dict[str, Any]:
    meta = payload.setdefault("meta", {})
    meta["version"] = "teacher" if is_teacher else "student"
    meta["show_answers"] = is_teacher
    meta.setdefault("source_artifacts", {"source_record": "source.yaml"})
    render = payload.setdefault("render", {})
    render["answer_key_position"] = "inline"

    questions: list[dict[str, Any]] = []
    for section in payload.get("sections", []):
        blocks = section.get("blocks", [])
        questions.extend(
            block
            for block in blocks
            if isinstance(block, dict) and block.get("type") in QUESTION_TYPES
        )
    if len(questions) != 1:
        raise ValueError(f"{item_id}: expected one question block, got {len(questions)}")
    question = questions[0]
    question["id"] = item_id
    meta["total_points"] = int(question.get("points") or 0)
    prompt_diagram = question.get("diagram_col") or question.get("prompt_diagram")
    if isinstance(prompt_diagram, dict):
        prompt_diagram["variant"] = "prompt"
        prompt_diagram["disclosure_policy"] = "clean"
        prompt_diagram.pop("caption", None)

    for section in payload.get("sections", []):
        blocks = section.get("blocks", [])
        standalone = [
            block
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "diagram"
        ]
        if standalone:
            if len(standalone) != 1 or question.get("diagram_col"):
                raise ValueError(f"{item_id}: ambiguous standalone prompt diagram")
            diagram = dict(standalone[0])
            diagram.pop("type", None)
            diagram.pop("id", None)
            question["diagram_col"] = diagram
            section["blocks"] = [block for block in blocks if block not in standalone]
        section["visibility"] = "both" if is_teacher else "student"

    if is_teacher:
        for index, image in enumerate(question.get("source_solution_images") or [], start=1):
            if not isinstance(image, dict):
                raise ValueError(f"{item_id}: invalid source solution image")
            image.setdefault("width", "0.96\\linewidth")
            image.setdefault("variant", "source_solution")
            image.setdefault("disclosure_policy", "teacher_only")
            image.setdefault("label", f"公众号原解答 {index}")
    return payload


def normalize_item(item_dir: Path) -> None:
    item_id = item_dir.name
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    student_path = item_dir / "student.resolved.assignment.yaml"
    source_path = item_dir / "source.yaml"
    teacher = normalize_assignment(
        read_yaml(teacher_path), item_id=item_id, is_teacher=True
    )
    student = normalize_assignment(
        read_yaml(student_path), item_id=item_id, is_teacher=False
    )
    source = read_yaml(source_path)
    source["content_hash"] = canonical_hash(
        {
            "teacher": teacher,
            "student": student,
            "crop_hashes": {
                role: [entry["output_sha256"] for entry in entries]
                for role, entries in source["crops"].items()
            },
        }
    )
    write_yaml(teacher_path, teacher)
    write_yaml(student_path, student)
    write_yaml(source_path, source)
    print(f"{item_id}: normalized")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    wanted = set(args.only)
    for item_dir in sorted((args.staging_dir / "items").glob("Q[0-9][0-9][0-9]")):
        if wanted and item_dir.name not in wanted:
            continue
        normalize_item(item_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
