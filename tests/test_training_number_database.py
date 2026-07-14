from __future__ import annotations

from pathlib import Path
from fractions import Fraction
import random
import sqlite3
import sys

import pytest
import yaml
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
DATA = ROOT / ".codex/skills/math-topic-question-bank/data"
sys.path.insert(0, str(SCRIPTS))

from training_number_contracts import TrainingNumberDatabase, TrainingNumberEntry  # noqa: E402
from training_number_contracts import largest_prime_factor  # noqa: E402
from generate_training_number_database import reconcile_review  # noqa: E402
from training_number_review_server import build_game_question, create_app  # noqa: E402
from training_number_review_state import (  # noqa: E402
    available_entries,
    load_database,
    load_review,
    rational_pair_subcategory,
)


def test_generated_database_has_expected_exact_families() -> None:
    payload = yaml.safe_load((DATA / "training-number-database.yaml").read_text(encoding="utf-8"))
    database = TrainingNumberDatabase.model_validate(payload)
    entries = database.entries_by_id()

    assert database.entry_count == 609
    assert "rational-3-over-4-x-2" in entries
    assert [value.display for value in entries["rational-3-over-4-x-2"].values] == ["3/4", "3/2"]
    rational_entries = [
        entry for entry in entries.values()
        if entry.family == "rational_multiple_pairs"
    ]
    assert len(rational_entries) == 273
    assert {
        entry.parameters["multiplier"]
        for entry in rational_entries
    } == {"2", "3", "4", "5", "6"}
    assert all("integer_multiplier" in entry.tags for entry in rational_entries)
    assert not any("fraction_multiplier" in entry.tags for entry in rational_entries)
    assert all(
        (
            max(value.coefficient_fraction for value in entry.values)
            / min(value.coefficient_fraction for value in entry.values)
        ).denominator == 1
        for entry in rational_entries
    )
    assert all(
        max(
            largest_prime_factor(value.coefficient_fraction.numerator),
            largest_prime_factor(value.coefficient_fraction.denominator),
        ) <= 7
        for entry in rational_entries
        for value in entry.values
    )
    assert "sqrt-ka-a3-k3" in entries
    assert [value.display for value in entries["sqrt-ka-a3-k3"].values] == ["sqrt(3)", "3"]
    assert "pythagorean-3-4-5" in entries
    assert "pythagorean-5-12-13" in entries
    assert "pythagorean-7-24-25" in entries
    assert "special-angle-30-60-90" in entries
    assert "special-angle-45-45-90" in entries

    assert not any(entry.family == "scaled_right_triangles" for entry in entries.values())
    integer_scaled = [
        entry for entry in entries.values()
        if entry.family == "integer_right_triangles_fraction_scaled"
    ]
    radical_scaled = [
        entry for entry in entries.values()
        if entry.family == "radical_right_triangles_simple_scaled"
    ]
    assert integer_scaled
    assert radical_scaled
    assert all(entry.parameters["scale"]["radicand"] == 1 for entry in integer_scaled)
    assert all("radical_scale" not in entry.tags for entry in integer_scaled)
    assert not any(entry.label == "(3*sqrt(3), 4*sqrt(3), 5*sqrt(3))" for entry in entries.values())


def test_review_button_state_persists_and_excludes_entry(tmp_path: Path) -> None:
    database_path = DATA / "training-number-database.yaml"
    review_path = tmp_path / "training-number-review.yaml"
    app = create_app(database_path, review_path)
    client = TestClient(app)
    entry_id = "sqrt-ka-a3-k3"

    initial = client.get("/api/database")
    assert initial.status_code == 200
    assert initial.json()["disabled_count"] == 0

    disabled = client.put(f"/api/entries/{entry_id}", json={"disabled": True})
    assert disabled.status_code == 200
    assert disabled.json()["disabled"] is True
    saved = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    assert saved["disabled_entry_ids"] == [entry_id]

    database = load_database(database_path)
    review = load_review(review_path, database)
    available_ids = {entry.id for entry in available_entries(database, review, "radical_multiple_pairs")}
    assert entry_id not in available_ids

    restored = client.put(f"/api/entries/{entry_id}", json={"disabled": False})
    assert restored.status_code == 200
    assert restored.json()["disabled"] is False
    assert yaml.safe_load(review_path.read_text(encoding="utf-8"))["disabled_entry_ids"] == []


