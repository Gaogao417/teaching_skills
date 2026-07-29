"""SourceQuestion v2 contracts for DOCX/PDF original-paper ingestion.

These contracts sit *alongside* the frozen v1 bundles in
:mod:`scripts.question_transcription.contracts` and exist only to give the
DOCX/PDF ingestion path a way to express ordered text-and-image content that v1
could not: image choices (A/B/C/D each a figure), multi-part questions where each
part has its own stem figure, and solution steps that carry their own diagrams.

The pipeline becomes::

    DOCX/PDF observer -> adapters -> v2 bundles
                                            -> SourceQuestionAssembler
                                            -> paper.source.yaml
                                               (math_exam_source_paper/v2)
                                            -> Projector
                                            -> existing paper.draft.yaml (v1)

Relationship to the v1 contracts:

- v1 stays frozen and is still read by the existing DraftAssembler.
- v2 is additive: it is *not* a silent migration. Nothing here overwrites or
  auto-converts v1 data.
- The Projector (not in this file) is what turns a v2 ``SourceQuestion`` back
  into the v1-friendly ``paper.draft.yaml``. v1 is the *output* of that
  projection, never the input to v2.

Scope decisions captured in these types (see plan discussion):

- An EMF whose classification is ``emf_class == "mixed_content"`` is a
  first-class image node, kept whole (its text is NOT extracted).
- OLE-bound vector media are deterministically ``formula``; unbound vector
  media are deterministically ``diagram`` unless a mixed-content suspicion is
  raised for human adjudication.
- ``mixed_content`` is always a human decision. An unresolved ambiguity is
  ``needs_review`` and links to a blocking review issue.
- ``formula`` assets never produce a content image node. Decorative media are
  filtered by the extractor and never enter this contract.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Strict base (mirrors contracts.py so both layers feel identical to use)
# --------------------------------------------------------------------------- #


class _Strict(BaseModel):
    """Strict base: reject unknown keys so contracts surface typos early."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Shared scalar aliases (re-declared locally; importing from contracts.py would
# couple v2 to v1's import graph; these are tiny value types).
# --------------------------------------------------------------------------- #

NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
QuestionRef = Annotated[str, Field(pattern=r"^\d{1,3}(-[A-Za-z0-9]+)?$")]

# Stable local identifiers for parts / steps within one question. Used as join
# keys by ImageAttributionV2 targets. Decimal, optionally suffixed, so a part
# can be "1", "2", and a step "1", "2", ... without colliding with question_ref.
PartId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")]
StepId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")]

# The four A/B/C/D choice keys. A choice_panel keeps the original label too.
ChoiceKey = Literal["A", "B", "C", "D"]

QuestionType = Literal["choice", "fillin", "problem", "short_answer"]


# --------------------------------------------------------------------------- #
# EMF / image classification
# --------------------------------------------------------------------------- #

# ``formula`` and ``diagram`` come from the deterministic OLE-binding rule.
# ``mixed_content`` is set only after human review. ``needs_review`` is the
# unresolved state while that decision is pending.
EmfClass = Literal["formula", "diagram", "mixed_content", "needs_review"]


class OleFormulaBinding(_Strict):
    """Deterministic evidence that a vector object is backed by an OLE formula.

    ``embedded`` is the classification authority for formula vs diagram. When
    true, at least one stable OOXML/OLE locator is required so an auditor can
    identify the exact formula object without trusting an observer proposal.
    """

    embedded: bool
    relationship_id: str | None = None
    object_path: str | None = None
    prog_id: str | None = None

    @model_validator(mode="after")
    def _embedded_has_locator(self) -> "OleFormulaBinding":
        locators = (self.relationship_id, self.object_path, self.prog_id)
        if self.embedded and not any(value for value in locators):
            raise ValueError(
                "OLE formula binding with embedded=true requires a relationship_id, "
                "object_path, or prog_id"
            )
        if not self.embedded and any(value is not None for value in locators):
            raise ValueError(
                "OLE formula locators are only valid when embedded=true"
            )
        return self


# --------------------------------------------------------------------------- #
# RichContent: ordered text | image nodes
# --------------------------------------------------------------------------- #


class TextNode(_Strict):
    """A run of transcribed text (LaTeX-inline, same convention as v1)."""

    kind: Literal["text"]
    text: NonEmptyStr


class ImageNode(_Strict):
    """A reference to one accepted image asset, in reading order.

    ``asset_id`` resolves inside the v2 attribution bundle's ``assets``. The
    node never carries image bytes, crop boxes, or hashes here -- those live on
    the asset and attribution records so a shared image is referenced once.
    """

    kind: Literal["image"]
    asset_id: NonEmptyStr


