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
from diagram_gate.semantic_checks import _point_relation_count  # noqa: E402
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


def solution_slot(slot_id: str, reuse: str, scene_code: str) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "diagram_ref": slot_id,
        "variant": "solution",
        "disclosure_policy": "annotated",
        "required": True,
        "on_failure": "fail_assignment",
        "placement": "diagram_col",
        "layout_role": "solution_annotation",
        "display_profile": "worksheet_geometry_sidecar",
        "caption": "教师辅助图",
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "teaching_intent": "practice_solution",
        "reuse_geometry_from": reuse,
        "engine_options": {
            "scene_payload": {
                "scene_code": scene_code,
                "points": ["A", "B", "C", "F"],
                "diagram_spec": {
                    "segments": [{"from": "A", "to": "F"}],
                    "labels": {"A": {"text": "A"}, "F": {"text": "F"}},
                },
            }
        },
    }


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


def write_solution_artifacts(artifact_dir: Path, manifest, scene_code: str) -> RendererBindingManifest:
    bindings = {}
    for index, job in enumerate(manifest.jobs):
        job_dir = artifact_dir / "build" / "diagram" / "jobs" / job.job_id
        rendered = job_dir / "rendered"
        rendered.mkdir(parents=True, exist_ok=True)
        points = {"A": [0, 2], "B": [-2, 0], "C": [2, 0]}
        if job.variant.value == "solution":
            points["F"] = [0, 0]
            write_json(job_dir / "scene_payload.json", {"scene_code": scene_code})
        spec = {
            "type": "synthetic_geometry",
            "points": points,
            "segments": [{"from": "A", "to": "B"}, {"from": "A", "to": "C"}],
            "labels": {name: {"text": name} for name in points},
        }
        write_json(job_dir / "final_renderer_spec.json", spec)
        fragment_name = f"{job.variant.value}.fragment.tex"
        (rendered / fragment_name).write_text(
            rf"\begin{{tikzpicture}}\draw (0,0)--({index + 1},0);\end{{tikzpicture}}",
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
            tikz_fragment_path=f"build/diagram/jobs/{job.job_id}/rendered/{fragment_name}",
            final_renderer_spec=f"build/diagram/jobs/{job.job_id}/final_renderer_spec.json",
            hash=f"sha256:solution-{index}",
        )
    return RendererBindingManifest(
        assignment_id=manifest.assignment_id,
        source_jobs="build/diagram/diagram_jobs.json",
        bindings=bindings,
    )


