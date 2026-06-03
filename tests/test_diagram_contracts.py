from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_contracts import (  # noqa: E402
    DiagramEngineOptions,
    DiagramModelConfig,
    GeometryRenderSpec,
    ScenePayload,
    WolframRenderResult,
)


class DiagramContractsTest(unittest.TestCase):
    def test_scene_payload_requires_scene_code_and_valid_diagram_spec(self) -> None:
        payload = ScenePayload(
            scene_code="GeometricScene[{A, B}, {EuclideanDistance[A, B] == 1}]",
            points=["A", "B"],
            diagram_spec={"segments": [["A", "B"]], "labels": {"A": "A"}},
        )
        self.assertEqual(payload.diagram_spec.segments[0].start, "A")
        self.assertEqual(payload.diagram_spec.labels["A"].text, "A")

        with self.assertRaises(ValidationError):
            ScenePayload(points=["A"])

        with self.assertRaises(ValidationError):
            ScenePayload(
                scene_code="GeometricScene[{A, B}, {}]",
                diagram_spec={"segments": [{"from": "A"}]},
            )

    def test_wolfram_render_result_contracts_success_and_failure_shapes(self) -> None:
        ok = WolframRenderResult(
            success=True,
            parameters={"A": [0, 0], "B": [1, 0]},
            render_image_requested=False,
        )
        self.assertTrue(ok.success)

        with self.assertRaises(ValidationError):
            WolframRenderResult(success=True, render_image_requested=True)

        failed = WolframRenderResult(success=False, message="kernel failed")
        self.assertEqual(failed.fail_type, "unknown")

    def test_geometry_render_spec_rejects_bad_references(self) -> None:
        spec = GeometryRenderSpec(
            points={"A": (0, 0), "B": (1, 0)},
            segments=[{"from": "A", "to": "B"}],
            polygons=[{"points": ["A", "B", "A"]}],
            markers=[{"type": "equal_ticks", "segments": [["A", "B"]]}],
        )
        self.assertEqual(spec.segments[0].end, "B")

        with self.assertRaises(ValidationError):
            GeometryRenderSpec(
                points={"A": (0, 0)},
                segments=[{"from": "A", "to": "Missing"}],
            )

    def test_model_config_preserves_aliases_and_mapping_access(self) -> None:
        options = DiagramEngineOptions(
            model_config={
                "text_model": "unit-text",
                "vision_models": ["unit-vision-a", "unit-vision-b"],
                "request_timeout_s": 30,
                "wl_kernel": "/Applications/WolframKernel",
            }
        )
        config = options.engine_model_config
        self.assertIsInstance(config, DiagramModelConfig)
        self.assertEqual(config["text_model"], "unit-text")
        self.assertEqual(config.get("wl_kernel"), "/Applications/WolframKernel")
        self.assertEqual(config.vision_models[1], "unit-vision-b")


if __name__ == "__main__":
    unittest.main()