def test_rational_pairs_are_derived_by_strict_integer_multiple_relationships() -> None:
    database = load_database(DATA / "training-number-database.yaml")
    entries = database.entries_by_id()
    expected = {
        "rational-2-over-3-x-2": "numerator_multiple_only",
        "rational-3-over-4-x-2": "denominator_multiple_only",
        "rational-1-over-2-x-4": "numerator_and_denominator_multiple",
    }
    for entry_id, subcategory in expected.items():
        assert rational_pair_subcategory(entries[entry_id])[0] == subcategory

    rational_entries = [
        entry for entry in entries.values()
        if entry.family == "rational_multiple_pairs"
    ]
    counts: dict[str, int] = {}
    for entry in rational_entries:
        key, _ = rational_pair_subcategory(entry)
        counts[key] = counts.get(key, 0) + 1
    assert set(counts) == {
        "numerator_multiple_only",
        "denominator_multiple_only",
        "numerator_and_denominator_multiple",
    }
    assert counts == {
        "numerator_multiple_only": 160,
        "denominator_multiple_only": 77,
        "numerator_and_denominator_multiple": 36,
    }
    assert sum(counts.values()) == len(rational_entries)
    assert all(count > 0 for count in counts.values())


def test_rational_pair_contract_rejects_fractional_multiplier() -> None:
    with pytest.raises(ValueError, match="multiplier must be an integer above one"):
        TrainingNumberEntry.model_validate(
            {
                "id": "fractional-multiplier-must-fail",
                "family": "rational_multiple_pairs",
                "label": "(1/2, 3/4)",
                "values": [
                    {"coefficient": "1/2", "radicand": 1, "latex": "1/2", "display": "1/2"},
                    {"coefficient": "3/4", "radicand": 1, "latex": "3/4", "display": "3/4"},
                ],
                "relation": "second_equals_multiplier_times_first",
                "tags": ["fraction_lengths", "rational_multiple", "fraction_multiplier"],
                "parameters": {"multiplier": "3/2"},
            }
        )


def test_review_rejects_unknown_entry(tmp_path: Path) -> None:
    client = TestClient(create_app(DATA / "training-number-database.yaml", tmp_path / "review.yaml"))
    response = client.put("/api/entries/not-a-real-group", json={"disabled": True})
    assert response.status_code == 404