class DiagramGateRegressionTest(unittest.TestCase):
    def test_incidence_relation_counts_point_used_inside_another_points_line(self) -> None:
        scene_code = (
            "GeometricScene[{A,B,C,D,P},{Element[D,Line[{B,C}]],"
            "Element[P,Line[{A,D}]]}]"
        )

        self.assertEqual(_point_relation_count(scene_code, "D"), 2)

    def test_prompt_semantic_coverage_prefers_narrow_slot_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            slot = synthetic_slot("q1.prompt")
            slot["problem_context"] = {
                "stem_latex": r"在 $\triangle ABC$ 中，$AB=AC$。",
                "source_problem_text": "只画原三角形 ABC，不画旋转后的 D、E。",
            }
            plan_data = plan_with_blocks(
                [
                    {
                        "type": "problem",
                        "id": "q1",
                        "stem_latex": (
                            r"在 $\triangle ABC$ 中，将其旋转为 $\triangle ADE$，"
                            r"边 $AD,DE$ 分别与 $BC$ 相交。"
                        ),
                        "diagram_slot": slot,
                    }
                ]
            )
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_fake_job_artifacts(artifact_dir, manifest)

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            semantic_blocks = {
                check.name
                for check in report.checks
                if check.status == "block" and check.name == "slot_semantic_coverage"
            }

        self.assertEqual(semantic_blocks, set())

    def test_declared_constructed_point_fixed_coordinates_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = (
                "GeometricScene[{A,B,C,P},{A=={0,2},B=={-2,0},C=={2,0},P=={0,1}}]"
            )
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"AD 与 BE 交于 P。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)
            solution_job = next(job for job in manifest.jobs if job.variant.value == "solution")
            write_json(
                artifact_dir / "build" / "diagram" / "jobs" / solution_job.job_id / "scene_payload.json",
                {
                    "scene_code": scene_code,
                    "point_roles": {"anchors": ["A", "B", "C"], "constructed": ["P"]},
                },
            )

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            blocks = {check.name for check in report.checks if check.status == "block"}

            self.assertIn("constructed_point_fixed_coordinates", blocks)

    def test_declared_constructed_intersection_constraints_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = (
                "GeometricScene[{A,B,C,D,E,P},{A=={0,2},B=={-2,0},C=={2,0},"
                "Element[P,Line[{A,D}]],Element[P,Line[{B,E}]]}]"
            )
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"AD 与 BE 交于 P。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)
            solution_job = next(job for job in manifest.jobs if job.variant.value == "solution")
            write_json(
                artifact_dir / "build" / "diagram" / "jobs" / solution_job.job_id / "scene_payload.json",
                {
                    "scene_code": scene_code,
                    "point_roles": {"anchors": ["A", "B", "C", "D", "E"], "constructed": ["P"]},
                },
            )

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            role_blocks = {
                check.name for check in report.checks
                if check.status == "block" and check.name.startswith("constructed_point")
            }

            self.assertEqual(role_blocks, set())

    def test_declared_constructed_rotation_transform_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = (
                "GeometricScene[{{A,B,F},{theta}},{A=={0,2},B=={-2,0},"
                "Equal[F,RotationTransform[theta,A][B]]}]"
            )
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"将 B 绕 A 旋转到 D。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)
            solution_job = next(job for job in manifest.jobs if job.variant.value == "solution")
            write_json(
                artifact_dir / "build" / "diagram" / "jobs" / solution_job.job_id / "scene_payload.json",
                {
                    "scene_code": scene_code,
                    "point_roles": {"anchors": ["A", "B"], "constructed": ["F"]},
                },
            )

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            role_blocks = {
                check.name for check in report.checks
                if check.status == "block" and (
                    check.name.startswith("constructed_point")
                    or check.name.startswith("solution_auxiliary")
                )
            }

            self.assertEqual(role_blocks, set())

    def test_constructed_point_with_two_metric_relations_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = (
                "GeometricScene[{A,B,C,F},{A=={0,2},B=={-2,0},C=={2,0},"
                "EuclideanDistance[A,F]==EuclideanDistance[A,B],"
                "PlanarAngle[{B,A,F}]==PlanarAngle[{F,A,C}]}]"
            )
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"由距离与角关系确定点 F。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)
            solution_job = next(job for job in manifest.jobs if job.variant.value == "solution")
            write_json(
                artifact_dir / "build" / "diagram" / "jobs" / solution_job.job_id / "scene_payload.json",
                {
                    "scene_code": scene_code,
                    "point_roles": {"anchors": ["A", "B", "C"], "constructed": ["F"]},
                },
            )

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            role_blocks = {
                check.name for check in report.checks
                if check.status == "block" and (
                    check.name.startswith("constructed_point")
                    or check.name.startswith("solution_auxiliary")
                )
            }

            self.assertEqual(role_blocks, set())

    def test_full_form_equal_fixed_coordinate_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = "GeometricScene[{A,B,F},{A=={0,2},B=={-2,0},Equal[F,{1,1}]}]"
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"将 B 绕 A 旋转到 D。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)
            solution_job = next(job for job in manifest.jobs if job.variant.value == "solution")
            write_json(
                artifact_dir / "build" / "diagram" / "jobs" / solution_job.job_id / "scene_payload.json",
                {
                    "scene_code": scene_code,
                    "point_roles": {"anchors": ["A", "B"], "constructed": ["F"]},
                },
            )

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            blocks = {check.name for check in report.checks if check.status == "block"}

            self.assertIn("constructed_point_fixed_coordinates", blocks)
            self.assertIn("solution_auxiliary_fixed_coordinates", blocks)

    def test_solution_auxiliary_fixed_coordinates_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"在三角形 ABC 中，作辅助线 AF。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot(
                        "q1.solution",
                        "q1.prompt",
                        "GeometricScene[{A,B,C,F},{A=={0,2},B=={-2,0},C=={2,0},F=={0,0}}]",
                    )
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(
                artifact_dir,
                manifest,
                "GeometricScene[{A,B,C,F},{A=={0,2},B=={-2,0},C=={2,0},F=={0,0}}]",
            )

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            blocks = {check.name for check in report.checks if check.status == "block"}

            self.assertIn("solution_auxiliary_fixed_coordinates", blocks)

    def test_solution_auxiliary_element_constraint_passes_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = (
                'GeometricScene[{A,B,C,F},{A=={0,2},B=={-2,0},C=={2,0},'
                'Element[F,InfiniteLine[{B,C}]],'
                'GeometricAssertion[{Line[{A,F}],Line[{B,C}]},"Perpendicular"]}]'
            )
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"在三角形 ABC 中，作辅助线 AF。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            auxiliary_blocks = {
                check.name for check in report.checks
                if check.status == "block" and check.name.startswith("solution_auxiliary")
            }

            self.assertEqual(auxiliary_blocks, set())

    def test_solution_auxiliary_single_incidence_is_underconstrained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            scene_code = (
                "GeometricScene[{A,B,C,F},{A=={0,2},B=={-2,0},C=={2,0},"
                "Element[F,InfiniteLine[{B,C}]]}]"
            )
            plan_data = plan_with_blocks([{
                "type": "problem",
                "id": "q1",
                "stem_latex": r"在三角形 ABC 中，作辅助线 AF。",
                "diagram_slot": synthetic_slot("q1.prompt"),
                "answer_space": {
                    "diagram_slot": solution_slot("q1.solution", "q1.prompt", scene_code)
                },
            }])
            plan_view, manifest = collect(plan_data, artifact_dir)
            artifacts = write_solution_artifacts(artifact_dir, manifest, scene_code)

            report = run_gate(plan_view, manifest, artifacts, artifact_dir, None)
            blocks = {check.name for check in report.checks if check.status == "block"}

            self.assertIn("solution_auxiliary_underconstrained", blocks)

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
