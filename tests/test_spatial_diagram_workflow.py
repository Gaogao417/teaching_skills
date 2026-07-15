from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from diagram_contracts import (  # noqa: E402
    DiagramJob,
    DiagramJobRequest,
    DiagramJobsManifest,
    RendererBinding,
    RendererBindingManifest,
)
from diagram_gate.spatial_checks import _check_spatial_renderer_specs  # noqa: E402
from assignment_pipeline import run_assignment_diagram_pipeline  # noqa: E402
from render_geometry_spec import render_geometry_spec  # noqa: E402
from spatial_diagram_workflow import build_spatial_render_spec  # noqa: E402
from tikz_renderer import compile_geometry_render_spec  # noqa: E402
from tikz_renderer.toolchain import PreviewResult  # noqa: E402


def _request(projection: str = "textbook_oblique") -> DiagramJobRequest:
    return DiagramJobRequest.model_validate(
        {
            "schema_version": "diagram-job-request/v2",
            "job_id": "spatial-hinge",
            "assignment_id": "spatial-test",
            "slot_id": "q1.prompt",
            "variant": "prompt",
            "disclosure_policy": "clean",
            "engine": "spatial_renderer",
            "diagram_kind": "spatial_geometry",
            "render_profile": {
                "display_profile": "worksheet_geometry_sidecar",
                "width": "60mm",
            },
            "engine_options": {
                "spatial_spec": {
                    "points3d": {
                        "A": [0, 0, 0],
                        "B": [4, 0, 0],
                        "C": [4, 3, 0],
                        "D": [0, 3, 0],
                        "E": [0, 0, -1],
                        "F": [4, 0, -1],
                        "G": [4, 0, 2],
                        "H": [0, 0, 2],
                        "O": [2, 0, 0],
                        "P": [2, 1, 0],
                        "Q": [2, 0, 1],
                    },
                    "polygons": [
                        {"id": "alpha", "points": ["A", "B", "C", "D"]},
                        {"id": "beta", "points": ["E", "F", "G", "H"]},
                    ],
                    "segments": [
                        {"id": "OP", "from": "O", "to": "P", "role": "main"},
                        {"id": "OQ", "from": "O", "to": "Q", "role": "secondary"},
                    ],
                    "derived_segments": [
                        {
                            "id": "l",
                            "relation": "plane_intersection_line",
                            "planes": ["alpha", "beta"],
                            "role": "intersection",
                        }
                    ],
                    "relations": [
                        {"relation": "line_in_plane", "objects": ["OP", "alpha"]},
                        {"relation": "line_in_plane", "objects": ["OQ", "beta"]},
                        {"relation": "perpendicular", "objects": ["OP", "l"]},
                        {"relation": "perpendicular", "objects": ["OQ", "l"]},
                        {"relation": "plane_intersection_line", "objects": ["alpha", "beta", "l"]},
                    ],
                    "markers": [
                        {"type": "angle_arc", "vertex": "O", "arms": ["P", "Q"]}
                    ],
                    "labels": {
                        "O": "O",
                        "P": "P",
                        "Q": "Q",
                        "D": {"text": "$\\alpha$", "show_point": False},
                        "H": {"text": "$\\beta$", "show_point": False},
                    },
                    "projection": {"mode": projection},
                    "quality_focus": {
                        "base_planes": ["alpha"],
                        "angle_checks": [{"id": "POQ", "vertex": "O", "arms": ["P", "Q"]}],
                    },
                }
            },
        }
    )


