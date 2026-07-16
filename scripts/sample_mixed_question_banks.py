#!/usr/bin/env python3
"""Sample equal-sized groups from ready question banks and shuffle one assignment."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import random
import secrets
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK_SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
sys.path.insert(0, str(QUESTION_BANK_SCRIPTS))

from question_bank_contracts import QuestionBank, QuestionBankItem  # noqa: E402
from sample_question_bank import (  # noqa: E402
    find_question,
    find_solution_diagrams,
    load_yaml,
    mark_shared_diagram_reuse,
    rebase_assets,
    weighted_sample_without_replacement,
)


def build_assignment(
    selections: list[tuple[Path, QuestionBank, QuestionBankItem]],
    version: str,
    output_dir: Path,
    title: str,
    provenance: list[dict[str, Any]],
    master_seed: int,
    shuffle_seed: int,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    solution_diagrams: list[dict[str, Any]] = []
    mixed_order: list[dict[str, Any]] = []
    first_job_by_asset: dict[str, str] = {}
    total_points = 0

    for position, (manifest_path, bank, item) in enumerate(selections, start=1):
        relative = item.student_assignment if version == "student" else item.teacher_assignment
        assignment_path = manifest_path.parent / relative
        source_assignment = load_yaml(assignment_path)
        block = rebase_assets(find_question(source_assignment), assignment_path.parent, output_dir)
        block["id"] = f"M{position:03d}"
        if block.get("type") in {"problem", "short_answer"}:
            block["label"] = f"第 {position} 题"
        mark_shared_diagram_reuse(block, first_job_by_asset)
        total_points += int(block.get("points") or 0)
        blocks.append(block)
        mixed_order.append(
            {
                "position": position,
                "topic": bank.bank.topic,
                "question_id": item.id,
            }
        )
        if version == "teacher":
            for source_diagram in find_solution_diagrams(source_assignment):
                solution_diagram = rebase_assets(source_diagram, assignment_path.parent, output_dir)
                solution_diagram = copy.deepcopy(solution_diagram)
                solution_diagram["id"] = f"M{position:03d}-solution"
                mark_shared_diagram_reuse(solution_diagram, first_job_by_asset)
                solution_diagrams.append(solution_diagram)

    sections: list[dict[str, Any]] = [
        {
            "id": "mixed-sampled-questions",
            "title": "相似模型混合练习",
            "type": "practice",
            "visibility": "student" if version == "student" else "both",
            "blocks": blocks,
        }
    ]
    if version == "teacher":
        answer_items = [
            {"latex": f"第 {index} 题：{block.get('answer', '')}"}
            for index, block in enumerate(blocks, start=1)
        ]
        sections.append(
            {
                "id": "answer-key",
                "title": "答案",
                "type": "answer_key",
                "visibility": "teacher",
                "blocks": [
                    {
                        "type": "answer",
                        "id": "mixed-sampled-answers",
                        "title": "答案速查",
                        "items": answer_items,
                    },
                    *solution_diagrams,
                ],
            }
        )

    return {
        "meta": {
            "title": f"{title} · {'学生版' if version == 'student' else '教师版'}",
            "grade": selections[0][1].bank.grade,
            "subject": selections[0][1].bank.subject,
            "total_points": total_points,
            "version": version,
            "show_answers": version == "teacher",
            "source_artifacts": {
                "question_banks": provenance,
                "master_seed": master_seed,
                "shuffle_seed": shuffle_seed,
                "mixed_order": mixed_order,
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
    parser.add_argument("--bank", action="append", type=Path, required=True)
    parser.add_argument("--count-per-bank", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--title", default="相似模型混合抽题")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    if len(args.bank) < 2:
        parser.error("--bank must be supplied at least twice")
    if args.count_per_bank < 1:
        parser.error("--count-per-bank must be positive")

    master_seed = args.seed if args.seed is not None else secrets.randbits(63)
    master_rng = random.Random(master_seed)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_all: list[tuple[Path, QuestionBank, QuestionBankItem]] = []
    provenance: list[dict[str, Any]] = []

    for bank_arg in args.bank:
        manifest_path = bank_arg.resolve()
        bank = QuestionBank.model_validate(load_yaml(manifest_path))
        if bank.bank.status != "ready":
            raise SystemExit(f"{manifest_path}: question bank must be ready")
        candidates = [item for item in bank.items if item.enabled]
        if args.count_per_bank > len(candidates):
            raise SystemExit(
                f"{manifest_path}: requested {args.count_per_bank}, only {len(candidates)} enabled"
            )
        bank_seed = master_rng.getrandbits(63)
        selected = weighted_sample_without_replacement(
            candidates, args.count_per_bank, random.Random(bank_seed)
        )
        selected_all.extend((manifest_path, bank, item) for item in selected)
        provenance.append(
            {
                "question_bank": Path(os.path.relpath(manifest_path, output_dir)).as_posix(),
                "topic": bank.bank.topic,
                "selected_question_ids": [item.id for item in selected],
                "random_seed": bank_seed,
            }
        )

    shuffle_seed = master_rng.getrandbits(63)
    random.Random(shuffle_seed).shuffle(selected_all)
    for version in ("student", "teacher"):
        assignment = build_assignment(
            selected_all,
            version,
            output_dir,
            args.title,
            provenance,
            master_seed,
            shuffle_seed,
        )
        output_path = output_dir / f"mixed.{version}.assignment.yaml"
        output_path.write_text(
            yaml.safe_dump(assignment, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        print(output_path)
    print(f"master_seed={master_seed} shuffle_seed={shuffle_seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
