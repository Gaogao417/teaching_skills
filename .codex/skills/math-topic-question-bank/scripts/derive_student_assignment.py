#!/usr/bin/env python3
"""Derive a student single-item assignment from a resolved teacher assignment."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import yaml


TEACHER_ONLY_KEYS = {"answer", "explanation", "solution_steps", "teaching"}


def is_solution_diagram(value: Any) -> bool:
    return isinstance(value, dict) and (
        value.get("variant") == "solution"
        or value.get("disclosure_policy") == "annotated"
    )


def strip_teacher_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_teacher_fields(child)
            for key, child in value.items()
            if key not in TEACHER_ONLY_KEYS and not is_solution_diagram(child)
        }
    if isinstance(value, list):
        return [strip_teacher_fields(child) for child in value]
    return value


def derive(teacher: dict[str, Any]) -> dict[str, Any]:
    student = copy.deepcopy(teacher)
    meta = student.setdefault("meta", {})
    meta["version"] = "student"
    meta["show_answers"] = False
    title = str(meta.get("title", ""))
    meta["title"] = title.replace("· 教师版", "· 学生版").replace("（教师版）", "（学生版）")

    kept_sections = []
    for section in student.get("sections", []):
        if not isinstance(section, dict):
            continue
        if section.get("type") == "answer_key" or section.get("visibility") == "teacher":
            continue
        section = strip_teacher_fields(section)
        section["visibility"] = "student"
        kept_sections.append(section)
    student["sections"] = kept_sections
    return student


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("teacher", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    raw = yaml.safe_load(args.teacher.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("teacher assignment root must be a mapping")
    if any(key == "diagram_slot" for key in _walk_keys(raw)):
        raise SystemExit("teacher assignment is not resolved: diagram_slot remains")
    student = derive(raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(student, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(args.out)
    return 0


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


if __name__ == "__main__":
    raise SystemExit(main())
