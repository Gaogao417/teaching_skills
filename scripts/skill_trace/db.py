#!/usr/bin/env python3
"""SQLite persistence for reviewed skill traces."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .contracts import SkillTraceDraft, prune_deprecated_step_fields
except ImportError:  # pragma: no cover - supports direct script execution.
    from contracts import SkillTraceDraft, prune_deprecated_step_fields


DEFAULT_DB_PATH = Path("artifacts/skill_trace.db")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS codex_threads (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL DEFAULT 'codex',
  created_at TEXT NOT NULL,
  last_used_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS problem_cases (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  raw_problem TEXT NOT NULL,
  provided_solution TEXT NOT NULL DEFAULT '',
  expected_thinking TEXT NOT NULL DEFAULT '',
  topic_tags_json TEXT NOT NULL DEFAULT '[]',
  target_student_level TEXT NOT NULL DEFAULT '',
  codex_thread_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (codex_thread_id) REFERENCES codex_threads(id)
);

CREATE TABLE IF NOT EXISTS skill_trace_drafts (
  id TEXT PRIMARY KEY,
  problem_case_id TEXT NOT NULL,
  codex_thread_id TEXT NOT NULL,
  draft_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (problem_case_id) REFERENCES problem_cases(id),
  FOREIGN KEY (codex_thread_id) REFERENCES codex_threads(id)
);

CREATE TABLE IF NOT EXISTS skill_trace_reviews (
  id TEXT PRIMARY KEY,
  draft_id TEXT NOT NULL,
  problem_case_id TEXT NOT NULL,
  codex_thread_id TEXT NOT NULL,
  reviewed_json TEXT NOT NULL,
  reviewer_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY (draft_id) REFERENCES skill_trace_drafts(id),
  FOREIGN KEY (problem_case_id) REFERENCES problem_cases(id),
  FOREIGN KEY (codex_thread_id) REFERENCES codex_threads(id)
);

CREATE TABLE IF NOT EXISTS skill_trace_steps (
  id TEXT PRIMARY KEY,
  reviewed_trace_id TEXT NOT NULL,
  step_order INTEGER NOT NULL,
  name TEXT NOT NULL,
  cognitive_layer TEXT NOT NULL,
  reuse_level TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT 'general',
  student_action_norm TEXT NOT NULL,
  common_errors_json TEXT NOT NULL DEFAULT '[]',
  is_core_step INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (reviewed_trace_id) REFERENCES skill_trace_reviews(id)
);
"""


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("SKILL_TRACE_DB", DEFAULT_DB_PATH))


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path | None = None) -> dict[str, Any]:
    path = resolve_db_path(db_path)
    with connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
    return {"status": "initialized", "db_path": str(path)}


def insert_draft(draft_payload: dict[str, Any] | SkillTraceDraft, db_path: str | Path | None = None) -> dict[str, Any]:
    draft = _coerce_draft(draft_payload)
    now = _now_iso()
    problem_case_id = _problem_case_id_for_draft(draft)

    with connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        _upsert_draft(connection, draft, problem_case_id, now)

    return {
        "status": "draft_inserted",
        "draft_id": draft.draft_id,
        "problem_case_id": problem_case_id,
        "codex_thread_id": draft.codex_thread_id,
    }


