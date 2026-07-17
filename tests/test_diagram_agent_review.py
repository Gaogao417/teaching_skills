from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "scripts" / "diagram_workflow"
CORE = WORKFLOW / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(WORKFLOW))
sys.path.insert(0, str(CORE))

from agent_prompt import diagram_agent_prompt, scene_writer_prompt  # noqa: E402
from agent_runner import _record_preview_inspection  # noqa: E402
from diagram_contracts import (  # noqa: E402
    DiagramEngineOptions,
    DiagramHumanRevision,
    DiagramJobRequest,
)
from tools import (  # noqa: E402
    _resolved_codex_config,
    _skill_inputs_for_request,
    finalize_round_action,
)


class DiagramAgentReviewContractTest(unittest.TestCase):
    def test_diagram_agent_uses_pinned_default_codex_model(self) -> None:
        self.assertEqual(_resolved_codex_config({})["codex_model"], "gpt-5.5")
        self.assertEqual(
            _resolved_codex_config({"codex_model": "explicit-model"})["codex_model"],
            "explicit-model",
        )

    def test_agent_review_retries_default_to_zero_but_remain_opt_in(self) -> None:
        self.assertEqual(DiagramEngineOptions().max_retries, 0)
        self.assertEqual(DiagramEngineOptions(max_retries=1).max_retries, 1)

    def test_normal_scene_writer_prompt_has_no_workflow_commands_or_visual_review(self) -> None:
        request = _request().model_dump(mode="json")

        prompt = scene_writer_prompt(request, skill_names="test")

        self.assertIn("SceneWriterOutput", prompt)
        self.assertIn("The Python host will", prompt)
        self.assertNotIn("--action", prompt)
        self.assertNotIn("render_geometry_spec.py", prompt)
        self.assertNotIn("inspect the rendered preview PNG yourself", prompt)

    def test_normal_scene_writer_repair_prompt_contains_only_failure_evidence(self) -> None:
        request = _request(max_retries=1).model_dump(mode="json")

        prompt = scene_writer_prompt(
            request,
            skill_names="test",
            repair_request={
                "failure_type": "no_solution",
                "failed_checks": ["wolfram_failed: no_solution"],
            },
        )

        self.assertIn("only automatic repair attempt", prompt)
        self.assertIn("wolfram_failed: no_solution", prompt)
        self.assertNotIn("--action", prompt)

    def test_solution_scene_writer_leaves_exact_base_locks_to_host(self) -> None:
        request = _request().model_dump(mode="json")
        request.update(
            {
                "variant": "solution",
                "diagram_variant": "solution",
                "reuse_geometry_from": "q1-prompt",
                "locked_base_points": {
                    "A": [0.0, 2.0],
                    "B": [-2.0, 0.0],
                    "C": [2.0, 0.0],
                },
            }
        )

        prompt = scene_writer_prompt(request, skill_names="test")

        self.assertIn("locked_base_points", prompt)
        self.assertIn("is Host-owned context", prompt)
        self.assertIn("The Host injects the exact point", prompt)
        self.assertIn("equalities before Wolfram runs", prompt)
        self.assertIn("copy their coordinates into scene_code", prompt)
        self.assertIn("rather than a property list", prompt)

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
        self.assertIn("round_3/rendered/prompt.preview.png", prompt)
        self.assertIn("round_4/rendered/prompt.preview.png", prompt)
        self.assertIn("image-view tool", prompt)
        self.assertIn("overwrite and rerender", prompt)
        self.assertIn("strictly below 180", prompt)
        self.assertIn("near-circle", prompt)
        self.assertNotIn("Agent visual review is disabled", prompt)
        self.assertNotIn("finalize immediately", prompt)

    def test_human_revision_skill_is_injected_only_for_revision_requests(self) -> None:
        ordinary = _skill_inputs_for_request(_request().model_dump(mode="json"))
        revision = DiagramHumanRevision(
            action_id="action-1",
            review_id="review_0001",
            feedback="角标错了",
            base_round=0,
            requested_round=1,
        )
        revised = _skill_inputs_for_request(
            _request(human_revision=revision).model_dump(mode="json")
        )

        self.assertEqual(
            [item["name"] for item in ordinary],
            [
                "math-geometry-diagram-renderer",
                "wolfram-geometricscene-reference",
                "dimensionless-constraints-library",
            ],
        )
        skill = next(item for item in revised if item["name"] == "diagram-human-revision")
        self.assertTrue(Path(skill["path"]).is_file())
        self.assertTrue(skill["path"].endswith("diagram-human-revision/SKILL.md"))

    def test_visual_inspection_evidence_requires_two_image_views_and_tracks_preview_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "rounds/round_0/rendered/prompt.preview.png"
            current = root / "rounds/round_1/rendered/prompt.preview.png"
            base.parent.mkdir(parents=True)
            current.parent.mkdir(parents=True)
            base.write_bytes(b"base-preview")
            current.write_bytes(b"current-preview")

            _record_preview_inspection(
                out_dir=str(root), base_round=0, requested_round=1, inspection_count=1
            )
            evidence = root / "rounds/round_1/visual_inspection.json"
            self.assertFalse(evidence.exists())

            _record_preview_inspection(
                out_dir=str(root), base_round=0, requested_round=1, inspection_count=2
            )
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["inspection_count"], 2)
            self.assertEqual(len(payload["base_preview_sha256"]), 64)
            self.assertEqual(len(payload["current_preview_sha256"]), 64)

    def test_human_revision_cannot_finalize_without_preview_inspection_evidence(self) -> None:
        revision = DiagramHumanRevision(
            action_id="action-1",
            review_id="review_0001",
            feedback="角标错了",
            base_round=0,
            requested_round=1,
        )
        request = _request(human_revision=revision).model_dump(mode="json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "rounds/round_1"
            round_dir.mkdir(parents=True)
            files = {}
            for name in (
                "scene_payload.json",
                "render_result.json",
                "final_renderer_spec.json",
                "renderer_result.json",
            ):
                path = round_dir / name
                path.write_text("{}", encoding="utf-8")
                files[name] = path
            audit = round_dir / "audit_result.json"
            audit.write_text('{"status":"pass"}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "opening the base and current preview"):
                finalize_round_action(
                    request,
                    files["scene_payload.json"],
                    files["render_result.json"],
                    files["final_renderer_spec.json"],
                    files["renderer_result.json"],
                    audit,
                    root,
                    1,
                )


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