RichContent = list[TextNode | ImageNode]


def _ensure_rich_nonempty(nodes: RichContent, where: str) -> RichContent:
    if not nodes:
        raise ValueError(f"{where}: RichContent must not be empty")
    return nodes


# --------------------------------------------------------------------------- #
# Solution step (stable step_id + RichContent)
# --------------------------------------------------------------------------- #


class SolutionStep(_Strict):
    """One numbered solution step with its own ordered content.

    A step may carry a diagram (an :class:`ImageNode` in ``content``) -- that is
    how v2 expresses "this step has a figure", which v1 could not. Steps are
    ordered by their position in the list; ``step_id`` is the stable join key.
    """

    step_id: StepId
    content: RichContent

    @model_validator(mode="after")
    def _nonempty(self) -> "SolutionStep":
        _ensure_rich_nonempty(self.content, f"step {self.step_id}")
        return self


# --------------------------------------------------------------------------- #
# Question part (stable part_id + RichContent stem + steps)
# --------------------------------------------------------------------------- #


class QuestionPart(_Strict):
    """One sub-question of a multi-part question.

    ``part_id`` is the stable join key for ``part_stem`` and
    ``part_solution_step`` image targets. ``label`` is the display label shown
    to students (e.g. "(1)", "（1）", "第(1)题"); it is free-form because exam
    papers differ.
    """

    part_id: PartId
    label: NonEmptyStr
    stem: RichContent
    solution_steps: list[SolutionStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _nonempty(self) -> "QuestionPart":
        _ensure_rich_nonempty(self.stem, f"part {self.part_id} stem")
        return self


# --------------------------------------------------------------------------- #
# Choice content (text | {content: RichContent})
# --------------------------------------------------------------------------- #


class ChoiceContent(_Strict):
    """One A/B/C/D choice, which may be an image or a text+image mix.

    A plain-string choice is expressed at the ``QuestionContentV2.choices``
    level as a ``str`` (the common, text-only case). An image-bearing choice
    uses this object so the choice keeps its ordered RichContent.
    """

    content: RichContent

    @model_validator(mode="after")
    def _nonempty(self) -> "ChoiceContent":
        _ensure_rich_nonempty(self.content, "choice content")
        return self


# A choice is either a bare string (text-only, the common case) or a structured
# object carrying RichContent (image / image+text choice).
ChoiceValue = str | ChoiceContent


# --------------------------------------------------------------------------- #
# Choice panel (synthetic four-choice figure, unconfirmed until human review)
# --------------------------------------------------------------------------- #


class ChoicePanelMapping(_Strict):
    """The A-D map for a single ``choice_panel`` image.

    Required when the four choices could NOT be reliably split into four
    separate :class:`ChoiceContent`. ``confirmed`` MUST be ``false`` until a
    human has validated the mapping; the assembler blocks promotion of an
    unconfirmed panel.
    """

    A: NonEmptyStr
    B: NonEmptyStr
    C: NonEmptyStr
    D: NonEmptyStr
    confirmed: bool = False

    @model_validator(mode="after")
    def _confirm_flag_default(self) -> "ChoicePanelMapping":
        # Defensive: the field defaults to False, but if a caller ever sets it
        # explicitly to a non-bool pydantic will already have rejected it.
        return self


class ChoicePanel(_Strict):
    """A single image that holds all four A-D choices, plus its A-D map.

    Used only when separate per-choice figures are not available. The panel is
    one shared asset referenced once; its mapping is human-gated.
    """

    asset_id: NonEmptyStr
    mapping: ChoicePanelMapping


# --------------------------------------------------------------------------- #
# QuestionContentV2
# --------------------------------------------------------------------------- #


class QuestionContentV2(_Strict):
    """The ordered, image-aware body of one SourceQuestion.

    ``stem`` is always present. It may be image-only after a reviewer confirms
    that an indivisible ``mixed_content`` asset contains the whole stem; the
    image is then preserved as-is rather than having its text extracted.

    For a ``choice`` question, exactly one of ``choices`` (four separate
    :class:`ChoiceValue`) or ``choice_panel`` is required.
    """

    stem: RichContent
    choices: list[ChoiceValue] = Field(default_factory=list)
    choice_panel: ChoicePanel | None = None
    parts: list[QuestionPart] = Field(default_factory=list)
    answer: NonEmptyStr
    clue: NonEmptyStr
    solution_steps: list[SolutionStep] = Field(default_factory=list)

    @field_validator("stem")
    @classmethod
    def _stem_nonempty(cls, nodes: RichContent) -> RichContent:
        return _ensure_rich_nonempty(nodes, "stem")

    @field_validator("choices")
    @classmethod
    def _choices_exactly_four(cls, choices: list[ChoiceValue]) -> list[ChoiceValue]:
        # Empty is fine (non-choice, or choice using choice_panel). When present
        # for a choice question, exactly four are required.
        if choices and len(choices) != 4:
            raise ValueError(
                f"choices must be exactly four when present; got {len(choices)}"
            )
        return choices

    @model_validator(mode="after")
    def _choice_panel_xor_choices(self) -> "QuestionContentV2":
        if self.choice_panel is not None and self.choices:
            raise ValueError(
                "choice question must use either choices or choice_panel, not both"
            )
        return self


# --------------------------------------------------------------------------- #
# Image attribution v2
# --------------------------------------------------------------------------- #

AttributionConfidence = Literal["high", "medium", "low"]
AttributionState = Literal["accepted", "needs_review", "rejected"]


class ImageRendition(_Strict):
    """The displayable raster produced from an asset.

    Separated from the asset bytes so the original (e.g. an EMF) and the shown
    PNG can differ: the original is the source-of-truth artifact, the rendition
    is what the renderer / Review UI embeds. Cropping is expressed by the
    target's crop box, not by mutating the rendition.
    """

    path: NonEmptyStr
    sha256: Sha256
    media_type: NonEmptyStr
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)


