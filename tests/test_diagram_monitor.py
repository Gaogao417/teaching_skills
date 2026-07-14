from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_monitor.scanner import DiagramArtifactScanner, safe_resolve  # noqa: E402
from diagram_monitor.server import create_app  # noqa: E402
from diagram_workflow.diagram_contracts import DiagramJobRequest  # noqa: E402

CORE = ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(CORE))
from agent_runner import _codex_agent_worker  # noqa: E402


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

    def test_job_detail_exposes_only_exact_request_problem_context_stem_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "stem-detail", batch_status="ok")
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            stem = "  如图，在 $\\triangle ABC$ 中，$DE\\parallel BC$。\n\n求 $AD:DB$。  "
            request = _read_json(job_dir / "request.json")
            request["problem_context"] = {"stem_latex": stem}
            _write_json(job_dir / "request.json", request)

            # These are intentionally plausible but prohibited fallback sources.
            _write_json(job_dir / "teaching_request.json", {"problem_context": {"stem_latex": "DECOY_TEACHING"}})
            (artifact / "assignment.resolved.assignment.yaml").write_text(
                "stem_latex: DECOY_ASSIGNMENT\n", encoding="utf-8"
            )
            sibling_dir = artifact / "build" / "diagram" / "jobs" / "q1-solution"
            _write_json(
                sibling_dir / "request.json",
                {"problem_context": {"stem_latex": "DECOY_SIBLING"}},
            )

            scanner = DiagramArtifactScanner(artifacts_root)
            scanner_detail = scanner.job_detail("stem-detail", "q1-prompt")
            response = TestClient(create_app(artifacts_root=artifacts_root)).get(
                "/api/job", params={"folder": "stem-detail", "job_id": "q1-prompt"}
            )
            request_path = job_dir / "request.json"
            request_path.unlink()
            decoy_only_response = TestClient(create_app(artifacts_root=artifacts_root)).get(
                "/api/job", params={"folder": "stem-detail", "job_id": "q1-prompt"}
            )

        self.assertEqual(scanner_detail["stem_latex"], stem)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stem_latex"], stem)
        self.assertNotIn("DECOY", response.json()["stem_latex"])
        self.assertEqual(decoy_only_response.status_code, 200)
        self.assertEqual(decoy_only_response.json()["stem_latex"], "")

    def test_job_detail_maps_missing_and_invalid_stem_shapes_to_safe_empty_string(self) -> None:
        cases: list[tuple[str, bytes | dict[str, Any] | list[object] | None]] = [
            ("missing-request", None),
            ("missing-context", {}),
            ("missing-stem", {"problem_context": {}}),
            ("non-object-root", ["not", "an", "object"]),
            ("non-object-context", {"problem_context": "not-an-object"}),
            ("number-stem", {"problem_context": {"stem_latex": 42}}),
            ("list-stem", {"problem_context": {"stem_latex": ["x"]}}),
            ("object-stem", {"problem_context": {"stem_latex": {"x": 1}}}),
            ("bool-stem", {"problem_context": {"stem_latex": True}}),
            ("null-stem", {"problem_context": {"stem_latex": None}}),
            ("malformed-json", b'{"problem_context":'),
            ("invalid-utf8", b"\xff\xfe\xfa"),
        ]
        for name, payload in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                artifacts_root = Path(tmp) / "artifacts"
                artifact = _write_successful_artifact(artifacts_root / "stem-detail", batch_status="ok")
                request_path = artifact / "build" / "diagram" / "jobs" / "q1-prompt" / "request.json"
                if payload is None:
                    request_path.unlink()
                elif isinstance(payload, bytes):
                    request_path.write_bytes(payload)
                else:
                    request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

                scanner_detail = DiagramArtifactScanner(artifacts_root).job_detail("stem-detail", "q1-prompt")
                response = TestClient(create_app(artifacts_root=artifacts_root)).get(
                    "/api/job", params={"folder": "stem-detail", "job_id": "q1-prompt"}
                )

                self.assertEqual(scanner_detail["stem_latex"], "")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["stem_latex"], "")
                self.assertEqual(response.json()["job_id"], "q1-prompt")

    def test_manifest_only_job_without_job_directory_still_exposes_empty_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "manifest-only", batch_status="ok")
            shutil.rmtree(artifact / "build" / "diagram" / "jobs" / "q1-prompt")

            scanner_detail = DiagramArtifactScanner(artifacts_root).job_detail("manifest-only", "q1-prompt")
            response = TestClient(create_app(artifacts_root=artifacts_root)).get(
                "/api/job", params={"folder": "manifest-only", "job_id": "q1-prompt"}
            )

        self.assertEqual(scanner_detail["stem_latex"], "")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stem_latex"], "")
        self.assertEqual(response.json()["job_id"], "q1-prompt")

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

    def test_revision_request_projects_legacy_fields_into_canonical_v2_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            _write_json(job_dir / "teaching_request.json", _legacy_revision_base_request())
            runner = _RevisionRunnerSpy()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))

            submitted = client.post(
                "/api/human-review",
                json=_review_action("canonical-action", "changes_requested", "把 P 标签移到点下方"),
            )

            self.assertEqual(submitted.status_code, 202)
            self.assertEqual(len(runner.calls), 1)
            request_path = runner.calls[0]["request_path"]
            diagram_request = _read_json(request_path)["diagram_request"]
            validated = DiagramJobRequest.model_validate(diagram_request)
            self.assertEqual(diagram_request, validated.model_dump(mode="json", by_alias=True))
            self.assertEqual(diagram_request["job_id"], "q1-prompt")
            for key in (
                "wolfram_render_image",
                "seed",
                "wolfram_timeout_s",
                "wolfram_hard_timeout_s",
                "reuse_geometry_from",
                "base_job_dir",
                "unknown_legacy_switch",
            ):
                self.assertNotIn(key, diagram_request)
            self.assertEqual(diagram_request["engine_options"]["seed"], 22025)
            self.assertEqual(diagram_request["engine_options"]["wolfram_timeout_s"], 45)
            self.assertEqual(diagram_request["engine_options"]["wolfram_hard_timeout_s"], 90)
            self.assertEqual(diagram_request["engine_options"]["max_retries"], 0)
            self.assertEqual(diagram_request["reuse"]["reuse_geometry_from"], "legacy/base/prompt")
            self.assertEqual(diagram_request["reuse"]["base_job_dir"], "canonical/base/job")
            self.assertEqual(
                diagram_request["human_revision"],
                {
                    "action_id": "canonical-action",
                    "review_id": "review_0001",
                    "feedback": "把 P 标签移到点下方",
                    "base_round": 0,
                    "requested_round": 1,
                },
            )

    def test_failed_revision_surfaces_fresh_child_error_instead_of_stale_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts_root = root / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            _write_json(job_dir / "teaching_request.json", _canonical_revision_base_request())
            _write_json(
                job_dir / "workflow_result.json",
                {"status": "ok", "stale_marker": "OLD_SUCCESS_MUST_NOT_SURFACE", "wolfram": {"success": True}},
            )
            fake_gsb = root / "fake-gsb" / "core"
            fake_gsb.mkdir(parents=True)
            (fake_gsb / "workflow.py").write_text(
                "import sys\nprint('FRESH_VALIDATION_MARKER: rejected current request')\nraise SystemExit(7)\n",
                encoding="utf-8",
            )

            def failing_wrapper_runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
                runtime_request = job_dir / ".human_review_runtime" / "test-request.json"
                _write_json(runtime_request, request["diagram_request"])
                command = [
                    sys.executable,
                    str(ROOT / "scripts" / "diagram_workflow" / "run_diagram_workflow.py"),
                    str(runtime_request),
                    "--out",
                    str(job_dir),
                    "--gsb-root",
                    str(fake_gsb.parent),
                    "--python",
                    sys.executable,
                    "--strict",
                ]
                completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
                if completed.returncode != 0:
                    raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
                return {"status": "ok", "selected_round": request["requested_round"]}

            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=failing_wrapper_runner))
            submitted = client.post(
                "/api/human-review",
                json=_review_action("fresh-failure", "changes_requested", "调整标签"),
            )
            current = _read_json(job_dir / "human_review.json")
            history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

            self.assertEqual(current["status"], "revision_failed")
            self.assertEqual(history["status"], "revision_failed")
            self.assertIn("FRESH_VALIDATION_MARKER", current["message"])
            self.assertNotIn("OLD_SUCCESS_MUST_NOT_SURFACE", current["message"])
            self.assertNotIn('"success": true', current["message"].lower())

    def test_zero_exit_child_without_fresh_result_cannot_reuse_stale_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = root / "q1-prompt"
            job_dir.mkdir()
            request_path = root / "request.json"
            _write_json(request_path, _canonical_revision_base_request())
            _write_json(
                job_dir / "workflow_result.json",
                {"status": "ok", "stale_marker": "ZERO_EXIT_OLD_SUCCESS", "wolfram": {"success": True}},
            )
            fake_gsb = root / "fake-gsb" / "core"
            fake_gsb.mkdir(parents=True)
            (fake_gsb / "workflow.py").write_text(
                "print('ZERO_EXIT_NO_RESULT_MARKER')\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(ROOT / "scripts" / "diagram_workflow" / "run_diagram_workflow.py"),
                str(request_path),
                "--out",
                str(job_dir),
                "--gsb-root",
                str(fake_gsb.parent),
                "--python",
                sys.executable,
                "--strict",
            ]

            completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            result = _read_json(job_dir / "workflow_result.json")

            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(result["status"], "failed")
            self.assertIn("ZERO_EXIT_NO_RESULT_MARKER", json.dumps(result))
            self.assertNotIn("ZERO_EXIT_OLD_SUCCESS", json.dumps(result))

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

    def test_current_sidecar_is_sole_thread_identity_for_success_and_idempotent_replay(self) -> None:
        calls: list[str] = []
        thread_starts: list[int] = []

        def runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            calls.append(request["review_id"])
            worker = _run_real_worker_with_fake_sdk(job_dir, request, failure="set_name")
            thread_starts.append(int(worker["thread_start_count"]))
            requested = int(request["requested_round"])
            (job_dir / "rounds" / f"round_{requested}").mkdir(parents=True)
            return {
                "status": "ok",
                "selected_round": requested,
                "agent_thread_id": "runner-result-must-not-be-authoritative",
            }

        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
            payload = _review_action("sidecar-success", "changes_requested", "移动标签")

            first = client.post("/api/human-review", json=payload)
            replay = client.post("/api/human-review", json=payload)
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            current = _read_json(job_dir / "human_review.json")
            history = _read_json(job_dir / "human_reviews" / f'{first.json()["review_id"]}.json')

            self.assertEqual(current["status"], "revision_completed")
            self.assertEqual(current["agent_thread_id"], "thread-current")
            self.assertEqual(history["agent_thread_id"], "thread-current")
            self.assertEqual(replay.json()["agent_thread_id"], "thread-current")
            self.assertEqual(replay.json()["review_id"], first.json()["review_id"])
            self.assertEqual(calls, [first.json()["review_id"]])
            self.assertEqual(thread_starts, [1])

    def test_real_worker_sidecar_survives_service_post_thread_failures(self) -> None:
        for failure in ("set_name", "turn", "timeout", "failed_result", "round_validation"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                artifacts_root = Path(tmp) / "artifacts"
                artifact = _write_successful_artifact(
                    artifacts_root / "reviewable", batch_status="ok", with_round=True
                )
                job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"

                def runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
                    worker_failure = "set_name" if failure in {"set_name", "timeout"} else "turn"
                    result = _run_real_worker_with_fake_sdk(job_dir, request, failure=worker_failure)
                    requested = int(request["requested_round"])
                    if failure != "round_validation":
                        (job_dir / "rounds" / f"round_{requested}").mkdir(parents=True, exist_ok=True)
                    if failure == "timeout":
                        raise TimeoutError("current post-thread timeout")
                    if failure == "failed_result":
                        return {"status": "failed", "selected_round": requested, "message": "artifact invalid"}
                    if failure == "round_validation":
                        return {"status": "ok", "selected_round": requested, "message": "missing requested round"}
                    raise RuntimeError(str(result.get("error") or f"current-{failure}-failed"))

                client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
                submitted = client.post(
                    "/api/human-review",
                    json=_review_action(f"post-{failure}", "changes_requested", "调整标签"),
                )
                current = _read_json(job_dir / "human_review.json")
                history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

                self.assertEqual(current["status"], "revision_failed")
                self.assertEqual(current["agent_thread_id"], "thread-current")
                self.assertEqual(history["agent_thread_id"], "thread-current")

    def test_pre_thread_failures_and_stale_or_malformed_metadata_never_bind(self) -> None:
        for failure, current_sidecar in (
            ("config", None),
            ("thread_start", None),
            ("thread_start", {"schema_version": "diagram-codex-task/v1", "review_id": "wrong-review", "agent_thread_id": "thread-wrong", "created_at": "now"}),
            ("thread_start", {"schema_version": "diagram-codex-task/v1", "review_id": "review_0001", "agent_thread_id": "", "created_at": "now"}),
            ("thread_start", {"not": "valid-json-contract"}),
        ):
            with self.subTest(failure=failure, sidecar=current_sidecar), tempfile.TemporaryDirectory() as tmp:
                artifacts_root = Path(tmp) / "artifacts"
                artifact = _write_successful_artifact(
                    artifacts_root / "reviewable", batch_status="ok", with_round=True
                )
                job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
                _write_codex_task_sidecar(job_dir, "review_old", "thread-old")
                _write_json(job_dir / "agent_result.json", {"agent_thread_id": "thread-old", "status": "ok"})
                _write_json(job_dir / "workflow_result.json", {"agent": {"agent_thread_id": "thread-old"}})

                def runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
                    if current_sidecar is not None:
                        _write_json(
                            job_dir / "human_reviews" / f'{request["review_id"]}.codex-task.json',
                            current_sidecar,
                        )
                    result = _run_real_worker_with_fake_sdk(job_dir, request, failure=failure)
                    raise RuntimeError(str(result.get("error") or "pre-thread failure"))

                client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
                submitted = client.post(
                    "/api/human-review",
                    json=_review_action(f"pre-{failure}-{len(str(current_sidecar))}", "changes_requested", "调整标签"),
                )
                current = _read_json(job_dir / "human_review.json")
                history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

                self.assertEqual(current["status"], "revision_failed")
                self.assertNotIn("agent_thread_id", current)
                self.assertNotIn("agent_thread_id", history)

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

    def test_revision_persists_only_the_current_review_codex_task_sidecar(self) -> None:
        def sidecar_runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            requested = int(request["requested_round"])
            review_id = str(request["review_id"])
            (job_dir / "rounds" / f"round_{requested}").mkdir(parents=True)
            _write_json(
                job_dir / "human_reviews" / f"{review_id}.codex-task.json",
                {
                    "schema_version": "diagram-codex-task/v1",
                    "review_id": review_id,
                    "agent_thread_id": "thread-from-sidecar",
                    "created_at": "2026-07-14T02:30:00+08:00",
                },
            )
            return {
                "status": "ok",
                "selected_round": requested,
                "agent_thread_id": "runner-result-must-be-ignored",
            }

        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=sidecar_runner))

            submitted = client.post(
                "/api/human-review",
                json=_review_action("sidecar-success", "changes_requested", "调整标签"),
            )
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            current = _read_json(job_dir / "human_review.json")
            history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

            self.assertEqual(current["status"], "revision_completed")
            self.assertEqual(current["agent_thread_id"], "thread-from-sidecar")
            self.assertEqual(history["agent_thread_id"], "thread-from-sidecar")

    def test_revision_rejects_sidecar_when_outer_or_inner_request_review_id_differs(self) -> None:
        for mismatch in ("outer", "inner"):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as tmp:
                artifacts_root = Path(tmp) / "artifacts"
                artifact = _write_successful_artifact(
                    artifacts_root / "reviewable", batch_status="ok", with_round=True
                )
                job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"

                def runner(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
                    current_review_id = str(request["review_id"])
                    _write_json(
                        job_dir / "human_reviews" / f"{current_review_id}.codex-task.json",
                        {
                            "schema_version": "diagram-codex-task/v1",
                            "review_id": current_review_id,
                            "agent_thread_id": "thread-must-be-rejected",
                            "created_at": "2026-07-14T02:30:00+08:00",
                        },
                    )
                    if mismatch == "outer":
                        request["review_id"] = "review-wrong-outer"
                    else:
                        request["diagram_request"]["human_revision"]["review_id"] = "review-wrong-inner"
                    raise RuntimeError("request identity mismatch")

                client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
                submitted = client.post(
                    "/api/human-review",
                    json=_review_action(f"request-mismatch-{mismatch}", "changes_requested", "调整标签"),
                )
                current = _read_json(job_dir / "human_review.json")
                history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

                self.assertEqual(current["status"], "revision_failed")
                self.assertNotIn("agent_thread_id", current)
                self.assertNotIn("agent_thread_id", history)

    def test_post_thread_failure_keeps_current_sidecar_but_rejects_stale_or_mismatched_ids(self) -> None:
        def created_then_failed(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            review_id = str(request["review_id"])
            _write_json(
                job_dir / "human_reviews" / f"{review_id}.codex-task.json",
                {
                    "schema_version": "diagram-codex-task/v1",
                    "review_id": review_id,
                    "agent_thread_id": "thread-current",
                    "created_at": "2026-07-14T02:31:00+08:00",
                },
            )
            raise RuntimeError("current turn failed")

        def mismatched_then_failed(*, job_dir: Path, request_path: Path, request: dict[str, Any]) -> dict[str, Any]:
            review_id = str(request["review_id"])
            _write_json(
                job_dir / "human_reviews" / f"{review_id}.codex-task.json",
                {
                    "schema_version": "diagram-codex-task/v1",
                    "review_id": "review-old",
                    "agent_thread_id": "thread-old",
                    "created_at": "2026-07-14T02:00:00+08:00",
                },
            )
            raise RuntimeError("failed before current thread")

        for runner, expected in ((created_then_failed, "thread-current"), (mismatched_then_failed, None)):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                artifacts_root = Path(tmp) / "artifacts"
                artifact = _write_successful_artifact(
                    artifacts_root / "reviewable", batch_status="ok", with_round=True
                )
                job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
                _write_json(
                    job_dir / "human_reviews" / "review-old.codex-task.json",
                    {
                        "schema_version": "diagram-codex-task/v1",
                        "review_id": "review-old",
                        "agent_thread_id": "thread-old",
                    },
                )
                client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=runner))
                submitted = client.post(
                    "/api/human-review",
                    json=_review_action("sidecar-failure", "changes_requested", "调整标签"),
                )
                current = _read_json(job_dir / "human_review.json")
                history = _read_json(job_dir / "human_reviews" / f'{submitted.json()["review_id"]}.json')

                self.assertEqual(current["status"], "revision_failed")
                self.assertEqual(current.get("agent_thread_id"), expected)
                self.assertEqual(history.get("agent_thread_id"), expected)

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

    def test_host_restores_historical_round_changed_by_revision(self) -> None:
        def historical_mutation_runner(
            *, job_dir: Path, request_path: Path, request: dict[str, Any]
        ) -> dict[str, Any]:
            requested = int(request["requested_round"])
            (job_dir / "rounds" / f"round_{requested}").mkdir(parents=True)
            (job_dir / "rounds" / "round_0" / "scene_payload.json").write_text(
                '{"scene_code":"tampered"}',
                encoding="utf-8",
            )
            return {"status": "ok", "selected_round": requested, "message": "mutated history"}

        with tempfile.TemporaryDirectory() as tmp:
            artifacts_root = Path(tmp) / "artifacts"
            artifact = _write_successful_artifact(artifacts_root / "reviewable", batch_status="ok", with_round=True)
            job_dir = artifact / "build" / "diagram" / "jobs" / "q1-prompt"
            historical_path = job_dir / "rounds" / "round_0" / "scene_payload.json"
            original = historical_path.read_bytes()
            client = TestClient(create_app(artifacts_root=artifacts_root, revision_runner=historical_mutation_runner))

            client.post(
                "/api/human-review",
                json=_review_action("historical-mutation", "changes_requested", "只调整新候选"),
            )
            current = _read_json(job_dir / "human_review.json")

            self.assertEqual(current["status"], "revision_failed")
            self.assertIn("historical rounds [0]", current["message"])
            self.assertIn("rolled back", current["message"])
            self.assertEqual(historical_path.read_bytes(), original)

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

    def test_job_grid_preserves_content_height_inside_scroll_pane(self) -> None:
        html = (ROOT / "scripts" / "diagram_monitor" / "templates" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'href="/static/monitor\.css\?v=[^"]+"')
        self.assertRegex(
            css,
            r"(?s)\.job-grid\s*\{[^}]*flex:\s*1(?:\s+1\s+auto)?;[^}]*grid-auto-rows:\s*max-content;",
        )
        self.assertRegex(
            css,
            r"(?s)\.job-grid\s*\{[^}]*align-content:\s*start;[^}]*overflow-y:\s*auto;",
        )

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
        self.assertIn("DiagramReviewState.candidatePreview", js)

    def test_human_review_panel_shows_persistent_codex_task_binding_without_fake_chat(self) -> None:
        js = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.js").read_text(encoding="utf-8")
        css = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.css").read_text(encoding="utf-8")

        for label in ["Codex 任务", "正在创建", "已创建", "创建失败", "Thread ID"]:
            self.assertIn(label, js)
        self.assertIn("agent_thread_id", js)
        self.assertIn("codex-task-binding", css)
        binding_call = "${codexTaskBinding(review)}"
        self.assertIn(binding_call, js)
        self.assertGreater(js.index(binding_call), js.index("human-review-actions"))
        self.assertRegex(css, r"(?s)\.codex-task-id\s*\{[^}]*font-family:\s*var\(--mono\)[^}]*overflow-wrap:\s*anywhere")
        binding_source = js[js.index("function codexTaskBinding"):js.index("function bindHumanReviewActions")]
        for forbidden in ["chat-transcript", "chat-composer", "<iframe"]:
            self.assertNotIn(forbidden, binding_source)

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

    def test_overview_renders_escaped_stem_before_candidate_and_omits_blank_stem(self) -> None:
        monitor_js = ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.js"
        script = f"""
const assert = require('assert');
const fs = require('fs');
const source = fs.readFileSync({json.dumps(str(monitor_js))}, 'utf8');
const renderSource = source.slice(
  source.indexOf('function renderOverview'),
  source.indexOf('function humanReviewPanel')
);
const detailBody = {{ innerHTML: '' }};
function el(id) {{ assert.strictEqual(id, 'detail-body'); return detailBody; }}
function selectedCandidateRound() {{ return 0; }}
const DiagramReviewState = {{ candidatePreview() {{ return ''; }} }};
function escapeHtml(value) {{ return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/'/g, '&#039;'); }}
function escapeAttr(value) {{ return escapeHtml(value); }}
function candidateAudit() {{ return 'pass'; }}
function humanReviewPanel() {{ return '<section class="human-review-panel"></section>'; }}
function statusBadge() {{ return ''; }}
function stageDetail() {{ return ''; }}
function keyItem() {{ return ''; }}
function formatDuration() {{ return '—'; }}
function fileUrl() {{ return ''; }}
function bindHumanReviewActions() {{}}
const STATUS_LABELS = {{ success: '成功' }};
eval(renderSource);

const maliciousStem = '\\n  第一行 $AB\\\\parallel CD$。\\n\\n<script>alert(1)</script> & <b>第二行</b>  \\n';
renderOverview({{ job_id: 'q1-prompt', status: 'success', stem_latex: maliciousStem, stages: {{}} }});
const rendered = detailBody.innerHTML;
assert.strictEqual((rendered.match(/class="question-stem"/g) || []).length, 1);
assert.ok(rendered.indexOf('class="question-stem"') < rendered.indexOf('class="candidate-label"'));
assert.ok(rendered.indexOf('class="candidate-label"') < rendered.indexOf('class="detail-preview"'));
assert.ok(rendered.includes('<h3>题干</h3>'));
const bodyMatch = rendered.match(/<([a-z][\\w-]*) class="question-stem-body">([\\s\\S]*?)<\\/\\1>/i);
assert.ok(bodyMatch, 'question stem body must be present');
const visibleText = bodyMatch[2]
  .replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;/g, "'")
  .replace(/&amp;/g, '&');
assert.strictEqual(visibleText, maliciousStem);
assert.ok(!rendered.includes('<script>'));
assert.ok(!rendered.includes('<b>第二行</b>'));

for (const absent of [undefined, null, '', '   \\n\\t']) {{
  renderOverview({{ job_id: 'q1-prompt', status: 'success', stem_latex: absent, stages: {{}} }});
  assert.ok(!detailBody.innerHTML.includes('question-stem'));
  assert.ok(detailBody.innerHTML.trimStart().startsWith('<div class="candidate-label"'));
}}
console.log('ok');
"""
        completed = subprocess.run(["node", "-e", script], text=True, capture_output=True, check=False)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "ok")

    def test_stem_block_wraps_without_fixed_height_or_horizontal_scroll(self) -> None:
        js = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.js").read_text(encoding="utf-8")
        css = (ROOT / "scripts" / "diagram_monitor" / "static" / "monitor.css").read_text(encoding="utf-8")
        html = (ROOT / "scripts" / "diagram_monitor" / "templates" / "index.html").read_text(encoding="utf-8")

        overview_source = js[js.index("function renderOverview"):js.index("function humanReviewPanel")]
        self.assertIn("job.stem_latex", overview_source)
        self.assertNotIn("problem_context", overview_source)
        self.assertNotIn("source_problem_text", overview_source)
        stem_match = re.search(r"(?s)\.question-stem\s*\{([^}]*)\}", css)
        body_match = re.search(r"(?s)\.question-stem-body\s*\{([^}]*)\}", css)
        self.assertIsNotNone(stem_match)
        self.assertIsNotNone(body_match)
        stem_css = stem_match.group(1)
        body_css = body_match.group(1)
        self.assertRegex(stem_css, r"min-width:\s*0")
        self.assertRegex(body_css, r"white-space:\s*pre-wrap")
        self.assertRegex(body_css, r"overflow-wrap:\s*anywhere")
        self.assertRegex(body_css, r"min-width:\s*0")
        for declarations in (stem_css, body_css):
            self.assertNotRegex(declarations, r"(?:^|;)\s*(?:height|max-height|overflow-x)\s*:")
            self.assertNotRegex(declarations, r"(?:^|;)\s*overflow\s*:\s*(?:auto|scroll)")
            self.assertNotRegex(declarations, r"white-space:\s*pre(?:\s|;|$)")

        css_version = re.search(r'monitor\.css\?v=([^"&]+)', html).group(1)
        js_version = re.search(r'monitor\.js\?v=([^"&]+)', html).group(1)
        self.assertEqual(css_version, js_version)

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
const initialPreview = review.candidatePreview({{
  preview_path: 'rendered/prompt.preview.png',
  selected_round: null,
  effective_round: null,
  rounds: [{{ round_index: 0, preview_path: '' }}],
}}, 0);
assert.strictEqual(initialPreview, 'rendered/prompt.preview.png');
const revisionPreview = review.candidatePreview({{
  preview_path: 'rendered/old.preview.png',
  selected_round: 0,
  human_review: {{ status: 'revision_completed', requested_round: 1 }},
  rounds: [
    {{ round_index: 0, preview_path: 'rounds/round_0/preview.png' }},
    {{ round_index: 1, preview_path: '' }},
  ],
}}, 1);
assert.strictEqual(revisionPreview, '');
assert.strictEqual(review.codexTaskBinding({{}}, false), null);
assert.deepStrictEqual(review.codexTaskBinding({{ codex_task_status: 'creating' }}, false), {{
  status: 'creating', label: '正在创建', threadId: ''
}});
const boundTask = review.codexTaskBinding({{
  status: 'revision_failed', codex_task_status: 'created', agent_thread_id: 'thread-exact-019f'
}}, false);
assert.deepStrictEqual(boundTask, {{ status: 'created', label: '已创建', threadId: 'thread-exact-019f' }});
assert.deepStrictEqual(
  review.codexTaskBinding({{ status: 'revision_failed', codex_task_status: 'created', agent_thread_id: 'thread-exact-019f' }}, false),
  boundTask
);
assert.deepStrictEqual(review.codexTaskBinding({{ codex_task_status: 'failed' }}, false), {{
  status: 'failed', label: '创建失败', threadId: ''
}});
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
        job_dir / "request.json",
        {**_canonical_revision_base_request(), "assignment_id": path.name},
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


