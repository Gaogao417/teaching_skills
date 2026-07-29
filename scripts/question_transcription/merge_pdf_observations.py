#!/usr/bin/env python3
"""Deterministically merge overlapping PDF page observations."""

from __future__ import annotations

import argparse
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.pdf_observation_contracts import (
    MergedPdfObservation,
    ObservationEvidence,
    ObservationFigure,
    ObservationQuestion,
    PdfPage,
    PdfPageObservation,
)
from scripts.question_transcription.contracts import (  # noqa: E402
    PageEvidence,
    RegionEvidence,
    QuestionContent,
)
from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    ReviewIssue,
    ReviewIssuesBundle,
)
from scripts.question_transcription.review_issue_engine import (  # noqa: E402
    FieldCandidate,
    build_issue,
    choose_by_confidence,
)


_CONFIDENCE_SCORE = {"low": 0, "medium": 1, "high": 2}


def _evidence_key(value: ObservationEvidence) -> tuple[int, tuple[int, ...]]:
    return value.page_number, tuple(value.box_px)


def _merge_evidence(
    left: list[ObservationEvidence], right: list[ObservationEvidence]
) -> list[ObservationEvidence]:
    by_key = {_evidence_key(item): item for item in left}
    for item in right:
        by_key.setdefault(_evidence_key(item), item)
    return [by_key[key] for key in sorted(by_key)]


def _figure_key(value: ObservationFigure) -> tuple[str, int]:
    return value.role, value.order


def _merge_questions(
    current: ObservationQuestion, incoming: ObservationQuestion
) -> ObservationQuestion:
    identity_fields = [
        "question_number",
        "section_ref",
        "section_title",
        "question_type",
        "points",
    ]
    for field in identity_fields:
        if getattr(current, field) != getattr(incoming, field):
            raise ValueError(
                f"transcription_conflict {current.question_ref}: field {field}"
            )
    if current.content is not None and incoming.content is not None:
        if current.content != incoming.content:
            raise ValueError(
                f"transcription_conflict {current.question_ref}: content differs"
            )
    content = current.content or incoming.content

    figures: dict[tuple[str, int], ObservationFigure] = {
        _figure_key(item): item for item in current.figures
    }
    for item in incoming.figures:
        key = _figure_key(item)
        existing = figures.get(key)
        if existing is not None and (
            existing.page_number != item.page_number
            or existing.box_px != item.box_px
            or existing.whiteout_px != item.whiteout_px
        ):
            raise ValueError(
                f"figure_conflict {current.question_ref}: {key[0]} order {key[1]}"
            )
        figures.setdefault(key, item)

    def anchor(name: str) -> str | None:
        left = getattr(current, name)
        right = getattr(incoming, name)
        if left and right and left != right:
            raise ValueError(
                f"transcription_conflict {current.question_ref}: {name} differs"
            )
        return left or right

    confidence = dict(current.confidence)
    rank = {"high": 2, "medium": 1, "low": 0}
    for key, value in incoming.confidence.items():
        if key not in confidence or rank[value] < rank[confidence[key]]:
            confidence[key] = value

    return ObservationQuestion(
        question_ref=current.question_ref,
        question_number=current.question_number,
        section_ref=current.section_ref,
        section_title=current.section_title,
        question_type=current.question_type,
        points=current.points,
        content=content,
        question_evidence=_merge_evidence(
            current.question_evidence, incoming.question_evidence
        ),
        solution_evidence=_merge_evidence(
            current.solution_evidence, incoming.solution_evidence
        ),
        solution_start_anchor=anchor("solution_start_anchor"),
        solution_end_anchor=anchor("solution_end_anchor"),
        figures=[
            figures[key]
            for key in sorted(figures, key=lambda value: (value[0], value[1]))
        ],
        confidence=confidence,
        continues_from_previous=(
            current.continues_from_previous or incoming.continues_from_previous
        ),
        continues_to_next=current.continues_to_next or incoming.continues_to_next,
        notes=list(dict.fromkeys(current.notes + incoming.notes)),
    )


def _pdf_source(archive: str, source: str) -> str:
    if Path(source).is_absolute() or source.startswith(f"{archive.rstrip('/')}/"):
        return source
    return f"{archive.rstrip('/')}/{source.lstrip('/')}"


def _question_confidence(question: ObservationQuestion, field: str | None = None) -> str:
    if field and field in question.confidence:
        return question.confidence[field]
    if question.confidence:
        return max(
            question.confidence.values(),
            key=lambda value: _CONFIDENCE_SCORE[value],
        )
    return "medium"


