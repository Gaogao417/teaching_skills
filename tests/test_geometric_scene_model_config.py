from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"))

from tools import (  # noqa: E402
    _float_config,
    _inject_solution_base_locks,
    _prepare_solution_reuse_context,
    _resolved_codex_config,
    _skill_inputs_for_group,
    _skills_root,
    _solution_reuse_check,
    _validate_scene_code,
    render_candidate_action,
)
from agent_prompt import agent_result_schema, scene_writer_output_schema  # noqa: E402
from agent_runner import _normalize_scene_writer_wire_payload  # noqa: E402


class GeometricSceneCodexConfigTest(unittest.TestCase):
    def test_empty_runtime_values_use_pinned_diagram_agent_defaults(self) -> None:
        with patch.dict(os.environ, {"CODEX_DIAGRAM_BIN": ""}):
            config = _resolved_codex_config(
                {
                    "codex_model": "",
                    "codex_bin": "",
                    "codex_timeout_s": None,
                }
            )

        self.assertEqual(config["codex_model"], "gpt-5.5")
        self.assertEqual(config["model_reasoning_effort"], "medium")
        self.assertEqual(config["service_tier"], "fast")
        self.assertIs(config["fast_mode"], True)
        self.assertEqual(config["codex_bin"], "")
        self.assertEqual(config["codex_timeout_s"], 120.0)
        self.assertNotIn("base_url", config)
        self.assertNotIn("api_key_env", config)

    def test_codex_bin_accepts_environment_override(self) -> None:
        with patch.dict(os.environ, {"CODEX_DIAGRAM_BIN": "/opt/codex"}):
            config = _resolved_codex_config({"codex_bin": ""})

        self.assertEqual(config["codex_bin"], "/opt/codex")

    def test_codex_bin_slot_config_overrides_environment(self) -> None:
        with patch.dict(os.environ, {"CODEX_DIAGRAM_BIN": "/opt/codex"}):
            config = _resolved_codex_config({"codex_bin": "/custom/codex"})

        self.assertEqual(config["codex_bin"], "/custom/codex")

    def test_codex_model_accepts_legacy_model_alias(self) -> None:
        config = _resolved_codex_config({"model": "gpt-test", "codex_timeout_s": "30"})

        self.assertEqual(config["codex_model"], "gpt-test")
        self.assertEqual(config["codex_timeout_s"], 30.0)

    def test_diagram_agent_runtime_defaults_can_be_overridden_per_job(self) -> None:
        config = _resolved_codex_config(
            {
                "codex_model": "gpt-test",
                "model_reasoning_effort": "high",
                "service_tier": "flex",
                "fast_mode": False,
            }
        )

        self.assertEqual(config["codex_model"], "gpt-test")
        self.assertEqual(config["model_reasoning_effort"], "high")
        self.assertEqual(config["service_tier"], "flex")
        self.assertIs(config["fast_mode"], False)

    def test_openai_compatible_fields_are_ignored(self) -> None:
        config = _resolved_codex_config(
            {
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key_env": "DASHSCOPE_API_KEY",
                "codex_model": "gpt-test",
            }
        )

        self.assertEqual(config["codex_model"], "gpt-test")
        self.assertNotIn("base_url", config)
        self.assertNotIn("api_key_env", config)

    def test_float_config_uses_default_for_none_and_empty_string(self) -> None:
        self.assertEqual(_float_config({"codex_timeout_s": None}, "codex_timeout_s", 120), 120.0)
        self.assertEqual(_float_config({"codex_timeout_s": ""}, "codex_timeout_s", 120), 120.0)
        self.assertEqual(_float_config({"codex_timeout_s": "45"}, "codex_timeout_s", 120), 45.0)

    def test_skill_loader_uses_repo_codex_skills(self) -> None:
        expected_root = (
            ROOT
            / "scripts"
            / "diagram_workflow"
            / "geometry_diagram_workflow"
            / ".codex"
            / "skills"
        )
        self.assertEqual(_skills_root(), expected_root)

        inputs = _skill_inputs_for_group("generate")

        inputs_by_name = {item["name"]: item for item in inputs}
        self.assertIn("math-geometry-diagram-renderer", inputs_by_name)
        self.assertIn("wolfram-geometricscene-reference", inputs_by_name)
        reference_path = Path(inputs_by_name["wolfram-geometricscene-reference"]["path"])
        self.assertTrue(reference_path.exists())
        self.assertEqual(reference_path.parents[1], expected_root)

    def test_agent_output_schema_is_strict(self) -> None:
        schema = agent_result_schema()

        self.assertFalse(schema["additionalProperties"])
        self.assertCountEqual(schema["required"], schema["properties"].keys())

    def test_scene_writer_output_schema_is_strict_and_has_no_workflow_paths(self) -> None:
        schema = scene_writer_output_schema()

        self.assertFalse(schema["additionalProperties"])
        self.assertCountEqual(schema["required"], schema["properties"].keys())
        self.assertNotIn("workflow_result_path", schema["properties"])
        self.assertNotIn("status", schema["properties"])

        def assert_closed_objects(value: object) -> None:
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(value.get("additionalProperties"), False)
                    self.assertCountEqual(
                        value.get("required", []),
                        value.get("properties", {}).keys(),
                    )
                for child in value.values():
                    assert_closed_objects(child)
            elif isinstance(value, list):
                for child in value:
                    assert_closed_objects(child)

        assert_closed_objects(schema)

    def test_scene_writer_wire_labels_normalize_to_scene_payload_map(self) -> None:
        payload = _normalize_scene_writer_wire_payload(
            {
                "diagram_spec": {
                    "labels": [
                        {
                            "name": "A",
                            "text": "A",
                            "placement": "above",
                            "dx": 0,
                            "dy": -24,
                            "show_point": True,
                        }
                    ]
                }
            }
        )

        self.assertEqual(payload["diagram_spec"]["labels"]["A"]["text"], "A")
        self.assertNotIn("name", payload["diagram_spec"]["labels"]["A"])

    def test_scene_code_rejects_nested_point_list(self) -> None:
        _validate_scene_code("GeometricScene[{A, B, C}, {A == {0, 1}}]")

        _validate_scene_code(
            "GeometricScene[{{A, B, C}, {r}}, {r > 0, Element[A, Circle[B, r]]}]"
        )

        with self.assertRaisesRegex(ValueError, "flat point list or the scalar-parameter form"):
            _validate_scene_code("GeometricScene[{{A, B, C}}, {A == {0, 1}}]")

    def test_scene_code_rejects_non_native_segment_and_ray_constructors(self) -> None:
        for constructor in ("LineSegment[{A, B}]", "Ray[{A, B}]"):
            with self.subTest(constructor=constructor), self.assertRaisesRegex(
                ValueError, "unsupported region constructor"
            ):
                _validate_scene_code(
                    f"GeometricScene[{{A, B, P}}, {{Element[P, {constructor}]}}]"
                )

    def test_scene_code_rejects_multiple_fixed_triangle_vertices(self) -> None:
        with self.assertRaisesRegex(ValueError, "fixes multiple triangle vertices"):
            _validate_scene_code(
                "GeometricScene[{A, B, C}, "
                "{A == {0, 0}, B == {3, 4}, "
                "EuclideanDistance[A, B] == 5}]"
            )

    def test_scene_code_allows_fixed_metrics_for_solution_reuse(self) -> None:
        _validate_scene_code(
            "GeometricScene[{A, B, C, D}, "
            "{A == {0, 0}, B == {3, 4}, C == {8, 0}, "
            "EuclideanDistance[A, D] == EuclideanDistance[A, B]}]",
            allow_fixed_metrics=True,
        )

    def test_scene_code_accepts_symbolic_triangle_with_horizontal_base(self) -> None:
        _validate_scene_code(
            'GeometricScene[{A, B, C}, {'
            'EuclideanDistance[A, B] == 10, '
            'GeometricAssertion[Line[{A, C}], "Horizontal"]}]'
        )

    def test_solution_reuse_context_loads_finalized_base_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            base_dir = jobs_dir / "q1-prompt"
            base_dir.mkdir(parents=True)
            (base_dir / "final_renderer_spec.json").write_text(
                json.dumps({"points": {"A": [0, 2], "B": [-2, 0], "C": [2, 0]}}),
                encoding="utf-8",
            )

            prepared = _prepare_solution_reuse_context(
                {
                    "variant": "solution",
                    "diagram_variant": "solution",
                    "reuse_geometry_from": "q1-prompt",
                },
                jobs_dir / "q1-solution",
            )

        self.assertEqual(
            prepared["locked_base_points"],
            {"A": [0.0, 2.0], "B": [-2.0, 0.0], "C": [2.0, 0.0]},
        )
        self.assertEqual(prepared["locked_base_point_names"], ["A", "B", "C"])

    def test_host_injects_locks_into_scalar_parameter_scene(self) -> None:
        scene_code = (
            "GeometricScene[{{A, B, C, D}, {theta}}, "
            "{0 < theta < Pi, D == RotationTransform[theta, A][B]}]"
        )

        injected = _inject_solution_base_locks(
            scene_code,
            {"A": [0, 2], "B": [-2, 0], "C": [2, 0]},
        )

        self.assertIn("A == {0, 2}", injected)
        self.assertIn("B == {-2, 0}", injected)
        self.assertIn("C == {2, 0}", injected)
        self.assertLess(injected.index("A == {0, 2}"), injected.index("0 < theta"))
        self.assertEqual(
            _inject_solution_base_locks(
                injected,
                {"A": [0, 2], "B": [-2, 0], "C": [2, 0]},
            ),
            injected,
        )

    def test_render_candidate_locks_prompt_points_before_wolfram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            base_dir = jobs_dir / "q1-prompt"
            out_dir = jobs_dir / "q1-solution"
            round_dir = out_dir / "rounds" / "round_0"
            base_dir.mkdir(parents=True)
            round_dir.mkdir(parents=True)
            (base_dir / "final_renderer_spec.json").write_text(
                json.dumps({"points": {"A": [0, 2], "B": [-2, 0], "C": [2, 0]}}),
                encoding="utf-8",
            )
            scene_payload_path = round_dir / "scene_payload.json"
            scene_payload_path.write_text(
                json.dumps(
                    {
                        "scene_code": (
                            "GeometricScene[{A, B, C, H}, "
                            "{Element[H, Line[{B, C}]]}]"
                        ),
                        "points": ["A", "B", "C", "H"],
                        "point_roles": {
                            "anchors": ["A", "B", "C"],
                            "constructed": [],
                            "auxiliary": ["H"],
                        },
                        "diagram_spec": {},
                    }
                ),
                encoding="utf-8",
            )
            request = {
                "variant": "solution",
                "diagram_variant": "solution",
                "disclosure_policy": "annotated",
                "reuse_geometry_from": "q1-prompt",
            }
            render_result = {
                "success": True,
                "fail_type": "",
                "message": "",
                "solve_time_s": 0.01,
                "parameters": [
                    ["A", [0, 2]],
                    ["B", [-2, 0]],
                    ["C", [2, 0]],
                    ["H", [0, 0]],
                ],
                "render_image_requested": False,
                "image_path": "",
            }

            with patch("tools._render_scene", return_value=render_result) as render:
                result = render_candidate_action(
                    request,
                    scene_payload_path,
                    out_dir,
                    0,
                )

            persisted = json.loads(scene_payload_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertTrue(
            result["render_result"]["solution_reuse_check"]["locked_points_same"]
        )
        self.assertIn("A == {0, 2}", persisted["scene_code"])
        self.assertEqual(
            persisted["solution_reuse"]["lock_strategy"],
            "host_injected_exact_coordinates",
        )
        rendered_scene = render.call_args.args[0]
        self.assertIn("C == {2, 0}", rendered_scene)

    def test_render_candidate_rejects_solution_that_omits_base_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            base_dir = jobs_dir / "q1-prompt"
            out_dir = jobs_dir / "q1-solution"
            round_dir = out_dir / "rounds" / "round_0"
            base_dir.mkdir(parents=True)
            round_dir.mkdir(parents=True)
            (base_dir / "final_renderer_spec.json").write_text(
                json.dumps({"points": {"A": [0, 2], "B": [-2, 0], "C": [2, 0]}}),
                encoding="utf-8",
            )
            scene_payload_path = round_dir / "scene_payload.json"
            scene_payload_path.write_text(
                json.dumps(
                    {
                        "scene_code": "GeometricScene[{A, B}, {}]",
                        "points": ["A", "B"],
                        "point_roles": {
                            "anchors": ["A", "B"],
                            "constructed": [],
                            "auxiliary": [],
                        },
                        "diagram_spec": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "omits locked base point.*C"):
                render_candidate_action(
                    {
                        "variant": "solution",
                        "diagram_variant": "solution",
                        "reuse_geometry_from": "q1-prompt",
                    },
                    scene_payload_path,
                    out_dir,
                    0,
                )

    def test_solution_reuse_canonicalizes_small_scale_aware_solver_noise(self) -> None:
        expected = [4347.249973443223, 9428.836568460503]
        render_result = {
            "success": True,
            "parameters": [["Global`A", [expected[0] - 3e-8, expected[1] + 1.3e-5]]],
        }
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            base_dir = jobs_dir / "q1-prompt"
            base_dir.mkdir(parents=True)
            (base_dir / "final_renderer_spec.json").write_text(
                json.dumps({"points": {"A": expected}}),
                encoding="utf-8",
            )

            check = _solution_reuse_check(
                {
                    "variant": "solution",
                    "diagram_variant": "solution",
                    "reuse_geometry_from": "q1-prompt",
                },
                jobs_dir / "q1-solution",
                render_result,
            )

        self.assertTrue(check["locked_points_same"])
        self.assertEqual(check["canonicalized_points"], ["A"])
        self.assertEqual(render_result["parameters"][0][1], expected)


if __name__ == "__main__":
    unittest.main()
