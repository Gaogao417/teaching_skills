#!/usr/bin/env python3
"""Question-span index: 先索引、后定点转写的观察前置层.

本模块实现 ``docs/question-span-index-redesign.md`` §4-§6:

* ``QuestionSpanIndex`` 及其子模型 (§4) —— 一个低成本的逐页预扫产物,给出每个
  ``question_ref`` 的题干页集合 / 答案页集合、题型提示和结构化 issue;
* :func:`build_index_from_pages` (§5.1) —— 从逐页文本锚定题号、章节标题、角色信号,
  分题目区 / 答案区两段建索引,再汇总到同一个 ``IndexedQuestion``;
* :func:`build_observation_batches` (§6) —— 把索引变成确定性、首轮页面互不重叠的
  正式观察批次.

它刻意不复刻 ``extract_docx_source.py::attribute_images()`` 的全或无单调状态机
(§5.1 step 3):该状态机会把解答内部的编号步骤和后置答案区的题号重启当作噪声,而本
模块必须分别容纳题目区和答案区两套独立序列.

下游 ``DocxObservationBundle`` / ``MergedPdfObservation`` / 公开
``QuestionTranscriptionBundle`` 的结构都不改变;本模块只决定"正式视觉转写每批看哪些
页、必须返回哪些题号".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.question_transcription.contracts import NonEmptyStr


# --------------------------------------------------------------------------- #
# Local strict base (re-declared per file, matching the existing convention)
# --------------------------------------------------------------------------- #


class _Strict(BaseModel):
    """Strict base: reject unknown keys so contracts surface typos early."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

QuestionRole = Literal["question", "solution"]
QuestionTypeHint = Literal["choice", "fillin", "problem", "short_answer", "unknown"]
IndexStatus = Literal["ready", "needs_review", "failed"]
IssueSeverity = Literal["warning", "blocking"]
Confidence = Literal["high", "medium", "low"]


# --------------------------------------------------------------------------- #
# §4 contracts
# --------------------------------------------------------------------------- #


class SourceFingerprint(_Strict):
    """Identity of the underlying source so observe can refuse a stale index.

    ``source_sha256`` is the whole-source hash (rendered PDF / original PDF) and
    is ``None`` when a builder genuinely cannot produce one; ``page_sha256`` is
    the per-page PNG hash list in page-number order (one entry per page).
    """

    source_sha256: str | None = None
    page_sha256: list[str] = Field(default_factory=list)
    page_number_offset: int = Field(default=0, ge=0)


class SpanIndexIssue(_Strict):
    """Structured index defect surfaced for human / tooling review."""

    code: NonEmptyStr
    severity: IssueSeverity
    detail: NonEmptyStr
    page_number: int | None = Field(default=None, ge=1)
    question_ref: str | None = None


class IndexedQuestion(_Strict):
    """A single question's page spans across the question and solution roles.

    ``question_pages`` / ``solution_pages`` are expanded *only* within their own
    role region; a role that does not appear in this source keeps an empty list
    (e.g. an answer-only file leaves ``question_pages`` empty). A page may belong
    to two questions when they both start on it.
    """

    question_ref: NonEmptyStr
    question_number: int = Field(ge=1)
    question_pages: list[int] = Field(default_factory=list)
    solution_pages: list[int] = Field(default_factory=list)
    question_section_ref: str | None = None
    solution_section_ref: str | None = None
    question_type_hint: QuestionTypeHint = "unknown"
    question_confidence: Confidence | None = None
    solution_confidence: Confidence | None = None

    @model_validator(mode="after")
    def _pages_sorted_and_unique(self) -> "IndexedQuestion":
        if not self.question_pages and not self.solution_pages:
            raise ValueError(
                "at least one of question_pages or solution_pages must be non-empty"
            )
        for field_name in ("question_pages", "solution_pages"):
            value = getattr(self, field_name)
            if value != sorted(set(value)):
                raise ValueError(
                    f"{field_name} must be a strictly ascending list of unique "
                    f"page numbers (got {value!r})"
                )
        return self


