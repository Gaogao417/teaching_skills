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


def _request() -> dict[str, object]:
    return {
        "job_id": "q1-prompt",
        "diagram_job_id": "q1-prompt",
        "variant": "prompt",
        "diagram_variant": "prompt",
        "disclosure_policy": "clean",
    }


def _agent_output(tag: str = "first") -> dict[str, object]:
    return {
        "scene_code": (
            "GeometricScene[{A,B,C},{EuclideanDistance[A,B]==EuclideanDistance[A,C],"
            'GeometricAssertion[Line[{B,C}],"Horizontal"]}]'
        ),
        "points": ["A", "B", "C"],
        "point_roles": {"anchors": ["A", "B", "C"], "constructed": [], "auxiliary": []},
        "diagram_spec": {
            "segments": [["A", "B"], ["A", "C"], ["B", "C"]],
            "labels": {"A": {"text": "A"}, "B": {"text": "B"}, "C": {"text": "C"}},
        },
        "rationale": tag,
        "model_used": "gpt-5.5",
        "model_attempts": [{"role": "text", "model": "gpt-5.5", "status": "ok"}],
        "raw_response": "{}",
        "agent_thread_id": f"thread-{tag}",
        "agent_turn_id": f"turn-{tag}",
        "agent_duration_ms": 12,
    }


def _render_ok() -> dict[str, object]:
    return {
        "status": "ok",
        "render_result": {
            "success": True,
            "render_image_requested": False,
            "points": {"A": [0, 2], "B": [-2, 0], "C": [2, 0]},
        },
    }


