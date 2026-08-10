#!/usr/bin/env python3
"""Deterministically merge overlapping DOCX window observations."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import PaperMeta, Provider  # noqa: E402
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxObservationBundle,
    DocxObservedQuestion,
    DocxObservedQuestionFragment,
    DocxWindowObservation,
)
from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    ReviewIssue,
    ReviewIssuesBundle,
)
from scripts.question_transcription.procedural.review_issue_engine import (  # noqa: E402
    FieldCandidate,
    build_issue,
)

_CONFIDENCE_SCORE = {"low": 0, "medium": 1, "high": 2}

# Transparent placeholder used when no window produced a real solution anchor.
# It intentionally matches no real source text so evidence-page expansion never
# mistakes it for a genuine anchor, while still satisfying the merged contract's
# NonEmptyStr requirement and signalling the gap for human review.
_PENDING_SOLUTION_ANCHOR = "<PENDING_SOLUTION_ANCHOR>"


def _question_score(question: DocxObservedQuestionFragment) -> int:
    confidence = question.transcription_confidence
    return sum(
        _CONFIDENCE_SCORE[value]
        for value in (confidence.stem, confidence.formula, confidence.solution_steps)
    )


def _is_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _window_role(window_id: str) -> str | None:
    """Classify a window as ``question``/``solution`` from its id prefix.

    Window ids follow the ``{role}-NNN-pXXX-pYYY`` convention globally, so the
    origin of each candidate is knowable without carrying an extra field.
    """
    if window_id.startswith("question-"):
        return "question"
    if window_id.startswith("solution-"):
        return "solution"
    return None


def _select_value(
    entries: list[tuple[str, DocxObservedQuestionFragment]],
    getter: Any,
    *,
    confidence_field: str | None = None,
    zero_is_missing: bool = False,
    preferred_role: str | None = None,
) -> tuple[Any, bool]:
    """Pick a field value across windows.

    Ranking is ``(-confidence, role_pref, json(value), window_id)``. The
    ``preferred_role`` tiebreak only breaks ties between candidates of equal
    confidence — a higher-confidence candidate always wins regardless of origin —
    so stem fields prefer the question window while solution fields prefer the
    solution window without discarding a genuinely more-confident reading.
    """
    candidates: list[tuple[str, DocxObservedQuestionFragment, Any]] = []
    for window_id, question in entries:
        value = getter(question)
        if zero_is_missing and value == 0:
            continue
        if _is_present(value):
            candidates.append((window_id, question, value))
    if not candidates:
        return None, False

    def score(item: tuple[str, DocxObservedQuestionFragment, Any]) -> tuple[Any, ...]:
        window_id, question, value = item
        confidence = (
            _CONFIDENCE_SCORE[getattr(question.transcription_confidence, confidence_field)]
            if confidence_field
            else _question_score(question)
        )
        role_pref = 0 if (preferred_role and _window_role(window_id) == preferred_role) else 1
        return (
            -confidence,
            role_pref,
            json.dumps(value, sort_keys=True, ensure_ascii=False),
            window_id,
        )

    ranked = sorted(candidates, key=score)
    unique = {
        json.dumps(value, sort_keys=True, ensure_ascii=False)
        for _, _, value in candidates
    }
    return ranked[0][2], len(unique) > 1


def _merged_evidence(
    entries: list[tuple[str, DocxObservedQuestionFragment]], role: str
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for _, question in entries:
        for evidence in getattr(question.evidence, role):
            dumped = evidence.model_dump(mode="json")
            unique[json.dumps(dumped, sort_keys=True, ensure_ascii=False)] = dumped
    return sorted(
        unique.values(),
        key=lambda item: (
            item["page_number"],
            item["source"],
            item.get("box_px", []),
        ),
    )


def _candidate_evidence(
    question: DocxObservedQuestionFragment, role: str
) -> tuple[Any, ...]:
    if role == "question":
        evidence = list(question.evidence.question)
    elif role == "solution":
        evidence = list(question.evidence.solution)
    else:
        evidence = list(question.evidence.question) + list(question.evidence.solution)
    if not evidence:
        evidence = list(question.evidence.question) + list(question.evidence.solution)
    return tuple(evidence)


def _field_issue(
    *,
    question_ref: str,
    entries: list[tuple[str, DocxObservedQuestionFragment]],
    selected: DocxObservedQuestion,
    field_path: str,
    getter: Any,
    confidence_field: str | None,
    evidence_role: str,
) -> ReviewIssue | None:
    candidates: list[FieldCandidate] = []
    for window_id, question in entries:
        value = getter(question)
        if not _is_present(value):
            continue
        confidence = (
            getattr(question.transcription_confidence, confidence_field)
            if confidence_field
            else max(
                (
                    question.transcription_confidence.stem,
                    question.transcription_confidence.formula,
                    question.transcription_confidence.solution_steps,
                ),
                key=lambda item: _CONFIDENCE_SCORE[item],
            )
        )
        candidates.append(
            FieldCandidate(
                window_id=window_id,
                value=value,
                confidence=confidence,
                evidence=_candidate_evidence(question, evidence_role),
            )
        )
    current: Any = selected
    for token in field_path.split("."):
        current = getattr(current, token)
    return build_issue(
        question_ref=question_ref,
        question_number=selected.question_number,
        field_path=field_path,
        candidates=candidates,
        selected_value=current,
    )


def _question_review_issues(
    question_ref: str,
    entries: list[tuple[str, DocxObservedQuestionFragment]],
    selected: DocxObservedQuestion,
) -> list[ReviewIssue]:
    specs: list[tuple[str, Any, str | None, str]] = []
    for field in (
        "question_number",
        "question_type",
        "points",
        "section_ref",
        "section_title",
    ):
        specs.append(
            (
                field,
                lambda question, name=field: getattr(question, name),
                None,
                "both",
            )
        )
    for field, confidence, role in (
        ("stem_latex", "stem", "question"),
        ("choices", "formula", "question"),
        ("answer", "solution_steps", "solution"),
        ("clue", "solution_steps", "solution"),
        ("solution_steps", "solution_steps", "solution"),
        ("solution_notes", "solution_steps", "solution"),
    ):
        specs.append(
            (
                f"content.{field}",
                lambda question, name=field: getattr(question.content, name),
                confidence,
                role,
            )
        )
    for field in ("solution_start_anchor", "solution_end_anchor"):
        specs.append(
            (
                f"evidence.{field}",
                lambda question, name=field: getattr(question.evidence, name),
                "solution_steps",
                "solution",
            )
        )

    issues: list[ReviewIssue] = []
    for field_path, getter, confidence_field, evidence_role in specs:
        issue = _field_issue(
            question_ref=question_ref,
            entries=entries,
            selected=selected,
            field_path=field_path,
            getter=getter,
            confidence_field=confidence_field,
            evidence_role=evidence_role,
        )
        if issue is not None:
            issues.append(issue)
    return issues


def _merge_question(
    question_ref: str,
    entries: list[tuple[str, DocxObservedQuestionFragment]],
) -> tuple[DocxObservedQuestion, list[str], str]:
    selected_window = sorted(
        entries,
        key=lambda entry: (
            -_question_score(entry[1]),
            entry[0],
        ),
    )[0][0]
    conflicts: set[str] = set()

    metadata: dict[str, Any] = {}
    for field in (
        "question_number",
        "question_type",
        "points",
        "section_ref",
        "section_title",
    ):
        value, changed = _select_value(
            entries,
            lambda question, name=field: getattr(question, name),
            zero_is_missing=field == "points",
        )
        if value is None and field == "points":
            value = 0
        if changed:
            conflicts.add(field)
        metadata[field] = value

    # Field -> (confidence field, preferred window origin). Stem/choices come
    # from the original paper (question window); answers/steps come from the
    # official-solution pages (solution window). clue carries no role signal.
    content_specs = {
        "stem_latex": ("stem", "question"),
        "choices": ("formula", "question"),
        "answer": ("solution_steps", "solution"),
        "clue": ("solution_steps", None),
        "solution_steps": ("solution_steps", "solution"),
        "solution_notes": ("solution_steps", "solution"),
    }
    content: dict[str, Any] = {}
    for field, (confidence_field, preferred_role) in content_specs.items():
        value, changed = _select_value(
            entries,
            lambda question, name=field: getattr(question.content, name),
            confidence_field=confidence_field,
            preferred_role=preferred_role,
        )
        if value is None and field in {"choices", "solution_steps", "solution_notes"}:
            value = []
        if changed:
            conflicts.add("content")
        content[field] = value

    start_anchor, start_changed = _select_value(
        entries,
        lambda question: question.evidence.solution_start_anchor,
        confidence_field="solution_steps",
        preferred_role="solution",
    )
    end_anchor, end_changed = _select_value(
        entries,
        lambda question: question.evidence.solution_end_anchor,
        confidence_field="solution_steps",
        preferred_role="solution",
    )
    if start_changed or end_changed:
        conflicts.add("evidence")
    # Safety net: the merged contract requires a NonEmptyStr anchor. If no window
    # produced a real anchor, surface a transparent placeholder (which matches no
    # real text, so evidence-page expansion cannot be fooled by it) rather than
    # aborting the whole merge or fabricating a deceptive "{num}．" value. The
    # placeholder is surfaced in the conflict list by ``merge_with_issues``.
    if start_anchor is None:
        start_anchor = _PENDING_SOLUTION_ANCHOR
    if end_anchor is None:
        end_anchor = _PENDING_SOLUTION_ANCHOR

    confidence: dict[str, str] = {}
    for field in ("stem", "formula", "solution_steps"):
        confidence[field] = max(
            (getattr(question.transcription_confidence, field) for _, question in entries),
            key=lambda value: _CONFIDENCE_SCORE[value],
        )

    data = {
        "question_ref": question_ref,
        **metadata,
        "content": content,
        "evidence": {
            "question": _merged_evidence(entries, "question"),
            "solution": _merged_evidence(entries, "solution"),
            "solution_start_anchor": start_anchor,
            "solution_end_anchor": end_anchor,
        },
        "transcription_confidence": confidence,
    }
    try:
        merged = DocxObservedQuestion.model_validate(data)
    except Exception as exc:
        raise ValueError(
            f"incomplete merged question {question_ref}; complementary window "
            f"observation is required: {exc}"
        ) from exc
    return merged, sorted(conflicts), selected_window


def merge_with_issues(
    windows: list[DocxWindowObservation],
    *,
    paper: PaperMeta,
    provider: Provider | None = None,
) -> tuple[DocxObservationBundle, ReviewIssuesBundle | None]:
    if not windows:
        raise ValueError("at least one window observation is required")

    pages_by_number = {}
    grouped: dict[str, list[tuple[str, DocxObservedQuestionFragment]]] = defaultdict(list)
    for window in sorted(windows, key=lambda w: w.window_id):
        for page in window.pages:
            previous = pages_by_number.get(page.page_number)
            if previous is not None and previous != page:
                raise ValueError(f"page {page.page_number}: immutable metadata conflict")
            pages_by_number[page.page_number] = page
        for question in window.questions:
            grouped[question.question_ref].append((window.window_id, question))

    questions = []
    conflicts = []
    review_issues: list[ReviewIssue] = []
    incomplete: list[str] = []
    for question_ref, entries in grouped.items():
        try:
            selected, changed, selected_window = _merge_question(question_ref, entries)
        except ValueError as exc:
            incomplete.append(str(exc))
            continue
        question_issues = _question_review_issues(question_ref, entries, selected)
        review_issues.extend(question_issues)
        blocking_fields = sorted(
            {
                issue.field_path
                for issue in question_issues
                if issue.severity in {"blocking", "warning"}
            }
        )
        if blocking_fields:
            conflicts.append(
                {
                    "question_ref": question_ref,
                    "selected_window_id": selected_window,
                    "other_window_ids": [
                        window_id for window_id, _ in entries if window_id != selected_window
                    ],
                    "fields": blocking_fields,
                }
            )
        # Surface placeholder-filled anchors (no window produced a real anchor)
        # so the review UI flags them for human attention. These are not
        # field_conflict review issues (there is no competing candidate) but the
        # question must still show up in the conflict list, not pass silently.
        placeholder_fields = [
            f"evidence.{name}"
            for name in ("solution_start_anchor", "solution_end_anchor")
            if getattr(selected.evidence, name) == _PENDING_SOLUTION_ANCHOR
        ]
        if placeholder_fields:
            conflicts.append(
                {
                    "question_ref": question_ref,
                    "selected_window_id": selected_window,
                    "other_window_ids": [
                        window_id for window_id, _ in entries if window_id != selected_window
                    ],
                    "fields": placeholder_fields,
                }
            )
        questions.append(selected)

    if incomplete:
        raise ValueError(
            "incomplete merged questions:\n- " + "\n- ".join(incomplete)
        )

    questions.sort(key=lambda q: (q.question_number, q.question_ref))
    actual_provider = provider or windows[0].provider
    observation = DocxObservationBundle.model_validate(
        {
            "schema": "math_docx_observation/v1",
            "paper": paper.model_dump(mode="json"),
            "pages": [
                pages_by_number[number].model_dump(mode="json")
                for number in sorted(pages_by_number)
            ],
            "questions": [q.model_dump(mode="json") for q in questions],
            "provider": actual_provider.model_dump(mode="json"),
            "conflicts": conflicts,
        }
    )
    issues_bundle = (
        ReviewIssuesBundle(
            schema="math_transcription_review_issues/v1",
            paper_id=paper.id,
            generated_at=datetime.now(timezone.utc),
            issues=review_issues,
        )
        if review_issues
        else None
    )
    return observation, issues_bundle


def merge(
    windows: list[DocxWindowObservation],
    *,
    paper: PaperMeta,
    provider: Provider | None = None,
) -> DocxObservationBundle:
    observation, _ = merge_with_issues(
        windows,
        paper=paper,
        provider=provider,
    )
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge DOCX window observations.")
    parser.add_argument("--windows", type=Path, nargs="+", required=True)
    parser.add_argument("--paper-meta", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--issues",
        type=Path,
        help="review issue sidecar (default: review-issues.yaml beside --output)",
    )
    args = parser.parse_args()
    windows = [
        DocxWindowObservation.model_validate(yaml.safe_load(path.read_text("utf-8")))
        for path in args.windows
    ]
    paper = PaperMeta.model_validate(yaml.safe_load(args.paper_meta.read_text("utf-8")))
    result, issues = merge_with_issues(windows, paper=paper)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(
            result.model_dump(by_alias=True, exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    issues_path = args.issues or args.output.with_name("review-issues.yaml")
    if issues is not None:
        issues_path.parent.mkdir(parents=True, exist_ok=True)
        issues_path.write_text(
            yaml.safe_dump(
                issues.model_dump(by_alias=True, exclude_none=True, mode="json"),
                allow_unicode=True,
                sort_keys=False,
                width=1000,
            ),
            encoding="utf-8",
        )
    print(
        f"DOCX OBSERVATIONS MERGED: questions={len(result.questions)} "
        f"conflicts={len(result.conflicts)} issues={len(issues.issues) if issues else 0} "
        f"output={args.output}"
    )
    if issues is not None:
        print(f"REVIEW ISSUES: {issues_path}")
    return 2 if result.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
