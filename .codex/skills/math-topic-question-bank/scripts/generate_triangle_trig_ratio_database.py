#!/usr/bin/env python3
"""Materialize a deduplicated acute trigonometric-ratio database."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from training_number_contracts import RIGHT_TRIANGLE_FAMILIES
from training_number_review_state import available_entries, load_database, load_review
from triangle_cosine_contracts import TrigRatioDatabase
from triangle_cosine_exact import expression_key, from_expr, stable_digest, to_expr


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
DEFAULT_NUMBER_DATABASE = SCRIPT_DIR.parent / "data/training-number-database.yaml"
DEFAULT_NUMBER_REVIEW = SCRIPT_DIR.parent / "data/training-number-review.yaml"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "data/triangle-trig-ratio-database.yaml"


def portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def generate(number_database: Path, number_review: Path) -> TrigRatioDatabase:
    database = load_database(number_database)
    review = load_review(number_review, database)
    collected: dict[tuple[str, str], dict] = {}
    for entry in available_entries(database, review):
        if entry.family not in RIGHT_TRIANGLE_FAMILIES:
            continue
        first_leg, second_leg, hypotenuse = entry.values
        for opposite, adjacent in ((first_leg, second_leg), (second_leg, first_leg)):
            sin_expr = to_expr(opposite) / to_expr(hypotenuse)
            cos_expr = to_expr(adjacent) / to_expr(hypotenuse)
            tan_expr = to_expr(opposite) / to_expr(adjacent)
            cot_expr = to_expr(adjacent) / to_expr(opposite)
            sin_value = from_expr(sin_expr)
            cos_value = from_expr(cos_expr)
            tan_value = from_expr(tan_expr)
            cot_value = from_expr(cot_expr)
            if any(value is None for value in (sin_value, cos_value, tan_value, cot_value)):
                continue
            key = (expression_key(sin_expr), expression_key(cos_expr))
            record = collected.setdefault(
                key,
                {
                    "id": f"trig-{stable_digest(*key)}",
                    "ratios": {
                        "sin": sin_value.model_dump(mode="json"),
                        "cos": cos_value.model_dump(mode="json"),
                        "tan": tan_value.model_dump(mode="json"),
                        "cot": cot_value.model_dump(mode="json"),
                    },
                    "source_number_entry_ids": [],
                },
            )
            record["source_number_entry_ids"].append(entry.id)

    entries = sorted(collected.values(), key=lambda value: value["id"])
    for entry in entries:
        entry["source_number_entry_ids"] = sorted(set(entry["source_number_entry_ids"]))
    payload = {
        "schema": "math_triangle_trig_ratio_database/v1",
        "database": {
            "id": "triangle-acute-trig-ratios",
            "source_number_database_id": database.database.id,
            "source_review_file": portable_path(number_review),
            "generator": "generate_triangle_trig_ratio_database.py",
        },
        "entries": entries,
    }
    return TrigRatioDatabase.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number-database", type=Path, default=DEFAULT_NUMBER_DATABASE)
    parser.add_argument("--number-review", type=Path, default=DEFAULT_NUMBER_REVIEW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = generate(args.number_database.resolve(), args.number_review.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(result.model_dump(by_alias=True, mode="json"), allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"TRIG RATIO DATABASE GENERATED: {len(result.entries)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
