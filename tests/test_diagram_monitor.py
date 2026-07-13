from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_monitor.scanner import DiagramArtifactScanner, safe_resolve  # noqa: E402
from diagram_monitor.server import create_app  # noqa: E402


class DiagramMonitorScannerTest(unittest.TestCase):
    def test_search_sorts_by_descendant_activity_and_reconciles_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            older = _write_successful_artifact(artifacts_root / "2026-07-09-比例辅助线边比", batch_status="ok")
            newer = _write_successful_artifact(
                artifacts_root / "2026-07-12-比例辅助线两组比例-待审核",
                batch_status="dry_run",
            )
            os.utime(older / "build" / "diagram" / "jobs" / "q1-prompt" / "workflow_result.json", (100, 100))
            os.utime(newer / "build" / "diagram" / "jobs" / "q1-prompt" / "workflow_result.json", (200, 200))

            result = DiagramArtifactScanner(artifacts_root).search("比例辅助线")

        self.assertEqual(result[0]["name"], "2026-07-12-比例辅助线两组比例-待审核")
        self.assertEqual(result[0]["status"], "success")
        self.assertTrue(result[0]["has_conflict"])
        self.assertIn("batch", " ".join(result[0]["status_warnings"]).lower())
        self.assertEqual(result[0]["job_counts"]["total"], 1)
        self.assertEqual(result[0]["job_counts"]["conflict"], 1)
        self.assertEqual(result[0]["preview_count"], 1)
        self.assertEqual(result[1]["status"], "success")

    def test_selected_round_audit_is_valid_evidence_when_root_copy_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "round-audit", batch_status="ok", with_round=True)
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            (job_dir / "rendered" / "prompt.preview.png").unlink()
            _write_json(job_dir / "renderer_audit.json", {"checks": {"image_exists": False}, "warnings": []})

            job = DiagramArtifactScanner(artifacts_root).folder_detail("round-audit")["jobs"][0]

        self.assertEqual(job["status"], "success")
        self.assertEqual(job["preview_path"], "build/diagram/jobs/q1-prompt/rounds/round_0/rendered/prompt.preview.png")
        self.assertEqual(job["stages"]["audit"], "success")
        self.assertEqual(job["audit_source"], "rounds/round_0/audit_result.json")
        self.assertEqual(job["effective_round"], 0)
        self.assertTrue(any("selected round 0" in item for item in job["status_warnings"]))

    def test_failed_renderer_identifies_renderer_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "renderer-failure", batch_status="failed")
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            _write_json(
                job_dir / "renderer_result.json",
                {"status": "failed", "fail_type": "tikz_compile_failed", "message": "bad marker"},
            )

            detail = DiagramArtifactScanner(artifacts_root).folder_detail("renderer-failure")
            job = detail["jobs"][0]

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["failed_stage"], "tikz")
        self.assertEqual(job["stages"]["renderer_spec"], "success")
        self.assertEqual(job["stages"]["tikz"], "failed")
        self.assertIn("bad marker", job["status_reasons"])

    def test_job_detail_exposes_rounds_events_and_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            _write_successful_artifact(artifacts_root / "round-detail", batch_status="ok", with_round=True)
            scanner = DiagramArtifactScanner(artifacts_root)

            detail = scanner.job_detail("round-detail", "q1-prompt")

        self.assertEqual(len(detail["rounds"]), 1)
        self.assertEqual(detail["events"][-1]["event"], "agent.end")
        artifact_paths = {item["path"] for group in detail["artifact_groups"] for item in group["items"]}
        self.assertIn("build/diagram/jobs/q1-prompt/scene_payload.json", artifact_paths)
        self.assertIn("build/diagram/jobs/q1-prompt/rendered/prompt.preview.png", artifact_paths)
        self.assertIn("build/diagram/jobs/q1-prompt/rounds/round_0/render_result.json", artifact_paths)

    def test_safe_resolve_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            root.mkdir()
            with self.assertRaises(ValueError):
                safe_resolve(root, "../secret.txt")


