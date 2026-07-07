from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from collect_diagram_jobs import collect_jobs  # noqa: E402
from diagram_contracts import AssignmentPlanDiagramView, RendererBinding, RendererBindingManifest  # noqa: E402
from diagram_gate.runner import run_gate  # noqa: E402
from renderer_bindings import write_json  # noqa: E402


def coordinate_slot(slot_id: str, stem_constraint: str = "AB:AC=2:5") -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "diagram_ref": slot_id,
        "variant": "prompt",
        "disclosure_policy": "clean",
        "required": True,
        "on_failure": "fail_assignment",
        "placement": "diagram_col",
        "layout_role": "question_sidecar",
        "display_profile": "worksheet_geometry_sidecar",
        "caption": "原题图",
        "engine": "coordinate_renderer",
        "diagram_kind": "coordinate_geometry",
        "teaching_intent": "practice_prompt",
        "semantic_constraints": {
            "given_objects": ["A", "B", "C", "D", "E"],
            "given_constraints": ["B on AC", "D on AE", "BD parallel CE", stem_constraint],
        },
        "analytic_requirements": {
            "coordinate_ir": {
                "viewport": {"x_min": -1, "x_max": 7, "y_min": -1, "y_max": 5},
                "axes": {"x": False, "y": False, "grid": False, "show_ticks": False},
                "objects": [
                    {"type": "point", "id": "A", "x": 0, "y": 0, "label": "A"},
                    {"type": "point", "id": "C", "x": 6, "y": 0, "label": "C"},
                    {"type": "point", "id": "E", "x": 6, "y": 4, "label": "E"},
                    {"type": "point", "id": "B", "x": 2, "y": 0, "label": "B"},
                    {"type": "point", "id": "D", "x": 2, "y": 4 / 3, "label": "D"},
                    {"type": "segment", "id": "AC", "from": "A", "to": "C"},
                    {"type": "segment", "id": "AE", "from": "A", "to": "E"},
                    {"type": "segment", "id": "BD", "from": "B", "to": "D"},
                    {"type": "segment", "id": "CE", "from": "C", "to": "E"},
                ],
            }
        },
    }


def synthetic_slot(slot_id: str, *, reuse: str = "") -> dict[str, object]:
    slot: dict[str, object] = {
        "slot_id": slot_id,
        "diagram_ref": slot_id,
        "variant": "prompt",
        "disclosure_policy": "clean",
        "required": True,
        "on_failure": "fail_assignment",
        "placement": "diagram_col",
        "layout_role": "question_sidecar",
        "display_profile": "worksheet_geometry_sidecar",
        "caption": "原题图",
        "engine": "renderer_spec",
        "diagram_kind": "synthetic_geometry",
        "teaching_intent": "practice_prompt",
        "semantic_constraints": {
            "given_objects": ["A", "B", "C"],
            "given_constraints": ["A-B-C collinear", "AB:BC=3:5", "AC=64"],
        },
        "engine_options": {
            "renderer_spec": {
                "points": {"A": [0, 0], "B": [3, 0], "C": [8, 0]},
                "segments": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}],
                "labels": {"A": "A", "B": "B", "C": "C"},
            }
        },
    }
    if reuse:
        slot["reuse_geometry_from"] = reuse
    return slot


def plan_with_blocks(blocks: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {"title": "diagram gate regression", "assignment_id": "diagram-gate-regression"},
        "render": {"template": "exam-zh-practice"},
        "sections": [{"id": "s1", "type": "practice", "blocks": blocks}],
    }


def collect(plan_data: dict[str, object], artifact_dir: Path):
    plan_view = AssignmentPlanDiagramView.model_validate(plan_data)
    return plan_view, collect_jobs(plan_view, artifact_dir / "assignment.plan.yaml", artifact_dir / "build" / "diagram")


def write_fake_job_artifacts(artifact_dir: Path, manifest, *, same_spec: bool = False) -> RendererBindingManifest:
    bindings = {}
    for index, job in enumerate(manifest.jobs):
        job_dir = artifact_dir / "build" / "diagram" / "jobs" / job.job_id
        rendered = job_dir / "rendered"
        rendered.mkdir(parents=True, exist_ok=True)
        spec = {
            "type": "synthetic_geometry",
            "points": {"A": [0, 0], "B": [2 if same_spec else 2 + index, 0], "C": [5, 0]},
            "segments": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}],
            "labels": {"A": "A", "B": "B", "C": "C"},
        }
        write_json(job_dir / "final_renderer_spec.json", spec)
        fragment = rendered / "prompt.fragment.tex"
        fragment.write_text(
            r"\begin{tikzpicture}\draw (0,0) -- (1,0);\end{tikzpicture}"
            if same_spec
            else rf"\begin{{tikzpicture}}\draw (0,0) -- ({index + 1},0);\end{{tikzpicture}}",
            encoding="utf-8",
        )
        bindings[job.diagram_ref] = RendererBinding(
            slot_id=job.slot_id,
            diagram_ref=job.diagram_ref,
            job_id=job.job_id,
            status="ok",
            bindable=True,
            variant=job.variant,
            disclosure_policy=job.disclosure_policy,
            tikz_fragment_path=f"build/diagram/jobs/{job.job_id}/rendered/prompt.fragment.tex",
            final_renderer_spec=f"build/diagram/jobs/{job.job_id}/final_renderer_spec.json",
            hash=f"sha256:{index}",
        )
    return RendererBindingManifest(
        assignment_id=manifest.assignment_id,
        source_jobs="build/diagram/diagram_jobs.json",
        bindings=bindings,
    )


