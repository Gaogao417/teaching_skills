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


# --------------------------------------------------------------------------- #
# Page-number semantic invariants (A-outlier precheck: the two failure modes
# the schema cannot catch — answer-block question seeds and non-monotonic
# question ordering. The validator must reject these so the agent self-corrects
# within its 3 retries instead of producing a draft that later expands into a
# 300-page evidence list.)
# --------------------------------------------------------------------------- #


def _page(n: int) -> dict:
    return {"kind": "page", "source": "exam.pdf", "page_number": n}


def _question(
    ref: str,
    number: int,
    *,
    q_type: str = "choice",
    q_page: int,
    s_page: int,
) -> dict:
    content = {"stem_latex": f"$Q{number}$", "answer": "A", "clue": "略"}
    if q_type == "choice":
        content["choices"] = ["1", "2", "3", "4"]
    elif q_type in ("problem", "short_answer"):
        content["solution_steps"] = ["step 1"]
    return {
        "question_ref": ref,
        "question_number": number,
        "question_type": q_type,
        "points": 4,
        "content": content,
        "evidence": {
            "question": [_page(q_page)],
            "solution": [_page(s_page)],
            "solution_start_anchor": f"p{s_page}",
            "solution_end_anchor": f"p{s_page}",
        },
    }


def _bundle(questions: list[dict]) -> dict:
    return {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": "P", "title": "未知", "grade": "初三", "subject": "数学",
            "source_archive": "exam.pdf",
        },
        "sections": [{"section_ref": "1", "title": "题", "questions": questions}],
        "provider": {"kind": "agent", "name": "fake", "version": "v1"},
    }


def test_separated_layout_rejects_question_seed_in_answer_block():
    """A1 outlier: trailing question's question page lands in the answer block.

    Reproduces the 2013-CHANGNING / 2018-YANGPU pattern (5 papers): a separated
    paper (solutions start at p9) where Q025's evidence.question is tagged p21
    — the agent saw the question number re-mentioned in the answer section and
    recorded that page as the question page.
    """
    bundle = _bundle([
        _question("1", 1, q_page=1, s_page=9),
        _question("2", 2, q_page=3, s_page=10),
        _question("25", 25, q_page=21, s_page=28),  # p21 >= first_solution p9
    ])
    result = _run({"draft": bundle})
    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "题 25" in text
    assert "答案区" in text
    assert "p21" in text


def test_interleaved_layout_allows_question_on_solution_page():
    """Interleaved (题答交织) papers legitimately share page 1 for q and s.

    The separated-layout rule must NOT fire when solution starts at page 1 —
    that is the interleaved signature. Q and S on the same page is normal.
    """
    bundle = _bundle([
        _question("1", 1, q_page=1, s_page=1),
        _question("2", 2, q_page=2, s_page=2),
    ])
    result = _run({"draft": bundle})
    assert result.get("is_error", False) is False
    assert result["content"][0]["text"].startswith("VALID")


def test_non_monotonic_question_pages_rejected_in_both_layouts():
    """A2 outlier: question page dips backwards (Q004=p1 after Q003=p2).

    Reproduces the 7-paper inversion pattern: same-page multi-question
    tie-break instability. Must fire in both separated and interleaved layouts.
    """
    # separated layout + inversion among first questions
    bundle_sep = _bundle([
        _question("1", 1, q_page=1, s_page=9),
        _question("2", 2, q_page=2, s_page=9),
        _question("3", 3, q_page=2, s_page=10),
        _question("4", 4, q_page=1, s_page=10),  # p1 < prev p2 → inversion
    ])
    result_sep = _run({"draft": bundle_sep})
    assert result_sep["is_error"] is True
    assert "题 4" in result_sep["content"][0]["text"]
    assert "非递减" in result_sep["content"][0]["text"]

    # interleaved layout + inversion
    bundle_il = _bundle([
        _question("1", 1, q_page=1, s_page=1),
        _question("2", 2, q_page=3, s_page=3),
        _question("3", 3, q_page=2, s_page=2),  # p2 < prev p3 → inversion
    ])
    result_il = _run({"draft": bundle_il})
    assert result_il["is_error"] is True
    assert "题 3" in result_il["content"][0]["text"]


def test_same_page_multi_question_is_not_an_inversion():
    """Equal page numbers across consecutive questions are legal (same page).

    Non-decreasing allows equality: Q003=p2 and Q004=p2 is fine (two questions
    on page 2), only Q004=p1 after Q003=p2 is an inversion.
    """
    bundle = _bundle([
        _question("1", 1, q_page=1, s_page=9),
        _question("2", 2, q_page=2, s_page=9),
        _question("3", 3, q_page=2, s_page=10),  # equal to prev, legal
        _question("4", 4, q_page=2, s_page=10),  # equal to prev, legal
    ])
    result = _run({"draft": bundle})
    assert result.get("is_error", False) is False
