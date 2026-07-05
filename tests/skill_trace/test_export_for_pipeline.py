from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_trace.db import insert_review  # noqa: E402
from skill_trace.export_for_pipeline import export_for_pipeline  # noqa: E402
from tests.skill_trace.test_contracts import valid_payload  # noqa: E402


class SkillTraceExportForPipelineTest(unittest.TestCase):
    def test_export_writes_reviewed_trace_structure_analysis_and_handoff(self) -> None:
        payload = valid_payload()
        problem = payload["problem_case"]
        assert isinstance(problem, dict)
        problem["expected_thinking"] = "先看要求量，再找对应关系。"
        steps = payload["steps"]
        assert isinstance(steps, list)
        steps[1]["common_errors"] = ["只看数字，不找对应线段"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "skill_trace.db"
            out_dir = tmp_path / "artifact"
            insert_review(
                draft_id="draft_demo",
                reviewed_json=payload,
                reviewed_trace_id="trace_demo",
                db_path=db_path,
            )

            result = export_for_pipeline(reviewed_trace_id="trace_demo", out_dir=out_dir, db_path=db_path)

            reviewed = json.loads((out_dir / "01-skill-trace.reviewed.json").read_text(encoding="utf-8"))
            structure = (out_dir / "01-structure-analysis.md").read_text(encoding="utf-8")
            handoff = json.loads((out_dir / "thread_handoff.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "exported")
        self.assertEqual(reviewed["reviewed_trace_id"], "trace_demo")
        self.assertEqual(reviewed["problem_case_id"], "case_draft_demo")
        self.assertEqual(reviewed["problem_case"]["raw_problem"], "已知 AB:BC=2:3，求 ED。")
        self.assertIn("## 已审阅技能 Trace 摘要", structure)
        self.assertIn("1. L3: 先确定题目要求的是 ED", structure)
        self.assertIn("- 只看数字，不找对应线段", structure)
        self.assertEqual(handoff["next"]["explanation"], "generate 02-student-explanation.assignment.yaml from reviewed trace")

    def test_cli_exports_pipeline_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "skill_trace.db"
            out_dir = tmp_path / "artifact"
            insert_review(
                draft_id="draft_demo",
                reviewed_json=valid_payload(),
                reviewed_trace_id="trace_demo",
                db_path=db_path,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "skill_trace" / "export_for_pipeline.py"),
                    "--db",
                    str(db_path),
                    "--reviewed-trace-id",
                    "trace_demo",
                    "--out-dir",
                    str(out_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            files = sorted(path.name for path in out_dir.iterdir())

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "exported")
        self.assertEqual(
            files,
            ["01-skill-trace.reviewed.json", "01-structure-analysis.md", "thread_handoff.json"],
        )


if __name__ == "__main__":
    unittest.main()
