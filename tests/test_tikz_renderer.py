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
from tikz_renderer.toolchain import PreviewResult  # noqa: E402


class TikzRendererTest(unittest.TestCase):
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
            self.assertIn(r"\path[", fragment)
            self.assertIn(r"\DrawSegment", fragment)
            self.assertIn(r"\AngleMark", fragment)
            self.assertIn(r"\RightAngleMark", fragment)
            self.assertIn(r"\DoubleEqualTick", fragment)
            self.assertIn(r"\PointDot", fragment)
            self.assertIn(r"\PointLabel", fragment)
            self.assertIn(r"A\_\textbackslash{}draw", fragment)
            self.assertNotIn(r"A_\draw", fragment)

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
                            {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"},
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
            self.assertIn(r"\addplot+", fragment)
            self.assertIn("dash pattern=on 5pt off 4pt", fragment)
            self.assertIn("axis cs:2,3", fragment)
            self.assertIn("{19}", fragment)
            self.assertNotIn("CD=19", fragment)

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
