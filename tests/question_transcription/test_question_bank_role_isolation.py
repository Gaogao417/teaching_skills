#!/usr/bin/env python3
"""Regression tests for the 2021 question-bank ingestion contract fixes.

Covers four root causes that broke single-paper merges:

1. span-index: the solution region's tail was truncated to the question
   region's first page (only the last question's start page survived).
2. observe (structured prompt): solution batches restated the stem, polluting
   stem/choices fields that belong to the question role.
3. observe: missing solution anchors were fabricated from the question number
   ("1．"), which downstream evidence-page expansion mistook for real anchors.
4. merge: field selection ignored window origin, so a solution-window restated
   stem could out-rank the original question-window stem on a text tiebreak.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.contracts import PaperMeta  # noqa: E402
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxWindowObservation,
)
from scripts.question_transcription.procedural.merge_docx_observations import (  # noqa: E402
    _PENDING_SOLUTION_ANCHOR,
    _select_value,
    _window_role,
    merge_with_issues,
)
from scripts.question_transcription.procedural.observe_docx_pages import (  # noqa: E402
    _structured_batch_prompt,
    normalize_observation_field_shapes,
)
from scripts.question_transcription.procedural.question_span_index import (  # noqa: E402
    PageText,
    SourceFingerprint,
    build_index_from_pages,
)


# --------------------------------------------------------------------------- #
# span-index: solution tail must reach the last page (fix 1)
# --------------------------------------------------------------------------- #


def _pages(spec: dict[int, str]) -> list[PageText]:
    return [PageText(page_number=num, text=txt) for num, txt in sorted(spec.items())]


def test_solution_region_tail_extends_to_last_page():
    """Regression: the last solution question used to keep only its start page.

    A paper whose answer region restarts at 1 on page 3 and whose last answer
    (question 2) starts on page 3 with trailing continuation pages 4-5 must own
    all of [3, 4, 5], not just [3].
    """
    pages = _pages({
        1: "选择题\n1. q1\n2. q2\n3. q3",
        2: "填空题\n4. q4",
        3: "参考答案\n1. a1\n2. a2 解答开始",
        4: "（a2 解答续）",
        5: "（a2 解答续）",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=SourceFingerprint())
    q2 = next(q for q in index.questions if q.question_ref == "2")
    assert q2.solution_pages == [3, 4, 5], (
        "solution tail must extend to the last page, not just the start page"
    )


def test_solution_region_tail_extends_when_question_region_is_earlier():
    """The question region's first page (page 1) must NOT cap the solution tail.

    Before the fix, _tail_exclusive('solution') returned first_page['question']
    (=1), collapsing the last answer's pages to its start page only.
    """
    pages = _pages({
        1: "选择题\n1. q1",
        2: "参考答案\n1. a1 解答",
        3: "（a1 解答续）",
        4: "（a1 解答续）",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=SourceFingerprint())
    q1 = next(q for q in index.questions if q.question_ref == "1")
    assert q1.solution_pages == [2, 3, 4]


# --------------------------------------------------------------------------- #
# span-index: cross-region missing question downgrades status (fix 1, derived)
# --------------------------------------------------------------------------- #


def test_cross_region_missing_question_is_blocking():
    """If a number exists in one region but not the other, surface a blocking
    issue so the index is not silently marked ready."""
    # Question region has 1,2,3; solution region only has 1,2 (3 missing).
    pages = _pages({
        1: "选择题\n1. q1\n2. q2\n3. q3",
        2: "参考答案\n1. a1\n2. a2",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=SourceFingerprint())
    codes = [issue.code for issue in index.issues]
    assert "solution_region_missing_question" in codes
    assert index.status == "needs_review"


def test_cross_region_aligned_has_no_missing_question_issue():
    """When both regions cover the same numbers, no cross-region issue appears."""
    pages = _pages({
        1: "选择题\n1. q1\n2. q2",
        2: "参考答案\n1. a1\n2. a2",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=SourceFingerprint())
    codes = [issue.code for issue in index.issues]
    assert "solution_region_missing_question" not in codes
    assert "question_region_missing_question" not in codes


# --------------------------------------------------------------------------- #
# observe: structured prompt isolates fields by role (fix 2)
# --------------------------------------------------------------------------- #


def _batch(role: str, refs: tuple[str, ...] = ("1",)):
    from scripts.question_transcription.procedural.question_span_index import ObservationBatch

    return ObservationBatch(
        batch_id=f"{role}-001-p001-p001",
        role=role,
        page_numbers=[1],
        expected_question_refs=list(refs),
    )


def test_structured_prompt_for_solution_role_forbids_stem_restatement():
    batch = _batch("solution")
    prompt = _structured_batch_prompt(batch, window_pages=[], ref_page_map={})
    assert "官方解答" in prompt
    # The prompt must explicitly forbid restating the stem in a solution batch.
    assert "不得重述题干" in prompt
    assert "stem_latex" in prompt or "题干" in prompt


def test_structured_prompt_for_question_role_forbids_answer():
    batch = _batch("question")
    prompt = _structured_batch_prompt(batch, window_pages=[], ref_page_map={})
    assert "题干" in prompt
    # The question batch must not transcribe answers/solutions.
    assert "只转题干" in prompt or "不得转录答案" in prompt


# --------------------------------------------------------------------------- #
# observe: missing anchors are NOT fabricated from the question number (fix 3)
# --------------------------------------------------------------------------- #


def test_normalize_leaves_missing_anchor_as_none():
    """normalize_observation_field_shapes must not turn a missing anchor into
    a fake ``1．`` derived from the question number."""
    raw = {
        "schema": "math_docx_window_observation/v1",
        "window_id": "question-001-p001-p001",
        "pages": [],
        "provider": {"kind": "vision_api", "name": "fake", "version": "v1"},
        "questions": [
            {
                "question_ref": "1",
                "question_number": 1,
                "question_type": "choice",
                "points": 4,
                "section_ref": "choice",
                "section_title": "选择题",
                "content": {
                    "stem_latex": "题干",
                    "choices": ["A", "B", "C", "D"],
                    "answer": None,
                    "clue": None,
                    "solution_steps": [],
                    "solution_notes": [],
                },
                "evidence": {
                    "question": [
                        {"kind": "page", "source": "documents/test/001.png", "page_number": 1}
                    ],
                    "solution": [],
                    # Model omitted both anchors.
                    "solution_start_anchor": None,
                    "solution_end_anchor": None,
                },
                "transcription_confidence": {
                    "stem": "high",
                    "formula": "high",
                    "solution_steps": "high",
                },
            }
        ],
    }
    normalized = normalize_observation_field_shapes(raw)
    evidence = normalized["questions"][0]["evidence"]
    assert evidence["solution_start_anchor"] is None
    assert evidence["solution_end_anchor"] is None
    # Crucially, not a fabricated question-number anchor.
    assert evidence["solution_start_anchor"] != "1．"


# --------------------------------------------------------------------------- #
# merge: source-aware selection prefers the correct window origin (fix 4)
# --------------------------------------------------------------------------- #


def _paper() -> PaperMeta:
    return PaperMeta.model_validate(
        {
            "id": "PAPER",
            "title": "测试试卷",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": "documents/test",
        }
    )


def _fragment(
    *,
    stem: str | None,
    answer: str | None,
    solution_steps: list[str] | None,
    confidence: str = "high",
    anchor: str | None = "解：",
    clue: str | None = "原卷未提供提示",
) -> dict:
    return {
        "question_ref": "1",
        "question_number": 1,
        "question_type": "choice",
        "points": 4,
        "section_ref": "choice",
        "section_title": "选择题",
        "content": {
            "stem_latex": stem,
            "choices": [] if stem is None else ["A", "B", "C", "D"],
            "answer": answer,
            "clue": clue,
            "solution_steps": solution_steps or [],
            "solution_notes": [],
        },
        "evidence": {
            "question": [] if stem is None else [
                {"kind": "page", "source": "documents/test/001.png", "page_number": 1}
            ],
            "solution": [] if answer is None else [
                {"kind": "page", "source": "documents/test/006.png", "page_number": 6}
            ],
            "solution_start_anchor": anchor,
            "solution_end_anchor": anchor,
        },
        "transcription_confidence": {
            "stem": confidence,
            "formula": confidence,
            "solution_steps": confidence,
        },
    }


def _window(window_id: str, questions: list[dict]) -> DocxWindowObservation:
    return DocxWindowObservation.model_validate(
        {
            "schema": "math_docx_window_observation/v1",
            "window_id": window_id,
            "pages": [
                {
                    "page_number": 1,
                    "source": "documents/test/001.png",
                    "width_px": 64,
                    "height_px": 80,
                    "sha256": "sha256:" + "0" * 64,
                }
            ],
            "questions": questions,
            "provider": {"kind": "vision_api", "name": "fake", "version": "v1"},
        }
    )


def test_window_role_classification():
    assert _window_role("question-001-p001-p003") == "question"
    assert _window_role("solution-001-p010-p013") == "solution"
    assert _window_role("pages-001") is None


def test_merge_prefers_question_window_for_stem_at_equal_confidence():
    """Regression: with equal confidence and differing stems, the merge used to
    pick the solution window's restated stem on a JSON-text tiebreak. It must
    now prefer the question window."""
    question_fragment = _fragment(
        stem="如果 $C$ 是线段 $AB$ 延长线上一点，那么 $AB:BC$ 等于（ ）",
        answer=None,
        solution_steps=[],
    )
    # The solution window restates the stem with a leading "(4分)" prefix; under
    # the old JSON-sort tiebreak this ASCII-led value beat the CJK-led original.
    solution_fragment = _fragment(
        stem="(4分) 如果 $C$ 是线段 $AB$ 延长线上一点，那么 $AB:BC$ 等于 ( )",
        answer="A",
        solution_steps=["解：比例计算。"],
    )
    merged, _ = merge_with_issues(
        [
            _window("question-001-p001-p003", [question_fragment]),
            _window("solution-001-p010-p013", [solution_fragment]),
        ],
        paper=_paper(),
    )
    question = merged.questions[0]
    assert question.content.stem_latex.startswith("如果"), (
        "stem must come from the question window, not the restated solution window"
    )
    # The solution window still contributes answer/steps.
    assert question.content.answer == "A"


def test_merge_higher_confidence_still_wins_over_role_preference():
    """role preference only breaks ties at equal confidence; a genuinely more
    confident reading wins regardless of origin."""
    question_fragment = _fragment(
        stem="低置信题干",
        answer=None,
        solution_steps=[],
        confidence="low",
    )
    solution_fragment = _fragment(
        stem="高置信解析页重述题干",
        answer="A",
        solution_steps=["解。"],
        confidence="high",
    )
    merged, _ = merge_with_issues(
        [
            _window("question-001-p001-p003", [question_fragment]),
            _window("solution-001-p010-p013", [solution_fragment]),
        ],
        paper=_paper(),
    )
    # The high-confidence solution stem wins despite stem preferring question.
    assert merged.questions[0].content.stem_latex == "高置信解析页重述题干"


def test_merge_pending_anchor_placeholder_when_no_real_anchor():
    """When no window has a real solution anchor, merge fills a transparent
    placeholder (never a deceptive ``1．``) and marks evidence as conflicted."""
    question_fragment = _fragment(stem="题干", answer=None, solution_steps=[], anchor=None)
    solution_fragment = _fragment(
        stem=None, answer="A", solution_steps=["解。"], anchor=None
    )
    merged, issues = merge_with_issues(
        [
            _window("question-001-p001-p003", [question_fragment]),
            _window("solution-001-p010-p013", [solution_fragment]),
        ],
        paper=_paper(),
    )
    question = merged.questions[0]
    assert question.evidence.solution_start_anchor == _PENDING_SOLUTION_ANCHOR
    assert question.evidence.solution_end_anchor == _PENDING_SOLUTION_ANCHOR
    # The placeholder must surface in the conflict list (not pass silently).
    conflict_fields = {
        field for conflict in merged.conflicts for field in conflict.fields
    }
    assert "evidence.solution_start_anchor" in conflict_fields
    assert "evidence.solution_end_anchor" in conflict_fields
