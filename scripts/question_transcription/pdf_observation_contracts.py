#!/usr/bin/env python3
"""Strict internal contracts for the PDF joint-observation pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.question_transcription.contracts import (
    AttributionConfidence,
    AttributionRole,
    AttributionState,
    NonEmptyStr,
    PaperMeta,
    Provider,
    QuestionContent,
    QuestionRef,
    QuestionType,
    Sha256,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PdfSource(_Strict):
    path: NonEmptyStr
    sha256: Sha256 | None = None


class PdfRender(_Strict):
    engine: Literal["pdftoppm", "pre_rendered"]
    dpi: int = Field(default=180, ge=72, le=600)


class PdfPage(_Strict):
    page_number: int = Field(ge=1)
    source: NonEmptyStr
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    sha256: Sha256


class PdfSourceManifest(_Strict):
    schema_: Literal["math_pdf_source/v1"] = Field(alias="schema")
    paper_id: NonEmptyStr
    source_archive: NonEmptyStr
    source: PdfSource
    render: PdfRender
    pages: list[PdfPage] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_pages(self) -> "PdfSourceManifest":
        numbers = [page.page_number for page in self.pages]
        sources = [page.source for page in self.pages]
        if len(numbers) != len(set(numbers)):
            raise ValueError("page_number must be unique")
        if len(sources) != len(set(sources)):
            raise ValueError("page source must be unique")
        if numbers != sorted(numbers):
            raise ValueError("pages must be sorted by page_number")
        return self


class ObservationEvidence(_Strict):
    page_number: int = Field(ge=1)
    box_px: list[int] = Field(min_length=4, max_length=4)


class ObservationFigure(_Strict):
    local_id: NonEmptyStr
    page_number: int = Field(ge=1)
    role: AttributionRole
    order: int = Field(default=0, ge=0)
    box_px: list[int] = Field(min_length=4, max_length=4)
    whiteout_px: list[list[int]] = Field(default_factory=list)
    confidence: AttributionConfidence
    state: AttributionState
    note: str | None = None
    needs_human_crop: bool = False


class ObservationQuestion(_Strict):
    question_ref: QuestionRef
    question_number: int = Field(ge=1)
    section_ref: NonEmptyStr = "questions"
    section_title: NonEmptyStr = "试题"
    question_type: QuestionType
    points: int = Field(ge=0)
    content: QuestionContent | None = None
    question_evidence: list[ObservationEvidence] = Field(default_factory=list)
    solution_evidence: list[ObservationEvidence] = Field(default_factory=list)
    solution_start_anchor: str | None = None
    solution_end_anchor: str | None = None
    figures: list[ObservationFigure] = Field(default_factory=list)
    confidence: dict[str, AttributionConfidence] = Field(default_factory=dict)
    continues_from_previous: bool = False
    continues_to_next: bool = False
    notes: list[str] = Field(default_factory=list)


class PdfPageObservation(_Strict):
    schema_: Literal["math_pdf_page_observation/v1"] = Field(alias="schema")
    paper: PaperMeta
    provider: Provider
    prompt_version: NonEmptyStr
    window_id: NonEmptyStr
    pages: list[PdfPage] = Field(min_length=1)
    questions: list[ObservationQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_coordinates(self) -> "PdfPageObservation":
        pages = {page.page_number: page for page in self.pages}
        for question in self.questions:
            if question.question_number != int(question.question_ref.split("-", 1)[0]):
                raise ValueError(
                    f"{question.question_ref}: question_number does not match question_ref"
                )
            regions = (
                list(question.question_evidence)
                + list(question.solution_evidence)
                + list(question.figures)
            )
            for region in regions:
                page = pages.get(region.page_number)
                if page is None:
                    raise ValueError(
                        f"{question.question_ref}: region references page "
                        f"{region.page_number} outside window"
                    )
                _validate_box(region.box_px, page, f"{question.question_ref} region")
                if isinstance(region, ObservationFigure):
                    for whiteout in region.whiteout_px:
                        _validate_box(
                            whiteout, page, f"{question.question_ref} whiteout"
                        )
        return self


class MergedPdfObservation(_Strict):
    schema_: Literal["math_pdf_merged_observation/v1"] = Field(alias="schema")
    paper: PaperMeta
    provider: Provider
    prompt_version: NonEmptyStr
    pages: list[PdfPage] = Field(min_length=1)
    questions: list[ObservationQuestion] = Field(default_factory=list)
    source_windows: list[NonEmptyStr] = Field(min_length=1)
    conflicts: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_as_one_window(self) -> "MergedPdfObservation":
        PdfPageObservation.model_validate(
            {
                "schema": "math_pdf_page_observation/v1",
                "paper": self.paper.model_dump(by_alias=True),
                "provider": self.provider.model_dump(),
                "prompt_version": self.prompt_version,
                "window_id": "merged-validation",
                "pages": [p.model_dump() for p in self.pages],
                "questions": [q.model_dump() for q in self.questions],
            }
        )
        return self


def _validate_box(box: list[int], page: PdfPage, label: str) -> None:
    if len(box) != 4 or any(type(value) is not int for value in box):
        raise ValueError(f"{label}: box_px must contain exactly four integers")
    left, top, right, bottom = box
    if not (0 <= left < right <= page.width_px):
        raise ValueError(f"{label}: horizontal bounds exceed page {page.page_number}")
    if not (0 <= top < bottom <= page.height_px):
        raise ValueError(f"{label}: vertical bounds exceed page {page.page_number}")
