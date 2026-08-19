#!/usr/bin/env python3
"""Typed contracts for archived exam sources, reviews, and paper manifests."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from question_bank_contracts import QuestionType


Sha256 = str
ReviewStatus = Literal["pending", "approved", "revision_requested", "rejected"]
TranscriptionStatus = Literal["pending", "author_pass", "review_pass", "approved", "rejected"]
PromptReviewStatus = Literal[
    "not_required",
    "author_pass",
    "needs_human_crop",
    "review_pass",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


AttributionConfidence = Literal["high", "medium", "low"]


class AttributionReview(StrictModel):
    """Pending-attribution metadata carried on a crop.

    Present only when the image attribution to this question/role was uncertain
    (``state == "needs_review"``). The Review UI surfaces it for human
    confirmation; once the whole item's review is approved, the attribution is
    considered confirmed. Absent on accepted crops.

    For composed multi-image groups, ``attribution_id`` joins the pending member
    ids (comma-separated) and ``member_attribution_ids`` lists them so the
    weakest-confidence member can be traced.
    """

    attribution_id: str = Field(min_length=1)
    state: Literal["needs_review"]
    confidence: AttributionConfidence
    member_attribution_ids: list[str] = Field(default_factory=list)


class CropEvidence(StrictModel):
    source: str = Field(min_length=1)
    source_sha256: Sha256
    box_px: tuple[int, int, int, int]
    whiteout_px: list[tuple[int, int, int, int]] = Field(default_factory=list)
    output: str = Field(min_length=1)
    output_sha256: Sha256
    attribution_review: AttributionReview | None = None

    @field_validator("source_sha256", "output_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        prefix, separator, digest = value.partition(":")
        if separator != ":" or prefix != "sha256" or len(digest) != 64:
            raise ValueError("hash must use sha256:<64 lowercase hex digits>")
        if any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("hash must use sha256:<64 lowercase hex digits>")
        return value

    @model_validator(mode="after")
    def validate_box(self) -> "CropEvidence":
        left, top, right, bottom = self.box_px
        if min(self.box_px) < 0 or left >= right or top >= bottom:
            raise ValueError("box_px must be [left, top, right, bottom] with positive area")
        crop_width = right - left
        crop_height = bottom - top
        for whiteout in self.whiteout_px:
            whiteout_left, whiteout_top, whiteout_right, whiteout_bottom = whiteout
            if (
                min(whiteout) < 0
                or whiteout_left >= whiteout_right
                or whiteout_top >= whiteout_bottom
                or whiteout_right > crop_width
                or whiteout_bottom > crop_height
            ):
                raise ValueError(
                    "whiteout_px entries must be positive-area boxes inside the crop"
                )
        return self


class CropGroups(StrictModel):
    question_evidence: list[CropEvidence] = Field(default_factory=list)
    prompt: list[CropEvidence] = Field(default_factory=list)
    solution: list[CropEvidence] = Field(default_factory=list)
    official_solution: list[CropEvidence] = Field(default_factory=list)


class WordEvidenceSpan(StrictModel):
    """整页图来源证据：页图路径 + 页码。文件级溯源，无段落范围。"""

    page_image: str = Field(min_length=1)
    page_image_sha256: Sha256
    page_number: int = Field(ge=1)

    @field_validator("page_image_sha256")
    @classmethod
    def validate_page_image_sha256(cls, value: str) -> str:
        return CropEvidence.validate_sha256(value)


class WordEvidenceGroups(StrictModel):
    question: list[WordEvidenceSpan] = Field(default_factory=list)
    official_solution: list[WordEvidenceSpan] = Field(default_factory=list)


class TranscriptionState(StrictModel):
    question_status: TranscriptionStatus
    official_solution_status: TranscriptionStatus
    independent_review: TranscriptionStatus = "pending"
    human_review: TranscriptionStatus = "pending"
    prompt_status: PromptReviewStatus = "author_pass"
    prompt_review_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prompt_review(self) -> "TranscriptionState":
        if self.prompt_status == "needs_human_crop" and not self.prompt_review_notes:
            raise ValueError(
                "prompt_review_notes is required when prompt_status is needs_human_crop"
            )
        return self


class ExamItemSource(StrictModel):
    schema_version: Literal["math_exam_item_source/v1"] = Field(alias="schema")
    item_id: str
    source_key: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    question_number: int = Field(ge=1)
    question_type: QuestionType
    points: int = Field(ge=0)
    section_title: str = Field(min_length=1)
    source_directory: str = Field(min_length=1)
    crops: CropGroups
    word_evidence: WordEvidenceGroups = Field(default_factory=WordEvidenceGroups)
    transcription: TranscriptionState
    content_hash: Sha256

    @model_validator(mode="after")
    def validate_source_evidence(self) -> "ExamItemSource":
        if not self.crops.question_evidence and not self.word_evidence.question:
            raise ValueError("question source evidence is required")
        if not self.crops.official_solution and not self.word_evidence.official_solution:
            raise ValueError("official solution source evidence is required")
        return self

    @field_validator("item_id")
    @classmethod
    def validate_item_id(cls, value: str) -> str:
        if len(value) != 4 or value[0] != "Q" or not value[1:].isdigit():
            raise ValueError("item_id must use Q001-style format")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return CropEvidence.validate_sha256(value)


class ExamItemReview(StrictModel):
    schema_version: Literal["math_exam_item_review/v1"] = Field(alias="schema")
    item_id: str
    source_key: str = Field(min_length=1)
    content_hash: Sha256
    status: ReviewStatus
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    notes: list[str] = Field(default_factory=list)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return CropEvidence.validate_sha256(value)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("review notes cannot contain blank entries")
        return values


class OfficialSolutionSpan(StrictModel):
    pages: list[str] = Field(default_factory=list)
    start_anchor: str = Field(min_length=1)
    end_anchor: str = Field(min_length=1)

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("span pages cannot contain blank paths")
        if len(values) != len(set(values)):
            raise ValueError("span pages must be unique and ordered")
        return values

    @field_validator("start_anchor", "end_anchor")
    @classmethod
    def validate_anchor(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("span anchors cannot be blank")
        return value


class PaperMapItem(StrictModel):
    item_id: str
    question_number: int = Field(ge=1)
    question_pages: list[str] = Field(default_factory=list)
    official_solution: OfficialSolutionSpan

    @field_validator("item_id")
    @classmethod
    def validate_item_id(cls, value: str) -> str:
        if len(value) != 4 or value[0] != "Q" or not value[1:].isdigit():
            raise ValueError("item_id must use Q001-style format")
        return value

    @field_validator("question_pages")
    @classmethod
    def validate_question_pages(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("question_pages cannot contain blank paths")
        if len(values) != len(set(values)):
            raise ValueError("question_pages must be unique and ordered")
        return values


class ExamPaperMap(StrictModel):
    schema_version: Literal["math_exam_paper_map/v1"] = Field(alias="schema")
    paper_id: str = Field(min_length=1)
    items: list[PaperMapItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> "ExamPaperMap":
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("paper-map item IDs must be unique")
        return self


class NonQuestionPageClaim(StrictModel):
    """显式认领的无题页（Phase 2 fail-closed 审计豁免的唯一载体）。

    由源包目录下的人写 non-question-pages.yaml 声明，经抽取→draft→staging
    paper.yaml 传递，audit_staging 只允许这些页不被任何 item 的 word_evidence
    覆盖；未声明未覆盖页仍整卷拒绝。
    """

    page_number: int = Field(ge=1)
    role: str = Field(min_length=1)
    note: str | None = None


class PaperMetadata(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    subject: str = "数学"
    duration: str | None = None
    source_archive: str | None = None
    non_question_pages: list[NonQuestionPageClaim] = Field(default_factory=list)


class PaperSection(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    item_ids: list[str] = Field(min_length=1)

    @field_validator("item_ids")
    @classmethod
    def validate_item_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("item_ids must be unique within a section")
        for value in values:
            if len(value) != 4 or value[0] != "Q" or not value[1:].isdigit():
                raise ValueError("item_ids must use Q001-style format")
        return values


class ExamPaperManifest(StrictModel):
    schema_version: Literal["math_exam_paper/v1"] = Field(alias="schema")
    paper: PaperMetadata
    question_bank: str = Field(min_length=1)
    sections: list[PaperSection] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> "ExamPaperManifest":
        ids = [item_id for section in self.sections for item_id in section.item_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("an item_id may appear only once in a paper manifest")
        section_ids = [section.id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("paper section ids must be unique")
        return self
