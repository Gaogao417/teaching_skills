"""Validator tests for the answer_key section-vs-block distinction (P6)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = (
    ROOT
    / ".codex"
    / "skills"
    / "math-assignment-latex"
    / "scripts"
    / "validate_assignment.py"
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_assignment", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AnswerKeyValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.v = _load_validator()

    def _teacher_frame(self, sections):
        return {
            "meta": {"title": "t", "version": "teacher"},
            "render": {"template": "exam-zh-practice"},
            "sections": sections,
        }

    def test_valid_answer_key_section_with_answers_block_passes(self) -> None:
        data = self._teacher_frame(
            [
                {
                    "id": "practice",
                    "type": "practice",
                    "visibility": "student",
                    "blocks": [
                        {
                            "type": "problem",
                            "id": "p1",
                            "stem": "q",
                            "answer_space": {"type": "lines"},
                        }
                    ],
                },
                {
                    "id": "answer-key",
                    "type": "answer_key",
                    "visibility": "teacher",
                    "blocks": [
                        {
                            "type": "answers",
                            "id": "answers-main",
                            "items": [{"id": "p1", "answer": "42"}],
                        }
                    ],
                },
            ]
        )
        errors = self.v.validate(data)
        self.assertEqual(errors, [], f"expected no errors, got {errors}")

    def test_block_level_answer_key_gives_guidance(self) -> None:
        data = self._teacher_frame(
            [
                {
                    "id": "s",
                    "type": "practice",
                    "visibility": "student",
                    "blocks": [
                        {"type": "answer_key", "id": "ak", "items": [{"id": "p1"}]},
                    ],
                }
            ]
        )
        errors = self.v.validate(data)
        joined = "\n".join(errors)
        self.assertIn("answer_key", joined)
        self.assertIn("section type", joined)
        # Must point the writer at the correct block types.
        self.assertIn("answers", joined)

    def test_block_type_misused_as_section_type_is_flagged(self) -> None:
        data = self._teacher_frame(
            [
                {
                    "id": "s",
                    "type": "answers",  # block type misused as section type
                    "visibility": "student",
                    "blocks": [],
                }
            ]
        )
        errors = self.v.validate(data)
        joined = "\n".join(errors)
        self.assertIn("block type", joined)


if __name__ == "__main__":
    unittest.main()
