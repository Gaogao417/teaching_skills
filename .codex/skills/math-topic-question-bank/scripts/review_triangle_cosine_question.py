#!/usr/bin/env python3
"""Record one hash-bound review decision for a triangle cosine question."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import yaml

from triangle_cosine_contracts import CandidateDatabase, QuestionReview, ReviewEntry


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CANDIDATES = SCRIPT_DIR.parent / "data/triangle-cosine-question-candidates.yaml"
DEFAULT_REVIEW = SCRIPT_DIR.parent / "data/triangle-cosine-question-review.yaml"


def load_candidates(path: Path) -> CandidateDatabase:
    return CandidateDatabase.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_review(path: Path) -> QuestionReview:
    if not path.exists():
        return QuestionReview.model_validate(
            {
                "schema": "math_triangle_cosine_review/v1",
                "candidate_database_id": "triangle-cosine-question-candidates",
                "entries": [],
            }
        )
    return QuestionReview.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def save_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=140)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question_id")
    parser.add_argument("--decision", choices=["approved", "rejected"], required=True)
    parser.add_argument("--reason")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()
    candidates = load_candidates(args.candidates.resolve())
    questions = {question.id: question for question in candidates.questions}
    if args.question_id not in questions:
        raise SystemExit(f"unknown question id: {args.question_id}")
    question = questions[args.question_id]
    entry = ReviewEntry(
        question_id=question.id,
        content_hash=question.content_hash,
        decision=args.decision,
        reason=args.reason,
    )
    review = load_review(args.review.resolve())
    entries = {existing.question_id: existing for existing in review.entries}
    entries[entry.question_id] = entry
    updated = review.model_copy(update={"entries": [entries[key] for key in sorted(entries)]})
    save_atomic(args.review.resolve(), updated.model_dump(by_alias=True, mode="json"))
    print(f"{question.id}: {entry.decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
