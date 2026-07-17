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

from agent_prompt import visual_decision_output_schema, visual_decision_prompt  # noqa: E402
from diagram_contracts import (  # noqa: E402
    CoordinatePolicy,
    DiagramExecutionPlan,
    DiagramJob,
    DiagramJobRequest,
    DiagramJobsManifest,
    EngineSource,
    RendererBinding,
    RendererBindingManifest,
)
from diagram_gate.runner import run_resolved_assignment_gate  # noqa: E402
from benchmark_diagram_harness import _launcher_path  # noqa: E402
from run_diagram_batch import (  # noqa: E402
    _cache_identity,
    _effective_model_cache_config,
    run_one_job,
)
from tools import _validate_scene_code  # noqa: E402
from workflow import _visual_decision_from_agent_result  # noqa: E402


def _job() -> DiagramJob:
    return DiagramJob(
        job_id="q1-prompt",
        slot_id="q1.prompt",
        diagram_ref="q1.prompt",
        slot_path="/sections/0/blocks/0/diagram_slot",
        engine="renderer_spec",
        diagram_kind="synthetic_geometry",
        request_path="build/diagram/jobs/q1-prompt/request.json",
        out_dir="build/diagram/jobs/q1-prompt",
        public_image_dir="diagram/jobs/q1-prompt/rendered",
        content_hash="sha256:slot",
        execution_plan={
            "job_id": "q1-prompt",
            "slot_id": "q1.prompt",
            "diagram_kind": "synthetic_geometry",
            "engine": "renderer_spec",
            "engine_source": "execution_override",
            "coordinate_policy": "reviewed_fixture",
            "requires_visual_decision": False,
        },
    )


def _request() -> DiagramJobRequest:
    return DiagramJobRequest(
        job_id="q1-prompt",
        assignment_id="harness-test",
        slot_id="q1.prompt",
        engine="renderer_spec",
        diagram_kind="synthetic_geometry",
        execution_plan={
            "job_id": "q1-prompt",
            "slot_id": "q1.prompt",
            "diagram_kind": "synthetic_geometry",
            "engine": "renderer_spec",
            "engine_source": "execution_override",
            "coordinate_policy": "reviewed_fixture",
            "requires_visual_decision": False,
        },
        engine_options={
            "renderer_spec": {
                "points": {"A": [0, 0], "B": [1, 0]},
                "segments": [{"from": "A", "to": "B"}],
                "labels": {"A": "A", "B": "B"},
            }
        },
    )


