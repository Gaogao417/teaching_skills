#!/usr/bin/env python3
"""Internal contracts for the DOCX page-observation pipeline.

These models deliberately sit upstream of the frozen public bundle contracts.
A provider may observe the same question in more than one overlapping window;
``merge_docx_observations`` resolves that repetition before the public
``QuestionTranscriptionBundle`` is emitted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.question_transcription.contracts import (
    NonEmptyStr,
    PaperMeta,
    Provider,
    QuestionContent,
    QuestionEvidence,
    QuestionRef,
    QuestionType,
    Sha256,
    EvidenceRef,
)


Confidence = Literal["high", "medium", "low"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocxPage(_Strict):
    page_number: int = Field(ge=1)
    source: NonEmptyStr
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    sha256: Sha256


class TranscriptionConfidence(_Strict):
    stem: Confidence
    formula: Confidence
    solution_steps: Confidence


class PartialQuestionContent(_Strict):
    """Window-local content; fields absent from the visible pages stay absent."""

    stem_latex: NonEmptyStr | None = None
    choices: list[NonEmptyStr] = Field(default_factory=list)
    answer: NonEmptyStr | None = None
    clue: NonEmptyStr | None = None
    solution_steps: list[NonEmptyStr] = Field(default_factory=list)
    solution_notes: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_visible_content(self) -> "PartialQuestionContent":
        if not any(
            (
                self.stem_latex,
                self.choices,
                self.answer,
                self.clue,
                self.solution_steps,
                self.solution_notes,
            )
        ):
            raise ValueError("window question fragment contains no visible content")
        return self


class PartialQuestionEvidence(_Strict):
    """Window-local evidence; question and solution roles may be separated."""

    question: list[EvidenceRef] = Field(default_factory=list)
    solution: list[EvidenceRef] = Field(default_factory=list)
    solution_start_anchor: NonEmptyStr | None = None
    solution_end_anchor: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _has_visible_evidence(self) -> "PartialQuestionEvidence":
        if not self.question and not self.solution:
            raise ValueError("window question fragment contains no visible evidence")
        return self


class DocxObservedQuestionFragment(_Strict):
    """A possibly partial observation of one question in one page window."""

    question_ref: QuestionRef
    question_number: int = Field(ge=1)
    question_type: QuestionType
    points: int = Field(ge=0)
    section_ref: NonEmptyStr
    section_title: NonEmptyStr
    content: PartialQuestionContent
    evidence: PartialQuestionEvidence
    transcription_confidence: TranscriptionConfidence


class DocxObservedQuestion(_Strict):
    question_ref: QuestionRef
    question_number: int = Field(ge=1)
    question_type: QuestionType
    points: int = Field(ge=0)
    section_ref: NonEmptyStr
    section_title: NonEmptyStr
    content: QuestionContent
    evidence: QuestionEvidence
    transcription_confidence: TranscriptionConfidence

    @model_validator(mode="after")
    def _shape_by_type(self) -> "DocxObservedQuestion":
        if self.question_type == "choice":
            if len(self.content.choices) != 4:
                raise ValueError("choice question requires exactly four choices")
            if self.content.answer.strip() not in {"A", "B", "C", "D"}:
                raise ValueError("choice answer must be A/B/C/D")
        if self.question_type in {"problem", "short_answer"} and not self.content.solution_steps:
            raise ValueError("problem/short_answer requires solution_steps")
        return self


class DocxWindowObservation(_Strict):
    schema_: Literal["math_docx_window_observation/v1"] = Field(alias="schema")
    window_id: NonEmptyStr
    pages: list[DocxPage] = Field(min_length=1)
    questions: list[DocxObservedQuestionFragment] = Field(default_factory=list)
    provider: Provider

    @model_validator(mode="after")
    def _unique_pages_and_refs(self) -> "DocxWindowObservation":
        page_numbers = [p.page_number for p in self.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("duplicate page_number in window")
        refs = [q.question_ref for q in self.questions]
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate question_ref in window")
        return self


class ObservationConflict(_Strict):
    question_ref: QuestionRef
    selected_window_id: NonEmptyStr
    other_window_ids: list[NonEmptyStr] = Field(min_length=1)
    fields: list[NonEmptyStr] = Field(min_length=1)


class DocxObservationBundle(_Strict):
    schema_: Literal["math_docx_observation/v1"] = Field(alias="schema")
    paper: PaperMeta
    pages: list[DocxPage] = Field(min_length=1)
    questions: list[DocxObservedQuestion] = Field(min_length=1)
    provider: Provider
    conflicts: list[ObservationConflict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_pages_and_refs(self) -> "DocxObservationBundle":
        pages = [p.page_number for p in self.pages]
        refs = [q.question_ref for q in self.questions]
        if len(pages) != len(set(pages)):
            raise ValueError("duplicate page_number in merged observation")
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate question_ref in merged observation")
        return self
