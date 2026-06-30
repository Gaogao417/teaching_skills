from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
OUT_DIR = ROOT / "build" / "e2e-coordinate-function-test"


PLAN_YAML = {
    "meta": {
        "title": "一次函数与反比例函数图像",
        "version": "student",
        "assignment_id": "e2e-coordinate-function",
    },
    "render": {"template": "exam-zh-practice"},
    "sections": [
        {
            "id": "s1",
            "type": "practice",
            "blocks": [
                {
                    "type": "problem",
                    "id": "q1",
                    "stem_latex": (
                        r"在同一平面直角坐标系中画出直线 $y=x-2$ 和双曲线 "
                        r"$y=\dfrac{3}{x}$ 的图像，并标出点 $A(3,1)$、$B(-1,-3)$。"
                    ),
                    "diagram_slot": {
                        "slot_id": "q1.prompt",
                        "diagram_ref": "q1.prompt",
                        "variant": "prompt",
                        "disclosure_policy": "clean",
                        "required": True,
                        "on_failure": "fail_assignment",
                        "placement": "diagram_col",
                        "layout_role": "question_sidecar",
                        "display_profile": "worksheet_geometry_sidecar",
                        "caption": "函数图像",
                        "engine": "coordinate_renderer",
                        "diagram_kind": "coordinate_geometry",
                        "teaching_intent": "practice_prompt",
                        "analytic_requirements": {
                            "coordinate_ir": {
                                "viewport": {
                                    "x_min": -4,
                                    "x_max": 5,
                                    "y_min": -6,
                                    "y_max": 5,
                                    "preserve_aspect": True,
                                },
                                "axes": {
                                    "x": True,
                                    "y": True,
                                    "grid": False,
                                    "show_ticks": True,
                                    "x_label": "x",
                                    "y_label": "y",
                                    "x_ticks": [-4, -2, 2, 4],
                                    "y_ticks": [-6, -4, -2, 2, 4],
                                    "x_tick_labels": [{"value": -4}, {"value": -2}, {"value": 2}, {"value": 4}],
                                    "y_tick_labels": [{"value": -6}, {"value": -4}, {"value": -2}, {"value": 2}, {"value": 4}],
                                },
                                "objects": [
                                    {
                                        "type": "function_curve",
                                        "id": "line",
                                        "variable": "x",
                                        "expression_latex": "x-2",
                                        "expression_wl": "x - 2",
                                        "domain_segments": [{"min": -4, "max": 5}],
                                        "label": "$y=x-2$",
                                        "sample_count": 120,
                                        "style": {
                                            "stroke": "#2563eb",
                                            "stroke_width": 2.4,
                                            "label_at": [2.7, -0.75],
                                            "label_anchor": "north west",
                                            "label_dx": 2,
                                            "label_dy": -3,
                                        },
                                    },
                                    {
                                        "type": "function_curve",
                                        "id": "hyperbola",
                                        "variable": "x",
                                        "expression_latex": r"\frac{3}{x}",
                                        "expression_wl": "3/x",
                                        "domain_segments": [
                                            {"min": -4, "max": -0.6},
                                            {"min": 0.6, "max": 5},
                                        ],
                                        "label": r"$y=\frac{3}{x}$",
                                        "sample_count": 120,
                                        "style": {
                                            "stroke": "#dc2626",
                                            "stroke_width": 2.4,
                                            "label_at": [-2.8, -1.15],
                                            "label_anchor": "north east",
                                            "label_dx": -2,
                                            "label_dy": -3,
                                        },
                                    },
                                    {"type": "point", "id": "A", "label": "A", "x": 3, "y": 1},
                                    {"type": "point", "id": "B", "label": "B", "x": -1, "y": -3},
                                ],
                            }
                        },
                        "semantic_constraints": {
                            "given_objects": [
                                "直线 y=x-2",
                                "双曲线 y=3/x",
                                "点 A(3,1)",
                                "点 B(-1,-3)",
                            ],
                            "clean_forbidden": ["不要标出未给出的面积或解题提示"],
                        },
                    },
                    "answer_space": {"type": "lines", "height": "35mm"},
                }
            ],
        }
    ],
}


def run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )


