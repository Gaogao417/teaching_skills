#!/usr/bin/env python3
"""Pydantic output models for the structured (pydantic_ai) DOCX observation.

These mirror :class:`DocxObservedQuestionFragment` but are tuned for use as a
``pydantic_ai`` ``output_type``: enum fields use explicit ``Literal`` types so
MiMo's tool-calling enforces them at the source (the whole point of switching
off the ad-hoc ``normalize_*`` post-hoc patches). The models intentionally do
not carry the cross-field ``_has_visible_*`` validators: those are batch-merge
concerns and would wrongly reject a legitimate question-only or solution-only
batch from a separated source. The fragment contract validates them downstream.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Confidence = Literal["high", "medium", "low"]
QuestionType = Literal["choice", "fillin", "problem", "short_answer"]


class OutputEvidenceItem(_Strict):
    kind: Literal["page"]
    source: str = Field(min_length=1)
    page_number: int = Field(ge=1)


class OutputEvidence(_Strict):
    question: list[OutputEvidenceItem] = Field(default_factory=list)
    solution: list[OutputEvidenceItem] = Field(default_factory=list)
    solution_start_anchor: str | None = None
    solution_end_anchor: str | None = None


class OutputContent(_Strict):
    stem_latex: str | None = None
    choices: list[str] = Field(default_factory=list)
    answer: str | None = None
    clue: str | None = None
    solution_steps: list[str] = Field(default_factory=list)
    solution_notes: list[str] = Field(default_factory=list)


class OutputConfidence(_Strict):
    stem: Confidence
    formula: Confidence
    solution_steps: Confidence


class OutputQuestion(_Strict):
    question_ref: str = Field(pattern=r"^\d{1,3}(-[A-Za-z0-9]+)?$")
    question_number: int = Field(ge=1)
    question_type: QuestionType
    points: int = Field(ge=0)
    section_ref: str = Field(min_length=1)
    section_title: str = Field(min_length=1)
    content: OutputContent
    evidence: OutputEvidence
    transcription_confidence: OutputConfidence


class DocxObservationOutput(_Strict):
    """The structured provider returns ``{"questions": [OutputQuestion, ...]}``."""

    questions: list[OutputQuestion] = Field(min_length=1)
