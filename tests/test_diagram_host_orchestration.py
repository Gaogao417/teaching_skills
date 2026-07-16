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
    def _run_with_host_doubles(self, root: Path, agent_side_effect: object, render_side_effect: object):
        source_request = root / "source-request.json"
        source_request.write_text(json.dumps(_request()), encoding="utf-8")
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
            result = workflow.run_workflow(_request(), out_dir, source_request)
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

    def test_repairable_failure_calls_scene_writer_exactly_once_more(self) -> None:
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

            repair = json.loads(
                (out_dir / "rounds" / "round_1" / "repair_request.json").read_text()
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(order.count("wolfram_render"), 2)
        self.assertEqual(order.count("finalize_round"), 1)
        self.assertEqual(repair["failure_type"], "no_solution")

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

    def test_second_repairable_failure_stops_after_two_scene_writer_calls(self) -> None:
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
                [_agent_output("first"), _agent_output("repair")],
                [failure, failure],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fail_type"], "no_solution")
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(order, ["wolfram_render", "wolfram_render"])


if __name__ == "__main__":
    unittest.main()
