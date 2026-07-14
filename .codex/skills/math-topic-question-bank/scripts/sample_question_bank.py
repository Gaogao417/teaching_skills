#!/usr/bin/env python3
"""Randomly sample ready single-item packages into student/teacher assignments."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import random
import secrets
from typing import Any

import yaml

from question_bank_contracts import QuestionBank, QuestionBankItem


QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return data


def find_question(assignment: dict[str, Any]) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    for section in assignment.get("sections", []):
        if not isinstance(section, dict) or section.get("type") != "practice":
            continue
        found.extend(
            block
            for block in section.get("blocks", [])
            if isinstance(block, dict) and block.get("type") in QUESTION_TYPES
        )
    if len(found) != 1:
        raise ValueError(f"single-item assignment contains {len(found)} practice questions")
    return found[0]


def find_solution_diagrams(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for section in assignment.get("sections", []):
        if not isinstance(section, dict) or section.get("type") != "answer_key":
            continue
        for block in section.get("blocks", []):
            if not isinstance(block, dict):
                continue
            variant = block.get("variant") or block.get("diagram_variant")
            if block.get("type") == "diagram" and variant == "solution":
                found.append(block)
    return found


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


def mark_shared_diagram_reuse(value: Any, first_job_by_asset: dict[str, str]) -> None:
    if isinstance(value, dict):
        asset = value.get("image_path") or value.get("tikz_path")
        job_id = value.get("diagram_job_id")
        if isinstance(asset, str) and isinstance(job_id, str):
            if asset in first_job_by_asset and job_id != first_job_by_asset[asset]:
                value["reuse_from"] = first_job_by_asset[asset]
            else:
                first_job_by_asset[asset] = job_id
        for child in value.values():
            mark_shared_diagram_reuse(child, first_job_by_asset)
    elif isinstance(value, list):
        for child in value:
            mark_shared_diagram_reuse(child, first_job_by_asset)


def weighted_sample_without_replacement(
    items: list[QuestionBankItem], count: int, rng: random.Random
) -> list[QuestionBankItem]:
    pool = list(items)
    chosen: list[QuestionBankItem] = []
    for _ in range(count):
        total = sum(item.weight for item in pool)
        needle = rng.random() * total
        running = 0.0
        selected_index = len(pool) - 1
        for index, item in enumerate(pool):
            running += item.weight
            if needle <= running:
                selected_index = index
                break
        chosen.append(pool.pop(selected_index))
    return chosen


def build_assignment(
    bank: QuestionBank,
    manifest_path: Path,
    selected: list[QuestionBankItem],
    version: str,
    output_dir: Path,
    seed: int,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    solution_diagrams: list[dict[str, Any]] = []
    first_job_by_asset: dict[str, str] = {}
    total_points = 0
    for index, item in enumerate(selected, start=1):
        relative = item.student_assignment if version == "student" else item.teacher_assignment
        assignment_path = manifest_path.parent / relative
        source_assignment = load_yaml(assignment_path)
        block = rebase_assets(find_question(source_assignment), assignment_path.parent, output_dir)
        if block.get("type") in {"problem", "short_answer"}:
            block["label"] = f"第 {index} 题"
        mark_shared_diagram_reuse(block, first_job_by_asset)
        total_points += int(block.get("points") or 0)
        blocks.append(block)
        if version == "teacher":
            for source_diagram in find_solution_diagrams(source_assignment):
                solution_diagram = rebase_assets(source_diagram, assignment_path.parent, output_dir)
                mark_shared_diagram_reuse(solution_diagram, first_job_by_asset)
                solution_diagrams.append(solution_diagram)

    answer_items = [
        {"latex": f"第 {index} 题：{block.get('answer', '')}"}
        for index, block in enumerate(blocks, start=1)
    ]
    sections: list[dict[str, Any]] = [
        {
            "id": "sampled-questions",
            "title": "专题抽题",
            "type": "practice",
            "visibility": "student" if version == "student" else "both",
            "blocks": blocks,
        }
    ]
    if version == "teacher":
        sections.append(
            {
                "id": "answer-key",
                "title": "答案",
                "type": "answer_key",
                "visibility": "teacher",
                "blocks": [
                    {"type": "answer", "id": "sampled-answers", "title": "答案速查", "items": answer_items},
                    *solution_diagrams,
                ],
            }
        )

    return {
        "meta": {
            "title": f"{bank.bank.topic}专题抽题 · {'学生版' if version == 'student' else '教师版'}",
            "grade": bank.bank.grade,
            "subject": bank.bank.subject,
            "total_points": total_points,
            "version": version,
            "show_answers": version == "teacher",
            "source_artifacts": {
                "question_bank": os.path.relpath(manifest_path, output_dir),
                "selected_question_ids": [item.id for item in selected],
                "random_seed": seed,
            },
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
    parser.add_argument("bank", type=Path)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--difficulty", choices=["foundation", "standard", "challenge"])
    parser.add_argument("--tag")
    args = parser.parse_args()

    manifest_path = args.bank.resolve()
    bank = QuestionBank.model_validate(load_yaml(manifest_path))
    if bank.bank.status != "ready":
        raise SystemExit("question bank must have bank.status: ready before sampling")
    candidates = [item for item in bank.items if item.enabled]
    if args.difficulty:
        candidates = [item for item in candidates if item.difficulty == args.difficulty]
    if args.tag:
        candidates = [item for item in candidates if args.tag in item.skill_tags]
    if args.count < 1 or args.count > len(candidates):
        raise SystemExit(f"count must be between 1 and {len(candidates)} after filtering")

    seed = args.seed if args.seed is not None else secrets.randbits(63)
    selected = weighted_sample_without_replacement(candidates, args.count, random.Random(seed))
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for version in ("student", "teacher"):
        assignment = build_assignment(bank, manifest_path, selected, version, output_dir, seed)
        out = output_dir / f"sample.{version}.assignment.yaml"
        out.write_text(
            yaml.safe_dump(assignment, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        print(out)
    print(f"selected={','.join(item.id for item in selected)} seed={seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
