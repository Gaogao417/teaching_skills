from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_trace.validate_trace import validate_trace_file  # noqa: E402
from tests.skill_trace.test_contracts import valid_payload  # noqa: E402


class ValidateTraceTest(unittest.TestCase):
    def test_validate_trace_file_accepts_valid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / "draft.json"
            draft_path.write_text(json.dumps(valid_payload(), ensure_ascii=False), encoding="utf-8")

            result = validate_trace_file(draft_path)

        self.assertEqual(result, {"ok": True, "errors": [], "warnings": []})

    def test_validate_trace_file_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / "draft.json"
            draft_path.write_text("{", encoding="utf-8")

            result = validate_trace_file(draft_path)

        self.assertFalse(result["ok"])
        self.assertIn("invalid JSON", result["errors"][0])

    def test_validate_trace_file_reports_missing_codex_thread_id(self) -> None:
        payload = valid_payload(codex_thread_id="")
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / "draft.json"
            draft_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = validate_trace_file(draft_path)

        self.assertFalse(result["ok"])
        self.assertTrue(any("codex_thread_id" in error for error in result["errors"]))

    def test_cli_outputs_json_and_nonzero_for_invalid_payload(self) -> None:
        payload = valid_payload(steps=[])
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / "draft.json"
            draft_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "skill_trace" / "validate_trace.py"), str(draft_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertTrue(any("steps" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
