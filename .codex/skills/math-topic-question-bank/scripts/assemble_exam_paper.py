#!/usr/bin/env python3
"""Assemble deterministic student/teacher assignments from an exam paper manifest."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
from typing import Any

import yaml

from derive_student_assignment import strip_teacher_fields
from exam_source_contracts import ExamItemSource, ExamPaperManifest
from question_bank_contracts import QuestionBank, QuestionBankItem
from validate_question_bank import load_yaml, validate_manifest


QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}


def find_question(assignment: dict[str, Any]) -> dict[str, Any]:
    found = [
        block
        for section in assignment.get("sections", [])
        if isinstance(section, dict) and section.get("type") == "practice"
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") in QUESTION_TYPES
    ]
    if len(found) != 1:
        raise ValueError(f"single-item assignment contains {len(found)} practice questions")
    return found[0]


def rebase_assets(value: Any, source_dir: Path, output_dir: Path) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"image_path", "tikz_path"} and isinstance(child, str):
                asset = Path(child)
                if not asset.is_absolute():
                    asset = (source_dir / asset).resolve()
                result[key] = Path(os.path.relpath(asset, output_dir)).as_posix()
            else:
                result[key] = rebase_assets(child, source_dir, output_dir)
        return result
    if isinstance(value, list):
        return [rebase_assets(child, source_dir, output_dir) for child in value]
    return copy.deepcopy(value)


def load_approved_source(bank_path: Path, item: QuestionBankItem) -> ExamItemSource:
    if not item.source_ref:
        raise ValueError(f"{item.id}: source_ref is required for exam paper assembly")
    source_path = bank_path.parent / item.source_ref
    source = ExamItemSource.model_validate(load_yaml(source_path))
    if source.item_id != item.id:
        raise ValueError(f"{item.id}: source_ref item_id differs")
    transcription = source.transcription
    if transcription.human_review != "approved":
        raise ValueError(f"{item.id}: human review has not been approved")
    return source


def assemble(
    manifest_path: Path, output_dir: Path, version: str
) -> dict[str, Any]:
    manifest = ExamPaperManifest.model_validate(load_yaml(manifest_path))
    bank_path = (manifest_path.parent / manifest.question_bank).resolve()
    bank, errors = validate_manifest(bank_path)
    if errors:
        raise ValueError("question bank validation failed: " + "; ".join(errors))
    assert bank is not None
    if bank.bank.status != "ready":
        raise ValueError("question bank must have status ready")
    by_id = {item.id: item for item in bank.items}

    sections: list[dict[str, Any]] = []
    total_points = 0
    ordered_ids: list[str] = []
    source_keys: list[str] = []
    for section in manifest.sections:
        blocks: list[dict[str, Any]] = []
        for ordinal, item_id in enumerate(section.item_ids, start=1):
            item = by_id.get(item_id)
            if item is None:
                raise ValueError(f"{item_id}: not found in question bank")
            source = load_approved_source(bank_path, item)
            teacher_path = bank_path.parent / item.teacher_assignment
            teacher = load_yaml(teacher_path)
            block = rebase_assets(
                find_question(teacher), teacher_path.parent.resolve(), output_dir.resolve()
            )
            if version == "student":
                block = strip_teacher_fields(block)
            if block.get("type") in {"problem", "short_answer"} and not block.get("label"):
                block["label"] = f"第 {ordinal} 题"
            total_points += int(block.get("points") or 0)
            ordered_ids.append(item_id)
            source_keys.append(source.source_key)
            blocks.append(block)
        sections.append(
            {
                "id": section.id,
                "title": section.title,
                "type": "practice",
                "visibility": "student" if version == "student" else "both",
                "blocks": blocks,
            }
        )

    suffix = "学生版" if version == "student" else "教师版"
    source_artifacts: dict[str, Any] = {
        "paper_manifest": os.path.relpath(manifest_path, output_dir),
        "question_bank": os.path.relpath(bank_path, output_dir),
        "selected_question_ids": ordered_ids,
        "source_keys": source_keys,
    }
    if manifest.paper.source_archive:
        source_artifacts["source_archive"] = manifest.paper.source_archive
    meta: dict[str, Any] = {
        "title": f"{manifest.paper.title} · {suffix}",
        "grade": manifest.paper.grade,
        "subject": manifest.paper.subject,
        "total_points": total_points,
        "version": version,
        "show_answers": version == "teacher",
        "source_artifacts": source_artifacts,
    }
    if manifest.paper.duration:
        meta["duration"] = manifest.paper.duration
    return {
        "meta": meta,
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "inline",
        },
        "sections": sections,
    }


def write_assignment(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        for version in ("student", "teacher"):
            output = output_dir / f"exam.{version}.assignment.yaml"
            write_assignment(output, assemble(manifest_path, output_dir, version))
            print(output)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
