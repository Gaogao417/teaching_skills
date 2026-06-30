from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from diagram_contracts import (  # noqa: E402
    CoordinateGeometryDiagramSlot,
    DiagramEngineOptions,
    DiagramModelConfig,
    FunctionGraphDiagramSlot,
    GeometryRendererResult,
    GeometryRenderSpec,
    RendererBinding,
    ResolvedDiagramPlacement,
    ResolvedDiagramTikz,
    ScenePayload,
    SyntheticGeometryDiagramSlot,
    WolframRenderResult,
    validate_diagram_slot,
)


class DiagramContractsTest(unittest.TestCase):
    def _base_slot_payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "slot_id": "q1.prompt",
            "placement": "diagram_col",
            "layout_role": "question_sidecar",
        }
        payload.update(overrides)
        return payload

    def test_diagram_slot_discriminates_synthetic_payload(self) -> None:
        slot = validate_diagram_slot(
            self._base_slot_payload(
                engine="geometric_scene",
                diagram_kind="synthetic_geometry",
                semantic_constraints={"given_objects": ["A", "B"]},
            )
        )

        self.assertIsInstance(slot, SyntheticGeometryDiagramSlot)
        self.assertEqual(slot.diagram_kind, "synthetic_geometry")
        self.assertEqual(slot.engine, "geometric_scene")
        self.assertEqual(slot.semantic_constraints.given_objects, ["A", "B"])

    def test_diagram_slot_discriminates_coordinate_payload(self) -> None:
        slot = validate_diagram_slot(
            self._base_slot_payload(
                engine="coordinate_renderer",
                diagram_kind="coordinate_geometry",
                analytic_requirements={
                    "objects": [
                        {"type": "point", "id": "A", "x": 0, "y": 1, "label": "A"}
                    ]
                },
            )
        )

        self.assertIsInstance(slot, CoordinateGeometryDiagramSlot)
        self.assertEqual(slot.diagram_kind, "coordinate_geometry")
        self.assertEqual(slot.analytic_requirements.objects[0].id, "A")

    def test_diagram_slot_discriminates_function_graph_payload(self) -> None:
        slot = validate_diagram_slot(
            self._base_slot_payload(
                engine="wolfram_client",
                diagram_kind="function_graph",
                analytic_requirements={
                    "functions": [{"id": "f", "expression_wl": "x^2"}]
                },
            )
        )

        self.assertIsInstance(slot, FunctionGraphDiagramSlot)
        self.assertEqual(slot.diagram_kind, "function_graph")
        self.assertEqual(slot.analytic_requirements.functions[0].id, "f")

    def test_function_graph_slot_requires_functions(self) -> None:
        with self.assertRaises(ValidationError):
            validate_diagram_slot(
                self._base_slot_payload(
                    engine="wolfram_client",
                    diagram_kind="function_graph",
                    analytic_requirements={
                        "objects": [{"type": "point", "id": "A", "x": 0, "y": 1}]
                    },
                )
            )

    def test_coordinate_slot_requires_coordinate_objects(self) -> None:
        with self.assertRaises(ValidationError):
            validate_diagram_slot(
                self._base_slot_payload(
                    engine="coordinate_renderer",
                    diagram_kind="coordinate_geometry",
                    analytic_requirements={},
                )
            )

    def test_synthetic_slot_rejects_analytic_requirements(self) -> None:
        with self.assertRaises(ValidationError):
            validate_diagram_slot(
                self._base_slot_payload(
                    engine="geometric_scene",
                    diagram_kind="synthetic_geometry",
                    analytic_requirements={
                        "objects": [{"type": "point", "id": "A"}]
                    },
                )
            )

    def test_synthetic_slot_rejects_analytic_engine(self) -> None:
        with self.assertRaises(ValidationError):
            validate_diagram_slot(
                self._base_slot_payload(
                    engine="coordinate_renderer",
                    diagram_kind="synthetic_geometry",
                )
            )

    def test_plan_slot_rejects_unrouted_diagram_kind_values(self) -> None:
        for diagram_kind in ("hybrid", "auto"):
            with self.subTest(diagram_kind=diagram_kind):
                with self.assertRaises(ValidationError):
                    validate_diagram_slot(
                        self._base_slot_payload(
                            engine="geometric_scene",
                            diagram_kind=diagram_kind,
                        )
                    )

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

    def test_tikz_renderer_result_requires_tikz_payload(self) -> None:
        ok = GeometryRendererResult(
            status="ok",
            tikz_fragment_path="rendered/prompt.fragment.tex",
            renderer_audit="renderer_audit.json",
        )
        self.assertEqual(ok.artifact_kind, "tikz")
        self.assertEqual(ok.renderer, "teaching-tikz-geometry-renderer")

        with self.assertRaises(ValidationError):
            GeometryRendererResult(status="ok")

    def test_bindable_renderer_binding_is_tikz_source_not_image(self) -> None:
        binding = RendererBinding(
            slot_id="q1.prompt",
            diagram_ref="q1.prompt",
            job_id="q1-prompt",
            status="ok",
            tikz_fragment=r"\begin{tikzpicture}\draw (0,0) -- (1,0);\end{tikzpicture}",
            hash="sha256:abc",
            bindable=True,
        )
        self.assertTrue(binding.bindable)

        with self.assertRaises(ValidationError):
            RendererBinding(
                slot_id="q1.prompt",
                diagram_ref="q1.prompt",
                job_id="q1-prompt",
                status="ok",
                hash="sha256:abc",
                bindable=True,
            )

    def test_resolved_diagram_placement_outputs_tikz_payload(self) -> None:
        tikz = ResolvedDiagramTikz(
            tikz_path="build/diagram/jobs/q1/rendered/prompt.fragment.tex",
            diagram_ref="q1.prompt",
            diagram_job_id="q1-prompt",
            width="60mm",
            caption="原题图",
            hash="sha256:abc",
        )
        placement = ResolvedDiagramPlacement(field="diagram_col", tikz=tikz)

        payload = placement.as_mapping()["diagram_col"]
        self.assertEqual(payload["kind"], "tikz")
        self.assertEqual(payload["tikz_path"], "build/diagram/jobs/q1/rendered/prompt.fragment.tex")

        with self.assertRaises(ValidationError):
            ResolvedDiagramTikz(
                diagram_ref="q1.prompt",
                diagram_job_id="q1-prompt",
            )


if __name__ == "__main__":
    unittest.main()
