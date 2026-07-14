#!/usr/bin/env python3
"""Run Wolfram generation, validate exact relations, and write the YAML database."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from training_number_contracts import TrainingNumberDatabase, TrainingNumberReview
from training_number_review_state import save_review


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "data" / "training-number-database.yaml"
WOLFRAM_GENERATOR = SCRIPT_DIR / "generate_training_numbers.wls"

FAMILY_COPY = {
    "rational_multiple_pairs": (
        "有倍数关系的分数边长",
        "最简分数与 2 至 6 的常见整数倍数组合。",
    ),
    "radical_multiple_pairs": (
        "sqrt(a) 与 sqrt(k a)",
        "保留原始被开方数，并记录化简值与商。",
    ),
    "noncoprime_radicand_pairs": (
        "非互质被开方数与系数组合",
        "a、b 不互质，x、y 为小整数系数。",
    ),
    "right_triangle_integer_triples": (
        "本原勾股数",
        "Wolfram 直接求出的 c≤100 本原整数解。",
    ),
    "right_triangle_special_angles": (
        "30/45 度特殊直角三角形",
        "30-60-90 与 45-45-90 的精确三边比。",
    ),
    "right_triangle_sqrt_square_sums": (
        "1-20 平方长度根式三角形",
        "x+y=z，且化简后被开方数小于 10。",
    ),
    "scaled_right_triangles": (
        "旧版缩放数值",
        "仅用于兼容旧数据。",
    ),
    "integer_right_triangles_fraction_scaled": (
        "整数直角三角形乘简单分数",
        "常见整数勾股数组只乘分子、分母不超过 7 的最简分数。",
    ),
    "radical_right_triangles_simple_scaled": (
        "带根号的直角三角形乘简单根式或分数",
        "特殊角根式三角形可乘小分数，或乘能与原边根式直接化简的简单根式。",
    ),
}


def localize_family_copy(raw: dict) -> None:
    for family in raw.get("families", []):
        family_id = family.get("id")
        if family_id in FAMILY_COPY:
            family["title"], family["description"] = FAMILY_COPY[family_id]


def reconcile_review(review_path: Path, database: TrainingNumberDatabase) -> TrainingNumberReview | None:
    if not review_path.exists():
        return None
    raw = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    review = TrainingNumberReview.model_validate(raw)
    reviewed_ids = set(review.disabled_entry_ids) | set(review.retired_entry_ids)
    live_ids = set(database.entries_by_id())
    disabled_ids = sorted(reviewed_ids & live_ids)
    retired_ids = sorted(reviewed_ids - live_ids)
    changed = disabled_ids != review.disabled_entry_ids or retired_ids != review.retired_entry_ids
    reconciled = review.model_copy(
        update={
            "database_id": database.database.id,
            "disabled_entry_ids": disabled_ids,
            "retired_entry_ids": retired_ids,
            "updated_at": datetime.now(timezone.utc).isoformat() if changed else review.updated_at,
        }
    )
    save_review(review_path, reconciled)
    return reconciled


def generate(
    output: Path,
    wolframscript: str = "wolframscript",
    review_path: Path | None = None,
) -> TrainingNumberDatabase:
    with tempfile.TemporaryDirectory(prefix="training-numbers-") as tmp_dir:
        raw_json = Path(tmp_dir) / "training-number-database.raw.json"
        result = subprocess.run(
            [wolframscript, "-file", str(WOLFRAM_GENERATOR), str(raw_json)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0 or not raw_json.exists():
            detail = (result.stdout + "\n" + result.stderr).strip()
            raise RuntimeError(f"Wolfram generation failed: {detail}")
        raw = json.loads(raw_json.read_text(encoding="utf-8"))
        localize_family_copy(raw)

    database = TrainingNumberDatabase.model_validate(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(
            database.model_dump(by_alias=True, mode="json"),
            allow_unicode=True,
            sort_keys=False,
            width=120,
        ),
        encoding="utf-8",
    )
    if review_path is not None:
        reconcile_review(review_path, database)
    return database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--wolframscript", default="wolframscript")
    args = parser.parse_args()

    output = args.output.resolve()
    review_path = args.review.resolve() if args.review else None
    if review_path is None and output == DEFAULT_OUTPUT.resolve():
        review_path = SCRIPT_DIR.parent / "data" / "training-number-review.yaml"
    database = generate(output, wolframscript=args.wolframscript, review_path=review_path)
    print(f"TRAINING NUMBER DATABASE GENERATED: {database.entry_count} groups -> {args.output}")
    for family in database.families:
        print(f"- {family.id}: {len(family.entries)}")
    if review_path and review_path.exists():
        review = TrainingNumberReview.model_validate(yaml.safe_load(review_path.read_text(encoding="utf-8")))
        print(
            f"- review: disabled={len(review.disabled_entry_ids)} "
            f"retired={len(review.retired_entry_ids)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
