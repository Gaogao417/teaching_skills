#!/usr/bin/env python3
"""Load and atomically persist disabled training-number entries."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from training_number_contracts import (
    TrainingNumberDatabase,
    TrainingNumberEntry,
    TrainingNumberReview,
)


RATIONAL_SUBCATEGORIES = {
    "numerator_multiple_only": "只有分子成整数倍关系",
    "denominator_multiple_only": "只有分母成整数倍关系",
    "numerator_and_denominator_multiple": "分子、分母同时成整数倍关系",
    "not_integer_multiple": "不满足整数倍关系（待审核）",
}


def _is_integer_multiple(first: int, second: int) -> bool:
    smaller, larger = sorted((first, second))
    return larger % smaller == 0


def rational_pair_subcategory(entry: TrainingNumberEntry) -> tuple[str, str] | None:
    if entry.family != "rational_multiple_pairs" or len(entry.values) != 2:
        return None
    first = entry.values[0].coefficient_fraction
    second = entry.values[1].coefficient_fraction
    numerators_are_multiples = _is_integer_multiple(first.numerator, second.numerator)
    denominators_are_multiples = _is_integer_multiple(first.denominator, second.denominator)
    if first.denominator == second.denominator and numerators_are_multiples:
        key = "numerator_multiple_only"
    elif first.numerator == second.numerator and denominators_are_multiples:
        key = "denominator_multiple_only"
    elif (
        first.numerator != second.numerator
        and first.denominator != second.denominator
        and numerators_are_multiples
        and denominators_are_multiples
    ):
        key = "numerator_and_denominator_multiple"
    else:
        key = "not_integer_multiple"
    return key, RATIONAL_SUBCATEGORIES[key]


def load_database(path: Path) -> TrainingNumberDatabase:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return TrainingNumberDatabase.model_validate(payload)


def empty_review(database: TrainingNumberDatabase) -> TrainingNumberReview:
    return TrainingNumberReview.model_validate(
        {
            "schema": "math_training_number_review/v1",
            "database_id": database.database.id,
            "disabled_entry_ids": [],
            "retired_entry_ids": [],
            "updated_at": "",
        }
    )


def load_review(path: Path, database: TrainingNumberDatabase) -> TrainingNumberReview:
    if not path.exists():
        return empty_review(database)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    review = TrainingNumberReview.model_validate(payload)
    if review.database_id != database.database.id:
        raise ValueError("review database_id does not match database")
    unknown = set(review.disabled_entry_ids) - set(database.entries_by_id())
    if unknown:
        raise ValueError(f"review contains unknown ids: {sorted(unknown)[:5]}")
    return review


def save_review(path: Path, review: TrainingNumberReview) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = review.model_dump(by_alias=True, mode="json")
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
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


def set_entry_disabled(
    review: TrainingNumberReview,
    entry_id: str,
    disabled: bool,
) -> TrainingNumberReview:
    disabled_ids = set(review.disabled_entry_ids)
    if disabled:
        disabled_ids.add(entry_id)
    else:
        disabled_ids.discard(entry_id)
    return review.model_copy(
        update={
            "disabled_entry_ids": sorted(disabled_ids),
            "retired_entry_ids": sorted(set(review.retired_entry_ids) - {entry_id}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def available_entries(
    database: TrainingNumberDatabase,
    review: TrainingNumberReview,
    family_id: str | None = None,
) -> list:
    disabled = set(review.disabled_entry_ids)
    return [
        entry
        for family in database.families
        if family_id is None or family.id == family_id
        for entry in family.entries
        if entry.id not in disabled
    ]
