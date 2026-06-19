from __future__ import annotations

import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"))

from analytic_diagram_workflow import run_analytic_workflow, sanitize_wl_expression  # noqa: E402
from check_diagram_gate import _check_analytic_renderer_specs  # noqa: E402
from diagram_contracts import (  # noqa: E402
    DiagramAnalyticRequirements,
    DiagramArtifact,
    DiagramArtifactsManifest,
    DiagramJob,
    DiagramJobsManifest,
    DiagramJobRequest,
)
from render_geometry_spec import SvgCoordinateRenderer, render_geometry_spec  # noqa: E402
from runtime import resolve_wolfram_kernel  # noqa: E402


def wolfram_available() -> bool:
    try:
        import wolframclient  # noqa: F401

        resolve_wolfram_kernel()
    except Exception:
        return False
    return True


class AnalyticDiagramWorkflowTest(unittest.TestCase):
    def test_contract_supports_wolfram_client_and_plot_alias(self) -> None:
        request = DiagramJobRequest(
            job_id="f1-prompt",
            assignment_id="contract",
            slot_id="f1.prompt",
            engine="wolfram_client",
            diagram_kind="function_graph",
        )
        self.assertEqual(request.engine.value, "wolfram_client")

        plot_options = DiagramAnalyticRequirements(
            wolfram_plot_options={"plot_range_padding": "Scaled[0.04]"}
        )
        self.assertEqual(
            plot_options.wolfram_client_options["plot_range_padding"],
            "Scaled[0.04]",
        )

    def test_expression_sanitizer_allows_basic_math_and_rejects_side_effects(self) -> None:
        self.assertEqual(sanitize_wl_expression("2*x - 1"), "2*x - 1")
        self.assertEqual(sanitize_wl_expression("Sin[x] + Sqrt[x^2]"), "Sin[x] + Sqrt[x^2]")
        with self.assertRaises(ValueError):
            sanitize_wl_expression("RunProcess[\"date\"]")

    def test_invalid_request_still_writes_failed_workflow_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "schema_version": "diagram-job-request/v2",
                        "job_id": "bad-request",
                        "assignment_id": "bad",
                        "slot_id": "bad.prompt",
                        "engine": "wolfram_client",
                        "diagram_kind": "function_graph",
                        "required": True,
                    }
                ),
                encoding="utf-8",
            )
            job_dir = root / "job"
            result = run_analytic_workflow(request_path, job_dir)

            self.assertEqual(result["status"], "failed")
            self.assertTrue((job_dir / "workflow_result.json").exists())
            self.assertIn("Extra inputs", result["message"])

    @unittest.skip("TikZ-only renderer will replace the legacy SVG/PNG renderer")
    def test_coordinate_renderer_outputs_function_objects_and_nonempty_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec = {
                "schema_version": "geometry-render-spec/v1",
                "job_id": "renderer-coordinate",
                "variant": "prompt",
                "disclosure_policy": "clean",
                "type": "function_graph",
                "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
                "axes": {"x": True, "y": True, "grid": True, "show_ticks": True},
                "functions": [{"id": "f", "variable": "x", "expression_wl": "2*x - 1"}],
                "samples": {"f": [[-2, -5], [0, -1], [2, 3], [6, 11]]},
                "objects": [
                    {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"},
                    {"type": "line", "id": "h", "equation": "y=0"},
                    {"type": "line", "id": "v", "equation": "x=2", "style": {"dash": "5 4"}},
                    {"type": "circle", "id": "c", "center": [2, 3], "radius": 2},
                    {"type": "polyline", "id": "p", "points": [[0, 0], [2, 3], [4, 0]]},
                    {
                        "type": "polygon",
                        "id": "poly",
                        "points": [[1, 1], [2, 3], [3, 1]],
                        "style": {"fill": "#fef3c7"},
                    },
                ],
            }
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            result = render_geometry_spec(spec_path, out_dir, width=720, height=520, size=1024)

            self.assertEqual(result["status"], "ok")
            image_path = out_dir / result["image_path"]
            svg_path = out_dir / result["preview_svg"]
            self.assertTrue(image_path.exists())
            self.assertGreater(image_path.stat().st_size, 0)
            self.assertIn("polyline", svg_path.read_text(encoding="utf-8"))

    def test_coordinate_renderer_preserves_equal_axis_units(self) -> None:
        renderer = SvgCoordinateRenderer(
            {
                "type": "coordinate_geometry",
                "viewport": {
                    "x_min": -2,
                    "x_max": 6,
                    "y_min": -6,
                    "y_max": 12,
                    "preserve_aspect": True,
                },
            },
            width=720,
            height=520,
        )
        origin = renderer.screen_xy(0, 0)
        one_x = renderer.screen_xy(1, 0)
        one_y = renderer.screen_xy(0, 1)

        self.assertAlmostEqual(one_x[0] - origin[0], origin[1] - one_y[1])
        self.assertEqual(renderer.scale_x, renderer.scale_y)

    def test_gate_blocks_analytic_spec_without_function_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            spec_path = artifact_dir / "build" / "diagram" / "jobs" / "f1-prompt" / "final_renderer_spec.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "type": "function_graph",
                        "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
                        "functions": [{"id": "f", "expression_wl": "2*x - 1"}],
                        "samples": {},
                    }
                ),
                encoding="utf-8",
            )
            jobs = DiagramJobsManifest(
                assignment_id="gate-analytic",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="f1-prompt",
                        slot_id="f1.prompt",
                        diagram_ref="f1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/f1-prompt/request.json",
                        out_dir="build/diagram/jobs/f1-prompt",
                        public_image_dir="diagram/jobs/f1-prompt/rendered",
                        engine="wolfram_client",
                        diagram_kind="function_graph",
                    )
                ],
            )
            artifacts = DiagramArtifactsManifest(
                assignment_id="gate-analytic",
                source_jobs="build/diagram/diagram_jobs.json",
                artifacts={
                    "f1.prompt": DiagramArtifact(
                        slot_id="f1.prompt",
                        job_id="f1-prompt",
                        status="ok",
                        tikz_fragment=r"\begin{tikzpicture}\draw (0,0) -- (1,0);\end{tikzpicture}",
                        hash="sha256:abc",
                        final_renderer_spec="build/diagram/jobs/f1-prompt/final_renderer_spec.json",
                        bindable=True,
                    )
                },
            )

            checks = _check_analytic_renderer_specs(jobs, artifacts, artifact_dir)
            self.assertEqual(checks[0].status, "block")
            self.assertIn("has no samples", checks[0].message)

            data = json.loads(spec_path.read_text(encoding="utf-8"))
            data["samples"] = {"f": [[-2, -5], [0, -1], [2, 3]]}
            spec_path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(_check_analytic_renderer_specs(jobs, artifacts, artifact_dir), [])

    @unittest.skipUnless(wolfram_available(), "Wolfram kernel or wolframclient is unavailable")
    def test_wolfram_client_workflow_samples_roots_intersections_and_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request = {
                "schema_version": "diagram-job-request/v2",
                "job_id": "analytic-e2e-prompt",
                "assignment_id": "analytic-e2e",
                "problem_id": "q1",
                "slot_id": "q1.prompt",
                "variant": "prompt",
                "disclosure_policy": "clean",
                "engine": "wolfram_client",
                "diagram_kind": "function_graph",
                "teaching_intent": "practice_prompt",
                "analytic_requirements": {
                    "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
                    "axes": {"x": True, "y": True, "grid": True, "show_ticks": True},
                    "functions": [
                        {
                            "id": "f",
                            "variable": "x",
                            "expression_wl": "2*x - 1",
                            "domain": {"min": -2, "max": 6},
                            "sample_count": 16,
                        }
                    ],
                    "objects": [
                        {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"},
                        {"type": "line", "id": "l1", "equation": "y=3"},
                        {"type": "circle", "id": "c1", "center": [2, 3], "radius": 3},
                        {"type": "intersection", "id": "I", "of": ["l1", "c1"]},
                        {"type": "intersection", "id": "J", "of": ["f", "l1"]},
                        {"type": "zero", "id": "Z", "of": "f"},
                    ],
                },
            }
            request_path.write_text(json.dumps(request), encoding="utf-8")

            job_dir = root / "job"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                result = run_analytic_workflow(request_path, job_dir)
            self.assertEqual(result["status"], "ok")

            spec = json.loads((job_dir / "final_renderer_spec.json").read_text(encoding="utf-8"))
            self.assertEqual(len(spec["samples"]["f"]), 16)
            computed = {obj["id"]: obj for obj in spec["objects"] if obj.get("computed")}
            self.assertIn("I1", computed)
            self.assertIn("I2", computed)
            self.assertEqual(computed["J"]["x"], 2.0)
            self.assertEqual(computed["Z"]["x"], 0.5)

            render_result = render_geometry_spec(job_dir / "final_renderer_spec.json", job_dir, 720, 520, 1024)
            self.assertEqual(render_result["status"], "ok")
            self.assertTrue((job_dir / render_result["image_path"]).exists())


if __name__ == "__main__":
    unittest.main()
