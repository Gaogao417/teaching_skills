from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from diagram_contracts import DiagramJob, DiagramJobRequest, DiagramJobsManifest  # noqa: E402
from run_diagram_batch import build_request, run_one_job  # noqa: E402


def _manifest(job_id: str = "q1-prompt", slot_id: str = "q1.prompt", engine: str = "renderer_spec") -> tuple[DiagramJobsManifest, dict]:
    diagram_kind = "coordinate_geometry" if engine != "renderer_spec" else "synthetic_geometry"
    plan_data = {
        "meta": {"title": "inline batch", "assignment_id": "inline-batch"},
        "sections": [
            {
                "blocks": [
                    {
                        "id": "q1",
                        "stem_latex": r"如图，$AB=AC$。",
                        "diagram_slot": {
                            "slot_id": slot_id,
                            "engine": engine,
                            "diagram_kind": diagram_kind,
                            "placement": "diagram_col",
                            "layout_role": "question_sidecar",
                            "semantic_constraints": {"given_objects": ["A", "B"]},
                        },
                    }
                ]
            }
        ],
    }
    manifest = DiagramJobsManifest(
        assignment_id="inline-batch",
        source_assignment="assignment.plan.yaml",
        jobs=[
            DiagramJob(
                job_id=job_id,
                slot_id=slot_id,
                diagram_ref=slot_id,
                slot_path="/sections/0/blocks/0/diagram_slot",
                problem_id="q1",
                engine=engine,
                diagram_kind=diagram_kind,
                request_path=f"build/diagram/jobs/{job_id}/request.json",
                out_dir=f"build/diagram/jobs/{job_id}",
                public_image_dir=f"diagram/jobs/{job_id}/rendered",
            )
        ],
    )
    return manifest, plan_data


class DiagramBatchInlineTest(unittest.TestCase):
    """Verify renderer_spec and coordinate_renderer jobs run in-process and
    produce workflow_result.json, renderer_result.json and a TikZ fragment
    without spawning a Python subprocess for the workflow/renderer stages."""

    def test_renderer_spec_job_produces_full_artifact_set(self) -> None:
        manifest, plan_data = _manifest(engine="renderer_spec")
        # Inject a deterministic renderer_spec so the in-process workflow can
        # build a GeometryRenderSpec without any LLM.
        plan_data["sections"][0]["blocks"][0]["diagram_slot"]["engine_options"] = {
            "renderer_spec": {
                "points": {"A": [0, 0], "B": [1, 0]},
                "segments": [{"from": "A", "to": "B"}],
                "labels": {"A": "A", "B": "B"},
            }
        }
        request = build_request(manifest.jobs[0], manifest, plan_data)

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            with patch("run_diagram_batch._run_workflow_subprocess") as workflow_subprocess:
                workflow_subprocess.side_effect = AssertionError("inline route spawned workflow subprocess")
                result = run_one_job(
                    manifest.jobs[0],
                    request,
                    artifact_dir,
                    sys.executable,
                    dry_run=False,
                )
                workflow_subprocess.assert_not_called()
            job_dir = artifact_dir / "build" / "diagram" / "jobs" / "q1-prompt"

            self.assertEqual(result.status, "ok", result.failure_reason or "")
            for name in ("request.json", "workflow_result.json",
                         "final_renderer_spec.json", "renderer_result.json"):
                self.assertTrue((job_dir / name).exists(), f"missing {name}")

            wf = json.loads((job_dir / "workflow_result.json").read_text(encoding="utf-8"))
            self.assertEqual(wf["status"], "ok")
            rr = json.loads((job_dir / "renderer_result.json").read_text(encoding="utf-8"))
            self.assertEqual(rr["status"], "ok")
            fragment = job_dir / rr["tikz_fragment_path"]
            self.assertTrue(fragment.exists() and fragment.stat().st_size > 0)

    def test_coordinate_renderer_job_produces_tikz_in_process(self) -> None:
        manifest, plan_data = _manifest(engine="coordinate_renderer")
        slot = plan_data["sections"][0]["blocks"][0]["diagram_slot"]
        slot["analytic_requirements"] = {
            "coordinate_ir": {
                "viewport": {"x_min": -2, "x_max": 3, "y_min": -2, "y_max": 3, "preserve_aspect": True},
                "axes": {"x": True, "y": True, "grid": False, "show_ticks": True},
                "objects": [
                    {
                        "type": "function_curve",
                        "id": "line",
                        "variable": "x",
                        "expression_latex": "x",
                        "expression_wl": "x",
                        "domain_segments": [{"min": -2, "max": 3}],
                        "label": "$y=x$",
                        "sample_count": 80,
                    }
                ],
            }
        }
        request = build_request(manifest.jobs[0], manifest, plan_data)

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            with patch("run_diagram_batch._run_workflow_subprocess") as workflow_subprocess:
                workflow_subprocess.side_effect = AssertionError("inline route spawned workflow subprocess")
                result = run_one_job(
                    manifest.jobs[0],
                    request,
                    artifact_dir,
                    sys.executable,
                    dry_run=False,
                )
                workflow_subprocess.assert_not_called()
            job_dir = artifact_dir / "build" / "diagram" / "jobs" / "q1-prompt"

            self.assertEqual(result.status, "ok", result.failure_reason or "")
            wf = json.loads((job_dir / "workflow_result.json").read_text(encoding="utf-8"))
            self.assertEqual(wf["status"], "ok")
            # coordinate_renderer uses the local sampler, so Wolfram is not used.
            self.assertFalse(wf["wolfram"]["success"])
            rr = json.loads((job_dir / "renderer_result.json").read_text(encoding="utf-8"))
            self.assertEqual(rr["status"], "ok")
            fragment = job_dir / rr["tikz_fragment_path"]
            self.assertTrue(fragment.exists() and fragment.stat().st_size > 0)
            self.assertIn(r"\begin{axis}", fragment.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
