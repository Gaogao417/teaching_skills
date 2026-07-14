#!/usr/bin/env python3
"""Validate a generated training-number database and optional review state."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from pydantic import ValidationError

from training_number_contracts import TrainingNumberDatabase, TrainingNumberReview


def load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def validate_paths(database_path: Path, review_path: Path | None = None) -> tuple[TrainingNumberDatabase | None, list[str]]:
    try:
        database = TrainingNumberDatabase.model_validate(load_yaml(database_path))
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
        return None, [str(exc)]

    errors: list[str] = []
    if review_path is not None and review_path.exists():
        try:
            review = TrainingNumberReview.model_validate(load_yaml(review_path))
            if review.database_id != database.database.id:
                errors.append("review database_id does not match database")
            unknown = sorted(set(review.disabled_entry_ids) - set(database.entries_by_id()))
            if unknown:
                errors.append(f"review contains unknown entry ids: {unknown[:5]}")
        except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
            errors.append(str(exc))
    return database, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    database, errors = validate_paths(args.database.resolve(), args.review.resolve() if args.review else None)
    if errors:
        print("TRAINING NUMBER DATABASE INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    assert database is not None
    print(f"TRAINING NUMBER DATABASE VALID: {database.entry_count} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