def get_draft(draft_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, problem_case_id, codex_thread_id, draft_json, created_at
            FROM skill_trace_drafts
            WHERE id = ?
            """,
            (draft_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"draft not found: {draft_id}")

    return {
        "draft_id": row["id"],
        "problem_case_id": row["problem_case_id"],
        "codex_thread_id": row["codex_thread_id"],
        "created_at": row["created_at"],
        "draft_json": json.loads(row["draft_json"]),
    }


def insert_review(
    *,
    draft_id: str,
    reviewed_json: dict[str, Any] | SkillTraceDraft,
    original_draft_json: dict[str, Any] | SkillTraceDraft | None = None,
    reviewer_note: str = "",
    reviewed_trace_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    reviewed = _coerce_draft(reviewed_json)
    if reviewed.draft_id != draft_id:
        raise ValueError(f"reviewed_json.draft_id {reviewed.draft_id!r} does not match draft_id {draft_id!r}")
    original_draft = _coerce_draft(original_draft_json) if original_draft_json is not None else reviewed
    if original_draft.draft_id != draft_id:
        raise ValueError(f"original_draft_json.draft_id {original_draft.draft_id!r} does not match draft_id {draft_id!r}")
    if original_draft.codex_thread_id != reviewed.codex_thread_id:
        raise ValueError(
            f"original_draft_json.codex_thread_id {original_draft.codex_thread_id!r} does not match reviewed thread "
            f"{reviewed.codex_thread_id!r}"
        )

    now = _now_iso()

    with connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        trace_id = reviewed_trace_id or _generate_reviewed_trace_id(connection)
        draft_row = connection.execute(
            """
            SELECT id, problem_case_id, codex_thread_id
            FROM skill_trace_drafts
            WHERE id = ?
            """,
            (draft_id,),
        ).fetchone()
        if draft_row is None:
            _upsert_draft(connection, original_draft, _problem_case_id_for_draft(original_draft), now)
            draft_row = connection.execute(
                """
                SELECT id, problem_case_id, codex_thread_id
                FROM skill_trace_drafts
                WHERE id = ?
                """,
                (draft_id,),
            ).fetchone()
        if draft_row is None:  # pragma: no cover - defensive guard.
            raise RuntimeError(f"failed to insert draft {draft_id!r}")
        if draft_row["codex_thread_id"] != reviewed.codex_thread_id:
            raise ValueError(
                f"reviewed_json.codex_thread_id {reviewed.codex_thread_id!r} does not match stored draft thread "
                f"{draft_row['codex_thread_id']!r}"
            )

        _upsert_codex_thread(connection, reviewed.codex_thread_id, now)
        connection.execute(
            """
            INSERT INTO skill_trace_reviews (
              id, draft_id, problem_case_id, codex_thread_id, reviewed_json, reviewer_note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              draft_id = excluded.draft_id,
              problem_case_id = excluded.problem_case_id,
              codex_thread_id = excluded.codex_thread_id,
              reviewed_json = excluded.reviewed_json,
              reviewer_note = excluded.reviewer_note
            """,
            (
                trace_id,
                draft_id,
                draft_row["problem_case_id"],
                reviewed.codex_thread_id,
                _json_dumps(_draft_to_json(reviewed)),
                reviewer_note,
                now,
            ),
        )
        connection.execute("DELETE FROM skill_trace_steps WHERE reviewed_trace_id = ?", (trace_id,))
        for step in reviewed.steps:
            connection.execute(
                """
                INSERT INTO skill_trace_steps (
                  id, reviewed_trace_id, step_order, name, cognitive_layer, reuse_level, domain,
                  student_action_norm, common_errors_json, is_core_step
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{trace_id}:{step.step_id}",
                    trace_id,
                    step.order,
                    step.name,
                    step.cognitive_layer.value,
                    step.reuse_level.value,
                    step.domain,
                    step.student_action_norm,
                    _json_dumps(step.common_errors),
                    int(step.is_core_step),
                ),
            )

    return {
        "status": "reviewed",
        "codex_thread_id": reviewed.codex_thread_id,
        "problem_case_id": draft_row["problem_case_id"],
        "draft_id": draft_id,
        "reviewed_trace_id": trace_id,
    }


def _generate_reviewed_trace_id(connection: sqlite3.Connection) -> str:
    for _ in range(8):
        trace_id = f"trace_{uuid.uuid4().hex}"
        row = connection.execute("SELECT 1 FROM skill_trace_reviews WHERE id = ?", (trace_id,)).fetchone()
        if row is None:
            return trace_id
    raise RuntimeError("failed to generate a unique reviewed_trace_id")


def get_review(reviewed_trace_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, draft_id, problem_case_id, codex_thread_id, reviewed_json, reviewer_note, created_at
            FROM skill_trace_reviews
            WHERE id = ?
            """,
            (reviewed_trace_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"reviewed trace not found: {reviewed_trace_id}")

        step_rows = connection.execute(
            """
            SELECT id, step_order, name, cognitive_layer, reuse_level, domain, student_action_norm,
                   common_errors_json, is_core_step
            FROM skill_trace_steps
            WHERE reviewed_trace_id = ?
            ORDER BY step_order ASC
            """,
            (reviewed_trace_id,),
        ).fetchall()

    return {
        "reviewed_trace_id": row["id"],
        "draft_id": row["draft_id"],
        "problem_case_id": row["problem_case_id"],
        "codex_thread_id": row["codex_thread_id"],
        "reviewer_note": row["reviewer_note"],
        "created_at": row["created_at"],
        "reviewed_json": json.loads(row["reviewed_json"]),
        "steps": [_step_row_to_dict(step_row) for step_row in step_rows],
    }


def get_thread_handoff(
    *,
    codex_thread_id: str | None = None,
    reviewed_trace_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not codex_thread_id and not reviewed_trace_id:
        raise ValueError("codex_thread_id or reviewed_trace_id is required")

    with connect(db_path) as connection:
        if reviewed_trace_id:
            review_row = connection.execute(
                """
                SELECT id, draft_id, problem_case_id, codex_thread_id
                FROM skill_trace_reviews
                WHERE id = ?
                """,
                (reviewed_trace_id,),
            ).fetchone()
        else:
            review_row = connection.execute(
                """
                SELECT id, draft_id, problem_case_id, codex_thread_id
                FROM skill_trace_reviews
                WHERE codex_thread_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (codex_thread_id,),
            ).fetchone()

        if review_row is not None:
            return {
                "codex_thread_id": review_row["codex_thread_id"],
                "problem_case_id": review_row["problem_case_id"],
                "draft_id": review_row["draft_id"],
                "reviewed_trace_id": review_row["id"],
                "next_suggested_actions": ["generate_student_explanation", "generate_adaptive_assignment"],
            }

        draft_row = connection.execute(
            """
            SELECT id, problem_case_id, codex_thread_id
            FROM skill_trace_drafts
            WHERE codex_thread_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (codex_thread_id,),
        ).fetchone()
        if draft_row is None:
            raise KeyError(f"thread handoff not found: {codex_thread_id or reviewed_trace_id}")

    return {
        "codex_thread_id": draft_row["codex_thread_id"],
        "problem_case_id": draft_row["problem_case_id"],
        "draft_id": draft_row["id"],
        "reviewed_trace_id": None,
        "next_suggested_actions": ["open_review"],
    }


def _upsert_codex_thread(connection: sqlite3.Connection, thread_id: str, now: str) -> None:
    connection.execute(
        """
        INSERT INTO codex_threads (id, provider, created_at, last_used_at, metadata_json)
        VALUES (?, 'codex', ?, ?, '{}')
        ON CONFLICT(id) DO UPDATE SET last_used_at = excluded.last_used_at
        """,
        (thread_id, now, now),
    )


def _upsert_draft(connection: sqlite3.Connection, draft: SkillTraceDraft, problem_case_id: str, now: str) -> None:
    _upsert_codex_thread(connection, draft.codex_thread_id, now)
    _upsert_problem_case(connection, problem_case_id, draft, now)
    connection.execute(
        """
        INSERT INTO skill_trace_drafts (id, problem_case_id, codex_thread_id, draft_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          problem_case_id = excluded.problem_case_id,
          codex_thread_id = excluded.codex_thread_id,
          draft_json = excluded.draft_json
        """,
        (
            draft.draft_id,
            problem_case_id,
            draft.codex_thread_id,
            _json_dumps(_draft_to_json(draft)),
            now,
        ),
    )


def _upsert_problem_case(connection: sqlite3.Connection, problem_case_id: str, draft: SkillTraceDraft, now: str) -> None:
    problem = draft.problem_case
    connection.execute(
        """
        INSERT INTO problem_cases (
          id, title, raw_problem, provided_solution, expected_thinking, topic_tags_json,
          target_student_level, codex_thread_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          title = excluded.title,
          raw_problem = excluded.raw_problem,
          provided_solution = excluded.provided_solution,
          expected_thinking = excluded.expected_thinking,
          topic_tags_json = excluded.topic_tags_json,
          target_student_level = excluded.target_student_level,
          codex_thread_id = excluded.codex_thread_id
        """,
        (
            problem_case_id,
            problem.title,
            problem.raw_problem,
            problem.provided_solution,
            problem.expected_thinking,
            _json_dumps(problem.topic_tags),
            problem.target_student_level,
            draft.codex_thread_id,
            now,
        ),
    )


def _coerce_draft(payload: dict[str, Any] | SkillTraceDraft) -> SkillTraceDraft:
    if isinstance(payload, SkillTraceDraft):
        return payload
    return SkillTraceDraft.model_validate(prune_deprecated_step_fields(payload))


def _draft_to_json(draft: SkillTraceDraft) -> dict[str, Any]:
    return draft.model_dump(mode="json")


def _problem_case_id_for_draft(draft: SkillTraceDraft) -> str:
    return f"case_{draft.draft_id}"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _step_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "order": row["step_order"],
        "name": row["name"],
        "cognitive_layer": row["cognitive_layer"],
        "reuse_level": row["reuse_level"],
        "domain": row["domain"],
        "student_action_norm": row["student_action_norm"],
        "common_errors": json.loads(row["common_errors_json"]),
        "is_core_step": bool(row["is_core_step"]),
    }


def _load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path; defaults to SKILL_TRACE_DB or artifacts/skill_trace.db")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize the SQLite schema")

    insert_draft_parser = subparsers.add_parser("insert-draft", help="Insert a SkillTraceDraft JSON file")
    insert_draft_parser.add_argument("--draft", type=Path, required=True)

    get_draft_parser = subparsers.add_parser("get-draft", help="Read a draft")
    get_draft_parser.add_argument("--draft-id", required=True)

    insert_review_parser = subparsers.add_parser("insert-review", help="Insert a reviewed trace JSON file")
    insert_review_parser.add_argument("--draft-id", required=True)
    insert_review_parser.add_argument("--reviewed-json", type=Path, required=True)
    insert_review_parser.add_argument("--reviewed-trace-id", default=None)
    insert_review_parser.add_argument("--reviewer-note", default="")

    get_review_parser = subparsers.add_parser("get-review", help="Read a reviewed trace")
    get_review_parser.add_argument("--reviewed-trace-id", required=True)

    get_handoff_parser = subparsers.add_parser("get-handoff", help="Read thread handoff details")
    handoff_group = get_handoff_parser.add_mutually_exclusive_group(required=True)
    handoff_group.add_argument("--codex-thread-id")
    handoff_group.add_argument("--reviewed-trace-id")

    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            result = initialize_database(args.db)
        elif args.command == "insert-draft":
            result = insert_draft(_load_json_file(args.draft), db_path=args.db)
        elif args.command == "get-draft":
            result = get_draft(args.draft_id, db_path=args.db)
        elif args.command == "insert-review":
            result = insert_review(
                draft_id=args.draft_id,
                reviewed_json=_load_json_file(args.reviewed_json),
                reviewer_note=args.reviewer_note,
                reviewed_trace_id=args.reviewed_trace_id,
                db_path=args.db,
            )
        elif args.command == "get-review":
            result = get_review(args.reviewed_trace_id, db_path=args.db)
        elif args.command == "get-handoff":
            result = get_thread_handoff(
                codex_thread_id=args.codex_thread_id,
                reviewed_trace_id=args.reviewed_trace_id,
                db_path=args.db,
            )
        else:  # pragma: no cover - argparse enforces valid choices.
            parser.error(f"unknown command: {args.command}")
    except (KeyError, ValueError, sqlite3.Error) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
