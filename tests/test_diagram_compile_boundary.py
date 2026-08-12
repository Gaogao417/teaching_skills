"""Compile-boundary policy tests for _compile_renderer_spec (P4).

Covers the three deterministic pre-audit cleanups that unblocked the p2
三垂直 square-midpoint failure:
- drop solver points whose name is not a simple label (aggregated Wolfram leak);
- sanitize label text that is a serialized Wolfram aggregate into the point name;
- strip unauthorized prompt markers (authorized ones kept).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(CORE))

import tools  # noqa: E402


def _request(markers=None, texts=None, variant="prompt", disclosure="clean"):
    return {
        "diagram_variant": variant,
        "disclosure_policy": disclosure,
        "visual_requirements": {
            "required_visible_annotations": {
                "markers": markers or [],
                "texts": texts or [],
            }
        },
    }


class CompileBoundaryTest(unittest.TestCase):
    def test_garbage_named_solver_point_is_dropped(self):
        garbage = '["regular", "{C[\\"GeometricPoint\\"][A]}"]'
        render_result = {"parameters": {"A": [0, 0], "B": [1, 0], garbage: [0.5, 0.5]}}
        scene_payload = {"diagram_spec": {"labels": {"A": {"text": "A"}}}}
        spec = tools._compile_renderer_spec(_request(), scene_payload, render_result)
        self.assertEqual(sorted(spec["points"].keys()), ["A", "B"])
        self.assertNotIn(garbage, spec["labels"])

    def test_aggregated_label_text_is_sanitized_to_point_name(self):
        render_result = {"parameters": {"A": [0, 0], "B": [1, 0]}}
        scene_payload = {
            "diagram_spec": {
                "labels": {
                    "A": {"text": "A"},
                    "B": {"text": '{C["GeometricPoint"][A], C["GeometricPoint"][B]}'},
                }
            }
        }
        spec = tools._compile_renderer_spec(_request(), scene_payload, render_result)
        self.assertEqual(spec["labels"]["B"]["text"], "B")
        warnings = spec["source"].get("compile_boundary_warnings", [])
        self.assertTrue(any("sanitized label 'B'" in w for w in warnings))

    def test_unauthorized_prompt_marker_is_stripped_authorized_kept(self):
        render_result = {"parameters": {"A": [0, 0], "B": [1, 0], "D": [0, 1], "E": [2, 2], "F": [3, 3]}}
        scene_payload = {
            "diagram_spec": {
                "markers": [
                    {"type": "right_angle", "vertex": "A", "arms": ["B", "D"]},   # authorized
                    {"type": "right_angle", "vertex": "E", "arms": ["A", "F"]},   # unauthorized
                ],
            }
        }
        request = _request(
            markers=[{"type": "right_angle", "vertex": "A", "arms": ["B", "D"]}]
        )
        spec = tools._compile_renderer_spec(request, scene_payload, render_result)
        vertices = sorted(m["vertex"] for m in spec["markers"])
        self.assertEqual(vertices, ["A"])
        warnings = spec["source"].get("compile_boundary_warnings", [])
        self.assertTrue(any("unauthorized prompt marker" in w for w in warnings))

    def test_solution_variant_keeps_all_markers(self):
        render_result = {"parameters": {"A": [0, 0], "B": [1, 0], "D": [0, 1], "E": [2, 2], "F": [3, 3]}}
        scene_payload = {
            "diagram_spec": {
                "markers": [
                    {"type": "right_angle", "vertex": "A", "arms": ["B", "D"]},
                    {"type": "right_angle", "vertex": "E", "arms": ["A", "F"]},
                ],
            }
        }
        request = _request(
            markers=[{"type": "right_angle", "vertex": "A", "arms": ["B", "D"]}],
            variant="solution",
            disclosure="annotated",
        )
        spec = tools._compile_renderer_spec(request, scene_payload, render_result)
        self.assertEqual(sorted(m["vertex"] for m in spec["markers"]), ["A", "E"])


if __name__ == "__main__":
    unittest.main()
