from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"))

from tools import (  # noqa: E402
    _float_config,
    _resolved_codex_config,
    _skill_inputs_for_group,
    _skills_root,
    _validate_scene_code,
)
from agent_prompt import agent_result_schema  # noqa: E402


class GeometricSceneCodexConfigTest(unittest.TestCase):
    def test_empty_runtime_values_use_codex_defaults(self) -> None:
        config = _resolved_codex_config(
            {
                "codex_model": "",
                "codex_bin": "",
                "codex_timeout_s": None,
            }
        )

        self.assertEqual(config["codex_model"], "")
        self.assertEqual(config["codex_bin"], "")
        self.assertEqual(config["codex_timeout_s"], 120.0)
        self.assertNotIn("base_url", config)
        self.assertNotIn("api_key_env", config)

    def test_codex_model_accepts_legacy_model_alias(self) -> None:
        config = _resolved_codex_config({"model": "gpt-test", "codex_timeout_s": "30"})

        self.assertEqual(config["codex_model"], "gpt-test")
        self.assertEqual(config["codex_timeout_s"], 30.0)

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

        self.assertEqual(inputs[0]["name"], "wolfram-geometricscene-reference")
        self.assertTrue(Path(inputs[0]["path"]).exists())
        self.assertEqual(Path(inputs[0]["path"]).parents[1], expected_root)

    def test_agent_output_schema_is_strict(self) -> None:
        schema = agent_result_schema()

        self.assertFalse(schema["additionalProperties"])
        self.assertCountEqual(schema["required"], schema["properties"].keys())

    def test_scene_code_rejects_nested_point_list(self) -> None:
        _validate_scene_code("GeometricScene[{A, B, C}, {A == {0, 1}}]")

        with self.assertRaisesRegex(ValueError, "flat GeometricScene point list"):
            _validate_scene_code("GeometricScene[{{A, B, C}}, {A == {0, 1}}]")


if __name__ == "__main__":
    unittest.main()