def _pdf_evidence(
    question: ObservationQuestion,
    *,
    role: str,
    pages: dict[int, PdfPage],
    archive: str,
) -> tuple[Any, ...]:
    values = (
        question.question_evidence
        if role == "question"
        else question.solution_evidence
    )
    if not values:
        values = list(question.question_evidence) + list(question.solution_evidence)
    rendered = []
    for evidence in values:
        page = pages[evidence.page_number]
        rendered.append(
            RegionEvidence(
                kind="region",
                source=_pdf_source(archive, page.source),
                page_number=evidence.page_number,
                box_px=evidence.box_px,
            )
        )
    return tuple(rendered)


def _pdf_field_candidates(
    entries: list[tuple[str, ObservationQuestion]],
    *,
    getter: Any,
    confidence_field: str | None,
    evidence_role: str,
    pages: dict[int, PdfPage],
    archive: str,
) -> list[FieldCandidate]:
    candidates = []
    for window_id, question in entries:
        value = getter(question)
        if value is None or value == "" or value == []:
            continue
        evidence = _pdf_evidence(
            question,
            role=evidence_role,
            pages=pages,
            archive=archive,
        )
        if not evidence:
            page_number = min(pages)
            page = pages[page_number]
            evidence = (
                PageEvidence(
                    kind="page",
                    source=_pdf_source(archive, page.source),
                    page_number=page_number,
                ),
            )
        candidates.append(
            FieldCandidate(
                window_id=window_id,
                value=value,
                confidence=_question_confidence(question, confidence_field),
                evidence=evidence,
            )
        )
    return candidates


def _merge_question_group(
    question_ref: str,
    entries: list[tuple[str, ObservationQuestion]],
    *,
    pages: dict[int, PdfPage],
    archive: str,
) -> tuple[ObservationQuestion, list[ReviewIssue]]:
    issues: list[ReviewIssue] = []

    def select(
        field_path: str,
        getter: Any,
        *,
        confidence_field: str | None = None,
        evidence_role: str = "question",
    ) -> Any:
        candidates = _pdf_field_candidates(
            entries,
            getter=getter,
            confidence_field=confidence_field,
            evidence_role=evidence_role,
            pages=pages,
            archive=archive,
        )
        if not candidates:
            return None
        selected = choose_by_confidence(candidates)
        issue = build_issue(
            question_ref=question_ref,
            question_number=entries[0][1].question_number,
            field_path=field_path,
            candidates=candidates,
            selected_value=selected.value,
        )
        if issue is not None:
            issues.append(issue)
        return selected.value

    metadata = {
        field: select(field, lambda question, name=field: getattr(question, name))
        for field in (
            "question_number",
            "section_ref",
            "section_title",
            "question_type",
            "points",
        )
    }

    content_values: dict[str, Any] = {}
    content_specs = (
        ("stem_latex", "stem", "question"),
        ("choices", "formula", "question"),
        ("answer", "formula", "solution"),
        ("clue", "formula", "solution"),
        ("solution_steps", "formula", "solution"),
        ("solution_notes", "formula", "solution"),
    )
    for field, confidence, role in content_specs:
        content_values[field] = select(
            f"content.{field}",
            lambda question, name=field: (
                getattr(question.content, name) if question.content is not None else None
            ),
            confidence_field=confidence,
            evidence_role=role,
        )
    if all(value is None for value in content_values.values()):
        content = None
    else:
        for field in ("choices", "solution_steps", "solution_notes"):
            if content_values[field] is None:
                content_values[field] = []
        content = QuestionContent.model_validate(content_values)

    start_anchor = select(
        "solution_start_anchor",
        lambda question: question.solution_start_anchor,
        confidence_field="formula",
        evidence_role="solution",
    )
    end_anchor = select(
        "solution_end_anchor",
        lambda question: question.solution_end_anchor,
        confidence_field="formula",
        evidence_role="solution",
    )

    question_evidence: list[ObservationEvidence] = []
    solution_evidence: list[ObservationEvidence] = []
    for _, question in entries:
        question_evidence = _merge_evidence(
            question_evidence, question.question_evidence
        )
        solution_evidence = _merge_evidence(
            solution_evidence, question.solution_evidence
        )

    figures: dict[tuple[str, int], list[tuple[str, ObservationFigure]]] = defaultdict(list)
    for window_id, question in entries:
        for figure in question.figures:
            figures[_figure_key(figure)].append((window_id, figure))
    selected_figures: list[ObservationFigure] = []
    for (role, order), figure_entries in sorted(figures.items()):
        ranked = sorted(
            figure_entries,
            key=lambda entry: (
                -_CONFIDENCE_SCORE[entry[1].confidence],
                entry[0],
            ),
        )
        selected_figure = ranked[0][1]
        selected_figures.append(selected_figure)
        candidates = [
            FieldCandidate(
                window_id=window_id,
                value={
                    "page_number": figure.page_number,
                    "box_px": figure.box_px,
                    "whiteout_px": figure.whiteout_px,
                },
                confidence=figure.confidence,
                evidence=(
                    RegionEvidence(
                        kind="region",
                        source=_pdf_source(archive, pages[figure.page_number].source),
                        page_number=figure.page_number,
                        box_px=figure.box_px,
                    ),
                ),
            )
            for window_id, figure in figure_entries
        ]
        issue = build_issue(
            question_ref=question_ref,
            question_number=int(metadata["question_number"]),
            field_path=f"figures.{role}.{order}",
            candidates=candidates,
            selected_value={
                "page_number": selected_figure.page_number,
                "box_px": selected_figure.box_px,
                "whiteout_px": selected_figure.whiteout_px,
            },
        )
        if issue is not None:
            issues.append(issue)

    confidence: dict[str, str] = {}
    for _, question in entries:
        for key, value in question.confidence.items():
            if key not in confidence or _CONFIDENCE_SCORE[value] > _CONFIDENCE_SCORE[confidence[key]]:
                confidence[key] = value

    return (
        ObservationQuestion(
            question_ref=question_ref,
            **metadata,
            content=content,
            question_evidence=question_evidence,
            solution_evidence=solution_evidence,
            solution_start_anchor=start_anchor,
            solution_end_anchor=end_anchor,
            figures=selected_figures,
            confidence=confidence,
            continues_from_previous=any(
                question.continues_from_previous for _, question in entries
            ),
            continues_to_next=any(
                question.continues_to_next for _, question in entries
            ),
            notes=list(
                dict.fromkeys(
                    note for _, question in entries for note in question.notes
                )
            ),
        ),
        issues,
    )


