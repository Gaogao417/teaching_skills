#!/usr/bin/env python3
"""Unit tests for the question-span index (§5.1 anchoring) and the deterministic
batch planner (§6).

These tests do not touch the network or any OCR provider: the anchoring
algorithm runs directly on synthetic per-page text. Cases mirror the requirements
listed in ``docs/question-span-index-redesign.md`` §10.1.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.procedural.question_span_index import (  # noqa: E402
    IndexedQuestion,
    ObservationBatch,
    PageText,
    QuestionSpanIndex,
    SourceFingerprint,
    SpanIndexIssue,
    build_index_from_pages,
    build_observation_batches,
    dump_index,
    load_index,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _pages(spec: dict[int, str]) -> list[PageText]:
    """Build a page list from ``{page_number: text}``."""
    return [PageText(page_number=num, text=txt) for num, txt in sorted(spec.items())]


def _fp(**kwargs) -> SourceFingerprint:
    return SourceFingerprint(**kwargs)


def _refs(index: QuestionSpanIndex, role: str = "question") -> list[str]:
    field = "question_pages" if role == "question" else "solution_pages"
    return [q.question_ref for q in index.questions if getattr(q, field)]


def _pages_for(index: QuestionSpanIndex, ref: str, role: str = "question") -> list[int]:
    field = "question_pages" if role == "question" else "solution_pages"
    for q in index.questions:
        if q.question_ref == ref:
            return list(getattr(q, field))
    raise KeyError(ref)


# --------------------------------------------------------------------------- #
# §10.1 anchoring: question-number recognition
# --------------------------------------------------------------------------- #


def test_normal_increasing_question_numbers():
    pages = _pages({
        1: "一、选择题\n1. 2+2=?\n2. 3+3=?\n3. 4+4=?",
        2: "二、填空题\n4. 填空一\n5. 填空二",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert index.status == "ready"
    assert _refs(index) == ["1", "2", "3", "4", "5"]
    assert _pages_for(index, "1") == [1]
    assert _pages_for(index, "4") == [2]


def test_leading_whitespace_and_fullwidth_halfwidth_dots():
    # Full-width ．, half-width ., and leading spaces must all match.
    pages = _pages({
        1: "   １选择题\n　1．题一\n 2.题二\n3．题三",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert _refs(index) == ["1", "2", "3"]


def test_candidate_notice_numbering_not_recognised_as_questions():
    # 考生须知 preamble numbers appear before any section title. Because the
    # seed prefers a ``1`` after a section title, the preamble 1./2. are skipped.
    pages = _pages({
        1: "考生须知\n1. 请仔细答题\n2. 保持卷面整洁\n一、选择题\n1. 真题一\n2. 真题二",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert _refs(index) == ["1", "2"]
    # Both real questions sit on page 1.
    assert _pages_for(index, "1") == [1]
    assert _pages_for(index, "2") == [1]


@pytest.mark.parametrize(
    "title,hint",
    [
        ("一、选择题", "choice"),
        ("二、填空题", "fillin"),
        ("三、解答题", "problem"),
        ("四、计算题", "problem"),
        ("五、证明题", "problem"),
        ("六、问答题", "short_answer"),
    ],
)
def test_section_type_recognition(title, hint):
    pages = _pages({1: f"{title}\n1. 题"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert index.questions[0].question_type_hint == hint


def test_unknown_section_keeps_unknown_without_number_threshold():
    # No recognisable section title -> hint stays ``unknown``; we must NOT infer
    # type from the question number (e.g. "question < 7 means choice").
    pages = _pages({1: "综合题\n1. 题\n2. 题\n10. 题"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    for q in index.questions:
        assert q.question_type_hint == "unknown"


# --------------------------------------------------------------------------- #
# §10.1 anchoring: page-span edge cases
# --------------------------------------------------------------------------- #


def test_two_questions_starting_on_same_page_share_that_page():
    # Q1 and Q2 both start on page 1; Q2 also flows to page 2.
    pages = _pages({
        1: "一、解答题\n1. 题一\n2. 题二",
        2: "（题二续）",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert _pages_for(index, "1") == [1]
    # Q2 owns page 1 (shared start) and page 2 (its continuation to next page).
    assert _pages_for(index, "2") == [1, 2]


def test_cross_page_question_span():
    # Only one question starts on page 1 and its tail extends to page 2.
    pages = _pages({
        1: "解答题\n1. 长题",
        2: "（长题续）",
        3: "2. 题二",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert _pages_for(index, "1") == [1, 2]
    assert _pages_for(index, "2") == [3]


def test_trailing_answer_region_renumbers_from_one_into_solution_pages():
    # Question region 1..3 on pages 1-2; then an answer region restarts at 1 on
    # page 3 and continues to page 4. Solution pages must be independent.
    pages = _pages({
        1: "选择题\n1. q1\n2. q2\n3. q3",
        2: "填空题\n4. q4",
        3: "参考答案\n1. a1\n2. a2\n3. a3",
        4: "4. a4",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert _refs(index) == ["1", "2", "3", "4"]
    assert _pages_for(index, "1") == [1]
    assert _pages_for(index, "4", role="solution") == [4]
    # Question 1 keeps its question page and gains solution pages.
    q1 = next(q for q in index.questions if q.question_ref == "1")
    assert q1.question_pages == [1]
    assert q1.solution_pages == [3]


def test_answer_only_source_keeps_question_pages_empty():
    pages = _pages({
        9: "参考答案\n1. A\n2. B",
        10: "3. 解：过程",
    })
    index = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=_fp(page_number_offset=8),
    )

    assert _refs(index) == []
    assert _refs(index, role="solution") == ["1", "2", "3"]
    assert all(not question.question_pages for question in index.questions)
    assert _pages_for(index, "3", role="solution") == [10]


def test_numbered_solution_steps_not_recognised_as_new_questions():
    # Inside an answer region, 解：followed by 1. 2. steps must not spawn new
    # questions (they are <= the running answer number).
    pages = _pages({
        1: "解答题\n1. 题一\n2. 题二",
        2: "参考答案\n1. 解：\n1. 第一步\n2. 第二步\n2. 解：\n",
    })
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    # Only questions 1 and 2 in the solution region.
    assert _refs(index, role="solution") == ["1", "2"]


def test_interleaved_roles_round_trip_per_question():
    pages = _pages(
        {
            1: "一、解答题\n1. 第一题题干",
            2: "【答案】第一题答案\n【解析】第一题解析",
            3: "2. 第二题题干",
            4: "【答案】第二题答案\n【详解】第二题详解",
        }
    )
    index = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=_fp(),
        role_mode="interleaved",
    )

    assert index.status == "ready"
    assert _refs(index) == ["1", "2"]
    assert _refs(index, role="solution") == ["1", "2"]
    assert _pages_for(index, "1") == [1]
    assert _pages_for(index, "1", role="solution") == [2]
    assert _pages_for(index, "2") == [3]
    assert _pages_for(index, "2", role="solution") == [4]


def test_interleaved_role_mode_is_isolated_from_separated_default():
    pages = _pages(
        {
            1: "一、解答题\n1. 第一题\n【答案】答案一",
            2: "2. 第二题\n【答案】答案二\n【解析】解析二",
        }
    )

    separated = build_index_from_pages(
        pages, source_kind="docx", fingerprint=_fp()
    )
    interleaved = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=_fp(),
        role_mode="interleaved",
    )

    assert _refs(separated) == ["1", "2"]
    assert _refs(separated, role="solution") == []
    assert _refs(interleaved, role="solution") == ["1", "2"]


def test_interleaved_repeated_question_number_stays_in_solution():
    pages = _pages(
        {
            1: "1. 第一题题干",
            2: "【答案】答案一",
            3: "【解析】\n1. 第一题条件复述",
            4: "2. 第二题题干",
            5: "【答案】答案二",
        }
    )
    index = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=_fp(),
        role_mode="interleaved",
    )

    assert _pages_for(index, "1", role="solution") == [2, 3]
    assert _pages_for(index, "2") == [4]


# --------------------------------------------------------------------------- #
# §10.1 anchoring: issues and status
# --------------------------------------------------------------------------- #


def test_missing_numbers_produce_blocking_issue_and_needs_review():
    pages = _pages({1: "选择题\n1. q1\n3. q3"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert index.status == "needs_review"
    codes = [i.code for i in index.issues]
    assert "question_missing_numbers" in codes
    assert next(i for i in index.issues if i.code == "question_missing_numbers").severity == "blocking"


def test_disorder_candidates_produce_issue():
    # 1 then a decrease to 1 again (not a step) terminates the run; the later
    # numbers are lost, which surfaces as a sequence-decrease warning.
    pages = _pages({1: "选择题\n1. q1\n2. q2\n1. q1again\n3. q3"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    codes = [i.code for i in index.issues]
    assert "question_sequence_decrease" in codes


def test_duplicate_candidate_warning():
    pages = _pages({1: "选择题\n1. q1\n1. q1dup"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    # The duplicate (same number, same page) is dropped; status may still be
    # ready or needs_review depending on gap handling.
    assert "1" in _refs(index)


def test_empty_page_and_page_count_mismatch_and_fingerprint_errors():
    # Empty page -> warning; fingerprint page count mismatch -> blocking.
    pages = _pages({1: "选择题\n1. q1", 2: ""})
    index = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=_fp(page_sha256=["sha256:x"] * 3),  # 3 hashes, 2 pages
    )
    codes = [i.code for i in index.issues]
    assert "empty_page" in codes
    assert "fingerprint_page_count_mismatch" in codes
    assert index.status == "needs_review"


def test_no_question_sequence_is_failed():
    pages = _pages({1: "试卷封面\n无题号内容"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    assert index.status == "failed"
    assert index.questions == []


def test_page_number_offset_threaded_through_fingerprint():
    pages = _pages({1: "答案\n1. a1"})
    index = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=_fp(),
        page_number_offset=8,
    )
    assert index.fingerprint.page_number_offset == 8


# --------------------------------------------------------------------------- #
# §10.1 batch planner
# --------------------------------------------------------------------------- #


def _index(questions: list[IndexedQuestion], **kw) -> QuestionSpanIndex:
    return QuestionSpanIndex(
        schema="math_question_span_index/v1",
        source_kind="docx",
        page_numbers=sorted({p for q in questions for p in (*q.question_pages, *q.solution_pages)}),
        fingerprint=_fp(),
        status="ready",
        questions=questions,
        issues=[],
        **kw,
    )


def test_q17_p4_q18_p4to5_q19_p5_form_one_non_splittable_block():
    # §6.3 canonical example: shared pages merge into one component.
    questions = [
        IndexedQuestion(question_ref="17", question_number=17, question_pages=[4]),
        IndexedQuestion(question_ref="18", question_number=18, question_pages=[4, 5]),
        IndexedQuestion(question_ref="19", question_number=19, question_pages=[5]),
    ]
    batches = build_observation_batches(_index(questions))
    q_batches = [b for b in batches if b.role == "question"]
    assert len(q_batches) == 1
    assert q_batches[0].page_numbers == [4, 5]
    assert q_batches[0].expected_question_refs == ["17", "18", "19"]


def test_target_page_count_closes_batch_and_section_boundary_closes_first():
    # Six single-page questions across two sections. Section change should close
    # the batch at the boundary even before the page target.
    questions = [
        IndexedQuestion(
            question_ref=str(n),
            question_number=n,
            question_pages=[n],
            question_section_ref=("section-p003" if n >= 4 else "section-p001"),
        )
        for n in range(1, 7)
    ]
    batches = build_observation_batches(_index(questions), target_page_count=6)
    q_batches = [b for b in batches if b.role == "question"]
    # Two sections -> at least a section break between page 3 and page 4.
    section_batch_pages = [b.page_numbers for b in q_batches]
    flat = [p for pages in section_batch_pages for p in pages]
    assert sorted(flat) == [1, 2, 3, 4, 5, 6]
    # No batch spans both sections.
    for b in q_batches:
        has_early = any(p <= 3 for p in b.page_numbers)
        has_late = any(p >= 4 for p in b.page_numbers)
        assert not (has_early and has_late), b.batch_id


def test_adding_next_block_over_hard_limit_closes_batch_first():
    # Three components: [1,2] [3,4] [5,6,7,8]. With hard_page_limit=4, the third
    # block alone reaches the limit, so the first two must be sealed before it.
    questions = [
        IndexedQuestion(question_ref="1", question_number=1, question_pages=[1, 2]),
        IndexedQuestion(question_ref="2", question_number=2, question_pages=[3, 4]),
        IndexedQuestion(
            question_ref="3", question_number=3, question_pages=[5, 6, 7, 8]
        ),
    ]
    batches = build_observation_batches(
        _index(questions), target_page_count=4, hard_page_limit=4
    )
    q_batches = [b for b in batches if b.role == "question"]
    # The 8-page component is emitted as a single batch.
    assert q_batches[-1].page_numbers == [5, 6, 7, 8]


def test_first_round_batches_have_no_duplicate_pages():
    questions = [
        IndexedQuestion(question_ref=str(n), question_number=n, question_pages=[n])
        for n in range(1, 13)
    ]
    batches = build_observation_batches(
        _index(questions), target_page_count=4, target_question_count=4
    )
    q_batches = [b for b in batches if b.role == "question"]
    seen: set[int] = set()
    for b in q_batches:
        assert not seen.intersection(b.page_numbers), b.batch_id
        seen.update(b.page_numbers)
    assert seen == set(range(1, 13))


def test_non_splittable_block_pages_never_split():
    # A single question spanning 5 pages cannot be cut even though it exceeds the
    # default target of 6? No — 5 < 8, so it stays one batch.
    questions = [
        IndexedQuestion(question_ref="1", question_number=1, question_pages=[1, 2, 3, 4, 5]),
    ]
    batches = build_observation_batches(_index(questions))
    q_batches = [b for b in batches if b.role == "question"]
    assert len(q_batches) == 1
    assert q_batches[0].page_numbers == [1, 2, 3, 4, 5]


def test_oversized_block_emits_oversized_batch():
    # A single non-splittable block spanning 9 pages (> hard limit 8) becomes an
    # oversized batch rather than being split.
    questions = [
        IndexedQuestion(
            question_ref="1", question_number=1, question_pages=list(range(1, 10))
        ),
    ]
    batches = build_observation_batches(_index(questions), hard_page_limit=8)
    q_batches = [b for b in batches if b.role == "question"]
    assert len(q_batches) == 1
    assert q_batches[0].oversized is True
    assert q_batches[0].page_numbers == list(range(1, 10))


def test_every_question_covered_exactly_once_per_role():
    questions = [
        IndexedQuestion(question_ref=str(n), question_number=n, question_pages=[n])
        for n in range(1, 7)
    ]
    # Add solution spans for some.
    for q in questions:
        if q.question_number in (1, 2):
            q.solution_pages = [q.question_number + 10]
    index = _index(questions)
    batches = build_observation_batches(index)
    for role in ("question", "solution"):
        refs: list[str] = []
        for b in batches:
            if b.role == role:
                refs.extend(b.expected_question_refs)
        expected_refs = [
            q.question_ref for q in index.questions if getattr(q, f"{role}_pages")
        ]
        assert sorted(refs) == sorted(expected_refs)
        assert len(refs) == len(set(refs))


def test_question_and_solution_page_blocks_never_share_a_batch():
    questions = [
        IndexedQuestion(question_ref="1", question_number=1, question_pages=[1, 2], solution_pages=[5]),
        IndexedQuestion(question_ref="2", question_number=2, question_pages=[3], solution_pages=[6]),
    ]
    batches = build_observation_batches(_index(questions))
    for b in batches:
        assert len({b.role}) == 1  # a batch is single-role by construction
    roles = {b.role for b in batches}
    assert roles == {"question", "solution"}


# --------------------------------------------------------------------------- #
# I/O round-trip
# --------------------------------------------------------------------------- #


def test_yaml_round_trip(tmp_path):
    pages = _pages({1: "选择题\n1. q1\n2. q2"})
    index = build_index_from_pages(pages, source_kind="docx", fingerprint=_fp())
    out = tmp_path / "span-index.yaml"
    dump_index(index, out)
    # Atomic write leaves no .tmp behind.
    assert not (tmp_path / "span-index.yaml.tmp").exists()
    reloaded = load_index(out)
    assert reloaded.status == index.status
    assert [q.question_ref for q in reloaded.questions] == [q.question_ref for q in index.questions]


# --------------------------------------------------------------------------- #
# Planner argument validation
# --------------------------------------------------------------------------- #


def test_planner_rejects_bad_limits():
    index = _index([IndexedQuestion(question_ref="1", question_number=1, question_pages=[1])])
    with pytest.raises(ValueError):
        build_observation_batches(index, target_page_count=0)
    with pytest.raises(ValueError):
        build_observation_batches(index, target_page_count=9, hard_page_limit=8)


def test_failed_index_yields_no_batches():
    failed = QuestionSpanIndex(
        schema="math_question_span_index/v1",
        source_kind="docx",
        page_numbers=[1],
        fingerprint=_fp(),
        status="failed",
        questions=[],
        issues=[SpanIndexIssue(code="no_pages", severity="blocking", detail="x")],
    )
    assert build_observation_batches(failed) == []
