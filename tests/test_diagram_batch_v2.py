from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_contracts import DiagramJob, DiagramJobsManifest  # noqa: E402
from run_diagram_batch import build_request, run_one_job  # noqa: E402


class DiagramBatchV2Test(unittest.TestCase):
    def _manifest(self) -> DiagramJobsManifest:
        return DiagramJobsManifest(
            assignment_id="synthetic-v2",
            source_assignment="assignment.plan.yaml",
            jobs=[
                DiagramJob(
                    job_id="q1-prompt",
                    slot_id="q1.prompt",
                    diagram_ref="q1.prompt",
                    slot_path="/sections/0/blocks/0/diagram_slot",
                    problem_id="q1",
                    request_path="build/diagram/jobs/q1-prompt/request.json",
                    out_dir="build/diagram/jobs/q1-prompt",
                    public_image_dir="diagram/jobs/q1-prompt/rendered",
                )
            ],
        )

    def _plan_data(self) -> dict:
        return {
            "meta": {"title": "等腰三角形", "assignment_id": "synthetic-v2"},
            "sections": [
                {
                    "blocks": [
                        {
                            "id": "q1",
                            "stem_latex": r"如图，$AB=AC$，点 $D$ 在 $BC$ 上。",
                            "diagram_slot": {
                                "slot_id": "q1.prompt",
                                "placement": "diagram_col",
                                "layout_role": "question_sidecar",
                                "semantic_constraints": {
                                    "given_objects": ["A", "B", "C", "D"],
                                    "given_constraints": ["AB=AC", "D on BC"],
                                    "clean_forbidden": ["不要画高 AH"],
                                },
                                "visual_requirements": {"caption": "原题图"},
                                "engine_options": {
                                    "seed": 7,
                                    "max_retries": 1,
                                    "model_config": {"text_model": "test-model"},
                                },
                            },
                        }
                    ]
                }
            ],
        }

    def test_build_request_preserves_slot_semantics(self) -> None:
        manifest = self._manifest()
        request = build_request(manifest.jobs[0], manifest, self._plan_data())

        self.assertEqual(request.schema_version, "diagram-job-request/v2")
        self.assertEqual(request.problem_context.stem_latex, r"如图，$AB=AC$，点 $D$ 在 $BC$ 上。")
        self.assertEqual(request.semantic_constraints.given_objects, ["A", "B", "C", "D"])
        self.assertEqual(request.semantic_constraints.given_constraints, ["AB=AC", "D on BC"])
        self.assertEqual(request.semantic_constraints.clean_forbidden, ["不要画高 AH"])
        self.assertEqual(request.visual_requirements.caption, "原题图")
        self.assertEqual(request.engine_options.seed, 7)
        self.assertEqual(request.engine_options.max_retries, 1)
        self.assertEqual(request.engine_options.engine_model_config["text_model"], "test-model")

    def test_build_request_preserves_function_graph_analytic_requirements(self) -> None:
        manifest = self._manifest()
        job_payload = manifest.jobs[0].model_dump(mode="json")
        job_payload["engine"] = "wolfram_client"
        job_payload["diagram_kind"] = "function_graph"
        manifest.jobs[0] = DiagramJob(**job_payload)

        plan_data = self._plan_data()
        slot = plan_data["sections"][0]["blocks"][0]["diagram_slot"]
        slot["engine"] = "wolfram_client"
        slot["diagram_kind"] = "function_graph"
        slot["analytic_requirements"] = {
            "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
            "axes": {"x": True, "y": True, "grid": True, "show_ticks": True},
            "functions": [
                {
                    "id": "f",
                    "variable": "x",
                    "expression_wl": "2*x - 1",
                    "domain": {"min": -2, "max": 6},
                    "sample_count": 32,
                }
            ],
            "objects": [
                {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"},
                {"type": "line", "id": "l1", "equation": "y=0"},
            ],
            "wolfram_client_options": {"sample_method": "table"},
        }

        request = build_request(manifest.jobs[0], manifest, plan_data)
        payload = request.model_dump(mode="json")

        self.assertEqual(payload["engine"], "wolfram_client")
        self.assertEqual(payload["diagram_kind"], "function_graph")
        analytic = payload["analytic_requirements"]
        self.assertEqual(analytic["viewport"]["x_min"], -2.0)
        self.assertEqual(analytic["viewport"]["y_max"], 12.0)
        self.assertEqual(analytic["functions"][0]["expression_wl"], "2*x - 1")
        self.assertEqual(analytic["functions"][0]["sample_count"], 32)
        self.assertEqual(analytic["objects"][1]["equation"], "y=0")
        self.assertEqual(analytic["wolfram_client_options"]["sample_method"], "table")

    def test_dry_run_writes_only_v2_request(self) -> None:
        manifest = self._manifest()
        job = manifest.jobs[0]
        request = build_request(job, manifest, self._plan_data())

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            result = run_one_job(
                job,
                request,
                artifact_dir,
                sys.executable,
                dry_run=True,
            )
            job_dir = artifact_dir / "build" / "diagram" / "jobs" / "q1-prompt"
            request_path = job_dir / "request.json"

            self.assertEqual(result.status, "dry_run")
            self.assertTrue(request_path.exists())
            self.assertFalse((job_dir / ("diagram" + "-request.json")).exists())
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "diagram-job-request/v2")
            self.assertEqual(payload["semantic_constraints"]["given_objects"], ["A", "B", "C", "D"])


if __name__ == "__main__":
    unittest.main()