def merge_observations_with_issues(
    observations: list[PdfPageObservation],
) -> tuple[MergedPdfObservation, ReviewIssuesBundle | None]:
    if not observations:
        raise ValueError("at least one observation is required")
    first = observations[0]
    pages: dict[int, PdfPage] = {}
    grouped: OrderedDict[str, list[tuple[str, ObservationQuestion]]] = OrderedDict()
    for observation in observations:
        if observation.paper != first.paper:
            raise ValueError("observations have different paper metadata")
        if observation.provider != first.provider:
            raise ValueError("observations have different providers")
        if observation.prompt_version != first.prompt_version:
            raise ValueError("observations have different prompt versions")
        for page in observation.pages:
            previous = pages.get(page.page_number)
            if previous is not None and previous != page:
                raise ValueError(f"page_conflict page {page.page_number}")
            pages[page.page_number] = page
        for question in observation.questions:
            grouped.setdefault(question.question_ref, []).append(
                (observation.window_id, question)
            )
    merged_questions: list[ObservationQuestion] = []
    issues: list[ReviewIssue] = []
    for question_ref, entries in grouped.items():
        question, question_issues = _merge_question_group(
            question_ref,
            entries,
            pages=pages,
            archive=first.paper.source_archive,
        )
        merged_questions.append(question)
        issues.extend(question_issues)
    conflicts = sorted(
        {
            issue.question_ref
            for issue in issues
            if issue.severity in {"blocking", "warning"}
        }
    )
    merged = MergedPdfObservation.model_validate(
        {
            "schema": "math_pdf_merged_observation/v1",
            "paper": first.paper.model_dump(by_alias=True, exclude_none=True),
            "provider": first.provider.model_dump(),
            "prompt_version": first.prompt_version,
            "pages": [
                pages[number].model_dump() for number in sorted(pages)
            ],
            "questions": [
                question.model_dump(exclude_none=True) for question in merged_questions
            ],
            "source_windows": [item.window_id for item in observations],
            "conflicts": conflicts,
        }
    )
    issue_bundle = (
        ReviewIssuesBundle(
            schema="math_transcription_review_issues/v1",
            paper_id=first.paper.id,
            generated_at=datetime.now(timezone.utc),
            issues=issues,
        )
        if issues
        else None
    )
    return merged, issue_bundle


def merge_observations(
    observations: list[PdfPageObservation],
) -> MergedPdfObservation:
    merged, _ = merge_observations_with_issues(observations)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--issues",
        type=Path,
        help="review issue sidecar (default: review-issues.yaml beside --output)",
    )
    args = parser.parse_args()
    values = [
        PdfPageObservation.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        for path in args.observations
    ]
    merged, issues = merge_observations_with_issues(values)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(
            merged.model_dump(by_alias=True, exclude_none=True),
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
        f"PDF OBSERVATIONS MERGED: {args.output} | "
        f"windows={len(values)} questions={len(merged.questions)} "
        f"conflicts={len(merged.conflicts)} issues={len(issues.issues) if issues else 0}"
    )
    if issues is not None:
        print(f"REVIEW ISSUES: {issues_path}")
    return 2 if merged.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
