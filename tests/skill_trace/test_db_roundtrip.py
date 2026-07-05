from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_trace.db import (  # noqa: E402
    get_review,
    get_thread_handoff,
    insert_draft,
    insert_review,
)
from tests.skill_trace.test_contracts import valid_payload  # noqa: E402


class SkillTraceDbRoundtripTest(unittest.TestCase):
    def test_insert_draft_creates_thread_and_problem_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"

            result = insert_draft(valid_payload(), db_path=db_path)

            self.assertEqual(result["status"], "draft_inserted")
            self.assertEqual(result["draft_id"], "draft_demo")
            self.assertEqual(result["problem_case_id"], "case_draft_demo")
            with sqlite3.connect(db_path) as connection:
                thread_count = connection.execute("SELECT COUNT(*) FROM codex_threads").fetchone()[0]
                problem_count = connection.execute("SELECT COUNT(*) FROM problem_cases").fetchone()[0]
                draft_count = connection.execute("SELECT COUNT(*) FROM skill_trace_drafts").fetchone()[0]

        self.assertEqual(thread_count, 1)
        self.assertEqual(problem_count, 1)
        self.assertEqual(draft_count, 1)

    def test_review_roundtrip_persists_reviewed_json_and_steps(self) -> None:
        payload = valid_payload()
        steps = payload["steps"]
        assert isinstance(steps, list)
        steps[1]["student_action_norm"] = "找到 ED 对应 BC"
        steps[1]["common_errors"] = ["只看数字，不看对应线段"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"
            insert_draft(payload, db_path=db_path)
            insert_result = insert_review(
                draft_id="draft_demo",
                reviewed_json=payload,
                reviewer_note="kept expected thinking",
                reviewed_trace_id="trace_demo",
                db_path=db_path,
            )

            review = get_review("trace_demo", db_path=db_path)

        self.assertEqual(insert_result["status"], "reviewed")
        self.assertEqual(insert_result["codex_thread_id"], "thr_demo")
        self.assertEqual(review["reviewed_trace_id"], "trace_demo")
        self.assertEqual(review["reviewer_note"], "kept expected thinking")
        self.assertEqual(review["reviewed_json"]["draft_id"], "draft_demo")
        self.assertEqual([step["order"] for step in review["steps"]], [1, 2])
        self.assertEqual(review["steps"][1]["common_errors"], ["只看数字，不看对应线段"])

    def test_insert_review_autoinserts_missing_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"

            result = insert_review(
                draft_id="draft_demo",
                reviewed_json=valid_payload(),
                reviewed_trace_id="trace_demo",
                db_path=db_path,
            )
            handoff = get_thread_handoff(reviewed_trace_id="trace_demo", db_path=db_path)

        self.assertEqual(result["problem_case_id"], "case_draft_demo")
        self.assertEqual(handoff["codex_thread_id"], "thr_demo")
        self.assertEqual(handoff["reviewed_trace_id"], "trace_demo")

    def test_get_thread_handoff_falls_back_to_draft_when_not_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"
            insert_draft(valid_payload(), db_path=db_path)

            handoff = get_thread_handoff(codex_thread_id="thr_demo", db_path=db_path)

        self.assertEqual(handoff["reviewed_trace_id"], None)
        self.assertEqual(handoff["next_suggested_actions"], ["open_review"])

    def test_cli_init_insert_and_get_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"
            draft_path = Path(tmp_dir) / "draft.json"
            draft_path.write_text(json.dumps(valid_payload(), ensure_ascii=False), encoding="utf-8")

            init_completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "skill_trace" / "db.py"), "--db", str(db_path), "init"],
                check=False,
                capture_output=True,
                text=True,
            )
            insert_completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "skill_trace" / "db.py"),
                    "--db",
                    str(db_path),
                    "insert-draft",
                    "--draft",
                    str(draft_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            review_completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "skill_trace" / "db.py"),
                    "--db",
                    str(db_path),
                    "insert-review",
                    "--draft-id",
                    "draft_demo",
                    "--reviewed-json",
                    str(draft_path),
                    "--reviewed-trace-id",
                    "trace_demo",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            get_completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "skill_trace" / "db.py"),
                    "--db",
                    str(db_path),
                    "get-review",
                    "--reviewed-trace-id",
                    "trace_demo",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(init_completed.returncode, 0, init_completed.stderr)
        self.assertEqual(insert_completed.returncode, 0, insert_completed.stderr)
        self.assertEqual(review_completed.returncode, 0, review_completed.stderr)
        self.assertEqual(get_completed.returncode, 0, get_completed.stderr)
        self.assertEqual(json.loads(get_completed.stdout)["reviewed_trace_id"], "trace_demo")


if __name__ == "__main__":
    unittest.main()