class QuestionSpanIndex(_Strict):
    """The frozen span index persisted as ``math_question_span_index/v1``."""

    schema_: Literal["math_question_span_index/v1"] = Field(alias="schema")
    source_kind: Literal["docx", "pdf"]
    page_numbers: list[int] = Field(min_length=1)
    fingerprint: SourceFingerprint
    status: IndexStatus
    questions: list[IndexedQuestion]
    issues: list[SpanIndexIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> "QuestionSpanIndex":
        if self.page_numbers != sorted(set(self.page_numbers)):
            raise ValueError("page_numbers must be strictly ascending and unique")
        known_pages = set(self.page_numbers)
        for question in self.questions:
            for page in (*question.question_pages, *question.solution_pages):
                if page not in known_pages:
                    raise ValueError(
                        f"question {question.question_ref} references page {page} "
                        f"which is not in page_numbers"
                    )
        refs = [question.question_ref for question in self.questions]
        if len(refs) != len(set(refs)):
            raise ValueError("question_ref must be unique within the index")
        # ``failed`` is reserved for indexes with no usable question sequence at
        # all; if there are questions the status must be ready or needs_review.
        if self.status == "failed" and self.questions:
            raise ValueError("status 'failed' must carry an empty question list")
        return self


# --------------------------------------------------------------------------- #
# §6 deterministic batch plan
# --------------------------------------------------------------------------- #


class ObservationBatch(_Strict):
    """A single first-round observation batch for one role.

    ``page_numbers`` is the batch's page footprint (first round, so disjoint
    across batches of the same role). ``expected_question_refs`` is the exact set
    the provider must return. ``oversized`` marks a single non-splittable block
    that by itself exceeds ``hard_page_limit``.
    """

    batch_id: NonEmptyStr
    role: QuestionRole
    page_numbers: list[int] = Field(min_length=1)
    expected_question_refs: list[NonEmptyStr] = Field(min_length=1)
    section_refs: list[str] = Field(default_factory=list)
    oversized: bool = False

    @model_validator(mode="after")
    def _pages_sorted_and_refs_unique(self) -> "ObservationBatch":
        if self.page_numbers != sorted(set(self.page_numbers)):
            raise ValueError(
                f"batch {self.batch_id} page_numbers must be strictly ascending "
                f"and unique (got {self.page_numbers!r})"
            )
        refs = self.expected_question_refs
        if len(refs) != len(set(refs)):
            raise ValueError(
                f"batch {self.batch_id} expected_question_refs must be unique"
            )
        return self


# --------------------------------------------------------------------------- #
# §5.1 page-text input + anchoring regexes
# --------------------------------------------------------------------------- #


class PageText(_Strict):
    """A single page's text used by the anchoring algorithm."""

    page_number: int = Field(ge=1)
    text: str = Field(default="")
    sha256: str | None = None


# Line-leading question-number candidate, tolerant of full-width / half-width
# dots and leading whitespace. A number followed by a dot is the Chinese exam
# question-number convention.
_QUESTION_NUMBER_RE = re.compile(r"^\s*(\d{1,3})[．.]")
# Answer sheets commonly place several short answers on one line:
# ``1.C； 2.B； 3.A``. Only semicolon-delimited occurrences are accepted after
# the first one so decimal/table values such as ``36.0 36.1`` are not promoted
# to question anchors.
_COMPACT_ANSWER_NUMBER_RE = re.compile(r"(?:^|[；;])\s*(\d{1,3})[．.]")

# Headings that switch the running role into the answer / solution region.
_ANSWER_REGION_RE = re.compile(
    r"参考答案|试题答案|答案及解析|答案与解析|参考答案及解析|答案部分|答案$|解析$"
)
# Role markers that indicate solution text (inside a question or a region).
_SOLUTION_MARKER_RE = re.compile(r"^\s*(?:解|证明|答|解答)[：:]")


@dataclass
class _NumberCandidate:
    """A line-leading question-number hit, with its inferred role and context."""

    page_number: int
    line: str
    number: int
    role: QuestionRole
    # Type hint of the most recent section title seen before this candidate.
    type_hint: QuestionTypeHint = "unknown"
    # True if a solution marker (解：/证明：/答：) appeared between the previous
    # candidate and this one on the same page → likely a numbered solution step.
    after_solution_marker: bool = False


@dataclass
class _RegionalItem:
    """An accepted question inside one role region, before merging."""

    question_ref: str
    question_number: int
    pages: list[int]
    section_ref: str | None
    type_hint: QuestionTypeHint
    confidence: Confidence


# --------------------------------------------------------------------------- #
# §5.1 build_index_from_pages
# --------------------------------------------------------------------------- #


def build_index_from_pages(
    pages: Sequence[PageText | Mapping[str, Any]],
    *,
    source_kind: Literal["docx", "pdf"],
    fingerprint: SourceFingerprint | Mapping[str, Any],
    page_number_offset: int = 0,
) -> QuestionSpanIndex:
    """Build a :class:`QuestionSpanIndex` from per-page text.

    ``pages`` is an ordered sequence of page records (either :class:`PageText`
    or mappings with ``page_number`` / ``text`` / optional ``sha256``). The
    algorithm keeps text per page (never concatenates into a whole-paper string),
    collects line-leading question-number candidates, splits them into a question
    region and a solution region, and builds the longest credible increasing
    sequence inside each region (§5.1).

    The status is derived from the structured issues (§5.1 gate):

    * ``ready`` —— question-number sequence and role spans are determinable;
    * ``needs_review`` —— a candidate index exists but a blocking issue could
      cause a missed question or a mis-split role;
    * ``failed`` —— no usable question sequence, page misalignment, or an
      incomplete fingerprint.
    """
    normalised_pages = _coerce_pages(pages)
    fp = _coerce_fingerprint(fingerprint, page_number_offset)
    issues: list[SpanIndexIssue] = []

    if not normalised_pages:
        issues.append(
            SpanIndexIssue(
                code="no_pages",
                severity="blocking",
                detail="span index received no pages",
            )
        )
        return QuestionSpanIndex(
            schema="math_question_span_index/v1",
            source_kind=source_kind,
            page_numbers=[],
            fingerprint=fp,
            status="failed",
            questions=[],
            issues=issues,
        )

    page_numbers = [page.page_number for page in normalised_pages]
    _validate_page_continuity(page_numbers, issues)

    # Fingerprint cross-check: if the builder supplied per-page SHAs, the count
    # must match the page count we were given.
    if fp.page_sha256 and len(fp.page_sha256) != len(normalised_pages):
        issues.append(
            SpanIndexIssue(
                code="fingerprint_page_count_mismatch",
                severity="blocking",
                detail=(
                    f"fingerprint has {len(fp.page_sha256)} page hashes but "
                    f"{len(normalised_pages)} pages were supplied"
                ),
            )
        )

    # Empty-page warnings (OCR may emit a blank page for a blank scan leaf).
    for page in normalised_pages:
        if not page.text.strip():
            issues.append(
                SpanIndexIssue(
                    code="empty_page",
                    severity="warning",
                    detail=f"page {page.page_number} has no extractable text",
                    page_number=page.page_number,
                )
            )

    candidates = _collect_candidates(normalised_pages)

    question_items, solution_items, region_issues = _assemble_regions(
        candidates, page_numbers
    )
    issues.extend(region_issues)

    # Merge the two regional sequences by question_ref. A ref appearing in both
    # regions keeps its question_pages from the question region and its
    # solution_pages from the solution region.
    questions = _merge_regional_items(question_items, solution_items)

    status = _derive_status(questions, issues)
    return QuestionSpanIndex(
        schema="math_question_span_index/v1",
        source_kind=source_kind,
        page_numbers=page_numbers,
        fingerprint=fp,
        status=status,
        questions=questions,
        issues=issues,
    )


# --------------------------------------------------------------------------- #
# Candidate collection
# --------------------------------------------------------------------------- #


def _collect_candidates(pages: list[PageText]) -> list[_NumberCandidate]:
    """Walk every page line and collect question-number candidates.

    The running role starts as ``question``. An answer-region heading (参考答案 /
    答案及解析 / ...) switches the role to ``solution`` for the remainder of the
    paper. A section title (选择题 / 填空题 / 解答题 / ...) contributes the
    running type hint but does not change the role.

    A solution marker (解：/ 证明：/ 答：) between two candidates on the same page
    flags the later candidate as a probable numbered solution step.
    """
    candidates: list[_NumberCandidate] = []
    role: QuestionRole = "question"
    current_hint: QuestionTypeHint = "unknown"
    saw_solution_marker_on_page = False

    for page in pages:
        saw_solution_marker_on_page = False
        for line in page.text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # An answer-region heading switches the running role for the rest of
            # the paper. We require it to look like a heading (short or ending
            # with heading punctuation) so body prose mentioning "答案" is ignored.
            if role == "question" and _is_answer_heading(stripped):
                role = "solution"
                continue

            title_hint = _match_section_title(stripped)
            if title_hint is not None:
                current_hint = title_hint
                continue

            # A solution marker flags subsequent numbered lines on the same page
            # as probable solution steps.
            if _SOLUTION_MARKER_RE.match(stripped):
                saw_solution_marker_on_page = True
                continue

            matches = (
                list(_COMPACT_ANSWER_NUMBER_RE.finditer(stripped))
                if role == "solution"
                else [match] if (match := _QUESTION_NUMBER_RE.match(stripped)) else []
            )
            for match in matches:
                number = int(match.group(1))
                candidates.append(
                    _NumberCandidate(
                        page_number=page.page_number,
                        line=stripped,
                        number=number,
                        role=role,
                        type_hint=current_hint,
                        after_solution_marker=saw_solution_marker_on_page,
                    )
                )
        # Once we have entered the answer region we keep role=solution across
        # pages (an answer section is contiguous and never flips back).
    return candidates


def _is_answer_heading(line: str) -> bool:
    """True when ``line`` looks like a standalone answer-region heading.

    We require both an answer keyword and heading-like shape (short line, or the
    keyword sits at the start/end) so ordinary sentences are not misread.
    """
    if not _ANSWER_REGION_RE.search(line):
        return False
    if len(line) <= 16:
        return True
    # Allow longer lines that are clearly a heading followed by punctuation.
    return line.endswith(("：", ":", "。", ".", ")", "）", "—", "-", " "))


def _match_section_title(line: str) -> QuestionTypeHint | None:
    """Return a type hint if ``line`` is a recognised section title."""
    if "选择题" in line:
        return "choice"
    if "填空题" in line:
        return "fillin"
    if "解答题" in line or "计算题" in line or "证明题" in line:
        return "problem"
    if "问答题" in line or "简答题" in line:
        return "short_answer"
    return None


# --------------------------------------------------------------------------- #
# Regional sequence assembly (the core of §5.1 step 3-5)
# --------------------------------------------------------------------------- #


def _assemble_regions(
    candidates: list[_NumberCandidate], page_numbers: list[int]
) -> tuple[list[_RegionalItem], list[_RegionalItem], list[SpanIndexIssue]]:
    """Split candidates into question / solution regions and find sequences.

    Each region's boundary is computed so the last question of a region may span
    continuation pages up to (but not including) the first page of the other
    role's region, or the last page if there is no other region (§5.1 step 5).
    """
    issues: list[SpanIndexIssue] = []
    by_role: dict[QuestionRole, list[_NumberCandidate]] = {
        "question": [],
        "solution": [],
    }
    for candidate in candidates:
        by_role[candidate.role].append(candidate)

    # Determine the first page of each region (the page of its earliest
    # candidate) so the other region's tail stops before it.
    first_page: dict[QuestionRole, int | None] = {"question": None, "solution": None}
    for role in ("question", "solution"):
        if by_role[role]:
            first_page[role] = min(c.page_number for c in by_role[role])

    def _tail_exclusive(role: QuestionRole) -> int:
        """Exclusive upper page bound for ``role``'s region.

        The question region stops where the solution region begins (or the last
        page if there is no solution region); the solution region is always last
        and always runs to the end of the document.
        """
        if role == "question":
            # Question region stops where the solution region begins; if there
            # is no solution region it runs to the last page.
            if first_page["solution"] is not None:
                return first_page["solution"]  # type: ignore[return-value]
            return page_numbers[-1] + 1
        # Solution region is always last and always runs to the end of the
        # document, regardless of where the question region started.
        return page_numbers[-1] + 1

    question_items, q_issues = _build_regional_sequence(
        by_role["question"],
        page_numbers,
        role="question",
        tail_exclusive=_tail_exclusive("question"),
    )
    solution_items, s_issues = _build_regional_sequence(
        by_role["solution"],
        page_numbers,
        role="solution",
        tail_exclusive=_tail_exclusive("solution"),
    )
    issues.extend(q_issues)
    issues.extend(s_issues)
    # Cross-region alignment: if both regions established a credible sequence,
    # a question number present in one region but absent from the other signals
    # a missing transcription target and must downgrade status to needs_review.
    # (This cannot detect a number missing from *both* regions at once — that
    # requires an expected question count, which is out of scope here.)
    q_nums = {item.question_number for item in question_items}
    s_nums = {item.question_number for item in solution_items}
    if q_nums and s_nums:
        for n in sorted(q_nums - s_nums):
            issues.append(
                SpanIndexIssue(
                    code="solution_region_missing_question",
                    severity="blocking",
                    detail=(
                        f"question {n} present in question region but absent from "
                        f"solution region"
                    ),
                    question_ref=str(n),
                )
            )
        for n in sorted(s_nums - q_nums):
            issues.append(
                SpanIndexIssue(
                    code="question_region_missing_question",
                    severity="blocking",
                    detail=(
                        f"question {n} present in solution region but absent from "
                        f"question region"
                    ),
                    question_ref=str(n),
                )
            )
    return question_items, solution_items, issues


def _build_regional_sequence(
    candidates: list[_NumberCandidate],
    page_numbers: list[int],
    *,
    role: QuestionRole,
    tail_exclusive: int,
) -> tuple[list[_RegionalItem], list[SpanIndexIssue]]:
    """Find the longest credible increasing sequence within one role region.

    Rules (§5.1 step 3-5):

    * Preamble numbering before the first section title (考生须知) is dropped.
    * A candidate is accepted as a real question when its number is strictly
      greater than the last accepted number. A candidate whose number is ``<=``
      the last accepted number is treated as a solution step / enumeration and
      skipped (with a warning). This is robust for the target domain: numbered
      solution steps only appear under large-numbered 解答题, so step numbers
      are always below the running question number.
    * The seed is the first ``1`` after a section title (or the first candidate
      if no section title was seen). We then keep the longest strictly-increasing
      run; a decrease terminates the credible run.
    * Pages are assigned by scanning forward from each accepted candidate's page
      up to (but not including) the next accepted candidate's page. Two questions
      may therefore share a start page.
    * The last question in a region does not swallow pages belonging to the
      other role: its tail is bounded by ``tail_exclusive`` (the first page of
      the next role's region, or one past the last page).
    """
    issues: list[SpanIndexIssue] = []
    if not candidates:
        return [], []

    sequence = _longest_increasing_run(candidates, role=role, issues=issues)
    if not sequence:
        issues.append(
            SpanIndexIssue(
                code=f"no_{role}_sequence",
                severity="blocking",
                detail=f"could not establish a credible {role} question sequence",
            )
        )
        return [], issues

    numbers = [item.number for item in sequence]
    _report_gaps_and_disorder(numbers, role, issues)

    page_set = set(page_numbers)
    items: list[_RegionalItem] = []
    for index, candidate in enumerate(sequence):
        start_page = candidate.page_number
        if index + 1 < len(sequence):
            next_page = sequence[index + 1].page_number
        else:
            # The last question spans its continuation pages up to the region's
            # boundary (the start of the other role's region, or one past last).
            next_page = tail_exclusive
        pages = _pages_between(start_page, next_page, page_set)
        if not pages:
            pages = [start_page] if start_page in page_set else []
        if not pages:
            # The candidate's page is outside page_numbers; record and skip.
            issues.append(
                SpanIndexIssue(
                    code=f"{role}_candidate_page_out_of_range",
                    severity="blocking",
                    detail=(
                        f"question {candidate.number} candidate page "
                        f"{start_page} is outside page_numbers"
                    ),
                    page_number=start_page,
                    question_ref=str(candidate.number),
                )
            )
            continue
        section_ref = _section_ref_for_candidate(candidate)
        items.append(
            _RegionalItem(
                question_ref=str(candidate.number),
                question_number=candidate.number,
                pages=pages,
                section_ref=section_ref,
                type_hint=candidate.type_hint,
                confidence="medium",
            )
        )
    return items, issues


def _longest_increasing_run(
    candidates: list[_NumberCandidate],
    *,
    role: QuestionRole,
    issues: list[SpanIndexIssue],
) -> list[_NumberCandidate]:
    """Return the longest credible strictly-increasing candidate subsequence.

    Real rendered pages contain numeric table rows (for example ``36.0``) and
    answer prose with numbered steps. Stopping at the first later decrease lets
    one such outlier truncate the entire paper. Starting from the trusted seed,
    choose the longest increasing subsequence instead; skipped decreases are
    still recorded for review.
    """
    if not candidates:
        return []

    # Choose the best seed: prefer the first ``1`` after a section title; fall
    # back to the first candidate whose type hint is known, then the first.
    seed_index = _choose_seed_index(candidates)
    if seed_index is None:
        return []

    tail = candidates[seed_index:]
    paths: list[list[int] | None] = [None] * len(tail)
    paths[0] = [0]
    for index in range(1, len(tail)):
        best: list[int] | None = None
        for previous in range(index):
            path = paths[previous]
            if path is None or tail[previous].number >= tail[index].number:
                continue
            proposal = [*path, index]
            if best is None or len(proposal) > len(best):
                best = proposal
            elif len(proposal) == len(best):
                # Prefer the path with smaller cumulative numeric jumps.
                proposal_gap = sum(
                    tail[b].number - tail[a].number
                    for a, b in zip(proposal, proposal[1:])
                )
                best_gap = sum(
                    tail[b].number - tail[a].number
                    for a, b in zip(best, best[1:])
                )
                if proposal_gap < best_gap:
                    best = proposal
        paths[index] = best

    viable = [path for path in paths if path]
    if not viable:
        return []
    best_path = max(
        viable,
        key=lambda path: (
            len(path),
            -sum(
                tail[b].number - tail[a].number
                for a, b in zip(path, path[1:])
            ),
        ),
    )
    accepted_indices = set(best_path)

    previous_raw = tail[0]
    for index, candidate in enumerate(tail[1:], start=1):
        if candidate.after_solution_marker and candidate.number <= previous_raw.number:
            issues.append(
                SpanIndexIssue(
                    code="solution_step_number",
                    severity="warning",
                    detail=(
                        f"number {candidate.number} on page "
                        f"{candidate.page_number} follows a solution marker and "
                        f"is <= preceding candidate {previous_raw.number}; treated as a "
                        f"solution step, not a new question"
                    ),
                    page_number=candidate.page_number,
                    question_ref=str(candidate.number),
                )
            )
        elif candidate.number < previous_raw.number:
            issues.append(
                SpanIndexIssue(
                    code=f"{role}_sequence_decrease",
                    severity="warning",
                    detail=(
                        f"candidate number decreased from {previous_raw.number} "
                        f"to {candidate.number} on page {candidate.page_number}; "
                        "the longest credible increasing sequence skips the noise"
                    ),
                    page_number=candidate.page_number,
                    question_ref=str(candidate.number),
                )
            )
        previous_raw = candidate

    return [tail[index] for index in best_path if index in accepted_indices]


def _choose_seed_index(candidates: list[_NumberCandidate]) -> int | None:
    """Pick the seed for the increasing run.

    Preference order: the first candidate with number ``1`` whose type hint is
    known (i.e. it sits after a section title, so 考生须知 preamble is skipped);
    failing that, the first candidate with number ``1``; failing that, the first
    candidate with a known type hint; otherwise the first candidate.
    """
    if not candidates:
        return None
    for index, candidate in enumerate(candidates):
        if candidate.number == 1 and candidate.type_hint != "unknown":
            return index
    for index, candidate in enumerate(candidates):
        if candidate.number == 1:
            return index
    for index, candidate in enumerate(candidates):
        if candidate.type_hint != "unknown":
            return index
    return 0


def _pages_between(start_page: int, end_page: int, page_set: set[int]) -> list[int]:
    """Return pages in ``page_set`` with ``start_page <= page < end_page``.

    When ``end_page <= start_page`` (two questions share a start page) return
    ``[start_page]`` so both questions own that page.
    """
    if end_page <= start_page:
        return [start_page] if start_page in page_set else []
    return sorted(p for p in page_set if start_page <= p < end_page)


def _section_ref_for_candidate(candidate: _NumberCandidate) -> str:
    """Stable advisory section label shared across one recognised section.

    A page-derived label made every page look like a section transition, which
    defeated greedy batch packing and regressed to one formal call per page.
    """
    return f"{candidate.role}-{candidate.type_hint}"


def _report_gaps_and_disorder(
    numbers: list[int], role: QuestionRole, issues: list[SpanIndexIssue]
) -> None:
    """Surface missing numbers inside an accepted sequence as a blocking issue."""
    if len(numbers) < 2:
        return
    expected = set(range(min(numbers), max(numbers) + 1))
    missing = sorted(expected - set(numbers))
    if missing:
        issues.append(
            SpanIndexIssue(
                code=f"{role}_missing_numbers",
                severity="blocking",
                detail=(
                    f"{role} sequence skips number(s) {missing} between "
                    f"{min(numbers)} and {max(numbers)}"
                ),
            )
        )


def _merge_regional_items(
    question_items: list[_RegionalItem], solution_items: list[_RegionalItem]
) -> list[IndexedQuestion]:
    """Merge question-region and solution-region items by ``question_ref``.

    Raw fields are accumulated in plain dicts and models are built once at the
    end. A source containing only official answers legitimately produces empty
    ``question_pages`` and populated ``solution_pages``.
    """
    accumulated: dict[str, dict[str, Any]] = {}

    def _ensure(ref: str) -> dict[str, Any]:
        return accumulated.setdefault(
            ref,
            {
                "question_ref": ref,
                "question_number": int(ref.split("-", 1)[0]),
                "question_pages": [],
                "solution_pages": [],
                "question_section_ref": None,
                "solution_section_ref": None,
                "question_type_hint": "unknown",
                "question_confidence": None,
                "solution_confidence": None,
            },
        )

    for item in question_items:
        record = _ensure(item.question_ref)
        record["question_pages"] = sorted(set(record["question_pages"] + item.pages))
        if record["question_section_ref"] is None and item.section_ref is not None:
            record["question_section_ref"] = item.section_ref
        if item.type_hint != "unknown":
            record["question_type_hint"] = item.type_hint
        if record["question_confidence"] is None:
            record["question_confidence"] = item.confidence

    for item in solution_items:
        record = _ensure(item.question_ref)
        record["solution_pages"] = sorted(set(record["solution_pages"] + item.pages))
        if record["solution_section_ref"] is None and item.section_ref is not None:
            record["solution_section_ref"] = item.section_ref
        if record["solution_confidence"] is None:
            record["solution_confidence"] = item.confidence
        # A solution-region hint still informs the type when the question region
        # had none (e.g. an answer-only source).
        if record["question_type_hint"] == "unknown" and item.type_hint != "unknown":
            record["question_type_hint"] = item.type_hint

    # Preserve the question-region order (exam order). Solution-only refs that
    # did not appear in the question region are appended in solution order.
    ordered_refs: list[str] = [item.question_ref for item in question_items]
    for item in solution_items:
        if item.question_ref not in ordered_refs:
            ordered_refs.append(item.question_ref)

    result: list[IndexedQuestion] = []
    for ref in ordered_refs:
        if ref not in accumulated:
            continue
        record = accumulated[ref]
        result.append(IndexedQuestion.model_validate(record))
    return result


# --------------------------------------------------------------------------- #
# Status derivation
# --------------------------------------------------------------------------- #


def _derive_status(
    questions: list[IndexedQuestion], issues: list[SpanIndexIssue]
) -> IndexStatus:
    if not questions:
        return "failed"
    if any(issue.severity == "blocking" for issue in issues):
        return "needs_review"
    return "ready"


def _validate_page_continuity(
    page_numbers: list[int], issues: list[SpanIndexIssue]
) -> None:
    """Warn / block on non-contiguous or non-ascending page numbers."""
    if len(page_numbers) < 2:
        return
    for prev, curr in zip(page_numbers, page_numbers[1:]):
        if curr <= prev:
            issues.append(
                SpanIndexIssue(
                    code="page_order",
                    severity="blocking",
                    detail=(
                        f"page numbers are not strictly ascending: {prev} -> {curr}"
                    ),
                )
            )
            return
        if curr - prev > 1:
            issues.append(
                SpanIndexIssue(
                    code="page_gap",
                    severity="warning",
                    detail=f"page gap between {prev} and {curr}",
                )
            )


# --------------------------------------------------------------------------- #
# §6 batch planner
# --------------------------------------------------------------------------- #


def build_observation_batches(
    index: QuestionSpanIndex,
    *,
    target_page_count: int = 6,
    hard_page_limit: int = 8,
    target_question_count: int = 12,
) -> list[ObservationBatch]:
    """Turn a :class:`QuestionSpanIndex` into disjoint first-round batches.

    Rules (§6):

    1. Question and solution roles are batched separately and never mixed.
    2. Within a role, questions whose role-page-sets share a page form one
       non-splittable connected component (a cross-page question cannot be cut).
    3. Adjacent components are greedily packed in page order: once a component
       is added, reaching ``target_page_count`` pages or ~``target_question_count``
       questions closes the batch; a section boundary closes the batch before
       adding a component from a new section.
    4. If adding the next component would exceed ``hard_page_limit``, close the
       current batch first. A single component larger than ``hard_page_limit``
       becomes its own ``oversized`` batch (we never split a cross-page question).
    5. First-round batches of the same role have pairwise-disjoint page sets.
    """
    if target_page_count < 1 or hard_page_limit < 1:
        raise ValueError("target_page_count and hard_page_limit must be positive")
    if target_page_count > hard_page_limit:
        raise ValueError("target_page_count must not exceed hard_page_limit")
    if index.status == "failed":
        # A failed index has no question set to batch.
        return []

    batches: list[ObservationBatch] = []
    for role in ("question", "solution"):
        role_batches = _plan_role_batches(
            index,
            role=role,
            target_page_count=target_page_count,
            hard_page_limit=hard_page_limit,
            target_question_count=target_question_count,
        )
        batches.extend(role_batches)
    return batches


def _plan_role_batches(
    index: QuestionSpanIndex,
    *,
    role: QuestionRole,
    target_page_count: int,
    hard_page_limit: int,
    target_question_count: int,
) -> list[ObservationBatch]:
    page_field = "question_pages" if role == "question" else "solution_pages"
    section_field = (
        "question_section_ref" if role == "question" else "solution_section_ref"
    )

    role_questions = [q for q in index.questions if getattr(q, page_field)]
    if not role_questions:
        return []

    components = _connected_components(role_questions, page_field)

    batches: list[ObservationBatch] = []
    current_pages: list[int] = []
    current_refs: list[str] = []
    current_sections: list[str] = []
    batch_counter = 0

    def _flush() -> None:
        nonlocal batch_counter, current_pages, current_refs, current_sections
        if not current_pages or not current_refs:
            return
        batch_counter += 1
        pages = sorted(set(current_pages))
        batches.append(
            ObservationBatch(
                batch_id=(
                    f"{role}-{batch_counter:03d}-p{pages[0]:03d}-p{pages[-1]:03d}"
                ),
                role=role,
                page_numbers=pages,
                expected_question_refs=list(current_refs),
                section_refs=list(current_sections),
            )
        )
        current_pages = []
        current_refs = []
        current_sections = []

    for component in components:
        comp_pages = sorted({p for q in component for p in getattr(q, page_field)})
        comp_refs = [q.question_ref for q in component]
        comp_sections = sorted(
            {
                getattr(q, section_field)
                for q in component
                if getattr(q, section_field)
            }
        )

        # A single component beyond the hard limit becomes its own oversized
        # batch; we never split a cross-page question to satisfy the limit.
        if len(comp_pages) > hard_page_limit:
            _flush()
            batch_counter += 1
            batches.append(
                ObservationBatch(
                    batch_id=(
                        f"{role}-{batch_counter:03d}-"
                        f"p{comp_pages[0]:03d}-p{comp_pages[-1]:03d}"
                    ),
                    role=role,
                    page_numbers=comp_pages,
                    expected_question_refs=comp_refs,
                    section_refs=comp_sections,
                    oversized=True,
                )
            )
            continue

        projected = sorted(set(current_pages + comp_pages))
        would_exceed = bool(current_pages) and len(projected) > hard_page_limit
        section_change = bool(current_sections and comp_sections) and not set(
            current_sections
        ).intersection(comp_sections)
        reached_target = (
            len(current_pages) >= target_page_count
            or len(current_refs) >= target_question_count
        )

        if would_exceed or section_change or reached_target:
            _flush()

        current_pages = current_pages + comp_pages
        current_refs = current_refs + comp_refs
        current_sections = sorted(set(current_sections + comp_sections))

    _flush()
    return batches


def _connected_components(
    questions: list[IndexedQuestion], page_field: str
) -> list[list[IndexedQuestion]]:
    """Group questions by shared pages into non-splittable components.

    Uses union-find over page numbers so any two questions sharing a page land
    in the same component (§6.2). Components are returned in deterministic order:
    each component sorted by question_number, the list of components sorted by
    each component's smallest start page.
    """
    parent: dict[int, int] = {}

    def _find(page: int) -> int:
        parent.setdefault(page, page)
        while parent[page] != page:
            parent[page] = parent[parent[page]]
            page = parent[page]
        return page

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for question in questions:
        pages = getattr(question, page_field)
        if not pages:
            continue
        first = pages[0]
        for page in pages[1:]:
            _union(first, page)

    component_of: dict[int, list[IndexedQuestion]] = {}
    for question in questions:
        pages = getattr(question, page_field)
        root = _find(pages[0]) if pages else -id(question)
        component_of.setdefault(root, []).append(question)

    components = list(component_of.values())
    for component in components:
        component.sort(key=lambda q: q.question_number)
    components.sort(key=lambda comp: min(getattr(q, page_field)[0] for q in comp))
    return components


# --------------------------------------------------------------------------- #
# YAML I/O helpers (matching the repo convention)
# --------------------------------------------------------------------------- #


def load_index(path: str | Path) -> QuestionSpanIndex:
    """Load a :class:`QuestionSpanIndex` from a YAML file."""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return QuestionSpanIndex.model_validate(data)


def dump_index(index: QuestionSpanIndex, path: str | Path) -> None:
    """Persist a :class:`QuestionSpanIndex` atomically to a YAML file."""
    import yaml

    payload = index.model_dump(by_alias=True, exclude_none=True)
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)