class DiagramMonitorServerTest(unittest.TestCase):
    def test_http_api_serves_monitor_and_text_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            _write_successful_artifact(artifacts_root / "比例辅助线", batch_status="ok")
            client = TestClient(create_app(artifacts_root=artifacts_root))

            page = client.get("/")
            folders = client.get("/api/folders", params={"query": "比例辅助线"})
            detail = client.get("/api/folder", params={"path": "比例辅助线"})
            content = client.get(
                "/api/content",
                params={"folder": "比例辅助线", "path": "build/diagram/jobs/q1-prompt/scene_payload.json"},
            )
            escaped = client.get(
                "/api/content",
                params={"folder": "比例辅助线", "path": "../../outside.txt"},
            )

        self.assertEqual(page.status_code, 200)
        self.assertIn("Diagram Pipeline Monitor", page.text)
        self.assertEqual(folders.status_code, 200)
        self.assertEqual(folders.json()["items"][0]["status"], "success")
        self.assertEqual(detail.json()["jobs"][0]["job_id"], "q1-prompt")
        self.assertEqual(content.status_code, 200)
        self.assertIn("scene_code", content.json()["content"])
        self.assertEqual(escaped.status_code, 400)

    def test_accept_requires_passed_candidate_audit_and_never_runs_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            runner = _RevisionRunnerSpy()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))

            accepted = client.post(
                "/api/human-review",
                json=_review_action("accept-action", decision="accepted"),
            )

            self.assertEqual(accepted.status_code, 200)
            record = accepted.json()
            self.assertEqual(record["decision"], "accepted")
            self.assertEqual(record["status"], "accepted")
            self.assertEqual(record["base_round"], 0)
            self.assertEqual(record["deterministic_audit"], "pass")
            self.assertEqual(runner.calls, [])
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            self.assertEqual(_read_json(job_dir / "human_review.json")["review_id"], record["review_id"])
            self.assertEqual(
                _read_json(job_dir / "human_reviews" / f'{record["review_id"]}.json')["status"],
                "accepted",
            )

            detail = client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["human_review"]["status"], "accepted")

            blocked_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt" / "rounds" / "round_0"
            _write_json(blocked_dir / "audit_result.json", {"status": "block", "issues": ["labels overlap"]})
            blocked = client.post(
                "/api/human-review",
                json=_review_action("blocked-accept", decision="accepted"),
            )
            self.assertEqual(blocked.status_code, 409)

            (blocked_dir / "audit_result.json").unlink()
            missing = client.post(
                "/api/human-review",
                json=_review_action("missing-accept", decision="accepted"),
            )
            self.assertEqual(missing.status_code, 409)
            self.assertEqual(len(runner.calls), 0)

            terminal = client.post(
                "/api/human-review",
                json=_review_action("after-accept", decision="changes_requested", feedback="不应再修改"),
            )
            self.assertEqual(terminal.status_code, 409)

    def test_change_request_rejects_empty_feedback_and_persists_one_safe_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            # The next Round must be allocated from disk, not from a stale workflow summary.
            (artifact / "build" / "diagram" / "jobs" / "q1-prompt" / "rounds" / "round_3").mkdir()
            runner = _RevisionRunnerSpy()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))

            empty = client.post(
                "/api/human-review",
                json=_review_action("empty-action", decision="changes_requested", feedback="   "),
            )
            self.assertEqual(empty.status_code, 422)
            self.assertEqual(runner.calls, [])

            feedback = "把右侧图例下移 4mm；不要执行 shell：$(touch /tmp/diagram-review-pwned)"
            submitted = client.post(
                "/api/human-review",
                json=_review_action("change-action", decision="changes_requested", feedback=feedback),
            )

            self.assertEqual(submitted.status_code, 202)
            record = submitted.json()
            self.assertEqual(record["status"], "queued")
            self.assertEqual(record["base_round"], 0)
            self.assertEqual(record["requested_round"], 4)
            self.assertEqual(record["feedback"], feedback)
            self.assertEqual(len(runner.calls), 1)
            call = runner.calls[0]
            self.assertEqual(call["request"]["feedback"], feedback)
            self.assertEqual(call["request"]["max_retries"], 0)
            self.assertEqual(call["request"]["base_round"], 0)
            self.assertEqual(call["request"]["requested_round"], 4)

            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            self.assertEqual(call["job_dir"], job_dir.resolve())
            self.assertTrue(call["request_path"].resolve().is_relative_to(job_dir.resolve()))
            request_path = job_dir / "human_reviews" / f'{record["review_id"]}.request.json'
            self.assertEqual(_read_json(request_path)["feedback"], feedback)
            self.assertFalse(Path("/tmp/diagram-review-pwned").exists())

    def test_review_action_id_is_idempotent_and_queued_job_rejects_another_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            runner = _RevisionRunnerSpy()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
            payload = _review_action("stable-action", decision="changes_requested", feedback="图例向下移动")

            first = client.post("/api/human-review", json=payload)
            replay = client.post("/api/human-review", json=payload)
            conflicting_replay = client.post(
                "/api/human-review",
                json={**payload, "feedback": "重复 action_id 但载荷不同"},
            )
            conflicting_decision = client.post(
                "/api/human-review",
                json={**payload, "decision": "accepted", "feedback": ""},
            )
            conflicting_base = client.post(
                "/api/human-review",
                json={**payload, "base_round": 9},
            )
            conflict = client.post(
                "/api/human-review",
                json=_review_action("different-action", decision="changes_requested", feedback="另一条建议"),
            )

            self.assertEqual(first.status_code, 202)
            self.assertIn(replay.status_code, {200, 202})
            self.assertEqual(replay.json()["review_id"], first.json()["review_id"])
            self.assertEqual(replay.json()["feedback"], "图例向下移动")
            self.assertEqual(conflicting_replay.status_code, 409)
            self.assertEqual(conflicting_decision.status_code, 409)
            self.assertEqual(conflicting_base.status_code, 409)
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(len(runner.calls), 1)
            history = list(
                (artifact / "build" / "diagram" / "jobs" / "q1-prompt" / "human_reviews").glob("review_*.json")
            )
            self.assertEqual(len([path for path in history if not path.name.endswith(".request.json")]), 1)

    def test_concurrent_change_requests_allocate_only_one_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            runner = _RevisionRunnerSpy()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
            payloads = [
                _review_action("concurrent-a", decision="changes_requested", feedback="建议 A"),
                _review_action("concurrent-b", decision="changes_requested", feedback="建议 B"),
            ]

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda payload: client.post("/api/human-review", json=payload), payloads))

            self.assertEqual(sorted(response.status_code for response in responses), [202, 409])
            self.assertEqual(len(runner.calls), 1)
            accepted = next(response.json() for response in responses if response.status_code == 202)
            self.assertEqual(accepted["requested_round"], 1)
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            records = [
                path
                for path in (job_dir / "human_reviews").glob("review_*.json")
                if not path.name.endswith(".request.json")
            ]
            self.assertEqual(len(records), 1)

    def test_human_review_api_rejects_folder_and_job_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            runner = _RevisionRunnerSpy()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))

            folder_escape = client.post(
                "/api/human-review",
                json={**_review_action("escape-folder", "accepted"), "folder": "../outside"},
            )
            job_escape = client.post(
                "/api/human-review",
                json={**_review_action("escape-job", "accepted"), "job_id": "../../outside"},
            )

            self.assertEqual(folder_escape.status_code, 400)
            self.assertEqual(job_escape.status_code, 400)
            self.assertEqual(runner.calls, [])

    def test_revision_terminal_states_update_history_and_job_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            success_runner = _RevisionRunnerSpy(result={"status": "ok", "selected_round": 1})
            success_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=success_runner))

            submitted = success_client.post(
                "/api/human-review",
                json=_review_action("success-action", "changes_requested", "移动点 E 标签"),
            )
            detail = success_client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

            self.assertEqual(detail.json()["human_review"]["status"], "revision_completed")
            self.assertEqual(history["status"], "revision_completed")

            _write_json(job_dir / "agent_result.json", {"status": "ok", "selected_round": 1})
            replay = success_client.post(
                "/api/human-review",
                json=_review_action("success-action", "changes_requested", "移动点 E 标签"),
            )
            self.assertIn(replay.status_code, {200, 202})
            self.assertEqual(replay.json()["review_id"], submitted.json()["review_id"])

            failing_runner = _RevisionRunnerSpy(error=RuntimeError("agent failed"))
            failed_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=failing_runner))
            failed = failed_client.post(
                "/api/human-review",
                json={**_review_action("failed-action", "changes_requested", "再调整标签"), "base_round": 1},
            )
            failed_detail = failed_client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})
            failed_history = _read_json(job_dir / "human_reviews" / f'{failed.json()["review_id"]}.json')

            self.assertEqual(failed_detail.json()["human_review"]["status"], "revision_failed")
            self.assertEqual(failed_history["status"], "revision_failed")
            self.assertIn("agent failed", failed_history["message"])

    def test_host_rejects_agent_that_creates_more_than_requested_round(self) -> None:
        def extra_round_runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            requested = int(request["requested_round"])
            (job_dir / "rounds" / f"round_{requested}").mkdir(parents=True)
            (job_dir / "rounds" / f"round_{requested + 1}").mkdir(parents=True)
            _write_json(job_dir / "agent_result.json", {"status": "ok", "selected_round": requested})
            return {"status": "ok", "selected_round": requested, "message": "created extras"}

        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=extra_round_runner))

            submitted = client.post(
                "/api/human-review",
                json=_review_action("extra-round", "changes_requested", "调整标签"),
            )
            detail = client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})

            self.assertEqual(submitted.status_code, 202)
            self.assertEqual(detail.json()["human_review"]["status"], "revision_failed")
            self.assertIn("exactly Round", detail.json()["human_review"]["message"])
            rounds_dir = artifacts_root / "reviewable/build/diagram/jobs/q1-prompt/rounds"
            self.assertEqual(sorted(path.name for path in rounds_dir.glob("round_*")), ["round_0", "round_1"])

            next_runner = _RevisionRunnerSpy()
            next_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=next_runner))
            next_revision = next_client.post(
                "/api/human-review",
                json={**_review_action("after-extra", "changes_requested", "继续调整"), "base_round": 1},
            )
            self.assertEqual(next_revision.status_code, 202)
            self.assertEqual(next_revision.json()["requested_round"], 2)

    def test_partial_failed_revision_becomes_the_same_candidate_in_ui_and_service(self) -> None:
        def partial_runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            requested = int(request["requested_round"])
            round_dir = job_dir / "rounds" / f"round_{requested}"
            (round_dir / "rendered").mkdir(parents=True)
            _write_json(round_dir / "audit_result.json", {"status": "block", "issues": ["label overlap"]})
            (round_dir / "rendered" / "prompt.preview.png").write_bytes(b"failed-candidate")
            raise RuntimeError("audit blocked")

        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            first_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=partial_runner))
            first_client.post(
                "/api/human-review",
                json=_review_action("partial", "changes_requested", "调整重叠标签"),
            )
            detail = first_client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})

            self.assertEqual(detail.json()["human_review"]["status"], "revision_failed")
            self.assertEqual(detail.json()["human_review"]["requested_round"], 1)
            self.assertEqual(detail.json()["rounds"][-1]["round_index"], 1)

            second_runner = _RevisionRunnerSpy()
            second_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=second_runner))
            next_revision = second_client.post(
                "/api/human-review",
                json={**_review_action("after-partial", "changes_requested", "继续调整"), "base_round": 1},
            )

            self.assertEqual(next_revision.status_code, 202)
            self.assertEqual(next_revision.json()["requested_round"], 2)

    def test_failed_revision_without_requested_round_falls_back_to_existing_round(self) -> None:
        def ghost_selected_runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            requested = int(request["requested_round"])
            _write_json(job_dir / "agent_result.json", {"status": "failed", "selected_round": requested})
            raise RuntimeError("agent failed before creating the requested round")

        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            first_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=ghost_selected_runner))
            first_client.post(
                "/api/human-review",
                json=_review_action("ghost-round", "changes_requested", "调整标签"),
            )
            detail = first_client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})

            self.assertEqual(detail.json()["human_review"]["status"], "revision_failed")
            self.assertEqual([item["round_index"] for item in detail.json()["rounds"]], [0])

            next_runner = _RevisionRunnerSpy()
            next_client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=next_runner))
            next_revision = next_client.post(
                "/api/human-review",
                json={**_review_action("after-ghost", "changes_requested", "重新调整"), "base_round": 0},
            )

            self.assertEqual(next_revision.status_code, 202)
            self.assertEqual(next_revision.json()["base_round"], 0)
            self.assertEqual(next_revision.json()["requested_round"], 1)

    def test_restart_recovers_stale_nonterminal_review_without_rerun(self) -> None:
        for stale_status in ("queued", "revision_running"):
            with self.subTest(status=stale_status), tempfile.TemporaryDirectory() as tmp:
                artifacts_root = Path(tmp) / "artifacts"
                artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
                job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
                stale = {
                    "schema_version": "diagram-human-review/v1",
                    "action_id": f"stale-{stale_status}",
                    "review_id": "review_0001",
                    "job_id": "q1-prompt",
                    "decision": "changes_requested",
                    "status": stale_status,
                    "feedback": "调整标签",
                    "base_round": 0,
                    "requested_round": 1,
                    "deterministic_audit": "pass",
                    "created_at": "2026-07-13T12:00:00+08:00",
                    "updated_at": "2026-07-13T12:00:00+08:00",
                    "message": "",
                }
                _write_json(job_dir / "human_review.json", stale)
                _write_json(job_dir / "human_reviews" / "review_0001.json", stale)
                runner = _RevisionRunnerSpy()

                client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
                detail = client.get("/api/job", params={"folder": "reviewable", "job_id": "q1-prompt"})

                self.assertEqual(detail.json()["human_review"]["status"], "revision_failed")
                self.assertIn("restart", detail.json()["human_review"]["message"].lower())
                self.assertEqual(runner.calls, [])


