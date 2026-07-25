#!/usr/bin/env python3
"""Validate similarity realizations and their number-database references."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import yaml

from similarity_triangle_contracts import SimilarityTriangleDatabase
from training_number_review_state import load_database


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = SCRIPT_DIR.parent / "data/similarity-triangle-database.yaml"
DEFAULT_NUMBERS = SCRIPT_DIR.parent / "data/training-number-database.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, nargs="?", default=DEFAULT_DATABASE)
    parser.add_argument("--number-database", type=Path, default=DEFAULT_NUMBERS)
    args = parser.parse_args()
    numbers = load_database(args.number_database.resolve())
    payload = yaml.safe_load(args.database.resolve().read_text(encoding="utf-8"))
    database = SimilarityTriangleDatabase.model_validate(payload)
    number_entries = numbers.entries_by_id()
    errors = []
    for entry in database.entries:
        source = number_entries.get(entry.number_entry_id)
        if source is None:
            errors.append(f"{entry.id}: unknown number entry {entry.number_entry_id}")
        elif source.family != entry.number_family_id:
            errors.append(f"{entry.id}: number family mismatch")
    if errors:
        print("SIMILARITY TRIANGLE DATABASE INVALID")
        for error in errors[:50]:
            print(f"- {error}")
        return 1
    counts = Counter(entry.model for entry in database.entries)
    print(f"SIMILARITY TRIANGLE DATABASE VALID: {len(database.entries)}")
    for model, count in sorted(counts.items()):
        print(f"- {model}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

