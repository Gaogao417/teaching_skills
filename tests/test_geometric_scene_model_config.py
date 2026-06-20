from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"))

from workflow import _float_config, _resolved_model_config  # noqa: E402


class GeometricSceneModelConfigTest(unittest.TestCase):
    def test_empty_runtime_values_fall_back_to_dashscope_defaults(self) -> None:
        config = _resolved_model_config(
            {
                "base_url": "",
                "api_key_env": "",
                "temperature": None,
                "request_timeout_s": None,
                "vision_temperature": None,
                "vision_request_timeout_s": None,
                "text_models": [],
                "vision_models": [],
            }
        )

        self.assertEqual(
            config["base_url"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.assertEqual(config["api_key_env"], "DASHSCOPE_API_KEY")
        self.assertGreater(len(config["text_models"]), 0)

    def test_float_config_uses_default_for_none_and_empty_string(self) -> None:
        self.assertEqual(_float_config({"temperature": None}, "temperature", 0.2), 0.2)
        self.assertEqual(_float_config({"request_timeout_s": ""}, "request_timeout_s", 120), 120.0)
        self.assertEqual(_float_config({"temperature": "0.4"}, "temperature", 0.2), 0.4)

    def test_env_model_pool_overrides_default_pool(self) -> None:
        with patch.dict("os.environ", {"GSB_TEXT_MODELS": "qwen-live-a,qwen-live-b"}):
            config = _resolved_model_config({})

        self.assertEqual(config["text_models"], ["qwen-live-a", "qwen-live-b"])

    def test_explicit_or_env_model_pool_does_not_append_defaults(self) -> None:
        self.assertEqual(
            _resolved_model_config({"text_models": ["explicit-model"]})["text_models"],
            ["explicit-model"],
        )
        with patch.dict("os.environ", {"GSB_TEXT_MODELS": "env-model-a,env-model-b"}):
            self.assertEqual(
                _resolved_model_config({})["text_models"],
                ["env-model-a", "env-model-b"],
            )


if __name__ == "__main__":
    unittest.main()