def test_review_reconciliation_archives_removed_ids(tmp_path: Path) -> None:
    database = load_database(DATA / "training-number-database.yaml")
    live_id = "sqrt-ka-a3-k3"
    removed_id = "scaled-pythagorean-3-4-5-by-sqrt3"
    review_path = tmp_path / "review.yaml"
    review_path.write_text(
        yaml.safe_dump(
            {
                "schema": "math_training_number_review/v1",
                "database_id": database.database.id,
                "disabled_entry_ids": [live_id, removed_id],
                "updated_at": "",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    reconciled = reconcile_review(review_path, database)
    assert reconciled is not None
    assert reconciled.disabled_entry_ids == [live_id]
    assert reconciled.retired_entry_ids == [removed_id]


def _matching_pair_options(payload: dict) -> list[int]:
    multiplier = Fraction(payload["multiplier"])
    return [
        index
        for index, option in enumerate(payload["options"])
        if (
            max(Fraction(option["values"][0]), Fraction(option["values"][1]))
            / min(Fraction(option["values"][0]), Fraction(option["values"][1]))
            == multiplier
        )
    ]


def test_game_question_has_four_distinct_options_and_one_answer(tmp_path: Path) -> None:
    database = load_database(DATA / "training-number-database.yaml")
    review = load_review(DATA / "training-number-review.yaml", database)
    payload = build_game_question(
        database,
        review,
        [
            "numerator_multiple_only",
            "denominator_multiple_only",
            "numerator_and_denominator_multiple",
        ],
        rng=random.Random(17),
    )

    assert len(payload["options"]) == 4
    assert len({option["entry_id"] for option in payload["options"]}) == 4
    assert all(len(option["values"]) == 2 for option in payload["options"])
    matches = _matching_pair_options(payload)
    assert len(matches) == 1
    assert matches[0] == payload["correct_index"]
    assert Fraction(payload["multiplier"]).denominator == 1
    assert all(
        (
            max(Fraction(value) for value in option["values"])
            / min(Fraction(value) for value in option["values"])
        ).denominator == 1
        for option in payload["options"]
    )


def test_game_question_respects_subcategory_and_review_state(tmp_path: Path) -> None:
    database_path = DATA / "training-number-database.yaml"
    review_path = tmp_path / "training-number-review.yaml"
    client = TestClient(create_app(database_path, review_path))
    response = client.post(
        "/api/game/question",
        json={"subcategories": ["denominator_multiple_only"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["subcategory"] == "denominator_multiple_only"
    assert len(_matching_pair_options(payload)) == 1

    disabled = client.put(f"/api/entries/{payload['entry_id']}", json={"disabled": True})
    assert disabled.status_code == 200
    next_response = client.post(
        "/api/game/question",
        json={
            "subcategories": ["denominator_multiple_only"],
            "exclude_entry_ids": [],
        },
    )
    assert next_response.status_code == 200
    assert next_response.json()["entry_id"] != payload["entry_id"]


def test_game_question_rejects_empty_content_selection(tmp_path: Path) -> None:
    client = TestClient(create_app(DATA / "training-number-database.yaml", tmp_path / "review.yaml"))
    response = client.post("/api/game/question", json={"subcategories": []})
    assert response.status_code == 422


def test_game_page_and_assets_disable_stale_browser_cache(tmp_path: Path) -> None:
    client = TestClient(create_app(DATA / "training-number-database.yaml", tmp_path / "review.yaml"))
    page = client.get("/game")
    script = client.get("/static/training-number-game.js")
    assert page.status_code == 200
    assert script.status_code == 200
    assert page.headers["cache-control"] == "no-store, max-age=0"
    assert script.headers["cache-control"] == "no-store, max-age=0"
    assert "training-number-game.js?v=20260714-pairs" in page.text


def test_game_history_persists_rounds_and_returns_summary(tmp_path: Path) -> None:
    review_path = tmp_path / "review.yaml"
    history_path = tmp_path / "history.sqlite3"
    client = TestClient(create_app(DATA / "training-number-database.yaml", review_path, history_path))
    first = client.post(
        "/api/game/history",
        json={
            "difficulty": "novice",
            "duration_ms": 20000,
            "subcategories": ["numerator_multiple_only"],
            "score": 780,
            "correct_count": 7,
            "total_questions": 10,
            "average_response_ms": 8500,
        },
    )
    second = client.post(
        "/api/game/history",
        json={
            "difficulty": "expert",
            "duration_ms": 7000,
            "subcategories": ["denominator_multiple_only", "numerator_and_denominator_multiple"],
            "score": 1040,
            "correct_count": 9,
            "total_questions": 10,
            "average_response_ms": 4200,
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["accuracy"] == 70
    assert first.json()["average_response_seconds"] == 8.5
    history = client.get("/api/game/history").json()
    assert [record["score"] for record in history["records"]] == [1040, 780]
    assert history["summary"] == {
        "rounds": 2,
        "best_score": 1040,
        "best_accuracy": 90,
        "fastest_average_response_ms": 4200,
        "fastest_average_response_seconds": 4.2,
    }
    assert history_path.exists()

    mismatch = client.post(
        "/api/game/history",
        json={
            "difficulty": "expert",
            "duration_ms": 20000,
            "subcategories": ["numerator_multiple_only"],
            "score": 0,
            "correct_count": 0,
            "total_questions": 10,
            "average_response_ms": 1000,
        },
    )
    assert mismatch.status_code == 422


def test_game_history_migrates_existing_database_for_average_time(tmp_path: Path) -> None:
    history_path = tmp_path / "legacy-history.sqlite3"
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            """
            CREATE TABLE game_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                completed_at TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                subcategories_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                total_questions INTEGER NOT NULL
            )
            """
        )

    create_app(DATA / "training-number-database.yaml", tmp_path / "review.yaml", history_path)
    with sqlite3.connect(history_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(game_rounds)")}
    assert "average_response_ms" in columns
