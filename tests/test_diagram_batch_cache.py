from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "scripts" / "diagram_workflow"
sys.path.insert(0, str(WORKFLOW))

from diagram_contracts import (  # noqa: E402
    DiagramBatchJobResult,
    DiagramJob,
    DiagramJobRequest,
    DiagramJobsManifest,
)
from run_diagram_batch import (  # noqa: E402
    _cache_identity,
    _scene_geometry_identity,
    _lookup_terminal_failure,
    _record_terminal_failure,
    run_batch,
    run_one_job,
)


def _renderer_job() -> tuple[DiagramJob, DiagramJobRequest]:
    job = DiagramJob(
        job_id="q1-prompt",
        slot_id="q1.prompt",
        diagram_ref="q1.prompt",
        slot_path="/sections/0/blocks/0/diagram_slot",
        engine="renderer_spec",
        diagram_kind="synthetic_geometry",
        request_path="build/diagram/jobs/q1-prompt/request.json",
        out_dir="build/diagram/jobs/q1-prompt",
        public_image_dir="diagram/jobs/q1-prompt/rendered",
        content_hash="sha256:slot",
    )
    request = DiagramJobRequest(
        job_id="q1-prompt",
        assignment_id="cache-test",
        slot_id="q1.prompt",
        engine="renderer_spec",
        diagram_kind="synthetic_geometry",
        engine_options={
            "renderer_spec": {
                "points": {"A": [0, 0], "B": [1, 0]},
                "segments": [{"from": "A", "to": "B"}],
                "labels": {"A": "A", "B": "B"},
            }
        },
    )
    return job, request


