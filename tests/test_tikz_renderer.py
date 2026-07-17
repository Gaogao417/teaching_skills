from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from render_geometry_spec import render_geometry_spec  # noqa: E402
from tikz_renderer.macros import DIAGRAM_TIKZ_MACROS  # noqa: E402
from tikz_renderer.toolchain import PreviewResult  # noqa: E402


class TikzRendererTest(unittest.TestCase):
    def test_equal_tick_marks_use_compact_third_length(self) -> None:
        self.assertIn("(0pt,-1.33pt) -- (0pt,1.33pt)", DIAGRAM_TIKZ_MACROS)
        self.assertNotIn("(0pt,-4pt) -- (0pt,4pt)", DIAGRAM_TIKZ_MACROS)

    def test_degenerate_angle_marker_blocks_tikz_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "straight-angle-marker",
                        "variant": "solution",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 0], "B": [1, 0], "C": [-1, 0]},
                        "segments": [{"from": "A", "to": "B"}, {"from": "A", "to": "C"}],
                        "markers": [
                            {"type": "angle_arc", "vertex": "A", "arms": ["B", "C"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="solution")

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["fail_type"], "tikz_compile_failed")
            self.assertIn("degenerate", result["message"])

    def test_minor_angle_marker_normalizes_reversed_arm_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "minor-angle-order",
                        "variant": "solution",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 0], "B": [4, 0], "C": [1, 2]},
                        "segments": [{"from": "A", "to": "B"}, {"from": "A", "to": "C"}],
                        "markers": [
                            {"type": "angle_arc", "vertex": "A", "arms": ["C", "B"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="solution")

            self.assertEqual(result["status"], "ok")
            tikz_spec = json.loads((out_dir / "rendered/solution.tikz_spec.json").read_text(encoding="utf-8"))
            angle_command = next(
                command for command in tikz_spec["commands"] if command["kind"] == "marker:angle_arc"
            )
            self.assertTrue(angle_command["tex"].endswith(r"{B}{A}{C}"))
            self.assertIn("angle radius=0.32cm", angle_command["tex"])
            angle_audit = tikz_spec["audit"]["angle_markers"][0]
            self.assertEqual(angle_audit["requested_arms"], ["C", "B"])
            self.assertEqual(angle_audit["normalized_arms"], ["B", "C"])
            self.assertTrue(angle_audit["swapped"])
            self.assertLess(angle_audit["sweep_deg"], 180)
            self.assertEqual(angle_audit["radius_cm"], 0.32)

    def test_synthetic_geometry_outputs_tikz_markers_and_escaped_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "synthetic-tikz",
                        "variant": "prompt",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 0], "B": [4, 0], "C": [1, 2]},
                        "segments": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}, {"from": "C", "to": "A"}],
                        "polygons": [{"points": ["A", "B", "C"], "fill": "#eff6ff"}],
                        "markers": [
                            {"type": "angle_arc", "vertex": "A", "arms": ["B", "C"]},
                            {"type": "right_angle", "vertex": "C", "arms": ["A", "B"]},
                            {"type": "equal_ticks", "segments": [["A", "B"]], "count": 2},
                        ],
                        "labels": {"A": {"text": r"A_\draw"}, "B": "B", "C": "C"},
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["renderer"], "teaching-tikz-geometry-renderer")
            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\begin{tikzpicture}", fragment)
            self.assertIn(r"\Triangle", fragment)
            self.assertIn(r"\DrawSegment", fragment)
            self.assertIn(r"\AngleMark", fragment)
            self.assertIn("angle radius=0.32cm", fragment)
            self.assertIn(r"\RightAngleMark", fragment)
            self.assertIn(r"\DoubleEqualTick", fragment)
            self.assertIn(r"\PointDot", fragment)
            self.assertIn(r"\PointLabel", fragment)
            self.assertIn(r"\PointLabel[left, xshift=", fragment)
            self.assertIn(r"\renewcommand{\DiagramPointRadius}{0.052cm}", fragment)
            self.assertIn(r"A\_\textbackslash{}draw", fragment)
            self.assertNotIn(r"A_\draw", fragment)

    def test_quadrilateral_polygon_uses_semantic_macro_and_outward_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "quad-tikz",
                        "variant": "prompt",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 0], "B": [3, 0], "C": [3, 2], "D": [0, 2]},
                        "segments": [
                            {"from": "A", "to": "B"},
                            {"from": "B", "to": "C"},
                            {"from": "C", "to": "D"},
                            {"from": "D", "to": "A"},
                        ],
                        "polygons": [{"points": ["A", "B", "C", "D"], "fill": "#eff6ff"}],
                        "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\Quadrilateral", fragment)
            self.assertIn(r"\PointLabel[below left, xshift=", fragment)
            self.assertIn(r"\PointLabel[below right, xshift=", fragment)
            self.assertIn(r"\PointLabel[above right, xshift=", fragment)
            self.assertIn(r"\PointLabel[above left, xshift=", fragment)

    def test_explicit_point_label_placement_overrides_polygon_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "explicit-placement",
                        "variant": "prompt",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 0], "B": [3, 0], "C": [0, 2]},
                        "segments": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}, {"from": "C", "to": "A"}],
                        "polygons": [{"points": ["A", "B", "C"], "fill": "#eff6ff"}],
                        "labels": {"A": {"text": "A", "placement": "above_right"}},
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\PointLabel[above right, xshift=", fragment)

    def test_segment_only_geometry_places_labels_outward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "segment-only",
                        "variant": "prompt",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 2.4], "B": [-3, 0], "C": [3, 0], "D": [0, 0]},
                        "segments": [
                            {"from": "A", "to": "B"},
                            {"from": "A", "to": "C"},
                            {"from": "B", "to": "C"},
                            {"from": "A", "to": "D"},
                        ],
                        "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\PointLabel[above, yshift=0.238cm]{A}", fragment)
            self.assertIn(r"\PointLabel[below left, xshift=-0.238cm, yshift=-0.238cm]{B}", fragment)
            self.assertIn(r"\PointLabel[below right, xshift=0.238cm, yshift=-0.238cm]{C}", fragment)
            self.assertIn(r"\PointLabel[below, yshift=-0.238cm]{D}", fragment)

    def test_polygon_default_is_unfilled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "unfilled-polygon",
                        "variant": "prompt",
                        "type": "synthetic_geometry",
                        "points": {"A": [0, 0], "B": [3, 0], "C": [0, 2]},
                        "segments": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}, {"from": "C", "to": "A"}],
                        "polygons": [{"points": ["A", "B", "C"]}],
                        "labels": {"A": "A", "B": "B", "C": "C"},
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir, variant="prompt")

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            triangle_line = next(line for line in fragment.splitlines() if r"\Triangle[" in line)
            self.assertIn("draw=", triangle_line)
            self.assertNotIn("fill=", triangle_line)

    def test_coordinate_geometry_outputs_axis_and_structured_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "coordinate-tikz",
                        "variant": "prompt",
                        "type": "function_graph",
                        "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
                        "axes": {"x": True, "y": True, "grid": True, "show_ticks": True},
                        "functions": [{"id": "f", "expression_wl": "2*x - 1", "label": "f(x)"}],
                        "samples": {"f": [[-2, -5], [0, -1], [2, 3], [6, 11]]},
                        "objects": [
                            {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A", "style": {"label_dx": -20, "label_dy": 16}},
                            {"type": "line", "equation": "x=2", "style": {"dash": "5 4"}},
                            {"type": "circle", "center": [2, 3], "radius": 2},
                            {"type": "polygon", "points": [[1, 1], [2, 3], [3, 1]], "style": {"fill": "#fef3c7"}},
                            {"type": "text", "x": 1, "y": 1, "text": "CD=19"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir)

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\begin{axis}", fragment)
            self.assertIn("grid=both", fragment)
            self.assertIn("clip=false", fragment)
            self.assertNotIn("xlabel=", fragment)
            self.assertNotIn("ylabel=", fragment)
            self.assertIn(r"at (axis cs:6,0) {$x$};", fragment)
            self.assertIn(r"at (axis cs:0,12) {$y$};", fragment)
            self.assertIn(r"\addplot+", fragment)
            self.assertIn("dash pattern=on 5pt off 4pt", fragment)
            self.assertIn("axis cs:2,3", fragment)
            self.assertIn("anchor=south east, xshift=-4.8pt, yshift=3.84pt", fragment)
            self.assertLess(fragment.index("coordinates {(1,1) (2,3) (3,1) (1,1)}"), fragment.index(r"{$\mathit{A}$}"))
            self.assertIn("{19}", fragment)
            self.assertNotIn("CD=19", fragment)

    def test_coordinate_tick_labels_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "coordinate-axis-labels",
                        "variant": "prompt",
                        "type": "coordinate_geometry",
                        "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
                        "axes": {
                            "x": True,
                            "y": True,
                            "grid": False,
                            "show_ticks": True,
                            "x_ticks": [-2, 0, 2, 4],
                            "y_tick_values": [-4, -2, 2],
                            "x_tick_labels": [
                                {"value": 2},
                                {"value": 4, "label": "$4$", "anchor": "north", "dy_pt": -6},
                            ],
                            "y_tick_labels": [
                                {"value": -2, "label": "-2", "anchor": "east", "dx_pt": -5},
                                {"value": 2, "at": [-0.15, 2], "anchor": "east"},
                            ],
                        },
                        "objects": [
                            {"type": "point", "id": "O", "x": 0, "y": 0}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir)

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertNotIn("xlabel=", fragment)
            self.assertNotIn("ylabel=", fragment)
            self.assertIn("xtick={-2,0,2,4}", fragment)
            self.assertIn("ytick={-4,-2,2}", fragment)
            self.assertIn(r"xticklabel=\empty", fragment)
            self.assertIn(r"yticklabel=\empty", fragment)
            self.assertIn(r"at (axis cs:2,0) {$2$};", fragment)
            self.assertIn(r"yshift=-6pt] at (axis cs:4,0) {$4$};", fragment)
            self.assertIn(r"xshift=-5pt] at (axis cs:0,-2) {$-2$};", fragment)
            self.assertIn(r"at (axis cs:-0.15,2) {$2$};", fragment)

    def test_coordinate_projection_guides_read_point_coordinates_on_axes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "coordinate-projection-guides",
                        "variant": "prompt",
                        "type": "coordinate_geometry",
                        "viewport": {"x_min": -2, "x_max": 5, "y_min": -1, "y_max": 5},
                        "axes": {"x": True, "y": True, "grid": False, "show_ticks": True},
                        "objects": [
                            {"type": "point", "id": "P", "x": 1, "y": 3, "label": "P", "computed": True},
                            {
                                "type": "projection_guide",
                                "id": "P_x",
                                "point": "P",
                                "to_axis": "x",
                                "label_style": {"label": "1"},
                            },
                            {
                                "type": "projection_guide",
                                "id": "P_y",
                                "point": "P",
                                "to_axis": "y",
                                "label_style": {"label": "3", "dx_pt": -6},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("render_geometry_spec.build_previews", return_value=PreviewResult()):
                result = render_geometry_spec(spec_path, out_dir)

            fragment = (out_dir / result["tikz_fragment_path"]).read_text(encoding="utf-8")
            self.assertIn("coordinates {(1,3) (1,0)}", fragment)
            self.assertIn("coordinates {(1,3) (0,3)}", fragment)
            self.assertIn(r"at (axis cs:1,0) {$1$};", fragment)
            self.assertIn(r"xshift=-6pt] at (axis cs:0,3) {$3$};", fragment)
            self.assertIn(r"++(0pt,-2.4pt) -- ++(0pt,4.8pt);", fragment)
            self.assertIn(r"++(-2.4pt,0pt) -- ++(4.8pt,0pt);", fragment)

    def test_invalid_spec_writes_failed_renderer_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            spec_path = out_dir / "final_renderer_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": "geometry-render-spec/v1",
                        "job_id": "bad",
                        "type": "function_graph",
                        "viewport": {"x_min": -1, "x_max": 1, "y_min": -1, "y_max": 1},
                        "functions": [{"id": "f", "expression_wl": "x"}],
                        "samples": {},
                    }
                ),
                encoding="utf-8",
            )

            result = render_geometry_spec(spec_path, out_dir)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["fail_type"], "invalid_renderer_spec")
            self.assertIn("has no samples", result["message"])
            self.assertTrue((out_dir / "renderer_result.json").exists())


if __name__ == "__main__":
    unittest.main()
