#!/usr/bin/env python3
"""Split the text side of a merged PDF observation into the public contract."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
import sys

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import QuestionTranscriptionBundle
from scripts.question_transcription.pdf_observation_contracts import (
    MergedPdfObservation,
)


def adapt(observation: MergedPdfObservation | dict) -> dict:
    if not isinstance(observation, MergedPdfObservation):
        observation = MergedPdfObservation.model_validate(observation)
    sections: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
    page_by_number = {page.page_number: page for page in observation.pages}
    for question in observation.questions:
        if question.content is None:
            raise ValueError(f"{question.question_ref}: transcription content missing")
        if not question.question_evidence:
            raise ValueError(f"{question.question_ref}: question evidence missing")
        if not question.solution_evidence:
            raise ValueError(f"{question.question_ref}: solution evidence missing")
        if not question.solution_start_anchor or not question.solution_end_anchor:
            raise ValueError(f"{question.question_ref}: solution anchors missing")

        def evidence(values):
            return [
                {
                    "kind": "region",
                    "source": _source(
                        observation.paper.source_archive,
                        page_by_number[item.page_number].source,
                    ),
                    "page_number": item.page_number,
                    "box_px": item.box_px,
                }
                for item in values
            ]

        sections.setdefault(
            (question.section_ref, question.section_title), []
        ).append(
            {
                "question_ref": question.question_ref,
                "question_number": question.question_number,
                "question_type": question.question_type,
                "points": question.points,
                "content": question.content.model_dump(),
                "evidence": {
                    "question": evidence(question.question_evidence),
                    "solution": evidence(question.solution_evidence),
                    "solution_start_anchor": question.solution_start_anchor,
                    "solution_end_anchor": question.solution_end_anchor,
                },
            }
        )
    result = {
        "schema": "math_question_transcription/v1",
        "paper": observation.paper.model_dump(by_alias=True, exclude_none=True),
        "sections": [
            {"section_ref": key[0], "title": key[1], "questions": questions}
            for key, questions in sections.items()
        ],
        "provider": observation.provider.model_dump(),
    }
    return QuestionTranscriptionBundle.model_validate(result).model_dump(
        by_alias=True, exclude_none=True
    )


def _source(archive: str, source: str) -> str:
    if Path(source).is_absolute() or source.startswith(f"{archive.rstrip('/')}/"):
        return source
    return f"{archive.rstrip('/')}/{source.lstrip('/')}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observation = MergedPdfObservation.model_validate(
        yaml.safe_load(args.observation.read_text(encoding="utf-8"))
    )
    bundle = adapt(observation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(bundle, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(f"PDF TRANSCRIPTION ADAPTED: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
