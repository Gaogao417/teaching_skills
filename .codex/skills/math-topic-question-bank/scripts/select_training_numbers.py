#!/usr/bin/env python3
"""Select only review-enabled number groups for question-bank authoring."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import yaml

from training_number_review_server import DEFAULT_DATABASE, DEFAULT_REVIEW
from training_number_review_state import (
    available_entries,
    load_database,
    load_review,
    rational_pair_subcategory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--family", required=True)
    parser.add_argument("--tag")
    parser.add_argument("--subcategory")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be positive")
    database = load_database(args.database.resolve())
    review = load_review(args.review.resolve(), database)
    candidates = available_entries(database, review, family_id=args.family)
    if args.tag:
        candidates = [entry for entry in candidates if args.tag in entry.tags]
    if args.subcategory:
        candidates = [
            entry for entry in candidates
            if (rational_pair_subcategory(entry) or (None, None))[0] == args.subcategory
        ]
    if len(candidates) < args.count:
        raise SystemExit(
            f"not enough enabled entries: requested {args.count}, available {len(candidates)}"
        )
    rng = random.Random(args.seed)
    selected = rng.sample(candidates, args.count)
    payload = {
        "database_id": database.database.id,
        "review_file": str(args.review),
        "family_id": args.family,
        "tag": args.tag,
        "subcategory": args.subcategory,
        "seed": args.seed,
        "entries": [entry.model_dump(mode="json") for entry in selected],
    }
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