class DiagramMonitorVisualContractTest(unittest.TestCase):
    def test_desktop_and_responsive_layout_match_contract(self) -> None:
        html = (ROOT / "scripts" / "diagram_monitor" / "templates" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.css").read_text(encoding="utf-8")

        self.assertIn('aria-label="搜索作业目录"', html)
        self.assertIn('id="folder-pane"', html)
        self.assertIn('id="job-pane"', html)
        self.assertIn('id="detail-pane"', html)
        self.assertIn("grid-template-columns: 300px minmax(420px, 1fr) minmax(420px, 0.95fr)", css)
        self.assertIn("aspect-ratio: 16 / 10", css)
        self.assertIn("@media (max-width: 1100px)", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("--success: #207a55", css)
        self.assertIn("--danger: #a33737", css)

    def test_state_is_visible_as_text_and_not_only_color(self) -> None:
        js = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.js").read_text(encoding="utf-8")

        for label in ["等待中", "运行中", "疑似卡住", "失败", "产物不完整", "成功", "状态冲突"]:
            self.assertIn(label, js)
        for tab in ["概览", "轮次", "事件", "产物", "性能"]:
            self.assertIn(tab, js)

    def test_human_review_panel_exposes_explicit_single_revision_actions(self) -> None:
        js = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.js").read_text(encoding="utf-8")
        css = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.css").read_text(encoding="utf-8")

        for label in ["人工复核", "当前候选", "修改建议", "接受当前图", "提交给 Agent"]:
            self.assertIn(label, js)
        for state in ["未复核", "已接受", "排队中", "Agent 修订中", "新版本待复核", "修订失败"]:
            self.assertIn(state, js)
        self.assertIn("只生成一个新 Round", js)
        self.assertIn("human-review-panel", css)
        self.assertIn("human-review-actions", css)
        self.assertIn("candidate?.preview_path", js)

    def test_human_review_panel_reuses_tokens_and_stacks_at_mobile_width(self) -> None:
        css = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.css").read_text(encoding="utf-8")

        self.assertRegex(
            css,
            r"(?s)\.human-review-panel\s*\{[^}]*border:\s*1px solid var\(--line\)[^}]*border-radius:\s*var\(--radius\)",
        )
        self.assertRegex(css, r"(?s)\.human-review-panel textarea\s*\{[^}]*min-height:\s*(?:9[6-9]|1\d{2})px")
        self.assertRegex(
            css,
            r"(?s)@media \(max-width: 720px\).*?\.human-review-actions\s*\{[^}]*grid-template-columns:\s*1fr",
        )
        self.assertRegex(
            css,
            r"(?s)@media \(max-width: 720px\).*?\.human-review-actions (?:button|\.text-button)\s*\{[^}]*width:\s*100%",
        )

    def test_human_review_state_module_enforces_controls_and_preserves_drafts(self) -> None:
        module = ROOT / "scripts" / "diagram_monitor" / "static" / "review_state.js"
        script = f"""
const assert = require('assert');
const review = require({json.dumps(str(module))});
for (const status of ['queued', 'revision_running']) {{
  const controls = review.reviewControls({{ status, deterministicAudit: 'pass' }});
  assert.strictEqual(controls.acceptDisabled, true);
  assert.strictEqual(controls.submitDisabled, true);
}}
const blocked = review.reviewControls({{ status: 'unreviewed', deterministicAudit: 'block' }});
assert.strictEqual(blocked.acceptDisabled, true);
assert.strictEqual(blocked.submitDisabled, false);
assert.match(blocked.acceptReason, /确定性审核未通过/);
const accepted = review.reviewControls({{ status: 'accepted', deterministicAudit: 'pass' }});
assert.strictEqual(accepted.acceptDisabled, true);
assert.strictEqual(accepted.submitDisabled, true);
assert.strictEqual(accepted.feedbackDisabled, true);
const candidate = review.candidateRound({{
  selected_round: 0,
  human_review: {{ status: 'revision_failed', requested_round: 1 }},
  rounds: [{{ round_index: 0, preview_path: 'old.png' }}, {{ round_index: 1, preview_path: 'new.png' }}],
}});
assert.strictEqual(candidate, 1);
const existingCandidate = review.candidateRound({{
  selected_round: 2,
  effective_round: 1,
  human_review: {{ status: 'revision_failed', requested_round: 2 }},
  rounds: [{{ round_index: 0 }}, {{ round_index: 1 }}],
}});
assert.strictEqual(existingCandidate, 1);
const drafts = {{ 'folder/q1': '正在输入的建议' }};
assert.strictEqual(review.preserveReviewDraft(drafts, 'folder/q1', ''), '正在输入的建议');
assert.strictEqual(review.preserveReviewDraft(drafts, 'folder/q1', '新输入'), '新输入');
console.log('ok');
"""
        completed = subprocess.run(["node", "-e", script], text=True, capture_output=True, check=False)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "ok")


def _write_successful_artifact(path: Path, batch_status: str, with_round: bool = False) -> Path:
    diagram_dir = path / "build" / "diagram"
    job_dir = diagram_dir / "jobs" / "q1-prompt"
    rendered_dir = job_dir / "rendered"
    rendered_dir.mkdir(parents=True)
    _write_json(
        diagram_dir / "diagram_jobs.json",
        {
            "schema_version": "diagram-jobs/v1",
            "assignment_id": path.name,
            "source_assignment": "assignment.plan.assignment.yaml",
            "jobs": [
                {
                    "job_id": "q1-prompt",
                    "slot_id": "q1.prompt",
                    "variant": "prompt",
                    "engine": "geometric_scene",
                    "diagram_kind": "synthetic_geometry",
                    "required": True,
                }
            ],
        },
    )
    _write_json(
        diagram_dir / "diagram_batch_report.json",
        {
            "schema_version": "diagram-batch-report/v1",
            "total_jobs": 1,
            "ok_count": 1 if batch_status == "ok" else 0,
            "failed_count": 1 if batch_status == "failed" else 0,
            "dry_run": batch_status == "dry_run",
            "jobs": [
                {
                    "job_id": "q1-prompt",
                    "status": batch_status,
                    "workflow_status": batch_status,
                    "renderer_status": batch_status,
                }
            ],
        },
    )
    _write_json(
        job_dir / "workflow_result.json",
        {
            "status": "ok",
            "wolfram": {"success": True, "solve_time_s": 0.1},
            "rounds": [{"round_index": 0}],
            "agent": {"duration_ms": 1200, "selected_round": 0},
        },
    )
    _write_json(
        job_dir / "renderer_result.json",
        {
            "status": "ok",
            "tikz_fragment_path": "rendered/prompt.fragment.tex",
            "preview_png_path": "rendered/prompt.preview.png",
            "renderer_audit": "renderer_audit.json",
        },
    )
    _write_json(job_dir / "renderer_audit.json", {"checks": {"image_exists": True}, "warnings": []})
    _write_json(
        job_dir / "scene_payload.json",
        {"scene_code": "GeometricScene[{A,B}, {A == {0,0}, B == {1,0}}]", "diagram_spec": {}},
    )
    _write_json(job_dir / "final_renderer_spec.json", {"status": "ready", "points": {"A": [0, 0], "B": [1, 0]}})
    (rendered_dir / "prompt.fragment.tex").write_text("\\begin{tikzpicture}\\end{tikzpicture}", encoding="utf-8")
    (rendered_dir / "prompt.preview.png").write_bytes(b"fake-png")
    (job_dir / "workflow_events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"ts": "2026-07-13T10:00:00", "event": "agent.start"}),
                json.dumps({"ts": "2026-07-13T10:00:02", "event": "agent.end", "status": "ok"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if with_round:
        round_dir = job_dir / "rounds" / "round_0"
        round_rendered = round_dir / "rendered"
        round_rendered.mkdir(parents=True)
        _write_json(round_dir / "scene_payload.json", {"scene_code": "GeometricScene[...]"})
        _write_json(round_dir / "render_result.json", {"success": True})
        _write_json(round_dir / "audit_result.json", {"status": "pass"})
        _write_json(
            round_dir / "renderer_result.json",
            {
                "status": "ok",
                "tikz_fragment_path": "rendered/prompt.fragment.tex",
                "preview_png_path": "rendered/prompt.preview.png",
            },
        )
        (round_rendered / "prompt.fragment.tex").write_text("\\begin{tikzpicture}\\end{tikzpicture}", encoding="utf-8")
        (round_rendered / "prompt.preview.png").write_bytes(b"round-png")
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _review_action(
    action_id: str,
    decision: str,
    feedback: str = "",
) -> dict[str, str]:
    return {
        "folder": "reviewable",
        "job_id": "q1-prompt",
        "action_id": action_id,
        "decision": decision,
        "feedback": feedback,
        "base_round": 0,
    }


class _RevisionRunnerSpy:
    def __init__(self, result: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result
        self.error = error

    def __call__(self, *, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any] | None:
        self.calls.append(
            {
                "job_dir": Path(job_dir),
                "request_path": Path(request_path),
                "request": request,
            }
        )
        if self.error:
            raise self.error
        if self.result and str(self.result.get("status") or "").lower() in {"ok", "success"}:
            selected = self.result.get("selected_round")
            if isinstance(selected, int):
                (Path(job_dir) / "rounds" / f"round_{selected}").mkdir(parents=True, exist_ok=True)
        return self.result


if __name__ == "__main__":
    unittest.main()
