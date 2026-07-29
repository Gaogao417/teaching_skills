#!/usr/bin/env python3
"""Adapt a merged DOCX observation into the frozen transcription bundle."""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    QuestionTranscriptionBundle,
)
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxObservationBundle,
)


def adapt(
    observation: DocxObservationBundle,
    *,
    allow_low_confidence: bool = False,
) -> QuestionTranscriptionBundle:
    if observation.conflicts:
        refs = ", ".join(c.question_ref for c in observation.conflicts)
        raise ValueError(f"unresolved overlapping-window conflicts: {refs}")
    return _adapt_selected(
        observation,
        allow_low_confidence=allow_low_confidence,
    )


def adapt_for_review_staging(
    observation: DocxObservationBundle,
    *,
    allow_low_confidence: bool = True,
) -> QuestionTranscriptionBundle:
    """Adapt provisional values only for an explicitly quarantined review staging."""

    if not observation.conflicts:
        raise ValueError("review-staging adapter requires unresolved conflicts")
    return _adapt_selected(
        observation,
        allow_low_confidence=allow_low_confidence,
    )


def _adapt_selected(
    observation: DocxObservationBundle,
    *,
    allow_low_confidence: bool,
) -> QuestionTranscriptionBundle:
    low = [
        q.question_ref
        for q in observation.questions
        if "low"
        in {
            q.transcription_confidence.stem,
            q.transcription_confidence.formula,
            q.transcription_confidence.solution_steps,
        }
    ]
    if low and not allow_low_confidence:
        raise ValueError(f"low-confidence transcription requires review: {', '.join(low)}")

    grouped: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
    for question in observation.questions:
        key = (question.section_ref, question.section_title)
        data = question.model_dump(mode="json")
        for internal in (
            "section_ref",
            "section_title",
            "transcription_confidence",
        ):
            data.pop(internal)
        grouped.setdefault(key, []).append(data)

    bundle = {
        "schema": "math_question_transcription/v1",
        "paper": observation.paper.model_dump(mode="json"),
        "sections": [
            {"section_ref": ref, "title": title, "questions": questions}
            for (ref, title), questions in grouped.items()
        ],
        "provider": observation.provider.model_dump(mode="json"),
    }
    return QuestionTranscriptionBundle.model_validate(bundle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt merged DOCX observations.")
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-low-confidence", action="store_true")
    args = parser.parse_args()
    observation = DocxObservationBundle.model_validate(
        yaml.safe_load(args.observation.read_text("utf-8"))
    )
    result = adapt(
        observation,
        allow_low_confidence=args.allow_low_confidence,
    )
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
    print(f"DOCX TRANSCRIPTION ADAPTED: questions={len(result.refs())} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
