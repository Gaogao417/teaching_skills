from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
DATA = ROOT / ".codex/skills/math-topic-question-bank/data"
sys.path.insert(0, str(SCRIPTS))

from similarity_triangle_contracts import SimilarityTriangleDatabase  # noqa: E402
from training_number_contracts import largest_prime_factor  # noqa: E402
from training_number_review_state import load_database  # noqa: E402


def load_realizations() -> SimilarityTriangleDatabase:
    payload = yaml.safe_load((DATA / "similarity-triangle-database.yaml").read_text(encoding="utf-8"))
    return SimilarityTriangleDatabase.model_validate(payload)


def test_similarity_realizations_are_wolfram_verified_and_reference_numbers() -> None:
    realizations = load_realizations()
    numbers = load_database(DATA / "training-number-database.yaml").entries_by_id()
    assert len(realizations.entries) == 543
    assert {entry.model for entry in realizations.entries} == {"reverse_a", "butterfly", "nested"}
    for entry in realizations.entries:
        assert entry.number_entry_id in numbers
        assert numbers[entry.number_entry_id].family == entry.number_family_id
        assert entry.number_family_id == "noncoprime_radicand_pairs"
        assert entry.quality.wolfram_verified is True
        assert entry.quality.minimum_angle_deg >= 30
        assert entry.quality.minimum_relative_side_gap >= 0.1
        assert entry.quality.inradius_circumradius_ratio > 0.1
        assert entry.quality.minimum_height_perimeter_ratio > 0.08
        assert all(value.coefficient_fraction.denominator == 1 for value in entry.source_values)
        assert all(
            max(largest_prime_factor(value.coefficient_fraction.numerator), largest_prime_factor(value.radicand)) <= 5
            for value in entry.source_values
        )
        assert entry.source_values[1].squared <= 3 * entry.source_values[0].squared
        scale_squared = entry.target_values[0].squared / entry.source_values[0].squared
        assert Fraction(1, 3) <= scale_squared <= 3
        assert (
            entry.small_triangle_sides[entry.source_pair_index].normalized_pair()
            == entry.source_values[0].normalized_pair()
        )
        assert (
            entry.small_triangle_sides[entry.target_pair_index].normalized_pair()
            == entry.source_values[1].normalized_pair()
        )


def test_similarity_realizations_have_enough_balanced_bank_candidates() -> None:
    realizations = load_realizations()
    entry_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    routes: dict[tuple[str, str], Counter[tuple[int, int]]] = defaultdict(Counter)
    for entry in realizations.entries:
        key = (entry.model, entry.number_family_id)
        entry_ids[key].add(entry.number_entry_id)
        routes[key][(entry.source_pair_index, entry.target_pair_index)] += 1
    for model in ("reverse_a", "butterfly", "nested"):
        key = (model, "noncoprime_radicand_pairs")
        assert len(entry_ids[key]) >= 50
        assert all(count > 0 for count in routes[key].values())
        assert len(routes[key]) == (2 if model == "nested" else 6)


def test_each_number_model_has_at_most_three_realizations() -> None:
    realizations = load_realizations()
    counts = Counter((entry.number_entry_id, entry.model) for entry in realizations.entries)
    assert counts
    assert max(counts.values()) <= 3