class DiagramExecutionPlanContractTest(unittest.TestCase):
    def test_synthetic_route_is_locked_before_agent_start(self) -> None:
        plan = DiagramExecutionPlan.for_route(
            job_id="q1-prompt",
            slot_id="q1.prompt",
            diagram_kind="synthetic_geometry",
            engine="geometric_scene",
        )

        self.assertEqual(plan.engine.value, "geometric_scene")
        self.assertEqual(plan.engine_source, EngineSource.ROUTE_POLICY)
        self.assertEqual(plan.coordinate_policy, CoordinatePolicy.SYMBOLIC_ONLY)
        self.assertTrue(plan.requires_visual_decision)

    def test_request_rejects_engine_mutation_after_planning(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution plan engine"):
            DiagramJobRequest(
                job_id="q1-prompt",
                assignment_id="engine-lock",
                slot_id="q1.prompt",
                engine="renderer_spec",
                diagram_kind="synthetic_geometry",
                execution_plan={
                    "job_id": "q1-prompt",
                    "slot_id": "q1.prompt",
                    "diagram_kind": "synthetic_geometry",
                    "engine": "geometric_scene",
                    "engine_source": "route_policy",
                    "coordinate_policy": "symbolic_only",
                },
            )

    def test_execution_plan_changes_cache_identity(self) -> None:
        job = _job()
        request = _request()
        with tempfile.TemporaryDirectory() as tmp:
            first, _ = _cache_identity(job, request, Path(tmp))
            changed = request.model_copy(deep=True)
            changed.execution_plan.requires_visual_decision = True
            second, _ = _cache_identity(job, changed, Path(tmp))

        self.assertNotEqual(first, second)

    def test_scene_writer_cache_identity_defaults_to_gpt55_low(self) -> None:
        config = _effective_model_cache_config(_request())

        self.assertEqual(config["model"], "gpt-5.5")
        self.assertEqual(config["model_reasoning_effort"], "low")

    def test_symbolic_only_static_gate_rejects_fixed_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "symbolic_only"):
            _validate_scene_code(
                "GeometricScene[{A,B},{A=={0,0},Element[B,Line[{A,B}]]}]",
                coordinate_policy="symbolic_only",
            )

    def test_single_anchor_policy_rejects_unlisted_anchor(self) -> None:
        with self.assertRaisesRegex(ValueError, "authorized anchor"):
            _validate_scene_code(
                "GeometricScene[{A,B},{B=={0,0}}]",
                coordinate_policy="allow_single_anchor",
                allowed_coordinate_anchors=["A"],
            )

    def test_symbolic_policy_accepts_only_host_injected_solution_locks(self) -> None:
        _validate_scene_code(
            "GeometricScene[{A,B},{A=={0,0},Element[B,Line[{A,B}]]}]",
            allow_fixed_metrics=True,
            coordinate_policy="symbolic_only",
            allowed_coordinate_anchors=["A"],
        )

        with self.assertRaisesRegex(ValueError, "symbolic_only"):
            _validate_scene_code(
                "GeometricScene[{A,B},{A=={0,0},B=={1,0}}]",
                allow_fixed_metrics=True,
                coordinate_policy="symbolic_only",
                allowed_coordinate_anchors=["A"],
            )


class DiagramSingleRenderTest(unittest.TestCase):
    def test_batch_accepts_complete_job_package_without_second_render(self) -> None:
        job = _job()
        request = _request()

        def workflow_side_effect(
            request_model: object,
            request_path: Path,
            job_dir: Path,
            build_dir: Path,
        ) -> str:
            del request_model, request_path, build_dir
            rendered = job_dir / "rendered"
            rendered.mkdir(parents=True)
            fragment = rendered / "prompt.fragment.tex"
            fragment.write_text(r"\draw (0,0)--(1,0);", encoding="utf-8")
            preview = rendered / "prompt.preview.png"
            preview.write_bytes(b"png")
            (job_dir / "final_renderer_spec.json").write_text(
                json.dumps({"schema_version": "geometry-render-spec/v1", "status": "ready"}),
                encoding="utf-8",
            )
            (job_dir / "renderer_result.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "tikz_fragment_path": "rendered/prompt.fragment.tex",
                        "tikz_source_path": "rendered/prompt.fragment.tex",
                        "preview_png_path": "rendered/prompt.preview.png",
                    }
                ),
                encoding="utf-8",
            )
            (job_dir / "workflow_result.json").write_text(
                json.dumps({"status": "ok", "final_renderer_spec": "final_renderer_spec.json"}),
                encoding="utf-8",
            )
            return "ok"

        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_diagram_batch._run_workflow_in_process",
            side_effect=workflow_side_effect,
        ), patch("run_diagram_batch._run_tikz_renderer") as renderer:
            result = run_one_job(job, request, Path(tmp), sys.executable, False)

        self.assertEqual(result.status, "ok")
        renderer.assert_not_called()


class DiagramBenchmarkHarnessTest(unittest.TestCase):
    def test_virtualenv_launcher_symlink_is_not_dereferenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_python = root / "base-python"
            base_python.write_text("", encoding="utf-8")
            launcher = root / "venv-python"
            launcher.symlink_to(base_python)

            selected = _launcher_path(launcher)

        self.assertEqual(selected, launcher.absolute())
        self.assertNotEqual(selected, launcher.resolve())


