#!/usr/bin/env python3
"""Deterministically merge overlapping DOCX window observations."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import PaperMeta, Provider  # noqa: E402
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxObservationBundle,
    DocxObservedQuestion,
    DocxObservedQuestionFragment,
    DocxWindowObservation,
)

_CONFIDENCE_SCORE = {"low": 0, "medium": 1, "high": 2}


def _question_score(question: DocxObservedQuestionFragment) -> int:
    confidence = question.transcription_confidence
    return sum(
        _CONFIDENCE_SCORE[value]
        for value in (confidence.stem, confidence.formula, confidence.solution_steps)
    )


def _is_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _select_value(
    entries: list[tuple[str, DocxObservedQuestionFragment]],
    getter: Any,
    *,
    confidence_field: str | None = None,
    zero_is_missing: bool = False,
) -> tuple[Any, bool]:
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
        return (
            -confidence,
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

    content_specs = {
        "stem_latex": "stem",
        "choices": "formula",
        "answer": "solution_steps",
        "clue": "solution_steps",
        "solution_steps": "solution_steps",
        "solution_notes": "solution_steps",
    }
    content: dict[str, Any] = {}
    for field, confidence_field in content_specs.items():
        value, changed = _select_value(
            entries,
            lambda question, name=field: getattr(question.content, name),
            confidence_field=confidence_field,
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
    )
    end_anchor, end_changed = _select_value(
        entries,
        lambda question: question.evidence.solution_end_anchor,
        confidence_field="solution_steps",
    )
    if start_changed or end_changed:
        conflicts.add("evidence")

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


def merge(
    windows: list[DocxWindowObservation],
    *,
    paper: PaperMeta,
    provider: Provider | None = None,
) -> DocxObservationBundle:
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
    incomplete: list[str] = []
    for question_ref, entries in grouped.items():
        try:
            selected, changed, selected_window = _merge_question(question_ref, entries)
        except ValueError as exc:
            incomplete.append(str(exc))
            continue
        if changed:
            conflicts.append(
                {
                    "question_ref": question_ref,
                    "selected_window_id": selected_window,
                    "other_window_ids": [
                        window_id for window_id, _ in entries if window_id != selected_window
                    ],
                    "fields": changed,
                }
            )
        questions.append(selected)

    if incomplete:
        raise ValueError(
            "incomplete merged questions:\n- " + "\n- ".join(incomplete)
        )

    questions.sort(key=lambda q: (q.question_number, q.question_ref))
    actual_provider = provider or windows[0].provider
    return DocxObservationBundle.model_validate(
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge DOCX window observations.")
    parser.add_argument("--windows", type=Path, nargs="+", required=True)
    parser.add_argument("--paper-meta", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    windows = [
        DocxWindowObservation.model_validate(yaml.safe_load(path.read_text("utf-8")))
        for path in args.windows
    ]
    paper = PaperMeta.model_validate(yaml.safe_load(args.paper_meta.read_text("utf-8")))
    result = merge(windows, paper=paper)
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
    print(
        f"DOCX OBSERVATIONS MERGED: questions={len(result.questions)} "
        f"conflicts={len(result.conflicts)} output={args.output}"
    )
    return 2 if result.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
