from __future__ import annotations

from collections import Counter
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


BANKS = (
    ROOT / "artifacts/题库/2026-07-16-反A形相似",
    ROOT / "artifacts/题库/2026-07-16-蝶形相似",
    ROOT / "artifacts/题库/2026-07-16-子母型相似",
)


def geometry_entries() -> dict[str, object]:
    payload = yaml.safe_load((DATA / "similarity-triangle-database.yaml").read_text(encoding="utf-8"))
    database = SimilarityTriangleDatabase.model_validate(payload)
    return {entry.id: entry for entry in database.entries}


def test_similarity_banks_use_fifty_unique_clean_number_pairs() -> None:
    geometries = geometry_entries()
    for bank in BANKS:
        coverage = yaml.safe_load((bank / "coverage-plan.yaml").read_text(encoding="utf-8"))
        slots = coverage["slots"]
        assert len(slots) == 50
        assert Counter(slot["difficulty"] for slot in slots) == Counter(
            {"foundation": 16, "standard": 20, "challenge": 14}
        )
        number_ids = [slot["number_selection"]["entry_id"] for slot in slots]
        assert len(set(number_ids)) == 50
        assert {slot["number_selection"]["family_id"] for slot in slots} == {
            "noncoprime_radicand_pairs"
        }
        route_counts = Counter(
            (
                slot["geometry_selection"]["source_pair_index"],
                slot["geometry_selection"]["target_pair_index"],
            )
            for slot in slots
        )
        assert max(route_counts.values()) - min(route_counts.values()) <= 1

        for slot in slots:
            selection = slot["number_selection"]
            assert selection["source_fractional_coefficients_allowed"] is False
            assert selection["unknown_value_restrictions"] == "none_beyond_positive_exact_value"
            assert selection["largest_prime_factor_max"] == 5
            assert selection["max_ratio"] == "sqrt(3)"
            numerator, denominator = selection["squared_ratio"]
            assert Fraction(numerator, denominator) <= 3

            geometry = geometries[slot["geometry_selection"]["entry_id"]]
            assert geometry.source_pair_index != geometry.target_pair_index
            assert slot["geometry_selection"]["number_side_indices"] == [
                geometry.source_pair_index,
                geometry.target_pair_index,
            ]
            assert (
                geometry.small_triangle_sides[geometry.source_pair_index].normalized_pair()
                == geometry.source_values[0].normalized_pair()
            )
            assert (
                geometry.small_triangle_sides[geometry.target_pair_index].normalized_pair()
                == geometry.source_values[1].normalized_pair()
            )
            for value in geometry.source_values:
                assert value.coefficient_fraction.denominator == 1
                assert max(
                    largest_prime_factor(value.coefficient_fraction.numerator),
                    largest_prime_factor(value.radicand),
                ) <= 5


def test_similarity_teacher_plans_freeze_number_and_geometry_selection() -> None:
    for bank in BANKS:
        manifest = yaml.safe_load((bank / "question-bank.yaml").read_text(encoding="utf-8"))
        assert manifest["bank"]["status"] == "ready"
        assert len(manifest["items"]) == 50
        for index in range(1, 51):
            item_id = f"Q{index:03d}"
            plan_path = bank / "items" / item_id / "teacher.plan.assignment.yaml"
            payload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            block = payload["sections"][0]["blocks"][0]
            assert block["id"] == item_id
            assert len(block["solution_steps"]) == 5
            assert block["teaching"]["number_selection"]["entry_id"]
            assert block["teaching"]["geometry_selection"]["entry_id"]
            assert block["diagram_slot"]["engine"] == "geometric_scene"
            assert block["diagram_slot"]["variant"] == "prompt"


def test_similarity_stems_ask_only_for_the_edge_task() -> None:
    noisy_process_prompts = ("证明", "写出", "比例式", "推理过程", "验算")
    for bank in BANKS:
        coverage = yaml.safe_load((bank / "coverage-plan.yaml").read_text(encoding="utf-8"))
        difficulties = {slot["id"]: slot["difficulty"] for slot in coverage["slots"]}
        for item_id, difficulty in difficulties.items():
            plan_path = bank / "items" / item_id / "teacher.plan.assignment.yaml"
            payload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            stem = payload["sections"][0]["blocks"][0]["stem_latex"]
            assert not any(prompt in stem for prompt in noisy_process_prompts)
            if bank.name == "2026-07-16-子母型相似":
                assert stem.endswith("的长。")
                assert "判断还可以求出哪条边" not in stem
            elif difficulty == "challenge":
                assert stem.endswith("判断还可以求出哪条边，并求出它的长度。")
            else:
                assert stem.endswith("的长。")
                assert "判断还可以求出哪条边" not in stem


def test_nested_bank_transfers_between_corresponding_and_collinear_conditions() -> None:
    bank = ROOT / "artifacts/题库/2026-07-16-子母型相似"
    coverage = yaml.safe_load((bank / "coverage-plan.yaml").read_text(encoding="utf-8"))
    allowed_routes = {
        "collinear_segments_to_corresponding_side",
        "corresponding_sides_to_collinear_segment",
        "collinear_triangle_sides_to_corresponding_side",
        "corresponding_sides_to_inner_collinear_segment",
        "corresponding_inner_side_to_outer_collinear_side",
    }
    assert {slot["condition_route"] for slot in coverage["slots"]} <= allowed_routes
    stems = []
    for slot in coverage["slots"]:
        payload = yaml.safe_load(
            (bank / "items" / slot["id"] / "teacher.plan.assignment.yaml").read_text(encoding="utf-8")
        )
        block = payload["sections"][0]["blocks"][0]
        stem = block["stem_latex"]
        stems.append(" ".join(stem.split()))
        solution = " ".join(step["content"] for step in block["solution_steps"])
        condition_text = stem.split("已知 ", 1)[1]
        assert "$BD=" not in condition_text and "$BC=" not in condition_text
        assert r"AB^2=AC\cdot AD" in solution
    assert len(stems) == len(set(stems)) == 50
