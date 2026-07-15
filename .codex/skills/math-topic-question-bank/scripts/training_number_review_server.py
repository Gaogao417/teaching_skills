#!/usr/bin/env python3
"""FastAPI review UI for enabling and disabling exact training-number groups."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import threading
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from training_number_review_state import (
    load_database,
    load_review,
    rational_pair_subcategory,
    save_review,
    set_entry_disabled,
)


PACKAGE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_DIR / "data"
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_DATABASE = DATA_DIR / "training-number-database.yaml"
DEFAULT_REVIEW = DATA_DIR / "training-number-review.yaml"
GAME_SUBCATEGORIES = (
    "numerator_multiple_only",
    "denominator_multiple_only",
    "numerator_and_denominator_multiple",
)


class EntryReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: bool


GameSubcategory = Literal[
    "numerator_multiple_only",
    "denominator_multiple_only",
    "numerator_and_denominator_multiple",
]


class GameQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subcategories: list[GameSubcategory] = Field(min_length=1)
    exclude_entry_ids: list[str] = Field(default_factory=list, max_length=20)


class GameMistake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_number: int = Field(ge=1, le=10)
    entry_id: str = Field(min_length=1)
    subcategory: GameSubcategory
    multiplier: str = Field(pattern=r"^[2-6]$")
    options: list[tuple[str, str]] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    selected_index: int | None = Field(default=None, ge=0, le=3)
    timed_out: bool
    response_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_answer_state(self) -> "GameMistake":
        matching_indices = []
        target = Fraction(self.multiplier)
        for index, pair in enumerate(self.options):
            values = [Fraction(value) for value in pair]
            if max(values) / min(values) == target:
                matching_indices.append(index)
        if matching_indices != [self.correct_index]:
            raise ValueError("mistake options must contain exactly one answer at correct_index")
        if self.timed_out and self.selected_index is not None:
            raise ValueError("timed-out mistake cannot have selected_index")
        if not self.timed_out and self.selected_index is None:
            raise ValueError("answered mistake requires selected_index")
        if self.selected_index == self.correct_index:
            raise ValueError("mistake selected_index cannot equal correct_index")
        return self


class GameHistoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    difficulty: Literal["novice", "intermediate", "expert"]
    duration_ms: Literal[20000, 12000, 7000]
    subcategories: list[GameSubcategory] = Field(min_length=1, max_length=3)
    score: int = Field(ge=0)
    correct_count: int = Field(ge=0, le=10)
    total_questions: Literal[10]
    average_response_ms: int = Field(ge=0)
    mistakes: list[GameMistake] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_difficulty_duration(self) -> "GameHistoryCreate":
        expected = {"novice": 20000, "intermediate": 12000, "expert": 7000}
        if self.duration_ms != expected[self.difficulty]:
            raise ValueError("difficulty and duration_ms do not match")
        if self.average_response_ms > self.duration_ms:
            raise ValueError("average_response_ms cannot exceed the question duration")
        if any(mistake.response_ms > self.duration_ms for mistake in self.mistakes):
            raise ValueError("mistake response_ms cannot exceed the question duration")
        return self


def _init_history_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS game_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                completed_at TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                subcategories_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                average_response_ms INTEGER,
                mistakes_json TEXT
            )
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(game_rounds)").fetchall()
        }
        if "average_response_ms" not in columns:
            connection.execute("ALTER TABLE game_rounds ADD COLUMN average_response_ms INTEGER")
        if "mistakes_json" not in columns:
            connection.execute("ALTER TABLE game_rounds ADD COLUMN mistakes_json TEXT")


def _history_row(row: sqlite3.Row) -> dict:
    average_response_ms = row["average_response_ms"]
    mistakes_recorded = row["mistakes_json"] is not None
    mistakes = json.loads(row["mistakes_json"]) if mistakes_recorded else []
    return {
        "id": row["id"],
        "completed_at": row["completed_at"],
        "difficulty": row["difficulty"],
        "duration_ms": row["duration_ms"],
        "subcategories": json.loads(row["subcategories_json"]),
        "score": row["score"],
        "correct_count": row["correct_count"],
        "total_questions": row["total_questions"],
        "accuracy": round(row["correct_count"] / row["total_questions"] * 100),
        "average_response_ms": average_response_ms,
        "average_response_seconds": (
            round(average_response_ms / 1000, 1)
            if average_response_ms is not None
            else None
        ),
        "mistakes_recorded": mistakes_recorded,
        "mistake_count": len(mistakes),
        "mistakes": mistakes,
    }


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def build_game_question(
    database,
    review,
    subcategories: list[str],
    exclude_entry_ids: list[str] | None = None,
    rng: random.Random | random.SystemRandom | None = None,
) -> dict:
    """Build four pair-options, exactly one of which has the target quotient."""
    rng = rng or random.SystemRandom()
    disabled_ids = set(review.disabled_entry_ids)
    requested = set(subcategories)
    candidates = []
    for entry in database.entries_by_id().values():
        classified = rational_pair_subcategory(entry)
        if entry.id in disabled_ids or not classified or classified[0] not in requested:
            continue
        values = [value.coefficient_fraction for value in entry.values]
        if (max(values) / min(values)).denominator != 1:
            continue
        candidates.append((entry, classified))
    if not candidates:
        raise ValueError("所选题型没有可用数值组")

    excluded = set(exclude_entry_ids or [])
    fresh = [candidate for candidate in candidates if candidate[0].id not in excluded]
    target_candidates = fresh or candidates
    rng.shuffle(target_candidates)

    for entry, classified in target_candidates:
        correct_values = [value.coefficient_fraction for value in entry.values]
        multiplier = max(correct_values) / min(correct_values)
        possible_distractors = []
        for distractor_entry, distractor_classified in candidates:
            if distractor_entry.id == entry.id:
                continue
            distractor_values = [value.coefficient_fraction for value in distractor_entry.values]
            distractor_multiplier = max(distractor_values) / min(distractor_values)
            if distractor_multiplier != multiplier:
                possible_distractors.append((distractor_entry, distractor_classified))
        if len(possible_distractors) < 3:
            continue
        option_entries = [(entry, classified)] + rng.sample(possible_distractors, 3)
        rng.shuffle(option_entries)
        correct_index = next(
            index
            for index, (option_entry, _) in enumerate(option_entries)
            if option_entry.id == entry.id
        )
        return {
            "entry_id": entry.id,
            "subcategory": classified[0],
            "subcategory_title": classified[1],
            "multiplier": _fraction_text(multiplier),
            "options": [
                {
                    "entry_id": option_entry.id,
                    "values": [
                        _fraction_text(value.coefficient_fraction)
                        for value in option_entry.values
                    ],
                    "subcategory": option_classified[0],
                }
                for option_entry, option_classified in option_entries
            ],
            "correct_index": correct_index,
        }
    raise ValueError("暂时无法为所选题型构造唯一答案，请换一组题型再试")


def create_app(
    database_path: Path = DEFAULT_DATABASE,
    review_path: Path = DEFAULT_REVIEW,
    history_path: Path | None = None,
) -> FastAPI:
    database_path = database_path.resolve()
    review_path = review_path.resolve()
    history_path = (history_path or review_path.with_name("training-number-game-history.sqlite3")).resolve()
    database = load_database(database_path)
    entries_by_id = database.entries_by_id()
    lock = threading.Lock()
    history_lock = threading.Lock()
    _init_history_database(history_path)

    app = FastAPI(title="Training Number Review", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def disable_game_asset_cache(request, call_next):
        response = await call_next(request)
        if request.url.path == "/game" or request.url.path.startswith("/static/training-number-game"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/")
    def review_page() -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "training-number-review.html", media_type="text/html")

    @app.get("/game")
    def game_page() -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "training-number-game.html", media_type="text/html")

    @app.get("/healthz")
    def healthz() -> dict[str, bool | int]:
        review = load_review(review_path, database)
        return {"ok": True, "groups": database.entry_count, "disabled": len(review.disabled_entry_ids)}

    @app.get("/api/database")
    def api_database() -> dict:
        review = load_review(review_path, database)
        disabled_ids = set(review.disabled_entry_ids)
        families = []
        for family in database.families:
            entries = []
            for entry in family.entries:
                subcategory = rational_pair_subcategory(entry)
                payload = {
                    "id": entry.id,
                    "label": entry.label,
                    "latex_values": [value.latex for value in entry.values],
                    "relation": entry.relation,
                    "tags": entry.tags,
                    "parameters": entry.parameters,
                    "disabled": entry.id in disabled_ids,
                }
                if subcategory:
                    payload["subcategory"] = subcategory[0]
                    payload["subcategory_title"] = subcategory[1]
                entries.append(payload)
            families.append(
                {
                    "id": family.id,
                    "title": family.title,
                    "description": family.description,
                    "count": len(entries),
                    "disabled_count": sum(entry["disabled"] for entry in entries),
                    "entries": entries,
                }
            )
        return {
            "database_id": database.database.id,
            "total_count": database.entry_count,
            "disabled_count": len(disabled_ids),
            "updated_at": review.updated_at,
            "families": families,
        }

    @app.put("/api/entries/{entry_id}")
    def api_update_entry(entry_id: str, update: EntryReviewUpdate) -> dict[str, str | bool | int]:
        if entry_id not in entries_by_id:
            raise HTTPException(status_code=404, detail=f"unknown training-number entry {entry_id!r}")
        with lock:
            review = load_review(review_path, database)
            review = set_entry_disabled(review, entry_id, update.disabled)
            save_review(review_path, review)
        return {
            "entry_id": entry_id,
            "disabled": update.disabled,
            "disabled_count": len(review.disabled_entry_ids),
            "updated_at": review.updated_at,
        }

    @app.post("/api/game/question")
    def api_game_question(request: GameQuestionRequest) -> dict:
        review = load_review(review_path, database)
        try:
            return build_game_question(
                database,
                review,
                request.subcategories,
                request.exclude_entry_ids,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/game/history")
    def api_game_history(limit: int = 50) -> dict:
        limit = min(max(limit, 1), 200)
        with sqlite3.connect(history_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM game_rounds ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            aggregate = connection.execute(
                """
                SELECT COUNT(*) AS rounds, COALESCE(MAX(score), 0) AS best_score,
                       COALESCE(MAX(correct_count * 100 / total_questions), 0) AS best_accuracy,
                       MIN(average_response_ms) AS fastest_average_response_ms
                FROM game_rounds
                """
            ).fetchone()
        records = [_history_row(row) for row in rows]
        all_time = {
            "rounds": aggregate["rounds"],
            "best_score": aggregate["best_score"],
            "best_accuracy": aggregate["best_accuracy"],
            "fastest_average_response_ms": aggregate["fastest_average_response_ms"],
            "fastest_average_response_seconds": (
                round(aggregate["fastest_average_response_ms"] / 1000, 1)
                if aggregate["fastest_average_response_ms"] is not None
                else None
            ),
        }
        return {"records": records, "summary": all_time}

    @app.post("/api/game/history", status_code=201)
    def api_create_game_history(payload: GameHistoryCreate) -> dict:
        completed_at = datetime.now(timezone.utc).isoformat()
        with history_lock, sqlite3.connect(history_path) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(
                """
                INSERT INTO game_rounds (
                    completed_at, difficulty, duration_ms, subcategories_json,
                    score, correct_count, total_questions, average_response_ms, mistakes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    completed_at,
                    payload.difficulty,
                    payload.duration_ms,
                    json.dumps(payload.subcategories, ensure_ascii=False),
                    payload.score,
                    payload.correct_count,
                    payload.total_questions,
                    payload.average_response_ms,
                    json.dumps(
                        [mistake.model_dump(mode="json") for mistake in payload.mistakes],
                        ensure_ascii=False,
                    ),
                ),
            )
            row = connection.execute(
                "SELECT * FROM game_rounds WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _history_row(row)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8876)
    args = parser.parse_args()
    uvicorn.run(
        create_app(args.database, args.review),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
