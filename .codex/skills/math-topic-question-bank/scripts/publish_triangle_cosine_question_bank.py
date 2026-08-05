#!/usr/bin/env python3
"""Publish hash-current approved candidates as a reusable question bank."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import yaml

from triangle_cosine_contracts import (
    CandidateDatabase,
    PublishedQuestionBank,
    QuestionReview,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CANDIDATES = SCRIPT_DIR.parent / "data/triangle-cosine-question-candidates.yaml"
DEFAULT_REVIEW = SCRIPT_DIR.parent / "data/triangle-cosine-question-review.yaml"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "data/triangle-cosine-question-bank.yaml"
PROBLEM_TYPES = ("sss", "sas", "ssa", "aas", "asa")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--topic", default="四类三角比下的解三角形")
    parser.add_argument("--grade", default="九年级")
    args = parser.parse_args()
    candidates_path = args.candidates.resolve()
    review_path = args.review.resolve()
    candidates = CandidateDatabase.model_validate(yaml.safe_load(candidates_path.read_text(encoding="utf-8")))
    review = QuestionReview.model_validate(yaml.safe_load(review_path.read_text(encoding="utf-8")))
    decisions = {entry.question_id: entry for entry in review.entries}
    approved = [
        question
        for question in candidates.questions
        if question.id in decisions
        and decisions[question.id].decision == "approved"
        and decisions[question.id].content_hash == question.content_hash
    ]
    if not approved:
        raise SystemExit("no hash-current approved questions")
    counts = {
        problem_type: sum(question.problem_type == problem_type for question in approved)
        for problem_type in PROBLEM_TYPES
    }
    missing = [problem_type for problem_type, count in counts.items() if count == 0]
    if missing:
        raise SystemExit("approved bank does not cover: " + ", ".join(missing))
    version_source = "|".join(f"{question.id}:{question.content_hash}" for question in approved)
    version = hashlib.sha256(version_source.encode("utf-8")).hexdigest()[:12]
    payload = {
        "schema": "math_triangle_cosine_question_bank/v1",
        "bank": {
            "id": "triangle-cosine-question-bank",
            "topic": args.topic,
            "grade": args.grade,
            "version": version,
            "candidate_database": str(candidates_path),
            "review_file": str(review_path),
        },
        "questions": [question.model_dump(mode="json") for question in approved],
    }
    bank = PublishedQuestionBank.model_validate(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(bank.model_dump(by_alias=True, mode="json"), allow_unicode=True, sort_keys=False, width=140),
        encoding="utf-8",
    )
    print(f"QUESTION BANK PUBLISHED: version={version} counts={counts} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
