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
from run_diagram_batch import _cache_identity, run_batch, run_one_job  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
