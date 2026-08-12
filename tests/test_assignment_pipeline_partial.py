"""Partial-build tests for the assignment diagram pipeline (P5).

Covers:
- ``resolve_assignment`` injects a textual placeholder for a failed slot and
  never impersonates a real diagram.
- ``run_assignment_diagram_pipeline`` writes a ``.partial.assignment.yaml`` plus
  a ``partial_resolution_report.json`` (and does NOT write the resolved YAML)
  when the batch has failures, then exits non-zero.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "scripts" / "diagram_workflow"
FIXTURE = ROOT / "tests" / "fixtures" / "diagram_regressions" / "triple_vertical"
sys.path.insert(0, str(WORKFLOW))

import yaml  # noqa: E402

from diagram_contracts import DiagramBatchJobResult, DiagramBatchReport  # noqa: E402
from renderer_bindings import RendererBindingManifest  # noqa: E402
from resolve_assignment_diagrams import resolve_assignment  # noqa: E402
import assignment_pipeline  # noqa: E402


def _p2_plan_text() -> str:
    return (FIXTURE / "p2-square-midpoint.plan.assignment.yaml").read_text(encoding="utf-8")


class PartialResolverTest(unittest.TestCase):
    def test_failed_slot_gets_text_placeholder(self) -> None:
        plan = yaml.safe_load(_p2_plan_text())
        empty_manifest = RendererBindingManifest(
            assignment_id="p2", source_jobs="x", bindings={}
        )

        # Without failed_slots + skip_required_check: slot is left as-is.
        as_is = resolve_assignment(plan, empty_manifest, skip_required_check=True)
        self.assertIn("diagram_slot", as_is["sections"][0]["blocks"][0])

        # With failed_slots: a textual placeholder replaces the slot.
        partial = resolve_assignment(
            plan,
            empty_manifest,
            skip_required_check=True,
            failed_slots={"p2.prompt": "workflow_failed: invalid_point_label"},
        )
        block = partial["sections"][0]["blocks"][0]
        self.assertNotIn("diagram_slot", block)
        placement = next(
            v for v in block.values()
            if isinstance(v, dict) and v.get("fallback") is True
        )
        self.assertIn("invalid_point_label", placement["message"])


class PartialPipelineTest(unittest.TestCase):
    def test_pipeline_produces_partial_artifacts_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_yaml = Path(tmp) / "p2.plan.assignment.yaml"
            plan_yaml.write_text(_p2_plan_text(), encoding="utf-8")

            failed_report = DiagramBatchReport(
                assignment_id="triple_vertical",
                total_jobs=1,
                ok_count=0,
                failed_count=1,
                jobs=[
                    DiagramBatchJobResult(
                        job_id="p2-prompt",
                        slot_id="p2.prompt",
                        variant="prompt",
                        status="workflow_failed",
                        workflow_status="deterministic_audit_failed",
                        failure_reason="invalid_point_label",
                        cache_key="KEY",
                    )
                ],
            )
            empty_manifest = RendererBindingManifest(
                assignment_id="triple_vertical", source_jobs="x", bindings={}
            )

            with patch.object(
                assignment_pipeline, "run_batch", return_value=failed_report
            ), patch.object(
                assignment_pipeline, "manifest_from_paths", return_value=empty_manifest
            ):
                with self.assertRaises(SystemExit) as cm:
                    assignment_pipeline.run_assignment_diagram_pipeline(
                        plan_yaml, skip_gate=True
                    )
                self.assertEqual(cm.exception.code, 1)

            partial_yaml = Path(tmp) / "p2.partial.assignment.yaml"
            resolved_yaml = Path(tmp) / "p2.resolved.assignment.yaml"
            partial_report = Path(tmp) / "build" / "diagram" / "partial_resolution_report.json"

            self.assertTrue(partial_yaml.exists())
            self.assertFalse(resolved_yaml.exists())
            self.assertTrue(partial_report.exists())

            data = yaml.safe_load(partial_yaml.read_text(encoding="utf-8"))
            self.assertEqual(data["build_status"], "partial")

            report = json.loads(partial_report.read_text(encoding="utf-8"))
            self.assertEqual(report["build_status"], "partial")
            self.assertEqual(report["ok_count"], 0)
            self.assertEqual(report["failed_count"], 1)
            self.assertEqual(report["failed_jobs"][0]["job_id"], "p2-prompt")


if __name__ == "__main__":
    unittest.main()