class DiagramHostOrchestrationTest(unittest.TestCase):
    def _run_with_host_doubles(
        self,
        root: Path,
        agent_side_effect: object,
        render_side_effect: object,
        *,
        request: dict[str, object] | None = None,
    ):
        workflow_request = request or _request()
        source_request = root / "source-request.json"
        source_request.write_text(json.dumps(workflow_request), encoding="utf-8")
        out_dir = root / "job"
        order: list[str] = []

        def render(*args: object, **kwargs: object) -> dict[str, object]:
            order.append("wolfram_render")
            if isinstance(render_side_effect, list):
                value = render_side_effect.pop(0)
            else:
                value = render_side_effect
            if isinstance(value, Exception):
                raise value
            return value

        def compile_spec(*args: object, **kwargs: object) -> dict[str, object]:
            order.append("tikz_compile")
            return {"status": "ok", "renderer_spec": {"status": "ready"}}

        def preview(*args: object, **kwargs: object) -> dict[str, object]:
            order.append("preview_render")
            round_dir = Path(args[1])
            preview_path = round_dir / "rendered" / "prompt.preview.png"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_bytes(b"preview")
            return {"status": "ok", "tikz_fragment_path": "rendered/prompt.fragment.tex"}

        def audit(*args: object, **kwargs: object) -> dict[str, object]:
            order.append("audit")
            return {"status": "ok", "audit_result": {"status": "pass", "issues": []}}

        def finalize(*args: object, **kwargs: object) -> dict[str, object]:
            order.append("finalize_round")
            return {"status": "ok"}

        agent_patch = (
            patch.object(workflow, "run_codex_diagram_agent", side_effect=agent_side_effect)
            if isinstance(agent_side_effect, list)
            else patch.object(workflow, "run_codex_diagram_agent", return_value=agent_side_effect)
        )
        with (
            agent_patch as agent,
            patch.object(workflow, "render_candidate_action", side_effect=render),
            patch.object(workflow, "compile_spec_action", side_effect=compile_spec),
            patch.object(workflow, "render_geometry_spec", side_effect=preview),
            patch.object(workflow, "audit_diagram_action", side_effect=audit),
            patch.object(workflow, "finalize_round_action", side_effect=finalize),
            patch.object(
                workflow,
                "_validate_final_agent_artifacts",
                return_value={"status": "ok"},
            ),
        ):
            result = workflow.run_workflow(workflow_request, out_dir, source_request)
        return result, order, agent, out_dir

    def test_normal_success_uses_one_scene_writer_then_host_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, out_dir = self._run_with_host_doubles(
                Path(tmp),
                _agent_output(),
                _render_ok(),
            )
            selected_round = json.loads(
                (out_dir / "agent_result.json").read_text()
            )["selected_round"]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(agent.call_count, 1)
        self.assertEqual(
            order,
            ["wolfram_render", "tikz_compile", "preview_render", "audit", "finalize_round"],
        )
        self.assertEqual(selected_round, 0)

    def test_wolfram_failure_stops_for_human_without_second_scene_writer(self) -> None:
        first_failure = {
            "status": "failed",
            "render_result": {
                "success": False,
                "fail_type": "no_solution",
                "message": "constraints are inconsistent",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, out_dir = self._run_with_host_doubles(
                Path(tmp),
                [_agent_output("first"), _agent_output("repair")],
                [first_failure, _render_ok()],
            )

            events = (out_dir / "workflow_events.jsonl").read_text(encoding="utf-8")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fail_type"], "human_confirmation_required")
        self.assertEqual(agent.call_count, 1)
        self.assertEqual(order, ["wolfram_render"])
        self.assertFalse((out_dir / "rounds" / "round_1" / "repair_request.json").exists())
        self.assertIn('"original_fail_type": "no_solution"', events)

    def test_wolfram_syntax_failure_gets_exactly_one_agent_repair(self) -> None:
        syntax_failure = {
            "status": "failed",
            "render_result": {
                "success": False,
                "fail_type": "invalid_head",
                "message": "unsupported Wolfram head",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, out_dir = self._run_with_host_doubles(
                Path(tmp),
                [_agent_output("first"), _agent_output("syntax-repair")],
                [syntax_failure, _render_ok()],
            )
            repair = json.loads(
                (out_dir / "rounds" / "round_1" / "repair_request.json").read_text()
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(order.count("wolfram_render"), 2)
        self.assertEqual(order.count("finalize_round"), 1)
        self.assertEqual(repair["failure_type"], "invalid_head")

    def test_second_wolfram_syntax_failure_stops_for_human(self) -> None:
        syntax_failure = {
            "status": "failed",
            "render_result": {
                "success": False,
                "fail_type": "invalid_head",
                "message": "unsupported Wolfram head",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, _out_dir = self._run_with_host_doubles(
                Path(tmp),
                [_agent_output("first"), _agent_output("syntax-repair")],
                [syntax_failure, syntax_failure],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fail_type"], "human_confirmation_required")
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(order, ["wolfram_render", "wolfram_render"])

    def test_environment_failure_does_not_call_scene_writer_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, _out_dir = self._run_with_host_doubles(
                Path(tmp),
                _agent_output(),
                FileNotFoundError("WolframKernel is missing"),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fail_type"], "host_environment_or_invariant_failed")
        self.assertEqual(agent.call_count, 1)
        self.assertEqual(order, ["wolfram_render"])

    def test_scene_writer_can_stop_before_wolfram_for_human_confirmation(self) -> None:
        failure = {
            "status": "failed",
            "render_result": {
                "success": False,
                "fail_type": "no_solution",
                "message": "constraints are inconsistent",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, _out_dir = self._run_with_host_doubles(
                Path(tmp),
                {
                    **_agent_output("uncertain"),
                    "status": "needs_human_confirmation",
                    "confirmation_question": "Please confirm triangle correspondence.",
                    "scene_code": "",
                },
                failure,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fail_type"], "human_confirmation_required")
        self.assertIn("triangle correspondence", result["message"])
        self.assertEqual(agent.call_count, 1)
        self.assertEqual(order, [])

    def test_solution_scene_writer_receives_finalized_base_point_context(self) -> None:
        solution_request = {
            "job_id": "q1-solution",
            "diagram_job_id": "q1-solution",
            "variant": "solution",
            "diagram_variant": "solution",
            "disclosure_policy": "annotated",
            "reuse_geometry_from": "q1-prompt",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_dir = root / "q1-prompt"
            base_dir.mkdir()
            (base_dir / "final_renderer_spec.json").write_text(
                json.dumps({"points": {"A": [0, 2], "B": [-2, 0], "C": [2, 0]}}),
                encoding="utf-8",
            )
            result, _order, agent, out_dir = self._run_with_host_doubles(
                root,
                _agent_output(),
                _render_ok(),
                request=solution_request,
            )
            scene_payload = json.loads(
                (out_dir / "rounds" / "round_0" / "scene_payload.json").read_text()
            )

        prepared_request = agent.call_args.kwargs["request"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            prepared_request["locked_base_points"],
            {"A": [0.0, 2.0], "B": [-2.0, 0.0], "C": [2.0, 0.0]},
        )
        self.assertEqual(
            scene_payload["solution_reuse"]["lock_strategy"],
            "host_injected_exact_coordinates",
        )

    def test_missing_solution_base_fails_before_scene_writer(self) -> None:
        solution_request = {
            "job_id": "q1-solution",
            "diagram_job_id": "q1-solution",
            "variant": "solution",
            "diagram_variant": "solution",
            "disclosure_policy": "annotated",
            "reuse_geometry_from": "missing-prompt",
        }
        with tempfile.TemporaryDirectory() as tmp:
            result, order, agent, _out_dir = self._run_with_host_doubles(
                Path(tmp),
                _agent_output(),
                _render_ok(),
                request=solution_request,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fail_type"], "host_environment_or_invariant_failed")
        self.assertEqual(agent.call_count, 0)
        self.assertEqual(order, [])

    def test_visual_accept_runs_after_deterministic_audit_before_finalize(self) -> None:
        request = _request()
        request["execution_plan"] = {
            "max_candidate_rounds": 2,
            "requires_visual_decision": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_request = root / "source-request.json"
            source_request.write_text(json.dumps(request), encoding="utf-8")
            out_dir = root / "job"
            order: list[str] = []

            def render(*args: object, **kwargs: object) -> dict[str, object]:
                order.append("wolfram_render")
                return _render_ok()

            def compile_spec(*args: object, **kwargs: object) -> dict[str, object]:
                order.append("tikz_compile")
                return {"status": "ok"}

            def preview(spec: Path, round_dir: Path, **kwargs: object) -> dict[str, object]:
                del spec, kwargs
                order.append("preview_render")
                path = round_dir / "rendered/prompt.preview.png"
                path.parent.mkdir(parents=True)
                path.write_bytes(b"preview")
                return {"status": "ok", "preview_png_path": "rendered/prompt.preview.png"}

            def audit(*args: object, **kwargs: object) -> dict[str, object]:
                order.append("audit")
                return {"status": "ok", "audit_result": {"status": "pass", "issues": []}}

            def finalize(*args: object, **kwargs: object) -> dict[str, object]:
                order.append("finalize_round")
                return {"status": "ok"}

            with (
                patch.object(
                    workflow,
                    "run_codex_diagram_agent",
                    side_effect=[
                        _agent_output(),
                        {"decision": "accept", "reason": "清晰", "patch": {}},
                    ],
                ) as agent,
                patch.object(workflow, "render_candidate_action", side_effect=render),
                patch.object(workflow, "compile_spec_action", side_effect=compile_spec),
                patch.object(workflow, "render_geometry_spec", side_effect=preview),
                patch.object(workflow, "audit_diagram_action", side_effect=audit),
                patch.object(workflow, "finalize_round_action", side_effect=finalize),
                patch.object(workflow, "_validate_final_agent_artifacts", return_value={"status": "ok"}),
            ):
                result = workflow.run_workflow(request, out_dir, source_request)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(
            order,
            ["wolfram_render", "tikz_compile", "preview_render", "audit", "finalize_round"],
        )

    def test_visual_revision_uses_next_candidate_without_second_scene_writer(self) -> None:
        request = _request()
        request["execution_plan"] = {
            "max_candidate_rounds": 2,
            "requires_visual_decision": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_request = root / "source-request.json"
            source_request.write_text(json.dumps(request), encoding="utf-8")
            out_dir = root / "job"
            preview_counter = 0

            def preview(spec: Path, round_dir: Path, **kwargs: object) -> dict[str, object]:
                nonlocal preview_counter
                del spec, kwargs
                preview_counter += 1
                path = round_dir / "rendered/prompt.preview.png"
                path.parent.mkdir(parents=True)
                path.write_bytes(f"preview-{preview_counter}".encode())
                return {"status": "ok", "preview_png_path": "rendered/prompt.preview.png"}

            with (
                patch.object(
                    workflow,
                    "run_codex_diagram_agent",
                    side_effect=[
                        _agent_output(),
                        {
                            "decision": "revise",
                            "reason": "标签遮挡",
                            "patch": {
                                "scene_code": _agent_output()["scene_code"],
                                "diagram_spec_json": "",
                            },
                        },
                        {"decision": "accept", "reason": "已修复", "patch": {}},
                    ],
                ) as agent,
                patch.object(workflow, "render_candidate_action", return_value=_render_ok()),
                patch.object(workflow, "compile_spec_action", return_value={"status": "ok"}),
                patch.object(workflow, "render_geometry_spec", side_effect=preview),
                patch.object(
                    workflow,
                    "audit_diagram_action",
                    return_value={"status": "ok", "audit_result": {"status": "pass", "issues": []}},
                ),
                patch.object(workflow, "finalize_round_action", return_value={"status": "ok"}),
                patch.object(workflow, "_validate_final_agent_artifacts", return_value={"status": "ok"}),
            ):
                result = workflow.run_workflow(request, out_dir, source_request)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(agent.call_count, 3)
        self.assertEqual(preview_counter, 2)

    def test_forbidden_visual_fields_are_ignored_but_safe_patch_is_rendered(self) -> None:
        request = _request()
        request["execution_plan"] = {
            "max_candidate_rounds": 2,
            "requires_visual_decision": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_request = root / "source-request.json"
            source_request.write_text(json.dumps(request), encoding="utf-8")
            out_dir = root / "job"

            def preview(spec: Path, round_dir: Path, **kwargs: object) -> dict[str, object]:
                del spec, kwargs
                path = round_dir / "rendered/prompt.preview.png"
                path.parent.mkdir(parents=True)
                path.write_bytes(b"preview")
                return {"status": "ok", "preview_png_path": "rendered/prompt.preview.png"}

            with (
                patch.object(
                    workflow,
                    "run_codex_diagram_agent",
                    side_effect=[
                        _agent_output(),
                        {
                            "decision": "revise",
                            "reason": "add a marker without moving points",
                            "patch": {
                                "diagram_spec_json": json.dumps(
                                    {
                                        "points": {"A": [0, 0]},
                                        "labels": {"A": {"text": "A", "placement": "above"}},
                                    }
                                )
                            },
                        },
                        {"decision": "accept", "reason": "clear", "patch": {}},
                    ],
                ) as agent,
                patch.object(workflow, "render_candidate_action", return_value=_render_ok()),
                patch.object(workflow, "compile_spec_action", return_value={"status": "ok"}),
                patch.object(workflow, "render_geometry_spec", side_effect=preview),
                patch.object(
                    workflow,
                    "audit_diagram_action",
                    return_value={"status": "ok", "audit_result": {"status": "pass", "issues": []}},
                ),
                patch.object(workflow, "finalize_round_action", return_value={"status": "ok"}),
                patch.object(workflow, "_validate_final_agent_artifacts", return_value={"status": "ok"}),
            ):
                result = workflow.run_workflow(request, out_dir, source_request)

            round_one_scene = json.loads(
                (out_dir / "rounds" / "round_1" / "scene_payload.json").read_text()
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(agent.call_count, 3)
        self.assertEqual(round_one_scene["diagram_spec"]["points"], {})
        self.assertEqual(round_one_scene["diagram_spec"]["labels"]["A"]["text"], "A")


if __name__ == "__main__":
    unittest.main()