class SourceImageAsset(_Strict):
    """One original media asset plus its display rendition.

    ``asset_id`` is the handle referenced by :class:`ImageNode` and the
    attribution targets. ``original`` keeps the bytes/hash of the source file
    (e.g. ``word/media/image1.emf``); ``rendition`` is the rendered PNG that
    downstream consumers display. Shared images are referenced by multiple
    targets through the same ``asset_id`` -- the asset record is NOT copied.
    """

    asset_id: NonEmptyStr
    original_path: NonEmptyStr
    original_sha256: Sha256
    original_media_type: NonEmptyStr
    emf_class: EmfClass
    ole_binding: OleFormulaBinding | None = None
    review_issue_id: str | None = None
    rendition: ImageRendition | None = None

    @model_validator(mode="after")
    def _classification_matches_evidence(self) -> "SourceImageAsset":
        suffix = self.original_path.lower().rsplit(".", 1)[-1]
        is_vector = suffix in {"emf", "wmf"} or self.original_media_type.lower() in {
            "image/emf",
            "image/wmf",
            "image/x-emf",
            "image/x-wmf",
        }
        if is_vector and self.ole_binding is None:
            raise ValueError(
                f"vector asset {self.asset_id}: ole_binding evidence is required"
            )
        embedded = bool(self.ole_binding and self.ole_binding.embedded)
        if self.emf_class == "formula" and not embedded:
            raise ValueError(
                f"asset {self.asset_id}: formula requires an embedded OLE formula"
            )
        if self.emf_class in {"diagram", "mixed_content", "needs_review"} and embedded:
            raise ValueError(
                f"asset {self.asset_id}: OLE-bound media must be classified formula"
            )
        if self.emf_class in {"mixed_content", "needs_review"}:
            if not self.review_issue_id:
                raise ValueError(
                    f"asset {self.asset_id}: {self.emf_class} requires review_issue_id"
                )
        elif self.emf_class == "formula" and self.review_issue_id is not None:
            raise ValueError(
                f"asset {self.asset_id}: formula must not carry review_issue_id"
            )
        return self


# The strict target union. Each target pins exactly the keys its role requires.
class TargetQuestionStem(_Strict):
    target: Literal["question_stem"] = "question_stem"


class TargetChoice(_Strict):
    target: Literal["choice"] = "choice"
    choice_key: ChoiceKey


class TargetChoicePanel(_Strict):
    target: Literal["choice_panel"] = "choice_panel"


class TargetPartStem(_Strict):
    target: Literal["part_stem"] = "part_stem"
    part_id: PartId


class TargetQuestionSolutionStep(_Strict):
    target: Literal["question_solution_step"] = "question_solution_step"
    step_id: StepId


class TargetPartSolutionStep(_Strict):
    target: Literal["part_solution_step"] = "part_solution_step"
    part_id: PartId
    step_id: StepId


ImageTarget = (
    TargetQuestionStem
    | TargetChoice
    | TargetChoicePanel
    | TargetPartStem
    | TargetQuestionSolutionStep
    | TargetPartSolutionStep
)


