from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from run_diagram_workflow import run_renderer_spec_workflow  # noqa: E402


class RendererSpecWorkflowTest(unittest.TestCase):
    def test_renderer_spec_engine_writes_final_renderer_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            with redirect_stdout(StringIO()):
                result = run_renderer_spec_workflow(
                    {
                        "schema_version": "diagram-job-request/v2",
                        "job_id": "q1-prompt",
                        "assignment_id": "unit",
                        "slot_id": "q1.prompt",
                        "engine": "renderer_spec",
                        "diagram_kind": "synthetic_geometry",
                        "engine_options": {
                            "renderer_spec": {
                                "points": {"A": [0, 0], "B": [1, 0]},
                                "segments": [{"from": "A", "to": "B"}],
                            }
                        },
                    },
                    out_dir,
                )

            self.assertEqual(result["status"], "ok")
            self.assertTrue((out_dir / "final_renderer_spec.json").exists())

    def test_renderer_spec_engine_rejects_unstructured_tikz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            with redirect_stdout(StringIO()):
                result = run_renderer_spec_workflow(
                    {
                        "schema_version": "diagram-job-request/v2",
                        "job_id": "bad",
                        "assignment_id": "unit",
                        "slot_id": "bad.prompt",
                        "engine": "renderer_spec",
                        "diagram_kind": "synthetic_geometry",
                        "engine_options": {"renderer_spec": {"tikz_fragment": r"\draw (0,0)--(1,0);"}},
                    },
                    out_dir,
                )

            self.assertEqual(result["status"], "failed")
            self.assertIn("forbidden key", result["message"])


if __name__ == "__main__":
    unittest.main()