class CoordinateFunctionDiagramE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        OUT_DIR.mkdir(parents=True)
        self.plan_path = OUT_DIR / "assignment.plan.yaml"
        self.build_dir = OUT_DIR / "build" / "diagram"
        self.jobs_path = self.build_dir / "diagram_jobs.json"
        self.jobs_dir = self.build_dir / "jobs"
        self.resolved_path = OUT_DIR / "assignment.resolved.yaml"
        self.plan_path.write_text(
            yaml.dump(PLAN_YAML, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def test_coordinate_ir_function_graph_pipeline_outputs_tikz_and_auditable_artifacts(self) -> None:
        pipeline = run_script([
            "scripts/diagram_workflow/run_assignment_diagrams.py",
            str(self.plan_path),
            "--out",
            str(self.resolved_path),
            "--max-workers",
            "1",
        ])
        self.assertEqual(pipeline.returncode, 0, pipeline.stderr)

        jobs = json.loads(self.jobs_path.read_text(encoding="utf-8"))
        self.assertEqual([job["job_id"] for job in jobs["jobs"]], ["q1-prompt"])
        self.assertEqual(jobs["jobs"][0]["engine"], "coordinate_renderer")
        self.assertEqual(jobs["jobs"][0]["diagram_kind"], "coordinate_geometry")

        batch_report = json.loads((self.build_dir / "diagram_batch_report.json").read_text(encoding="utf-8"))
        self.assertEqual(batch_report["ok_count"], 1)

        job_dir = self.jobs_dir / "q1-prompt"
        request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
        ir_objects = request["analytic_requirements"]["coordinate_ir"]["objects"]
        self.assertEqual([obj["type"] for obj in ir_objects[:2]], ["function_curve", "function_curve"])
        self.assertEqual(ir_objects[1]["domain_segments"], [{"min": -4.0, "max": -0.6}, {"min": 0.6, "max": 5.0}])

        workflow = json.loads((job_dir / "workflow_result.json").read_text(encoding="utf-8"))
        self.assertEqual(workflow["status"], "ok")
        self.assertFalse(workflow["wolfram"]["success"])

        spec = json.loads((job_dir / "final_renderer_spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["type"], "coordinate_geometry")
        self.assertEqual([func["id"] for func in spec["functions"]], ["line", "hyperbola__seg1", "hyperbola__seg2"])
        self.assertEqual(set(spec["samples"]), {"line", "hyperbola__seg1", "hyperbola__seg2"})
        self.assertEqual({key: len(value) for key, value in spec["samples"].items()}, {
            "line": 120,
            "hyperbola__seg1": 120,
            "hyperbola__seg2": 120,
        })
        self.assertTrue(spec["diagnostics"]["local_sampler_used"])
        self.assertFalse(spec["diagnostics"]["wolfram_used"])
        self.assertEqual(spec["source"]["coordinate_ir"]["objects"][0]["type"], "function_curve")
        self.assertEqual([obj["id"] for obj in spec["objects"]], ["A", "B"])

        renderer = json.loads((job_dir / "renderer_result.json").read_text(encoding="utf-8"))
        self.assertEqual(renderer["status"], "ok")
        self.assertGreater(renderer["natural_height_pt"], 180)
        fragment_path = job_dir / renderer["tikz_fragment_path"]
        fragment = fragment_path.read_text(encoding="utf-8")
        self.assertIn(r"\begin{axis}", fragment)
        self.assertIn("axis equal image", fragment)
        self.assertNotIn("xlabel=", fragment)
        self.assertNotIn("ylabel=", fragment)
        self.assertIn("xtick={-4,-2,2,4}", fragment)
        self.assertIn("ytick={-6,-4,-2,2,4}", fragment)
        self.assertIn(r"xticklabel=\empty", fragment)
        self.assertIn(r"yticklabel=\empty", fragment)
        self.assertIn(r"at (axis cs:4,0) {$4$};", fragment)
        self.assertIn(r"at (axis cs:0,4) {$4$};", fragment)
        self.assertIn(r"at (axis cs:5,0) {$x$};", fragment)
        self.assertIn(r"at (axis cs:0,5) {$y$};", fragment)
        self.assertEqual(fragment.count(r"\addplot+"), 5)  # 3 curves + 2 point marks
        self.assertIn("xshift=2pt, yshift=-3pt", fragment)
        self.assertIn("xshift=-2pt, yshift=-3pt", fragment)
        self.assertIn("$y=x-2$", fragment)
        self.assertIn(r"$y=\frac{3}{x}$", fragment)
        self.assertIn(r"{$\mathit{A}$}", fragment)
        self.assertIn(r"{$\mathit{B}$}", fragment)

        resolved = yaml.safe_load(self.resolved_path.read_text(encoding="utf-8"))
        diagram_col = resolved["sections"][0]["blocks"][0]["diagram_col"]
        self.assertEqual(diagram_col["kind"], "tikz")
        self.assertEqual(diagram_col["diagram_job_id"], "q1-prompt")
        self.assertTrue((OUT_DIR / diagram_col["tikz_path"]).exists())


if __name__ == "__main__":
    unittest.main()
