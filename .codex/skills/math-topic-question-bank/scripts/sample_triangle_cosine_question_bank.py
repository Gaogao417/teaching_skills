#!/usr/bin/env python3
"""Sample approved four-ratio triangle questions into one answer-only assignment."""

from __future__ import annotations

import argparse
import random
import secrets
from pathlib import Path
from typing import Any

import yaml

from triangle_cosine_contracts import PublishedQuestionBank


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BANK = SCRIPT_DIR.parent / "data/triangle-cosine-question-bank.yaml"
PROBLEM_TYPES = ("sss", "sas", "ssa", "aas", "asa")


def answer_latex(question: Any) -> str:
    return r"\text{ 或 }".join(answer.latex for answer in question.answers)


def build_assignment(bank: PublishedQuestionBank, selected: list[Any], seed: int) -> dict[str, Any]:
    question_blocks = [
        {
            "type": "fillin",
            "id": question.id.lower(),
            "stem_latex": question.stem_latex,
            "answer": answer_latex(question),
            "fillin_type": "line",
        }
        for question in selected
    ]
    answer_items = [
        {"latex": rf"{index}.\ {answer_latex(question)}"}
        for index, question in enumerate(selected, start=1)
    ]
    return {
        "meta": {
            "title": bank.bank.topic,
            "grade": bank.bank.grade,
            "subject": "数学",
            "version": "both",
            "show_answers": True,
            "source_artifacts": {
                "question_bank_id": bank.bank.id,
                "question_bank_version": bank.bank.version,
                "selected_question_ids": [question.id for question in selected],
                "random_seed": seed,
            },
        },
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "after_page_break",
        },
        "sections": [
            {
                "id": "triangle-cosine-questions",
                "title": "练习",
                "type": "practice",
                "visibility": "both",
                "blocks": question_blocks,
            },
            {
                "id": "answer-key",
                "title": "答案",
                "type": "answer_key",
                "visibility": "both",
                "blocks": [
                    {
                        "type": "answer",
                        "id": "triangle-cosine-answer-key",
                        "title": "答案",
                        "items": answer_items,
                    }
                ],
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", nargs="?", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count-per-type", type=int, default=1)
    for problem_type in PROBLEM_TYPES:
        parser.add_argument(f"--{problem_type}", type=int)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    bank_path = args.bank.resolve()
    bank = PublishedQuestionBank.model_validate(yaml.safe_load(bank_path.read_text(encoding="utf-8")))
    counts = {
        problem_type: getattr(args, problem_type)
        if getattr(args, problem_type) is not None
        else args.count_per_type
        for problem_type in PROBLEM_TYPES
    }
    if any(count < 0 for count in counts.values()) or sum(counts.values()) < 1:
        raise SystemExit("sampling counts must be non-negative and total at least one")
    seed = args.seed if args.seed is not None else secrets.randbits(63)
    rng = random.Random(seed)
    selected = []
    shortages = []
    excluded: set[str] = set()
    for problem_type in PROBLEM_TYPES:
        pool = [
            question
            for question in bank.questions
            if question.problem_type == problem_type and question.id not in excluded
        ]
        requested = counts[problem_type]
        if requested > len(pool):
            shortages.append(f"{problem_type}: requested {requested}, available {len(pool)}")
            continue
        chosen = rng.sample(pool, requested)
        selected.extend(chosen)
        excluded.update(question.id for question in chosen)
    if shortages:
        raise SystemExit("insufficient questions: " + "; ".join(shortages))
    assignment = build_assignment(bank, selected, seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(assignment, allow_unicode=True, sort_keys=False, width=160),
        encoding="utf-8",
    )
    print(
        f"ASSIGNMENT SAMPLED: selected={','.join(question.id for question in selected)} "
        f"seed={seed} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
