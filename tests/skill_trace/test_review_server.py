from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_trace.db import get_draft, insert_draft  # noqa: E402
from skill_trace.open_review import MANUAL_THREAD_WARNING, prepare_review  # noqa: E402
from skill_trace.review_server import create_app, submit_review_payload  # noqa: E402
from tests.skill_trace.test_contracts import valid_payload  # noqa: E402


class ReviewServerTest(unittest.TestCase):
    def test_prepare_review_overrides_thread_and_inserts_draft(self) -> None:
        payload = valid_payload(codex_thread_id="old_thread")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            draft_path = tmp_path / "draft.json"
            db_path = tmp_path / "skill_trace.db"
            draft_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = prepare_review(
                draft_path=draft_path,
                codex_thread_id="thr_from_cli",
                db_path=db_path,
                port=8765,
            )
            draft = get_draft("draft_demo", db_path=db_path)

        self.assertEqual(result["status"], "review_ui_opened")
        self.assertEqual(result["codex_thread_id"], "thr_from_cli")
        self.assertEqual(draft["codex_thread_id"], "thr_from_cli")
        self.assertEqual(draft["draft_json"]["codex_thread_id"], "thr_from_cli")

    def test_prepare_review_generates_manual_thread_when_missing(self) -> None:
        payload = valid_payload()
        payload.pop("codex_thread_id")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            draft_path = tmp_path / "draft.json"
            db_path = tmp_path / "skill_trace.db"
            draft_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = prepare_review(draft_path=draft_path, db_path=db_path)
            draft = get_draft("draft_demo", db_path=db_path)

        self.assertTrue(result["codex_thread_id"].startswith("manual_"))
        self.assertEqual(result["warnings"], [MANUAL_THREAD_WARNING])
        self.assertEqual(draft["draft_json"]["codex_thread_id"], result["codex_thread_id"])

    def test_submit_review_payload_persists_review(self) -> None:
        payload = valid_payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"
            insert_draft(payload, db_path=db_path)

            result = submit_review_payload(
                {
                    "draft_id": "draft_demo",
                    "codex_thread_id": "thr_demo",
                    "reviewed_json": payload,
                    "reviewer_note": "checked",
                },
                db_path=db_path,
            )

        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["draft_id"], "draft_demo")
        self.assertTrue(result["reviewed_trace_id"].startswith("trace_"))

    def test_http_routes_return_draft_page_and_review(self) -> None:
        payload = valid_payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "skill_trace.db"
            insert_draft(payload, db_path=db_path)

            server, thread, port = _start_uvicorn_test_server(db_path)
            try:
                health = _request_json(port, "GET", "/healthz")
                draft = _request_json(port, "GET", "/api/drafts/draft_demo")
                page_status, page_body = _request_text(port, "GET", "/review/draft_demo")
                review = _request_json(
                    port,
                    "POST",
                    "/api/reviews",
                    {
                        "draft_id": "draft_demo",
                        "codex_thread_id": "thr_demo",
                        "reviewed_json": payload,
                        "reviewer_note": "",
                    },
                )
                fetched = _request_json(port, "GET", f"/api/reviews/{review['reviewed_trace_id']}")
            finally:
                server.should_exit = True
                thread.join(timeout=5)

        self.assertEqual(health, {"ok": True})
        self.assertEqual(draft["draft_json"]["draft_id"], "draft_demo")
        self.assertEqual(page_status, 200)
        self.assertIn("Skill Trace Review", page_body)
        self.assertEqual(review["status"], "reviewed")
        self.assertEqual(fetched["reviewed_json"]["draft_id"], "draft_demo")

    def test_open_review_prepare_only_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "skill_trace.db"
            draft_path = tmp_path / "draft.json"
            draft_path.write_text(json.dumps(valid_payload(), ensure_ascii=False), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "skill_trace" / "open_review.py"),
                    "--draft",
                    str(draft_path),
                    "--db",
                    str(db_path),
                    "--prepare-only",
                    "--no-browser",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "review_ui_opened")


def _start_uvicorn_test_server(db_path: Path) -> tuple[uvicorn.Server, threading.Thread, int]:
    port = _free_port()
    config = uvicorn.Config(create_app(db_path=db_path), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            _request_json(port, "GET", "/healthz")
            return server, thread, port
        except Exception:
            time.sleep(0.05)
    server.should_exit = True
    raise RuntimeError("uvicorn test server did not start")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_json(port: int, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    status, body = _request_text(port, method, path, payload)
    result = json.loads(body)
    if status >= 400:
        raise AssertionError(result)
    return result


def _request_text(
    port: int,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read().decode("utf-8")
        return response.status, data
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
