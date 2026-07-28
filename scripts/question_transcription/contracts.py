#!/usr/bin/env python3
"""Frozen v1 contracts for scripted question transcription.

These are the two standard Bundle types that upstream providers must emit, plus
the :class:`AssemblyReport` the deterministic assembler returns. They are the
shared interface described in ``docs/question-transcription-architecture.md``
§6. Anything that wants to feed the assembler -- Agent, vision API, OCR, DOCX
structure, or manual entry -- produces one of these two bundles; the assembler
itself never imports a provider format.

The two bundles join on ``question_ref`` (a source-local, decimal question
number string). The assembler owns ``Q001`` file-name assignment; providers
must not invent their own item IDs.

JSON Schema for every contract is emitted by :mod:`schema_dump`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --------------------------------------------------------------------------- #
# Shared scalar aliases / enums
# --------------------------------------------------------------------------- #

QuestionType = Literal["choice", "fillin", "problem", "short_answer"]
NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[
    str,
    Field(pattern=r"^sha256:[0-9a-f]{64}$"),
]

# The join key between the two bundles. Source-local, decimal question number.
QuestionRef = Annotated[str, Field(pattern=r"^\d{1,3}(-[A-Za-z0-9]+)?$")]

ProviderKind = Literal[
    "agent", "vision_api", "ocr", "docx_structure", "detection_model", "manual"
]
AttributionConfidence = Literal["high", "medium", "low"]
AttributionState = Literal["accepted", "needs_review", "rejected"]
AssetDisposition = Literal["attributed", "ignored", "needs_review"]
AttributionRole = Literal["prompt", "solution"]


class _Strict(BaseModel):
    """Strict base: reject unknown keys so contracts surface typos early."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #


class Provider(_Strict):
    """Who produced a given bundle / attribution. Provenance, not authority."""

    kind: ProviderKind
    name: NonEmptyStr
    version: NonEmptyStr


# --------------------------------------------------------------------------- #
# Evidence reference (the page vs region union)
# --------------------------------------------------------------------------- #


class PageEvidence(_Strict):
    """Whole-page evidence. Typical for DOCX rendered pages."""

    kind: Literal["page"]
    source: NonEmptyStr
    page_number: int = Field(ge=1)


class RegionEvidence(_Strict):
    """Region evidence. Typical for PDF / scanned pages with a crop box."""

    kind: Literal["region"]
    source: NonEmptyStr
    page_number: int = Field(ge=1)
    box_px: list[int] = Field(min_length=4, max_length=4)


EvidenceRef = PageEvidence | RegionEvidence


class QuestionEvidence(_Strict):
    """Evidence split by role within a single question."""

    question: list[EvidenceRef] = Field(min_length=1)
    solution: list[EvidenceRef] = Field(min_length=1)
    solution_start_anchor: NonEmptyStr
    solution_end_anchor: NonEmptyStr


# --------------------------------------------------------------------------- #
# Transcription content
# --------------------------------------------------------------------------- #


class QuestionContent(_Strict):
    """The transcribed body of one question.

    The assembler copies these fields verbatim; it never summarizes, merges, or
    re-splits ``solution_steps``.
    """

    stem_latex: NonEmptyStr
    choices: list[NonEmptyStr] = Field(default_factory=list)
    answer: NonEmptyStr
    clue: NonEmptyStr
    solution_steps: list[NonEmptyStr] = Field(default_factory=list)
    solution_notes: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_by_type(self) -> "QuestionContent":
        # Choice validation lives on the question (needs question_type); here
        # we only guard the steps/choices shapes that the bundle can check
        # without the type. Field-level type checks already happened.
        return self


# --------------------------------------------------------------------------- #
# Transcription Bundle
# --------------------------------------------------------------------------- #


