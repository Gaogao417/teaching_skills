from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from check_diagram_gate import _check_slot_layout_profiles, _check_svg_readability  # noqa: E402
from diagram_contracts import (  # noqa: E402
    DiagramArtifact,
    DiagramArtifactsManifest,
    DiagramDisplayProfile,
    DiagramJob,
    DiagramJobsManifest,
    DiagramSlot,
)
from render_geometry_spec import SvgCoordinateRenderer, SvgGeometryRenderer  # noqa: E402
from resolve_assignment_diagrams import resolve_assignment  # noqa: E402


def slot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "slot_id": "q1.prompt",
        "placement": "diagram_col",
        "layout_role": "question_sidecar",
    }
    payload.update(overrides)
    return payload


class DiagramProfileTest(unittest.TestCase):
    def test_slot_resolves_sidecar_profile_defaults_and_width_override(self) -> None:
        slot = DiagramSlot(**slot_payload())
        profile = slot.resolved_render_profile()

        self.assertEqual(profile.display_profile, DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR)
        self.assertEqual(profile.width, "60mm")
        self.assertEqual(profile.canvas_width_px, 720)
        self.assertEqual(profile.canvas_height_px, 360)
        self.assertEqual(profile.body_scale, "large")
        self.assertEqual(profile.point_label_px, 44)
        self.assertEqual(profile.condition_label_px, 36)
        self.assertEqual(profile.point_label_font_weight, "normal")

        dense = DiagramSlot(**slot_payload(visual_requirements={"label_density": "dense"}))
        self.assertEqual(dense.resolved_render_profile().point_label_px, 52)

        overridden = DiagramSlot(**slot_payload(width_hint=r"0.32\linewidth"))
        self.assertEqual(overridden.resolved_render_profile().width, r"0.32\linewidth")

        with self.assertRaises(ValidationError):
            DiagramSlot(**slot_payload(width_hint="60 px"))

    def test_resolver_uses_profile_width_when_width_hint_is_absent(self) -> None:
        plan_data = {
            "meta": {"assignment_id": "profile-resolve"},
            "sections": [
                {
                    "blocks": [
                        {
                            "id": "q1",
                            "diagram_slot": slot_payload(caption="原题图"),
                        }
                    ]
                }
            ],
        }
        artifacts = DiagramArtifactsManifest(
            assignment_id="profile-resolve",
            source_jobs="build/diagram/diagram_jobs.json",
            artifacts={
                "q1.prompt": DiagramArtifact(
                    slot_id="q1.prompt",
                    job_id="q1-prompt",
                    status="ok",
                    image_path="build/diagram/jobs/q1-prompt/rendered/prompt.png",
                    hash="sha256:abc",
                    bindable=True,
                )
            },
        )

        resolved = resolve_assignment(plan_data, artifacts)
        diagram_col = resolved["sections"][0]["blocks"][0]["diagram_col"]
        self.assertEqual(diagram_col["width"], "60mm")
        self.assertEqual(diagram_col["caption"], "原题图")

    def test_renderers_use_profile_label_style_and_value_only_conditions(self) -> None:
        profile = DiagramSlot(**slot_payload()).resolved_render_profile().model_dump(mode="json")
        synthetic_svg = SvgGeometryRenderer(
            {
                "render_profile": profile,
                "points": {"A": [0, 0], "B": [1, 0]},
                "segments": [{"from": "A", "to": "B"}],
            },
            width=720,
            height=360,
        ).render()

        self.assertIn('font-family="Times New Roman, Georgia, serif"', synthetic_svg)
        self.assertIn('font-size="44.0"', synthetic_svg)
        self.assertIn('font-style="italic"', synthetic_svg)
        self.assertIn('font-weight="normal"', synthetic_svg)
        self.assertIn('data-label-kind="point"', synthetic_svg)
        self.assertNotIn("Arial", synthetic_svg)

        coordinate_svg = SvgCoordinateRenderer(
            {
                "type": "coordinate_geometry",
                "render_profile": profile,
                "viewport": {"x_min": -1, "x_max": 3, "y_min": -1, "y_max": 3},
                "axes": {"x": False, "y": False, "grid": False, "show_ticks": True},
                "objects": [
                    {"type": "point", "id": "C", "x": 0, "y": 0, "label": "C"},
                    {"type": "text", "x": 1, "y": 1, "text": "CD=19"},
                ],
            },
            width=720,
            height=360,
        ).render()

        self.assertIn(">19</text>", coordinate_svg)
        self.assertNotIn("CD=19", coordinate_svg)
        self.assertNotIn(">x</text>", coordinate_svg)
        self.assertNotIn(">y</text>", coordinate_svg)

    def test_gate_checks_sidecar_width_and_svg_readability(self) -> None:
        plan_data = {
            "meta": {"assignment_id": "gate-profile"},
            "sections": [
                {
                    "blocks": [
                        {
                            "diagram_slot": slot_payload(width_hint="50mm"),
                        }
                    ]
                }
            ],
        }
        layout_checks = _check_slot_layout_profiles(plan_data)
        self.assertEqual(layout_checks[0].name, "diagram_sidecar_width")
        self.assertEqual(layout_checks[0].status, "block")

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            svg_path = artifact_dir / "build" / "diagram" / "jobs" / "q1-prompt" / "rendered" / "prompt.svg"
            svg_path.parent.mkdir(parents=True)
            svg_path.write_text(
                '<svg><text font-family="Arial" font-size="15" font-weight="800" '
                'data-label-kind="point">A</text><text>AB=7</text></svg>',
                encoding="utf-8",
            )
            jobs = DiagramJobsManifest(
                assignment_id="gate-profile",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="q1-prompt",
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/q1-prompt/request.json",
                        out_dir="build/diagram/jobs/q1-prompt",
                        public_image_dir="diagram/jobs/q1-prompt/rendered",
                    )
                ],
            )
            artifacts = DiagramArtifactsManifest(
                assignment_id="gate-profile",
                source_jobs="build/diagram/diagram_jobs.json",
                artifacts={
                    "q1.prompt": DiagramArtifact(
                        slot_id="q1.prompt",
                        job_id="q1-prompt",
                        status="ok",
                        image_path="build/diagram/jobs/q1-prompt/rendered/prompt.png",
                        preview_svg="rendered/prompt.svg",
                        hash="sha256:abc",
                        bindable=True,
                    )
                },
            )

            svg_checks = _check_svg_readability(jobs, artifacts, artifact_dir)
            names = {check.name for check in svg_checks}
            self.assertIn("diagram_svg_font_weight", names)
            self.assertIn("diagram_svg_arial_bold", names)
            self.assertIn("diagram_svg_point_label_size", names)
            self.assertIn("diagram_svg_condition_label_style", names)


if __name__ == "__main__":
    unittest.main()