class ImageCrop(_Strict):
    """The box carved out of an asset for one target.

    Defaults to the full asset (``kind="full"``); a region crop carries the
    ``box_px`` and optional ``whiteout_px`` in the same convention as v1. A
    shared asset referenced by multiple targets typically uses ``full`` for
    each -- the asset is shared, the crop is per-target.
    """

    kind: Literal["full", "region"] = "full"
    box_px: list[int] = Field(default_factory=list)
    whiteout_px: list[list[int]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _region_needs_box(self) -> "ImageCrop":
        if self.kind == "region":
            if len(self.box_px) != 4:
                raise ValueError("region crop requires box_px with four ints")
            left, top, right, bottom = self.box_px
            if min(self.box_px) < 0 or left >= right or top >= bottom:
                raise ValueError(
                    "region box_px must be [left, top, right, bottom] with positive area"
                )
            for w in self.whiteout_px:
                if len(w) != 4:
                    raise ValueError("whiteout_px entries must have four ints")
                wl, wt, wr, wb = w
                if min(w) < 0 or wl >= wr or wt >= wb:
                    raise ValueError("whiteout_px entries must have positive area")
        else:
            # full crop: box_px / whiteout_px must be empty
            if self.box_px or self.whiteout_px:
                raise ValueError("full crop must not carry box_px or whiteout_px")
        return self


class ImageAttributionV2(_Strict):
    """One accepted attribution of an asset to a structural target.

    ``asset_id`` + ``target`` together pin where the image goes. ``order`` is
    the reading order *within* the target's content list, matching the
    position of the :class:`ImageNode` that references this asset.
    """

    attribution_id: NonEmptyStr
    asset_id: NonEmptyStr
    question_ref: QuestionRef
    target: ImageTarget
    crop: ImageCrop = Field(default_factory=ImageCrop)
    order: int = Field(ge=0)
    confidence: AttributionConfidence
    state: AttributionState


# --------------------------------------------------------------------------- #
# The paper-level v2 bundle: SourceQuestion list + assets + attributions
# --------------------------------------------------------------------------- #


class SourceQuestion(_Strict):
    """One question in authoritative v2 form.

    Carries its own ``question_ref`` (the same source-local decimal key as v1)
    so the assembler can join against the v1 transcription bundle when needed.
    ``content`` is the v2 image-aware body.
    """

    question_ref: QuestionRef
    question_number: int = Field(ge=1)
    question_type: QuestionType
    points: int = Field(ge=0)
    content: QuestionContentV2

    @model_validator(mode="after")
    def _type_invariants(self) -> "SourceQuestion":
        t = self.question_type
        c = self.content
        if t == "choice":
            if c.choice_panel is None and not c.choices:
                raise ValueError(
                    f"choice question {self.question_ref}: requires choices or choice_panel"
                )
            if c.choice_panel is not None and c.choices:
                # already enforced on QuestionContentV2, but keep defense-in-depth
                raise ValueError(
                    f"choice question {self.question_ref}: use choices or choice_panel, not both"
                )
        if t in {"problem", "short_answer"}:
            if not c.solution_steps and not any(p.solution_steps for p in c.parts):
                raise ValueError(
                    f"{self.question_ref}: {t} requires solution_steps (on the "
                    "question or on at least one part)"
                )
        if t in {"fillin", "choice"} and c.parts:
            raise ValueError(
                f"{self.question_ref}: {t} questions must not carry parts"
            )
        return self


class SourcePaper(_Strict):
    """Schema ``math_exam_source_paper/v2``.

    The authoritative per-paper v2 artifact. The assembler writes it; the
    Projector reads it and emits the v1 ``paper.draft.yaml``. Mixing v1 and v2
    outputs for the same paper is allowed (v1 is the projection target), but v2
    never silently overwrites v1.
    """

    schema_: Literal["math_exam_source_paper/v2"] = Field(alias="schema")
    paper_id: NonEmptyStr
    questions: list[SourceQuestion] = Field(min_length=1)
    assets: list[SourceImageAsset] = Field(default_factory=list)
    attributions: list[ImageAttributionV2] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cross_refs(self) -> "SourcePaper":
        # unique question_ref
        refs = [q.question_ref for q in self.questions]
        if len(refs) != len(set(refs)):
            dupes = sorted({r for r in refs if refs.count(r) > 1})
            raise ValueError(f"duplicate question_ref: {dupes}")

        # unique asset_id
        asset_ids = [a.asset_id for a in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            dupes = sorted({a for a in asset_ids if asset_ids.count(a) > 1})
            raise ValueError(f"duplicate asset_id: {dupes}")

        known_assets = set(asset_ids)
        asset_by_id = {asset.asset_id: asset for asset in self.assets}
        question_by_ref = {
            question.question_ref: question for question in self.questions
        }

        def image_ids(nodes: RichContent) -> list[str]:
            return [node.asset_id for node in nodes if isinstance(node, ImageNode)]

        content_image_ids: list[str] = []
        for question in self.questions:
            content_image_ids.extend(image_ids(question.content.stem))
            for choice in question.content.choices:
                if isinstance(choice, ChoiceContent):
                    content_image_ids.extend(image_ids(choice.content))
            if question.content.choice_panel is not None:
                content_image_ids.append(question.content.choice_panel.asset_id)
            for step in question.content.solution_steps:
                content_image_ids.extend(image_ids(step.content))
            for part in question.content.parts:
                content_image_ids.extend(image_ids(part.stem))
                for step in part.solution_steps:
                    content_image_ids.extend(image_ids(step.content))

        for asset_id in content_image_ids:
            if asset_id not in known_assets:
                raise ValueError(f"content image asset_id {asset_id!r} not in assets")
            if asset_by_id[asset_id].emf_class == "formula":
                raise ValueError(
                    f"formula asset {asset_id!r} must not appear as a content image"
                )

        seen_attr: set[str] = set()
        for attr in self.attributions:
            if attr.asset_id not in known_assets:
                raise ValueError(
                    f"attribution {attr.attribution_id}: asset_id "
                    f"{attr.asset_id!r} not in assets"
                )
            if attr.attribution_id in seen_attr:
                raise ValueError(f"duplicate attribution_id: {attr.attribution_id}")
            seen_attr.add(attr.attribution_id)
            if attr.question_ref not in question_by_ref:
                raise ValueError(
                    f"attribution {attr.attribution_id}: question_ref "
                    f"{attr.question_ref!r} not in questions"
                )
            question = question_by_ref[attr.question_ref]
            target = attr.target
            if isinstance(target, (TargetChoice, TargetChoicePanel)):
                if question.question_type != "choice":
                    raise ValueError(
                        f"attribution {attr.attribution_id}: choice target requires "
                        "a choice question"
                    )
            elif isinstance(target, TargetPartStem):
                part_ids = {part.part_id for part in question.content.parts}
                if target.part_id not in part_ids:
                    raise ValueError(
                        f"attribution {attr.attribution_id}: unknown part_id "
                        f"{target.part_id!r} in question {attr.question_ref}"
                    )
            elif isinstance(target, TargetQuestionSolutionStep):
                step_ids = {
                    step.step_id for step in question.content.solution_steps
                }
                if target.step_id not in step_ids:
                    raise ValueError(
                        f"attribution {attr.attribution_id}: unknown step_id "
                        f"{target.step_id!r} in question {attr.question_ref}"
                    )
            elif isinstance(target, TargetPartSolutionStep):
                part = next(
                    (
                        part
                        for part in question.content.parts
                        if part.part_id == target.part_id
                    ),
                    None,
                )
                if part is None:
                    raise ValueError(
                        f"attribution {attr.attribution_id}: unknown part_id "
                        f"{target.part_id!r} in question {attr.question_ref}"
                    )
                step_ids = {step.step_id for step in part.solution_steps}
                if target.step_id not in step_ids:
                    raise ValueError(
                        f"attribution {attr.attribution_id}: unknown step_id "
                        f"{target.step_id!r} in part {target.part_id}"
                    )
            asset = asset_by_id[attr.asset_id]
            if attr.state == "accepted":
                if asset.emf_class not in {"diagram", "mixed_content"}:
                    raise ValueError(
                        f"attribution {attr.attribution_id}: accepted attribution "
                        f"cannot target {asset.emf_class} asset {attr.asset_id!r}"
                    )
                if asset.rendition is None:
                    raise ValueError(
                        f"attribution {attr.attribution_id}: accepted asset "
                        f"{attr.asset_id!r} requires a rendition"
                    )
        return self


__all__ = [
    "ChoiceKey",
    "ChoiceContent",
    "ChoiceValue",
    "ChoicePanel",
    "ChoicePanelMapping",
    "EmfClass",
    "ImageAttributionV2",
    "ImageCrop",
    "ImageNode",
    "ImageRendition",
    "ImageTarget",
    "PartId",
    "QuestionContentV2",
    "QuestionRef",
    "QuestionPart",
    "QuestionType",
    "RichContent",
    "SolutionStep",
    "SourceImageAsset",
    "SourcePaper",
    "SourceQuestion",
    "StepId",
    "TargetChoice",
    "TargetChoicePanel",
    "TargetPartSolutionStep",
    "TargetPartStem",
    "TargetQuestionSolutionStep",
    "TargetQuestionStem",
    "TextNode",
    "NonEmptyStr",
    "OleFormulaBinding",
    "Sha256",
]
