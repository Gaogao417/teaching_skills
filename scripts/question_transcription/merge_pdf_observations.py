#!/usr/bin/env python3
"""Deterministically merge overlapping PDF page observations."""

from __future__ import annotations

import argparse
from collections import OrderedDict
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


def merge_observations(
    observations: list[PdfPageObservation],
) -> MergedPdfObservation:
    if not observations:
        raise ValueError("at least one observation is required")
    first = observations[0]
    pages: dict[int, PdfPage] = {}
    questions: OrderedDict[str, ObservationQuestion] = OrderedDict()
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
            previous = questions.get(question.question_ref)
            questions[question.question_ref] = (
                _merge_questions(previous, question) if previous else question
            )
    return MergedPdfObservation.model_validate(
        {
            "schema": "math_pdf_merged_observation/v1",
            "paper": first.paper.model_dump(by_alias=True, exclude_none=True),
            "provider": first.provider.model_dump(),
            "prompt_version": first.prompt_version,
            "pages": [
                pages[number].model_dump() for number in sorted(pages)
            ],
            "questions": [
                question.model_dump(exclude_none=True)
                for question in questions.values()
            ],
            "source_windows": [item.window_id for item in observations],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = [
        PdfPageObservation.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        for path in args.observations
    ]
    merged = merge_observations(values)
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
    print(
        f"PDF OBSERVATIONS MERGED: {args.output} | "
        f"windows={len(values)} questions={len(merged.questions)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
