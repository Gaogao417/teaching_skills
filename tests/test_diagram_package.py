from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from attach_diagram_package import build_package, diagram_block


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class DiagramPackageTest(unittest.TestCase):
    def test_renderer_spec_without_png_does_not_insert_broken_diagram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diagram_dir = root / "diagram"
            target = root / "assignment.yaml"
            write_json(
                diagram_dir / "workflow_result.json",
                {
                    "status": "ok",
                    "final_diagram_spec": "final_diagram_spec.json",
                    "final_renderer_spec": "final_renderer_spec.json",
                },
            )
            write_json(
                diagram_dir / "final_diagram_spec.json",
                {"renderer_spec_path": "final_renderer_spec.json"},
            )
            write_json(
                diagram_dir / "final_renderer_spec.json",
                {"schema_version": "geometry-render-spec/v1", "points": {"A": [0, 0]}},
            )

            package = build_package(diagram_dir, target, "观察图形")
            block = diagram_block(package, "fig-main", "hint")

        self.assertEqual(package["status"], "pending_renderer")
        self.assertEqual(package["image_path"], "")
        self.assertEqual(block["type"], "hint")

    def test_renderer_result_and_png_insert_diagram_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diagram_dir = root / "diagram"
            target = root / "assignment.yaml"
            png_path = diagram_dir / "rendered" / "diagram.png"
            png_path.parent.mkdir(parents=True, exist_ok=True)
            png_path.write_bytes(b"png")
            write_json(
                diagram_dir / "workflow_result.json",
                {
                    "status": "ok",
                    "final_diagram_spec": "final_diagram_spec.json",
                    "final_renderer_spec": "final_renderer_spec.json",
                },
            )
            write_json(
                diagram_dir / "final_diagram_spec.json",
                {
                    "renderer_spec_path": "final_renderer_spec.json",
                    "renderer_spec": {"teaching_focus": ["看高线"]},
                },
            )
            write_json(
                diagram_dir / "final_renderer_spec.json",
                {"schema_version": "geometry-render-spec/v1", "points": {"A": [0, 0]}},
            )
            write_json(
                diagram_dir / "renderer_result.json",
                {"status": "ok", "image_path": "rendered/diagram.png"},
            )

            package = build_package(diagram_dir, target, "观察高线")
            block = diagram_block(package, "fig-main", "hint")

        self.assertEqual(package["status"], "ok")
        self.assertEqual(package["image_path"], "diagram/rendered/diagram.png")
        self.assertEqual(block["type"], "diagram")
        self.assertEqual(block["source"]["renderer_result"], "diagram/renderer_result.json")


if __name__ == "__main__":
    unittest.main()
