from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "scripts" / "diagram_workflow"
CORE = WORKFLOW / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(WORKFLOW))
sys.path.insert(0, str(CORE))

from agent_prompt import diagram_agent_prompt  # noqa: E402
from diagram_contracts import (  # noqa: E402
    DiagramEngineOptions,
    DiagramHumanRevision,
    DiagramJobRequest,
)


class DiagramAgentReviewContractTest(unittest.TestCase):
    def test_agent_review_retries_default_to_zero_but_remain_opt_in(self) -> None:
        self.assertEqual(DiagramEngineOptions().max_retries, 0)
        self.assertEqual(DiagramEngineOptions(max_retries=1).max_retries, 1)

    def test_zero_retry_prompt_runs_one_fixed_round_without_visual_self_review(self) -> None:
        request = _request().model_dump(mode="json")

        prompt = diagram_agent_prompt(request, Path("/tmp/job"), Path("/tmp/job/request.json"), skill_names="test")

        self.assertIn("Use exactly round index 0", prompt)
        self.assertIn("Agent visual review is disabled", prompt)
        self.assertIn("deterministic audit passes, finalize immediately", prompt)
        self.assertNotIn("inspect the rendered preview PNG yourself", prompt)
        self.assertNotIn("repair the next round", prompt)

    def test_positive_retry_explicitly_restores_visual_review_loop(self) -> None:
        request = _request(max_retries=1).model_dump(mode="json")

        prompt = diagram_agent_prompt(request, Path("/tmp/job"), Path("/tmp/job/request.json"), skill_names="test")

        self.assertIn("initial + 1 repairs", prompt)
        self.assertIn("inspect the rendered preview PNG yourself", prompt)
        self.assertIn("repair the next round", prompt)

    def test_human_revision_is_typed_and_names_exact_next_round(self) -> None:
        revision = DiagramHumanRevision(
            action_id="action-1",
            review_id="review_0001",
            feedback="图例不要遮住辅助线，点 E 的标签向左移。",
            base_round=3,
            requested_round=4,
        )
        request = _request(human_revision=revision)

        prompt = diagram_agent_prompt(
            request.model_dump(mode="json"),
            Path("/tmp/job"),
            Path("/tmp/job/request.json"),
            skill_names="test",
        )

        self.assertEqual(request.human_revision.requested_round, 4)
        self.assertEqual(request.engine_options.max_retries, 0)
        self.assertIn("Use exactly round index 4", prompt)
        self.assertIn("图例不要遮住辅助线，点 E 的标签向左移。", prompt)
        self.assertIn("base Round 3", prompt)


def _request(
    *,
    max_retries: int | None = None,
    human_revision: object | None = None,
) -> DiagramJobRequest:
    options = {} if max_retries is None else {"max_retries": max_retries}
    payload: dict[str, object] = {
        "job_id": "q1-prompt",
        "assignment_id": "human-review-test",
        "slot_id": "q1.prompt",
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "engine_options": options,
    }
    if human_revision is not None:
        payload["human_revision"] = human_revision
    return DiagramJobRequest(**payload)


if __name__ == "__main__":
    unittest.main()