# --------------------------------------------------------------------------- #
# Input coercion helpers
# --------------------------------------------------------------------------- #


def _coerce_pages(
    pages: Sequence[PageText | Mapping[str, Any]],
) -> list[PageText]:
    normalised: list[PageText] = []
    for raw in pages:
        if isinstance(raw, PageText):
            normalised.append(raw)
        elif isinstance(raw, Mapping):
            normalised.append(PageText.model_validate(dict(raw)))
        else:
            raise TypeError(
                f"page must be a PageText or mapping, got {type(raw).__name__}"
            )
    return normalised


def _coerce_fingerprint(
    fingerprint: SourceFingerprint | Mapping[str, Any], page_number_offset: int
) -> SourceFingerprint:
    if isinstance(fingerprint, SourceFingerprint):
        fp = fingerprint
    elif isinstance(fingerprint, Mapping):
        fp = SourceFingerprint.model_validate(dict(fingerprint))
    else:
        raise TypeError(
            f"fingerprint must be a SourceFingerprint or mapping, "
            f"got {type(fingerprint).__name__}"
        )
    # ``page_number_offset`` from the CLI always wins so the builder and observer
    # agree on offset handling for separated answer files.
    if page_number_offset and not fp.page_number_offset:
        fp = fp.model_copy(update={"page_number_offset": page_number_offset})
    return fp
