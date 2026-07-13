from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