class TranscriptionQuestion(_Strict):
    """One question in a :class:`QuestionTranscriptionBundle`."""

    question_ref: QuestionRef
    question_number: int = Field(ge=1)
    question_type: QuestionType
    points: int = Field(ge=0)
    content: QuestionContent
    evidence: QuestionEvidence

    @model_validator(mode="after")
    def _validate_choice(self) -> "TranscriptionQuestion":
        if self.question_type == "choice":
            if len(self.content.choices) != 4:
                raise ValueError(
                    f"choice question {self.question_ref}: exactly four choices required"
                )
            if not any(
                c.strip() in {"A", "B", "C", "D"} for c in self.content.choices
            ):
                # choices are bare option text; the answer must be A/B/C/D.
                pass
        if self.question_type in {"problem", "short_answer"}:
            if not self.content.solution_steps:
                raise ValueError(
                    f"{self.question_ref}: problem/short_answer requires solution_steps"
                )
        if self.question_type == "choice":
            answer = self.content.answer.strip()
            if answer not in {"A", "B", "C", "D"}:
                raise ValueError(
                    f"choice question {self.question_ref}: answer must be A/B/C/D"
                )
        return self


class TranscriptionSection(_Strict):
    section_ref: NonEmptyStr
    title: NonEmptyStr
    questions: list[TranscriptionQuestion] = Field(min_length=1)


class PaperMeta(_Strict):
    id: NonEmptyStr
    title: NonEmptyStr
    grade: NonEmptyStr
    subject: NonEmptyStr = "数学"
    source_archive: NonEmptyStr
    question_bank: NonEmptyStr = "../../question-bank.yaml"
    duration: str | None = None


class QuestionTranscriptionBundle(_Strict):
    """Schema ``math_question_transcription/v1``.

    One paper's transcribed text + evidence. ``sections[].questions[]`` order is
    the final paper order; the assembler emits ``Q001``, ``Q002`` in that order.
    """

    schema_: Literal["math_question_transcription/v1"] = Field(alias="schema")
    paper: PaperMeta
    sections: list[TranscriptionSection] = Field(min_length=1)
    provider: Provider

    @model_validator(mode="after")
    def _unique_refs(self) -> "QuestionTranscriptionBundle":
        refs = [
            q.question_ref
            for section in self.sections
            for q in section.questions
        ]
        if len(refs) != len(set(refs)):
            dupes = sorted({r for r in refs if refs.count(r) > 1})
            raise ValueError(f"duplicate question_ref in bundle: {dupes}")
        return self

    def refs(self) -> list[str]:
        """Question refs in paper order."""
        return [
            q.question_ref
            for section in self.sections
            for q in section.questions
        ]


# --------------------------------------------------------------------------- #
# Image attribution Bundle
# --------------------------------------------------------------------------- #


class FullCrop(_Strict):
    """Use the whole asset. Assembler expands to ``[0, 0, width, height]``."""

    kind: Literal["full"]


class RegionCrop(_Strict):
    """A bounded region of the asset. Copied verbatim into the draft."""

    kind: Literal["region"]
    box_px: list[int] = Field(min_length=4, max_length=4)
    whiteout_px: list[list[int]] = Field(default_factory=list)

    @field_validator("box_px")
    @classmethod
    def _positive_area(cls, box: list[int]) -> list[int]:
        left, top, right, bottom = box
        if min(box) < 0 or left >= right or top >= bottom:
            raise ValueError("region box_px must be [left, top, right, bottom] with positive area")
        return box

    @field_validator("whiteout_px")
    @classmethod
    def _whiteout(cls, boxes: list[list[int]]) -> list[list[int]]:
        for b in boxes:
            if len(b) != 4:
                raise ValueError("whiteout_px entries must have four ints")
            left, top, right, bottom = b
            if min(b) < 0 or left >= right or top >= bottom:
                raise ValueError("whiteout_px entries must have positive area")
        return boxes


CropSpec = FullCrop | RegionCrop


