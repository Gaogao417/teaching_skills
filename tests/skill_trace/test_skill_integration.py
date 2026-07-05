from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


class SkillTraceIntegrationFilesTest(unittest.TestCase):
    def test_skill_and_prompt_files_are_installed(self) -> None:
        skill_path = ROOT / ".codex" / "skills" / "math-skill-trace-ingestion" / "SKILL.md"
        prompt_path = ROOT / "prompts" / "skill_trace_draft_prompt.md"

        skill_text = skill_path.read_text(encoding="utf-8")
        prompt_text = prompt_path.read_text(encoding="utf-8")

        self.assertIn("name: math-skill-trace-ingestion", skill_text)
        self.assertIn("scripts/skill_trace/open_review.py", skill_text)
        self.assertIn("docs/skill-graph-conceptual-model.md", skill_text)
        self.assertIn("只输出 `SkillTraceDraft` JSON", prompt_text)
        self.assertIn("每个 step 只能表达一个学生动作", prompt_text)
        self.assertNotIn("TODO", skill_text)


if __name__ == "__main__":
    unittest.main()