class DiagramVisualDecisionContractTest(unittest.TestCase):
    def test_visual_turn_has_strict_decision_schema_and_no_side_effect_authority(self) -> None:
        schema = visual_decision_output_schema()
        prompt = visual_decision_prompt(
            request={"job_id": "q1-prompt", "engine": "geometric_scene"},
            scene_payload={"scene_code": "GeometricScene[{A,B},{}]"},
            audit_result={"status": "pass", "issues": []},
        )

        self.assertEqual(schema["properties"]["decision"]["enum"], ["accept", "revise"])
        self.assertNotIn("engine", schema["properties"])
        self.assertNotIn("round_index", schema["properties"])
        self.assertNotIn("command", schema["properties"])
        self.assertIn("real preview image", prompt)
        self.assertNotIn("--action", prompt)
        self.assertNotIn("finalize", prompt.lower())

    def test_sdk_telemetry_is_not_part_of_strict_visual_contract(self) -> None:
        decision = _visual_decision_from_agent_result(
            {
                "decision": "accept",
                "reason": "layout is readable",
                "patch": {},
                "agent_thread_id": "thread-1",
                "agent_turn_id": "turn-1",
                "agent_duration_ms": 120,
                "raw_response": "{}",
            }
        )

        self.assertEqual(decision.decision, "accept")

    def test_clean_prompt_rubric_does_not_require_repeated_stem_annotations(self) -> None:
        prompt = visual_decision_prompt(
            request={
                "job_id": "q1-prompt",
                "variant": "prompt",
                "disclosure_policy": "clean",
                "problem_text": "Label AB=AC=5 and cos C=4/5.",
                "semantic_constraints": {"given_constraints": ["AB=AC=5"]},
            },
            scene_payload={"scene_code": "GeometricScene[{A,B,C},{}]"},
            audit_result={"status": "pass", "issues": []},
        )

        self.assertIn("do NOT have to be", prompt)
        self.assertIn("geometric degeneration", prompt)
        self.assertIn("severely displaced", prompt)
        self.assertIn("required_visible_annotations", prompt)

    def test_solution_rubric_checks_requested_teaching_annotations(self) -> None:
        prompt = visual_decision_prompt(
            request={
                "job_id": "q1-solution",
                "variant": "solution",
                "disclosure_policy": "annotated",
            },
            scene_payload={"scene_code": "GeometricScene[{A,B,C},{}]"},
            audit_result={"status": "pass", "issues": []},
        )

        self.assertIn("solution/annotated teaching diagram", prompt)
        self.assertIn("annotations explicitly requested", prompt)


class ResolvedAssignmentGateTest(unittest.TestCase):
    def test_student_solution_binding_blocks_after_resolve(self) -> None:
        plan = {
            "meta": {"assignment_id": "gate-test", "version": "student"},
            "sections": [
                {
                    "blocks": [
                        {
                            "id": "q1",
                            "diagram_col": {
                                "kind": "tikz",
                                "tikz_path": "build/diagram/jobs/q1-prompt/rendered/prompt.fragment.tex",
                                "diagram_ref": "q1.prompt",
                                "diagram_job_id": "q1-prompt",
                                "artifact_hash": "sha256:abc",
                                "variant": "solution",
                                "disclosure_policy": "annotated",
                            },
                        }
                    ]
                }
            ],
        }
        manifest = DiagramJobsManifest(
            assignment_id="gate-test",
            source_assignment="assignment.plan.yaml",
            jobs=[_job()],
        )
        binding = RendererBinding(
            slot_id="q1.prompt",
            diagram_ref="q1.prompt",
            job_id="q1-prompt",
            status="ok",
            bindable=True,
            variant="prompt",
            disclosure_policy="clean",
            tikz_fragment=r"\draw (0,0)--(1,0);",
            hash="sha256:abc",
        )
        bindings = RendererBindingManifest(
            assignment_id="gate-test",
            source_jobs="build/diagram/diagram_jobs.json",
            bindings={"q1.prompt": binding},
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = root / "assignment.resolved.yaml"
            import yaml

            resolved.write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
            report = run_resolved_assignment_gate(
                plan,
                manifest,
                bindings,
                root,
                resolved,
            )

        names = {check.name for check in report.checks if check.status == "block"}
        self.assertIn("student_no_solution", names)
        self.assertIn("student_no_annotated", names)


if __name__ == "__main__":
    unittest.main()
