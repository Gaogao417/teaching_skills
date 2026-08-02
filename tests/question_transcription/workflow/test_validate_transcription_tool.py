"""Tests for the in-process ``validate_transcription`` MCP tool handler.

The handler is callable directly (no SDK / no MCP) so it can be unit-tested:
feed it a draft dict, assert VALID vs. is_error. This locks the contract the
Claude Code agent relies on (see WHOLE_PAPER_SYSTEM_PROMPT "输出前自检").
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.tools.validate_transcription import (
    validate_transcription_handler,
)


def _run(args):
    return asyncio.run(validate_transcription_handler(args))


def test_valid_bundle_returns_valid_without_error():
    bundle = {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": "P", "title": "未知", "grade": "初三", "subject": "数学",
            "source_archive": "exam.pdf",
        },
        "sections": [
            {"section_ref": "1", "title": "选择题", "questions": [
                {"question_ref": "1", "question_number": 1, "question_type": "choice",
                 "points": 4,
                 "content": {"stem_latex": "$2+2=$", "choices": ["3", "4", "5", "6"],
                             "answer": "B", "clue": "加法"},
                 "evidence": {
                     "question": [{"kind": "page", "source": "exam.pdf", "page_number": 1}],
                     "solution": [{"kind": "page", "source": "exam.pdf", "page_number": 1}],
                     "solution_start_anchor": "1", "solution_end_anchor": "1"}},
            ]},
        ],
        "provider": {"kind": "agent", "name": "fake", "version": "v1"},
    }
    result = _run({"draft": bundle})
    text = result["content"][0]["text"]
    assert text.startswith("VALID")
    assert "1 道题" in text
    assert result.get("is_error", False) is False


def test_invalid_bundle_returns_error_with_validation_text():
    # missing required fields (no schema, no sections) → pydantic ValidationError
    result = _run({"draft": {"paper": {"id": "P"}}})
    assert result["is_error"] is True
    text = result["content"][0]["text"]
    # the full ValidationError string is returned so the agent can fix the draft
    assert "ValidationError" in text or "validation error" in text.lower()


def test_non_dict_draft_is_an_error():
    result = _run({"draft": "not a dict"})
    assert result["is_error"] is True
    assert "JSON 对象" in result["content"][0]["text"]


def test_missing_draft_key_is_an_error():
    result = _run({})
    assert result["is_error"] is True
