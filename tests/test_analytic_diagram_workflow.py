from __future__ import annotations

import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"))

from analytic_diagram_workflow import run_analytic_workflow, sanitize_wl_expression  # noqa: E402
from check_diagram_gate import _check_analytic_renderer_specs  # noqa: E402
from diagram_contracts import (  # noqa: E402
    DiagramAnalyticRequirements,
    DiagramJob,
    DiagramJobsManifest,
    DiagramJobRequest,
    RendererBinding,
    RendererBindingManifest,
)
from render_geometry_spec import render_geometry_spec  # noqa: E402
from runtime import resolve_wolfram_kernel  # noqa: E402
from tikz_renderer.toolchain import PreviewResult  # noqa: E402


def wolfram_available() -> bool:
    try:
        import wolframclient  # noqa: F401

        resolve_wolfram_kernel()
    except Exception:
        return False
    return True


class FakeAnalyticKernel:
    def __init__(self, kernel_path: str | None = None):
        self.kernel_path = kernel_path or "fake-wolfram"

    def __enter__(self) -> FakeAnalyticKernel:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def sample_function(
        self,
        expression: str,
        variable: str,
        x_min: float,
        x_max: float,
        sample_count: int,
    ) -> list[tuple[float, float]]:
        del variable
        step = (x_max - x_min) / (sample_count - 1)
        xs = [x_min + step * index for index in range(sample_count)]
        if expression == "1/x":
            return [(x, 1 / x) for x in xs]
        return [(x, 2 * x - 1) for x in xs]

    def solve_points(self, equations: list[str], variables: tuple[str, str] = ("x", "y")) -> list[tuple[float, float]]:
        del variables
        if any(eq == "y == 0" for eq in equations):
            return [(0.5, 0.0)]
        return [(2.0, 3.0)]


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

    def test_coordinate_renderer_with_explicit_objects_does_not_require_wolfram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request = {
                "schema_version": "diagram-job-request/v2",
                "job_id": "coord-explicit-prompt",
                "assignment_id": "coord-explicit",
                "slot_id": "coord.prompt",
                "variant": "prompt",
                "disclosure_policy": "clean",
                "engine": "coordinate_renderer",
                "diagram_kind": "coordinate_geometry",
                "analytic_requirements": {
                    "viewport": {"x_min": -1, "x_max": 5, "y_min": -1, "y_max": 4},
                    "axes": {"x": False, "y": False, "grid": False, "show_ticks": False},
                    "objects": [
                        {"type": "point", "id": "A", "x": 0, "y": 0, "label": "A"},
                        {"type": "point", "id": "B", "x": 4, "y": 0, "label": "B"},
                        {"type": "polyline", "id": "AB", "points": ["A", "B"]},
                    ],
                },
            }
            request_path.write_text(json.dumps(request), encoding="utf-8")

            job_dir = root / "job"
            with patch("analytic_diagram_workflow.WolframAnalyticKernel", side_effect=AssertionError("wolfram should not run")):
                result = run_analytic_workflow(request_path, job_dir)

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["wolfram"]["success"])
            spec = json.loads((job_dir / "final_renderer_spec.json").read_text(encoding="utf-8"))
            self.assertFalse(spec["diagnostics"]["wolfram_used"])
            self.assertEqual(spec["objects"][0]["id"], "A")
            events = (job_dir / "workflow_events.jsonl").read_text(encoding="utf-8")
            self.assertIn("wolfram_skipped", events)

    def test_typed_coordinate_ir_generates_segmented_function_samples_and_computed_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request = {
                "schema_version": "diagram-job-request/v2",
                "job_id": "coord-ir-prompt",
                "assignment_id": "coord-ir",
                "slot_id": "coord.prompt",
                "variant": "prompt",
                "disclosure_policy": "clean",
                "engine": "wolfram_client",
                "diagram_kind": "coordinate_geometry",
                "analytic_requirements": {
                    "coordinate_ir": {
                        "viewport": {"x_min": -4, "x_max": 4, "y_min": -5, "y_max": 5},
                        "axes": {"x": True, "y": True, "grid": True, "show_ticks": True},
                        "objects": [
                            {
                                "type": "function_curve",
                                "id": "f",
                                "expression_wl": "2*x - 1",
                                "domain_segments": [{"min": -2, "max": 6}],
                                "sample_count": 80,
                                "label": "y=2x-1",
                            },
                            {
                                "type": "function_curve",
                                "id": "g",
                                "expression_wl": "1/x",
                                "domain_segments": [
                                    {"min": -4, "max": -0.5},
                                    {"min": 0.5, "max": 4},
                                ],
                                "sample_count": 80,
                            },
                            {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"},
                            {"type": "line", "id": "l1", "equation": "y=3"},
                            {"type": "derived_point", "id": "J", "derive": "intersection", "of": ["f", "l1"]},
                            {"type": "derived_point", "id": "Z", "derive": "zero", "of": "f"},
                            {"type": "projection_guide", "id": "J_x", "point": "J", "to_axis": "x"},
                            {"type": "projection_guide", "id": "J_y", "point": "J", "to_axis": "y"},
                        ],
                    }
                },
            }
            request_path.write_text(json.dumps(request), encoding="utf-8")

            job_dir = root / "job"
            with patch("analytic_diagram_workflow.WolframAnalyticKernel", FakeAnalyticKernel):
                result = run_analytic_workflow(request_path, job_dir)

            self.assertEqual(result["status"], "ok")
            spec = json.loads((job_dir / "final_renderer_spec.json").read_text(encoding="utf-8"))
            self.assertEqual([func["id"] for func in spec["functions"]], ["f", "g__seg1", "g__seg2"])
            self.assertEqual(set(spec["samples"]), {"f", "g__seg1", "g__seg2"})
            self.assertNotIn("g", spec["samples"])
            self.assertEqual(spec["diagnostics"]["coordinate_ir_has_function"], True)
            computed = {obj["id"]: obj for obj in spec["objects"] if obj.get("computed")}
            self.assertEqual(computed["J"]["x"], 2.0)
            self.assertEqual(computed["Z"]["x"], 0.5)
            projections = {obj["id"]: obj for obj in spec["objects"] if obj["type"] == "projection_guide"}
            self.assertEqual(projections["J_x"]["point"], "J")
            self.assertEqual(projections["J_x"]["to_axis"], "x")
            self.assertEqual(projections["J_y"]["to_axis"], "y")
            self.assertNotIn("derived_point", {obj["type"] for obj in spec["objects"]})

    def test_coordinate_renderer_outputs_function_objects_and_tikz_fragment(self) -> None:
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
                "functions": [{"id": "f", "variable": "x", "expression_wl": "2*x - 1", "label": "f(x)"}],
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

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, width=720, height=520, size=1024)

            self.assertEqual(result["status"], "ok")
            fragment_path = out_dir / result["tikz_fragment_path"]
            self.assertTrue(fragment_path.exists())
            fragment = fragment_path.read_text(encoding="utf-8")
            self.assertIn(r"\begin{axis}", fragment)
            self.assertIn(r"\addplot+", fragment)
            self.assertIn("axis cs:2,3", fragment)
            self.assertIn("f(x)", fragment)

    def test_coordinate_renderer_preserves_equal_axis_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "type": "coordinate_geometry",
                        "viewport": {
                            "x_min": -2,
                            "x_max": 6,
                            "y_min": -6,
                            "y_max": 12,
                            "preserve_aspect": True,
                        },
                        "objects": [{"type": "point", "id": "O", "x": 0, "y": 0}],
                    }
                ),
                encoding="utf-8",
            )
            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, width=720, height=520, size=1024)
            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")

        self.assertIn("axis equal image", fragment)

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
            artifacts = RendererBindingManifest(
                assignment_id="gate-analytic",
                source_jobs="build/diagram/diagram_jobs.json",
                bindings={
                    "f1.prompt": RendererBinding(
                        slot_id="f1.prompt",
                        diagram_ref="f1.prompt",
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

            data["functions"] = []
            data["source"] = {
                "coordinate_ir": {
                    "objects": [
                        {
                            "type": "function_curve",
                            "id": "f",
                            "expression_wl": "2*x - 1",
                            "domain_segments": [{"min": -2, "max": 6}],
                        }
                    ]
                }
            }
            spec_path.write_text(json.dumps(data), encoding="utf-8")
            checks = _check_analytic_renderer_specs(jobs, artifacts, artifact_dir)
            self.assertEqual(checks[0].status, "block")
            self.assertIn("function_curve", checks[0].message)

            data["source"] = {}
            data["objects"] = [
                {
                    "type": "polyline",
                    "id": "fake-f",
                    "expression_wl": "2*x - 1",
                    "points": [[-2, -5], [2, 3]],
                }
            ]
            spec_path.write_text(json.dumps(data), encoding="utf-8")
            checks = _check_analytic_renderer_specs(jobs, artifacts, artifact_dir)
            self.assertEqual(checks[0].status, "block")
            self.assertIn("polyline cannot carry function expression", checks[0].message)

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
                            "sample_count": 80,
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
            self.assertEqual(len(spec["samples"]["f"]), 80)
            computed = {obj["id"]: obj for obj in spec["objects"] if obj.get("computed")}
            self.assertIn("I1", computed)
            self.assertIn("I2", computed)
            self.assertEqual(computed["J"]["x"], 2.0)
            self.assertEqual(computed["Z"]["x"], 0.5)

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                render_result = render_geometry_spec(job_dir / "final_renderer_spec.json", job_dir, 720, 520, 1024)
            self.assertEqual(render_result["status"], "ok")
            self.assertTrue((job_dir / render_result["tikz_fragment_path"]).exists())


if __name__ == "__main__":
    unittest.main()