class DiagramBatchCacheTest(unittest.TestCase):
    def test_scene_geometry_identity_ignores_visual_annotation_changes(self) -> None:
        first = {
            "engine": "geometric_scene",
            "diagram_kind": "synthetic_geometry",
            "engine_options": {
                "seed": 7,
                "scene_payload": {
                    "scene_code": "GeometricScene[{A,B},{A=={0,0},B=={1,0}}]",
                    "points": ["A", "B"],
                    "diagram_spec": {
                        "annotations": [{"target": ["A", "B"], "text": "2份", "color": "blue"}]
                    },
                },
            },
        }
        second = json.loads(json.dumps(first))
        second["engine_options"]["scene_payload"]["diagram_spec"]["annotations"][0].update(
            {"color": "green", "normal_offset_cm": 0.22}
        )
        self.assertEqual(_scene_geometry_identity(first), _scene_geometry_identity(second))
        second["engine_options"]["scene_payload"]["scene_code"] = "GeometricScene[{A,B},{A=={0,0},B=={2,0}}]"
        self.assertNotEqual(_scene_geometry_identity(first), _scene_geometry_identity(second))

    def test_second_identical_run_uses_cache_without_workflow_or_renderer(self) -> None:
        job, request = _renderer_job()
        calls = {"workflow": 0, "renderer": 0}

        def workflow_side_effect(
            request: object,
            request_path: Path,
            job_dir: Path,
            build_dir: Path,
        ) -> str:
            del request, request_path, build_dir
            calls["workflow"] += 1
            (job_dir / "final_renderer_spec.json").write_text(
                json.dumps({"schema_version": "geometry-render-spec/v1", "status": "ready"}),
                encoding="utf-8",
            )
            (job_dir / "workflow_result.json").write_text(
                json.dumps({"status": "ok", "final_renderer_spec": "final_renderer_spec.json"}),
                encoding="utf-8",
            )
            return "ok"

        def renderer_side_effect(
            spec_path: Path,
            job_dir: Path,
            variant: str,
        ) -> tuple[str, str, str]:
            del spec_path
            calls["renderer"] += 1
            rendered = job_dir / "rendered"
            rendered.mkdir(parents=True, exist_ok=True)
            fragment = rendered / f"{variant}.fragment.tex"
            fragment.write_text("\\draw (0,0)--(1,0);", encoding="utf-8")
            (job_dir / "renderer_result.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "tikz_fragment_path": f"rendered/{variant}.fragment.tex",
                        "tikz_source_path": f"rendered/{variant}.fragment.tex",
                    }
                ),
                encoding="utf-8",
            )
            return "ok", f"rendered/{variant}.fragment.tex", f"rendered/{variant}.fragment.tex"

        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_diagram_batch._run_workflow_in_process",
            side_effect=workflow_side_effect,
        ) as workflow_mock, patch(
            "run_diagram_batch._run_tikz_renderer",
            side_effect=renderer_side_effect,
        ) as renderer_mock:
            artifact_dir = Path(tmp)
            first = run_one_job(job, request, artifact_dir, sys.executable, False)
            second = run_one_job(job, request, artifact_dir, sys.executable, False)

            cached_fragment = (
                artifact_dir
                / "build"
                / "diagram"
                / "cache"
                / first.cache_key
                / "artifacts"
                / "rendered"
                / "prompt.fragment.tex"
            )
            cached_fragment.write_text("corrupt", encoding="utf-8")
            third = run_one_job(job, request, artifact_dir, sys.executable, False)

            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            self.assertFalse(third.cache_hit)
            self.assertEqual(first.cache_key, second.cache_key)
            self.assertEqual(calls, {"workflow": 2, "renderer": 2})
            self.assertEqual(workflow_mock.call_count, 2)
            self.assertEqual(renderer_mock.call_count, 2)
            events = (
                artifact_dir
                / "build"
                / "diagram"
                / "jobs"
                / job.job_id
                / "workflow_events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn('"event": "cache.hit"', events)

    def test_base_geometry_change_invalidates_solution_cache_key(self) -> None:
        job = DiagramJob(
            job_id="q1-solution",
            slot_id="q1.solution",
            diagram_ref="q1.solution",
            slot_path="/sections/0/blocks/0/answer_space/diagram_slot",
            variant="solution",
            disclosure_policy="annotated",
            request_path="build/diagram/jobs/q1-solution/request.json",
            out_dir="build/diagram/jobs/q1-solution",
            public_image_dir="diagram/jobs/q1-solution/rendered",
            depends_on=["q1-prompt"],
            reuse_geometry_from="q1-prompt",
        )
        request = DiagramJobRequest(
            job_id="q1-solution",
            assignment_id="cache-test",
            slot_id="q1.solution",
            variant="solution",
            disclosure_policy="annotated",
            reuse={"reuse_geometry_from": "q1-prompt"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            base_spec = (
                artifact_dir
                / "build"
                / "diagram"
                / "jobs"
                / "q1-prompt"
                / "final_renderer_spec.json"
            )
            base_spec.parent.mkdir(parents=True)
            base_spec.write_text('{"points":{"A":[0,0]}}', encoding="utf-8")
            first_key, first_identity = _cache_identity(job, request, artifact_dir)
            base_spec.write_text('{"points":{"A":[1,0]}}', encoding="utf-8")
            second_key, second_identity = _cache_identity(job, request, artifact_dir)

        self.assertNotEqual(first_key, second_key)
        self.assertNotEqual(
            first_identity["base_geometry_hash"],
            second_identity["base_geometry_hash"],
        )

    def test_filtered_solution_run_accepts_durable_finalized_prompt_dependency(self) -> None:
        prompt = DiagramJob(
            job_id="q1-prompt",
            slot_id="q1.prompt",
            diagram_ref="q1.prompt",
            slot_path="/sections/0/blocks/0/diagram_slot",
            request_path="build/diagram/jobs/q1-prompt/request.json",
            out_dir="build/diagram/jobs/q1-prompt",
            public_image_dir="diagram/jobs/q1-prompt/rendered",
        )
        solution = DiagramJob(
            job_id="q1-solution",
            slot_id="q1.solution",
            diagram_ref="q1.solution",
            slot_path="/sections/0/blocks/0/answer_space/diagram_slot",
            variant="solution",
            disclosure_policy="annotated",
            request_path="build/diagram/jobs/q1-solution/request.json",
            out_dir="build/diagram/jobs/q1-solution",
            public_image_dir="diagram/jobs/q1-solution/rendered",
            depends_on=["q1-prompt"],
            reuse_geometry_from="q1-prompt",
        )
        manifest = DiagramJobsManifest(
            assignment_id="filtered-cache-test",
            source_assignment="assignment.plan.yaml",
            jobs=[prompt, solution],
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            base_dir = artifact_dir / prompt.out_dir
            base_dir.mkdir(parents=True)
            (base_dir / "workflow_result.json").write_text(
                '{"status":"ok"}', encoding="utf-8"
            )
            (base_dir / "final_renderer_spec.json").write_text(
                '{"status":"ready"}', encoding="utf-8"
            )
            with patch(
                "run_diagram_batch.run_one_job",
                return_value=DiagramBatchJobResult(
                    job_id="q1-solution",
                    slot_id="q1.solution",
                    variant="solution",
                    status="ok",
                    workflow_status="ok",
                    renderer_status="ok",
                ),
            ) as run_mock:
                report = run_batch(
                    manifest,
                    artifact_dir,
                    sys.executable,
                    max_workers=1,
                    dry_run=False,
                    jobs_filter={"q1-solution"},
                    plan_data=None,
                )

        self.assertEqual(report.ok_count, 1)
        self.assertEqual(report.failed_count, 0)
        run_mock.assert_called_once()

    # -- terminal-failure ledger (P3) --------------------------------------

    def _failing_workflow(self, classification: dict, status: str = "failed"):
        """A workflow double that writes a classified failed workflow_result."""
        calls = {"count": 0}

        def side_effect(request, request_path, job_dir, build_dir):  # type: ignore[no-untyped-def]
            del request, request_path, build_dir
            calls["count"] += 1
            (Path(job_dir) / "workflow_result.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "fail_type": "deterministic_audit_failed",
                        "failed_stage": "audit",
                        "failure_classification": classification,
                    }
                ),
                encoding="utf-8",
            )
            return status

        return side_effect, calls

    def _single_job_manifest(self) -> DiagramJobsManifest:
        job, _ = _renderer_job()
        return DiagramJobsManifest(
            assignment_id="ledger-test",
            source_assignment="assignment.plan.yaml",
            jobs=[job],
        )

    def test_semantic_terminal_failure_is_cached_and_short_circuits(self) -> None:
        semantic = {
            "failure_class": "semantic_contract",
            "terminal": True,
            "retry_allowed": False,
            "issues": ["prompt_disallowed_marker:('right_angle','E',('A','F'))"],
        }
        side_effect, calls = self._failing_workflow(semantic)
        manifest = self._single_job_manifest()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_diagram_batch._run_workflow_in_process", side_effect=side_effect
        ):
            artifact_dir = Path(tmp)
            first = run_batch(manifest, artifact_dir, sys.executable, 1, False, None, None)
            self.assertEqual(first.failed_count, 1)
            self.assertEqual(first.jobs[0].status, "workflow_failed")
            self.assertEqual(calls["count"], 1)

            # Ledger now holds a terminal failure for this request hash.
            second = run_batch(manifest, artifact_dir, sys.executable, 1, False, None, None)
            self.assertEqual(second.failed_count, 1)
            self.assertEqual(second.jobs[0].status, "cached_terminal_failure")
            # The scene-authoring workflow must NOT be called again.
            self.assertEqual(calls["count"], 1)

    def test_force_job_overrides_cached_terminal_failure(self) -> None:
        semantic = {
            "failure_class": "semantic_contract",
            "terminal": True,
            "retry_allowed": False,
            "issues": ["prompt_disallowed_marker:x"],
        }
        side_effect, calls = self._failing_workflow(semantic)
        manifest = self._single_job_manifest()
        job, _ = _renderer_job()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_diagram_batch._run_workflow_in_process", side_effect=side_effect
        ):
            artifact_dir = Path(tmp)
            run_batch(manifest, artifact_dir, sys.executable, 1, False, None, None)
            self.assertEqual(calls["count"], 1)

            forced = run_batch(
                manifest, artifact_dir, sys.executable, 1, False, None, None,
                force_jobs={job.job_id},
            )
            # force bypasses the cached terminal failure -> workflow called again.
            self.assertEqual(forced.jobs[0].status, "workflow_failed")
            self.assertEqual(calls["count"], 2)

    def test_syntax_failure_is_not_cached_so_it_reruns(self) -> None:
        syntax = {
            "failure_class": "syntax_serialization",
            "terminal": False,
            "retry_allowed": True,
            "issues": ["invalid_point_label: aggregate"],
        }
        side_effect, calls = self._failing_workflow(syntax)
        manifest = self._single_job_manifest()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_diagram_batch._run_workflow_in_process", side_effect=side_effect
        ):
            artifact_dir = Path(tmp)
            run_batch(manifest, artifact_dir, sys.executable, 1, False, None, None)
            run_batch(manifest, artifact_dir, sys.executable, 1, False, None, None)
            # Non-terminal failures are not cached, so both runs invoke the workflow.
            self.assertEqual(calls["count"], 2)

    def test_record_then_clear_terminal_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = Path(tmp) / "build" / "diagram"
            job_dir = build_dir / "jobs" / "x"
            job_dir.mkdir(parents=True)
            (job_dir / "workflow_result.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "fail_type": "deterministic_audit_failed",
                        "failed_stage": "audit",
                        "failure_classification": {
                            "failure_class": "semantic_contract",
                            "terminal": True,
                            "issues": ["prompt_disallowed_marker:y"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            _record_terminal_failure(build_dir, "x", "KEY", "workflow_failed", job_dir)
            self.assertIsNotNone(_lookup_terminal_failure(build_dir, "KEY"))
            # Re-recording produces a stable fingerprint for identical input.
            rec = _lookup_terminal_failure(build_dir, "KEY")
            self.assertEqual(rec["failure_class"], "semantic_contract")
            self.assertTrue(rec["fingerprint"])


if __name__ == "__main__":
    unittest.main()
