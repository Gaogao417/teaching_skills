from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "scripts" / "diagram_workflow"
CORE = WORKFLOW / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(WORKFLOW))
sys.path.insert(0, str(CORE))

import workflow  # noqa: E402
from audit import _audit_degenerate_geometry, audit_diagram_action  # noqa: E402
from tools import render_candidate_action  # noqa: E402


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class DiagramPreviewWorkflowTest(unittest.TestCase):
    def test_interactive_render_cli_forces_wolfram_debug_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            scene_path = root / "scene.json"
            _write(
                request_path,
                {
                    "schema_version": "diagram-job-request/v2",
                    "job_id": "interactive-render",
                    "assignment_id": "unit",
                    "slot_id": "unit.prompt",
                },
            )
            _write(
                scene_path,
                {
                    "scene_code": "GeometricScene[{A,B},{EuclideanDistance[A,B]==1}]",
                    "points": ["A", "B"],
                    "diagram_spec": {"segments": [["A", "B"]]},
                },
            )
            argv = [
                "workflow.py",
                "--action",
                "render",
                "--request",
                str(request_path),
                "--out",
                str(root / "out"),
                "--scene-payload",
                str(scene_path),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(workflow, "render_candidate_action", return_value={"status": "ok"}) as render,
                patch("builtins.print"),
            ):
                workflow.main()

            normalized_request = render.call_args.args[0]
            self.assertIs(normalized_request["wolfram_render_image"], True)

    def test_interactive_render_materializes_reviewed_inline_scene_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            payload = {
                "scene_code": "GeometricScene[{A,B},{EuclideanDistance[A,B]==1}]",
                "points": ["A", "B"],
                "diagram_spec": {"segments": [["A", "B"]]},
            }
            _write(
                request_path,
                {
                    "schema_version": "diagram-job-request/v2",
                    "job_id": "inline-render",
                    "assignment_id": "unit",
                    "slot_id": "unit.prompt",
                    "engine_options": {"scene_payload": payload},
                },
            )
            out_dir = root / "out"
            argv = [
                "workflow.py",
                "--action",
                "render",
                "--request",
                str(request_path),
                "--out",
                str(out_dir),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(workflow, "render_candidate_action", return_value={"status": "ok"}) as render,
                patch("builtins.print"),
            ):
                workflow.main()

            scene_path = out_dir / "rounds/round_0/scene_payload.json"
            self.assertEqual(json.loads(scene_path.read_text(encoding="utf-8")), payload)
            self.assertEqual(render.call_args.args[1], scene_path)

    def test_degenerate_audit_blocks_flat_triangle_drawn_as_segments(self) -> None:
        issues: list[str] = []
        warnings: list[str] = []
        _audit_degenerate_geometry(
            {
                "points": {"A": [4.0, 0.3], "B": [0.0, 0.0], "C": [8.0, 0.0]},
                "segments": [
                    {"from": "A", "to": "B"},
                    {"from": "B", "to": "C"},
                    {"from": "C", "to": "A"},
                ],
                "polygons": [],
            },
            issues,
            warnings,
        )

        self.assertIn("degenerate_triangle_cycle:A:B:C", issues)

    def test_render_stops_for_human_after_one_failed_adjustment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "job"
            scene_path = out_dir / "rounds/round_0/scene_payload.json"
            _write(
                scene_path,
                {
                    "scene_code": "GeometricScene[{A,B},{EuclideanDistance[A,B]==1}]",
                    "points": ["A", "B"],
                    "diagram_spec": {"segments": [["A", "B"]]},
                },
            )
            failure = {
                "success": False,
                "fail_type": "invalid_head",
                "message": "bad syntax",
                "render_image_requested": False,
            }
            with patch("tools._render_scene", return_value=failure):
                first = render_candidate_action({}, scene_path, out_dir, 0)
                second = render_candidate_action({}, scene_path, out_dir, 0)

            self.assertEqual(first["status"], "failed")
            self.assertEqual(second["status"], "needs_human_confirmation")
            self.assertEqual(second["attempt_count"], 2)

    def test_audit_blocks_missing_required_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "job"
            round_dir = out_dir / "rounds/round_0"
            scene_path = round_dir / "scene_payload.json"
            render_path = round_dir / "render_result.json"
            spec_path = round_dir / "final_renderer_spec.json"
            result_path = round_dir / "renderer_result.json"
            _write(
                scene_path,
                {
                    "scene_code": "GeometricScene[{D,F,G},{Element[F,Line[{D,G}]]}]",
                    "diagram_spec": {"segments": [["D", "F"], ["D", "G"]]},
                },
            )
            _write(
                render_path,
                {"success": True, "render_image_requested": False, "points": {"D": [0, 0]}},
            )
            _write(
                spec_path,
                {
                    "schema_version": "geometry-render-spec/v1",
                    "status": "ready",
                    "variant": "solution",
                    "type": "synthetic_geometry",
                    "points": {"D": [0, 0], "F": [1, 0], "G": [0, 1]},
                    "segments": [{"from": "D", "to": "F"}, {"from": "D", "to": "G"}],
                    "labels": {"D": "D", "F": "F", "G": "G"},
                },
            )
            rendered = round_dir / "rendered"
            rendered.mkdir(parents=True)
            (rendered / "solution.fragment.tex").write_text("tikz", encoding="utf-8")
            (rendered / "solution.preview.png").write_bytes(b"png")
            _write(
                result_path,
                {
                    "schema_version": "geometry-renderer-result/v1",
                    "status": "ok",
                    "diagram_variant": "solution",
                    "disclosure_policy": "annotated",
                    "tikz_fragment_path": "rendered/solution.fragment.tex",
                    "preview_png_path": "rendered/solution.preview.png",
                },
            )
            request = {
                "variant": "solution",
                "disclosure_policy": "annotated",
                "visual_requirements": {
                    "required_visible_annotations": {
                        "markers": [
                            {
                                "type": "equal_ticks",
                                "segments": [["D", "F"], ["D", "G"]],
                            }
                        ],
                        "texts": [],
                    }
                },
            }

            result = audit_diagram_action(
                request, scene_path, render_path, spec_path, result_path, out_dir, 0
            )

            self.assertEqual(result["status"], "failed")
            self.assertTrue(
                any(
                    issue.startswith("missing_required_marker:")
                    for issue in result["audit_result"]["issues"]
                )
            )

    def test_renderer_blocking_label_warning_blocks_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "job"
            round_dir = out_dir / "rounds/round_0"
            scene_path = round_dir / "scene_payload.json"
            render_path = round_dir / "render_result.json"
            spec_path = round_dir / "final_renderer_spec.json"
            result_path = round_dir / "renderer_result.json"
            _write(
                scene_path,
                {
                    "scene_code": "GeometricScene[{F,G},{EuclideanDistance[F,G]==1}]",
                    "diagram_spec": {"segments": [["F", "G"]]},
                },
            )
            _write(
                render_path,
                {"success": True, "render_image_requested": False, "points": {"F": [0, 0]}},
            )
            _write(
                spec_path,
                {
                    "schema_version": "geometry-render-spec/v1",
                    "status": "ready",
                    "variant": "solution",
                    "type": "synthetic_geometry",
                    "points": {"F": [0, 0], "G": [1, 0]},
                    "segments": [{"from": "F", "to": "G"}],
                    "labels": {"F": "F", "G": "G"},
                },
            )
            rendered = round_dir / "rendered"
            rendered.mkdir(parents=True)
            (rendered / "solution.fragment.tex").write_text("tikz", encoding="utf-8")
            (rendered / "solution.preview.png").write_bytes(b"png")
            _write(round_dir / "renderer_audit.json", {"warnings": ["blocking:label_overlap:F:G"]})
            _write(
                result_path,
                {
                    "schema_version": "geometry-renderer-result/v1",
                    "status": "ok",
                    "diagram_variant": "solution",
                    "disclosure_policy": "annotated",
                    "tikz_fragment_path": "rendered/solution.fragment.tex",
                    "preview_png_path": "rendered/solution.preview.png",
                    "renderer_audit": "renderer_audit.json",
                },
            )

            result = audit_diagram_action(
                {"variant": "solution", "disclosure_policy": "annotated"},
                scene_path,
                render_path,
                spec_path,
                result_path,
                out_dir,
                0,
            )

            self.assertEqual(result["status"], "failed")
            self.assertIn(
                "renderer_audit:blocking:label_overlap:F:G",
                result["audit_result"]["issues"],
            )

    def test_preview_visual_patch_reuses_render_result_without_wolfram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "job"
            round_dir = out_dir / "rounds/round_0"
            scene_path = round_dir / "scene_payload.json"
            render_path = round_dir / "render_result.json"
            patch_path = Path(tmp) / "visual_patch.json"
            _write(
                scene_path,
                {
                    "scene_code": "GeometricScene[{D,F,G},{EuclideanDistance[D,F]==EuclideanDistance[D,G]}]",
                    "points": ["D", "F", "G"],
                    "diagram_spec": {
                        "segments": [["D", "F"], ["D", "G"]],
                        "markers": [
                            {
                                "type": "equal_segments",
                                "segments": [["D", "F"], ["D", "G"]],
                            }
                        ],
                        "labels": {"D": "D", "F": "F", "G": "G"},
                    },
                },
            )
            _write(
                render_path,
                {
                    "success": True,
                    "render_image_requested": False,
                    "points": {"D": [0, 0], "F": [1, 0], "G": [0, 1]},
                },
            )
            _write(patch_path, {"labels": {"F": {"placement": "below left", "dx": -12}}})
            request = {"variant": "solution", "disclosure_policy": "annotated"}

            def fake_renderer(spec_path: Path, candidate_dir: Path, **_: object) -> dict[str, object]:
                preview = candidate_dir / "rendered/solution.preview.png"
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_bytes(b"png")
                return {
                    "status": "ok",
                    "preview_png_path": "rendered/solution.preview.png",
                }

            with (
                patch.object(workflow, "render_candidate_action") as wolfram_render,
                patch.object(workflow, "run_codex_diagram_agent") as sdk_agent,
                patch.object(workflow, "render_geometry_spec", side_effect=fake_renderer),
                patch.object(
                    workflow,
                    "audit_diagram_action",
                    return_value={
                        "status": "ok",
                        "audit_result": {"status": "pass", "issues": []},
                    },
                ),
            ):
                first = workflow.preview_candidate_action(
                    request, scene_path, render_path, out_dir, 0
                )
                second = workflow.preview_candidate_action(
                    request, scene_path, render_path, out_dir, 0, patch_path
                )

            final_spec = json.loads(
                (round_dir / "final_renderer_spec.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            self.assertEqual(final_spec["points"]["F"], [1.0, 0.0])
            self.assertEqual(final_spec["labels"]["F"]["dx"], -12.0)
            self.assertEqual(final_spec["markers"][0]["type"], "equal_ticks")
            wolfram_render.assert_not_called()
            sdk_agent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