class SpatialDiagramWorkflowTest(unittest.TestCase):
    def test_spatial_minor_angle_normalizes_after_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = build_spatial_render_spec(_request(), Path(tmp))
        spec.markers[0].arms = ["Q", "P"]

        tikz_spec = compile_geometry_render_spec(spec)

        angle_command = next(
            command for command in tikz_spec.commands if command.kind == "marker:angle_arc"
        )
        self.assertIn(r"\AngleMark[draw=black!70]{P}{O}{Q}", angle_command.tex)
        self.assertEqual(tikz_spec.audit.angle_markers[0]["normalized_arms"], ["P", "Q"])
        self.assertTrue(tikz_spec.audit.angle_markers[0]["swapped"])
        self.assertLess(tikz_spec.audit.angle_markers[0]["sweep_deg"], 180)

    def test_workflow_preserves_3d_coordinates_and_derives_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = build_spatial_render_spec(_request(), Path(tmp))

        self.assertEqual(spec.type, "spatial_geometry")
        self.assertFalse(spec.points)
        self.assertIn("A", spec.points3d)
        self.assertEqual(spec.source["projection_backend"], "tikz_coordinate_basis")
        intersection = next(segment for segment in spec.segments if segment.id == "l")
        self.assertEqual(intersection.role.value, "intersection")
        self.assertTrue(intersection.start.startswith("_l_"))
        self.assertTrue(spec.diagnostics["spatial_projection"]["plane_openings"])

    def test_textbook_projection_compiles_3d_tikz_basis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec = build_spatial_render_spec(_request(), out_dir)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(spec.model_dump(mode="json", by_alias=True), ensure_ascii=False),
                encoding="utf-8",
            )
            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            self.assertEqual(result["status"], "ok")
            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn("x={(", fragment)
            self.assertIn("y={(", fragment)
            self.assertIn("z={(0cm,", fragment)
            self.assertIn(r"\coordinate (A) at (0,0,0);", fragment)
            self.assertNotIn(r"\tdplotsetmaincoords", fragment)
            self.assertIn("spatial intersection", fragment)

    def test_hinge_projection_compiles_tikz_3dplot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec = build_spatial_render_spec(_request("hinge_planes"), out_dir)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(spec.model_dump(mode="json", by_alias=True), ensure_ascii=False),
                encoding="utf-8",
            )
            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            standalone = (out_dir / result["tikz_standalone_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\tdplotsetmaincoords{50}{120}", fragment)
            self.assertIn("tdplot_main_coords", fragment)
            self.assertIn(r"\usepackage{tikz-3dplot}", standalone)

    def test_invalid_spatial_relation_is_rejected(self) -> None:
        request = _request()
        request.engine_options.spatial_spec["relations"] = [
            {"relation": "parallel", "objects": ["OP", "OQ"]}
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "spatial relation failed"):
                build_spatial_render_spec(request, Path(tmp))

    def test_gate_blocks_collapsed_required_spatial_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            spec_path = artifact_dir / "build/diagram/jobs/q1-prompt/final_renderer_spec.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "type": "spatial_geometry",
                        "points3d": {"A": [0, 0, 0], "B": [4, 0, 0], "C": [4, 0.1, 0]},
                        "points": {},
                        "source": {"coordinates": "3d", "projection_backend": "tikz_coordinate_basis"},
                        "diagnostics": {
                            "spatial_projection": {
                                "warnings": ["base plane opening 0.010 is below 0.160"]
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            jobs = DiagramJobsManifest(
                assignment_id="spatial-gate",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="q1-prompt",
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/q1-prompt/request.json",
                        out_dir="build/diagram/jobs/q1-prompt",
                        public_image_dir="diagram/jobs/q1-prompt/rendered",
                        engine="spatial_renderer",
                        diagram_kind="spatial_geometry",
                    )
                ],
            )
            bindings = RendererBindingManifest(
                assignment_id="spatial-gate",
                source_jobs="build/diagram/diagram_jobs.json",
                bindings={
                    "q1.prompt": RendererBinding(
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        job_id="q1-prompt",
                        status="ok",
                        tikz_fragment=r"\begin{tikzpicture}\end{tikzpicture}",
                        hash="sha256:test",
                        final_renderer_spec="build/diagram/jobs/q1-prompt/final_renderer_spec.json",
                        bindable=True,
                    )
                },
            )

            checks = _check_spatial_renderer_specs(jobs, bindings, artifact_dir)
            self.assertTrue(any(check.name == "spatial_projection_readability" for check in checks))
            self.assertTrue(all(check.status == "block" for check in checks))

    def test_assignment_pipeline_resolves_spatial_slot_to_tikz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            spatial_spec = _request().engine_options.spatial_spec
            plan = {
                "meta": {
                    "title": "空间图管线测试",
                    "version": "student",
                    "assignment_id": "spatial-pipeline",
                },
                "render": {"template": "exam-zh-practice"},
                "sections": [
                    {
                        "id": "s1",
                        "type": "practice",
                        "blocks": [
                            {
                                "type": "choice",
                                "id": "q1",
                                "stem": "如图，观察两个相交平面及其交线。",
                                "choices": {"A": "A", "B": "B", "C": "C", "D": "D"},
                                "answer": "A",
                                "diagram_slot": {
                                    "slot_id": "q1.prompt",
                                    "variant": "prompt",
                                    "disclosure_policy": "clean",
                                    "required": True,
                                    "on_failure": "fail_assignment",
                                    "placement": "diagram_col",
                                    "layout_role": "question_sidecar",
                                    "display_profile": "worksheet_geometry_sidecar",
                                    "engine": "spatial_renderer",
                                    "diagram_kind": "spatial_geometry",
                                    "teaching_intent": "practice_prompt",
                                    "engine_options": {"spatial_spec": spatial_spec},
                                },
                            }
                        ],
                    }
                ],
            }
            plan_path = artifact_dir / "assignment.plan.assignment.yaml"
            resolved_path = artifact_dir / "assignment.resolved.assignment.yaml"
            plan_path.write_text(
                yaml.safe_dump(plan, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result_path = run_assignment_diagram_pipeline(
                    plan_path,
                    out=resolved_path,
                    max_workers=1,
                )

            resolved = yaml.safe_load(result_path.read_text(encoding="utf-8"))
            block = resolved["sections"][0]["blocks"][0]
            self.assertNotIn("diagram_slot", block)
            self.assertEqual(block["diagram_col"]["kind"], "tikz")
            self.assertTrue(block["diagram_col"]["tikz_path"].endswith("prompt.fragment.tex"))
            job_profile = json.loads(
                (artifact_dir / "build/diagram/jobs/q1-prompt/performance_profile.json").read_text(encoding="utf-8")
            )
            self.assertIn("workflow", job_profile)
            self.assertIn("renderer", job_profile)
            self.assertTrue(job_profile["workflow"]["stages"])
            pipeline_profile = json.loads(
                (artifact_dir / "build/diagram/pipeline_performance.json").read_text(encoding="utf-8")
            )
            stage_names = {stage["name"] for stage in pipeline_profile["assignment_pipeline"]["stages"]}
            self.assertEqual(stage_names, {"collect", "batch", "gate", "resolve"})


if __name__ == "__main__":
    unittest.main()