def _canonical_revision_base_request() -> dict[str, Any]:
    return {
        "schema_version": "diagram-job-request/v2",
        "job_id": "q1-prompt",
        "assignment_id": "reviewable",
        "slot_id": "q1.prompt",
        "variant": "prompt",
        "disclosure_policy": "clean",
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "engine_options": {"seed": 12025, "max_retries": 0},
    }


def _legacy_revision_base_request() -> dict[str, Any]:
    return {
        **_canonical_revision_base_request(),
        "diagram_job_id": "q1-prompt",
        "job_id": None,
        "engine_options": {
            "seed": 22025,
            "wolfram_timeout_s": 45,
            "max_retries": 3,
        },
        "reuse": {"base_job_dir": "canonical/base/job"},
        "wolfram_render_image": False,
        "seed": 12025,
        "wolfram_timeout_s": 30,
        "wolfram_hard_timeout_s": 90,
        "reuse_geometry_from": "legacy/base/prompt",
        "base_job_dir": "legacy/base/job",
        "unknown_legacy_switch": True,
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


class _WorkerQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def put(self, payload: dict[str, Any]) -> None:
        self.messages.append(payload)


@contextmanager
def _monitor_fake_codex_sdk(failure: str):
    capture = SimpleNamespace(thread_starts=0)
    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        full_access = "full_access"

    class ThreadSource:
        user = "user"

    class CodexConfig:
        def __init__(self, **kwargs: object) -> None:
            if failure == "config":
                raise RuntimeError("current-config-failed")

    class SkillInput:
        def __init__(self, *, name: str, path: str) -> None:
            self.name = name
            self.path = path

    class TextInput:
        def __init__(self, text: str) -> None:
            self.text = text

    class FakeThread:
        id = "thread-current"

        def set_name(self, name: str) -> None:
            if failure == "set_name":
                raise RuntimeError("current-name-failed")

        def turn(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("current-turn-failed")

    class Codex:
        def __init__(self, *, config: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def thread_start(self, **kwargs: object) -> FakeThread:
            capture.thread_starts += 1
            if failure == "thread_start":
                raise RuntimeError("current-thread-start-failed")
            return FakeThread()

    empty_type = type("EmptyNotification", (), {})
    sdk = SimpleNamespace(
        ApprovalMode=ApprovalMode,
        Codex=Codex,
        CodexConfig=CodexConfig,
        Sandbox=Sandbox,
        SkillInput=SkillInput,
        TextInput=TextInput,
    )
    generated = SimpleNamespace(
        ItemCompletedNotification=empty_type,
        ThreadSource=ThreadSource,
        ThreadTokenUsageUpdatedNotification=empty_type,
        TurnCompletedNotification=empty_type,
    )
    with patch.dict(
        sys.modules,
        {
            "openai_codex": sdk,
            "openai_codex.generated": SimpleNamespace(v2_all=generated),
            "openai_codex.generated.v2_all": generated,
        },
    ):
        yield capture


def _run_real_worker_with_fake_sdk(
    job_dir: Path,
    request: dict[str, Any],
    *,
    failure: str,
) -> dict[str, Any]:
    queue = _WorkerQueue()
    home = job_dir / ".test-codex-home"
    home.mkdir(exist_ok=True)
    human = request["diagram_request"]["human_revision"]
    with patch.dict("os.environ", {"CODEX_HOME": str(home)}), _monitor_fake_codex_sdk(failure) as capture:
        _codex_agent_worker(
            queue,
            prompt="human revision",
            output_schema={"type": "object"},
            cwd=str(ROOT),
            model="gpt-test",
            codex_bin="codex-test",
            skill_inputs=[],
            out_dir=str(job_dir),
            job_id=request["job_id"],
            review_id=human["review_id"],
            requested_round=human["requested_round"],
        )
    result = [item for item in queue.messages if item.get("kind") == "result"][-1]
    result["thread_start_count"] = capture.thread_starts
    return result


def _write_codex_task_sidecar(job_dir: Path, review_id: str, thread_id: str) -> None:
    _write_json(
        job_dir / "human_reviews" / f"{review_id}.codex-task.json",
        {
            "schema_version": "diagram-codex-task/v1",
            "review_id": review_id,
            "agent_thread_id": thread_id,
            "created_at": "2026-07-14T12:00:00+08:00",
        },
    )


if __name__ == "__main__":
    unittest.main()