class AttributionAsset(_Strict):
    """A single image asset and its disposition (whether it belongs to a paper)."""

    asset_id: NonEmptyStr
    source: NonEmptyStr
    sha256: Sha256
    media_type: NonEmptyStr
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    disposition: AssetDisposition
    disposition_reason: str | None = None

    @model_validator(mode="after")
    def _ignored_can_be_bare(self) -> "AttributionAsset":
        if self.disposition == "attributed":
            # The contract says an attributed asset must have at least one
            # attribution, but that check spans the whole bundle; enforced on
            # the bundle.
            pass
        return self


class AttributionProvider(_Strict):
    """Provider for an attribution. Carries optional structural evidence."""

    kind: ProviderKind
    name: NonEmptyStr
    version: NonEmptyStr
    evidence: dict[str, object] = Field(default_factory=dict)


class Attribution(_Strict):
    """One image-to-question attribution, at question granularity (not step)."""

    attribution_id: NonEmptyStr
    asset_id: NonEmptyStr
    question_ref: QuestionRef
    role: AttributionRole
    crop: CropSpec
    order: int = Field(ge=0)
    confidence: AttributionConfidence
    state: AttributionState
    provider: AttributionProvider

    @model_validator(mode="after")
    def _region_needs_whiteout_optional(self) -> "Attribution":
        # nothing extra to enforce per-row; cross-row checks on the bundle.
        return self


class ImageAttributionBundle(_Strict):
    """Schema ``math_image_attribution/v1``.

    All image assets for a paper plus the accepted/needs_review attributions.
    The assembler consumes only ``state == "accepted"`` attributions, exactly
    once each. ``disposition == "ignored"`` assets are not consumed.
    """

    schema_: Literal["math_image_attribution/v1"] = Field(alias="schema")
    paper_id: NonEmptyStr
    assets: list[AttributionAsset] = Field(default_factory=list)
    attributions: list[Attribution] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cross_refs(self) -> "ImageAttributionBundle":
        asset_ids = {a.asset_id for a in self.assets}
        seen_attr: set[str] = set()
        attributed_assets = {a.asset_id for a in self.assets if a.disposition == "attributed"}
        assets_with_attribution: set[str] = set()
        for attr in self.attributions:
            if attr.asset_id not in asset_ids:
                raise ValueError(
                    f"attribution {attr.attribution_id}: asset_id {attr.asset_id!r} not in assets"
                )
            if attr.attribution_id in seen_attr:
                raise ValueError(f"duplicate attribution_id: {attr.attribution_id}")
            seen_attr.add(attr.attribution_id)
            if attr.state in {"accepted", "needs_review"}:
                assets_with_attribution.add(attr.asset_id)
        # attributed assets must have at least one accepted/needs_review attribution
        missing = attributed_assets - assets_with_attribution
        if missing:
            raise ValueError(
                f"assets with disposition=attributed have no attribution: {sorted(missing)}"
            )
        return self


# --------------------------------------------------------------------------- #
# Assembly report
# --------------------------------------------------------------------------- #


class AssemblyWarning(_Strict):
    code: NonEmptyStr
    attribution_id: NonEmptyStr | None = None
    asset_id: NonEmptyStr | None = None
    detail: str | None = None


class AssemblyError(_Strict):
    code: NonEmptyStr
    detail: NonEmptyStr
    question_ref: str | None = None
    attribution_id: str | None = None
    asset_id: str | None = None


class AssemblyReport(_Strict):
    """Schema ``math_draft_assembly_report/v1``.

    Not a review gate: ``errors`` non-empty means the assembler refused to write
    the draft; ``warnings`` ride along into the existing human review.
    """

    schema_: Literal["math_draft_assembly_report/v1"] = Field(alias="schema")
    paper_id: NonEmptyStr
    draft_path: str | None = None
    question_count: int = Field(ge=0)
    accepted_attributions: int = Field(ge=0)
    consumed_attributions: int = Field(ge=0)
    ignored_assets: int = Field(ge=0)
    unresolved_assets: int = Field(ge=0)
    errors: list[AssemblyError] = Field(default_factory=list)
    warnings: list[AssemblyWarning] = Field(default_factory=list)
