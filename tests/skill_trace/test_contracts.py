from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_trace.contracts import (  # noqa: E402
    CognitiveLayer,
    ReuseLevel,
    SkillTraceDraft,
    find_compound_action_warnings,
)


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "draft_id": "draft_demo",
        "codex_thread_id": "thr_demo",
        "problem_case": {
            "title": "比例线段",
            "raw_problem": "已知 AB:BC=2:3，求 ED。",
            "provided_solution": "",
            "expected_thinking": "",
            "topic_tags": ["ratio"],
        },
        "trace_summary": {
            "target": "求 ED",
            "core_strategy": "目标驱动选关系",
        },
        "steps": [
            {
                "step_id": "s1",
                "order": 1,
                "name": "先看目标量",
                "cognitive_layer": "L3_strategy",
                "reuse_level": "generic_action",
                "student_action_norm": "先确定题目要求的是 ED",
            },
            {
                "step_id": "s2",
                "order": 2,
                "name": "找对应线段",
                "cognitive_layer": "L0_structure",
                "reuse_level": "domain_action",
                "student_action_norm": "找到 ED 对应 BC",
            },
        ],
    }
    payload.update(overrides)
    return payload


class SkillTraceContractsTest(unittest.TestCase):
    def test_valid_payload_builds_draft(self) -> None:
        draft = SkillTraceDraft.model_validate(valid_payload())

        self.assertEqual(draft.schema_version, "skill_trace_draft.v0")
        self.assertEqual(draft.steps[0].cognitive_layer, CognitiveLayer.L3_STRATEGY)
        self.assertEqual(draft.steps[1].reuse_level, ReuseLevel.DOMAIN_ACTION)

    def test_rejects_duplicate_order(self) -> None:
        payload = valid_payload()
        steps = payload["steps"]
        assert isinstance(steps, list)
        steps[1]["order"] = 1

        with self.assertRaisesRegex(ValidationError, "order values must be unique"):
            SkillTraceDraft.model_validate(payload)

    def test_rejects_missing_strategy_step(self) -> None:
        payload = valid_payload()
        steps = payload["steps"]
        assert isinstance(steps, list)
        steps[0]["cognitive_layer"] = "L2_execution"

        with self.assertRaisesRegex(ValidationError, "L3_strategy"):
            SkillTraceDraft.model_validate(payload)

    def test_rejects_missing_structure_or_encoding_step(self) -> None:
        payload = valid_payload()
        steps = payload["steps"]
        assert isinstance(steps, list)
        steps[1]["cognitive_layer"] = "L2_execution"

        with self.assertRaisesRegex(ValidationError, "L0_structure or L1_encoding"):
            SkillTraceDraft.model_validate(payload)

    def test_warns_for_likely_compound_action(self) -> None:
        payload = valid_payload()
        steps = payload["steps"]
        assert isinstance(steps, list)
        steps[1]["student_action_norm"] = "找到对应关系并计算 ED 的长度"
        draft = SkillTraceDraft.model_validate(payload)

        self.assertEqual(
            find_compound_action_warnings(draft),
            ["s2: student_action_norm may contain multiple actions; split it into separate steps"],
        )


if __name__ == "__main__":
    unittest.main()

