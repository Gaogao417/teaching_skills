#!/usr/bin/env python3
"""Promote an approved exam source to human-approved transcription state."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from exam_source_contracts import ExamItemReview
from validate_exam_source import load_yaml, validate_source


def promote(source_path: Path, review_path: Path, repo_root: Path | None = None) -> dict:
    source, errors = validate_source(
        source_path, review_path=review_path, repo_root=repo_root
    )
    if errors:
        raise ValueError("; ".join(errors))
    assert source is not None
    review = ExamItemReview.model_validate(load_yaml(review_path))
    if review.status != "approved":
        raise ValueError(f"review status must be approved, got {review.status}")
    payload = load_yaml(source_path)
    payload["transcription"]["human_review"] = "approved"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()
    try:
        payload = promote(
            args.source.resolve(),
            args.review.resolve(),
            repo_root=args.repo_root,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