class DiagramGateRegressionTest(unittest.TestCase):
    def test_duplicate_coordinate_geometry_regression_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            plan_data = plan_with_blocks([
                {
                    "type": "problem",
                    "id": "q1",
                    "stem_latex": r"如图，在 $\triangle ACE$ 中，$BD\parallel CE$，$AB:AC=2:5$，求 $AD:AE$。",
                    "diagram_slot": coordinate_slot("q1.prompt"),
                },
                {
                    "type": "problem",
                    "id": "q2",
                    "stem_latex": r"如图，在 $\triangle ACE$ 中，$BD\parallel CE$，$AB:AC=3:7$，求 $BD:CE$。",
                    "diagram_slot": coordinate_slot("q2.prompt"),
                },
            ])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_fake_job_artifacts(artifact_dir, manifest, same_spec=True)

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            check_names = {check.name for check in report.checks if check.status == "block"}

            self.assertEqual(report.status, "block")
            self.assertIn("duplicate_prompt_geometry_slot", check_names)
            self.assertIn("duplicate_prompt_geometry_spec", check_names)
            self.assertIn("duplicate_prompt_geometry_tikz", check_names)
            self.assertIn("coordinate_geometry_scope", check_names)

    def test_coordinate_function_graph_still_passes_scope_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            plan_data = plan_with_blocks([
                {
                    "type": "problem",
                    "id": "f1",
                    "stem_latex": r"在平面直角坐标系中，函数 $y=x+1$ 的图像经过点 $A(1,2)$。",
                    "diagram_slot": {
                        "slot_id": "f1.prompt",
                        "diagram_ref": "f1.prompt",
                        "variant": "prompt",
                        "disclosure_policy": "clean",
                        "required": True,
                        "on_failure": "fail_assignment",
                        "placement": "diagram_col",
                        "layout_role": "question_sidecar",
                        "engine": "coordinate_renderer",
                        "diagram_kind": "coordinate_geometry",
                        "semantic_constraints": {
                            "given_objects": ["A", "f"],
                            "given_constraints": ["A(1,2)", "y=x+1"],
                        },
                        "analytic_requirements": {
                            "coordinate_ir": {
                                "viewport": {"x_min": -2, "x_max": 4, "y_min": -2, "y_max": 5},
                                "objects": [
                                    {
                                        "type": "function_curve",
                                        "id": "f",
                                        "expression_wl": "x + 1",
                                        "domain_segments": [{"min": -2, "max": 4}],
                                    },
                                    {"type": "point", "id": "A", "x": 1, "y": 2, "label": "A"},
                                ],
                            }
                        },
                    },
                }
            ])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_fake_job_artifacts(artifact_dir, manifest)

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            blocking_names = {check.name for check in report.checks if check.status == "block"}

            self.assertNotIn("coordinate_geometry_scope", blocking_names)

    def test_explicit_prompt_reuse_allows_duplicate_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            plan_data = plan_with_blocks([
                {
                    "type": "problem",
                    "id": "q1",
                    "stem_latex": r"点 $A,B,C$ 在同一直线上，$AB:BC=3:5$，$AC=64$。",
                    "diagram_slot": synthetic_slot("q1.prompt"),
                },
                {
                    "type": "problem",
                    "id": "q2",
                    "stem_latex": r"点 $A,B,C$ 在同一直线上，$AB:BC=3:5$，$AC=64$。",
                    "diagram_slot": synthetic_slot("q2.prompt", reuse="q1.prompt"),
                },
            ])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_fake_job_artifacts(artifact_dir, manifest, same_spec=True)

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            duplicate_blocks = [
                check for check in report.checks
                if check.status == "block" and check.name.startswith("duplicate_prompt_geometry")
            ]

            self.assertEqual(duplicate_blocks, [])

    def test_bad_fixture_cli_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            plan_path = artifact_dir / "assignment.plan.yaml"
            build_dir = artifact_dir / "build" / "diagram"
            jobs_path = build_dir / "diagram_jobs.json"
            jobs_dir = build_dir / "jobs"
            plan_data = plan_with_blocks([
                {
                    "type": "problem",
                    "id": "q1",
                    "stem_latex": r"如图，在 $\triangle ACE$ 中，$BD\parallel CE$，$AB:AC=2:5$，求 $AD:AE$。",
                    "diagram_slot": coordinate_slot("q1.prompt"),
                },
                {
                    "type": "problem",
                    "id": "q2",
                    "stem_latex": r"如图，在 $\triangle ACE$ 中，$BD\parallel CE$，$AB:AC=3:7$，求 $BD:CE$。",
                    "diagram_slot": coordinate_slot("q2.prompt"),
                },
            ])
            plan_path.write_text(yaml.safe_dump(plan_data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            plan_view, manifest = collect(plan_data, artifact_dir)
            build_dir.mkdir(parents=True, exist_ok=True)
            jobs_path.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
            for job in manifest.jobs:
                job_dir = jobs_dir / job.job_id
                rendered = job_dir / "rendered"
                rendered.mkdir(parents=True, exist_ok=True)
                write_json(job_dir / "workflow_result.json", {"status": "ok"})
                write_json(job_dir / "final_renderer_spec.json", {"points": {"A": [0, 0], "B": [1, 0]}})
                fragment = rendered / "prompt.fragment.tex"
                fragment.write_text(r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}", encoding="utf-8")
                write_json(
                    job_dir / "renderer_result.json",
                    {"status": "ok", "tikz_fragment_path": "rendered/prompt.fragment.tex"},
                )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "diagram_workflow" / "check_diagram_gate.py"),
                    "--plan",
                    str(plan_path),
                    "--jobs",
                    str(jobs_path),
                    "--jobs-dir",
                    str(jobs_dir),
                    "--artifact-dir",
                    str(artifact_dir),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("duplicate_prompt_geometry", result.stdout)
            self.assertIn("coordinate_geometry_scope", result.stdout)


if __name__ == "__main__":
    unittest.main()
