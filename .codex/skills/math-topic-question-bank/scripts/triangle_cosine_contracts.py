#!/usr/bin/env python3
"""Contracts for exact four-ratio triangle question banks."""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from training_number_contracts import normalize_length, parse_fraction, squarefree


ProblemType = Literal["sss", "sas", "ssa", "aas", "asa"]
AngleKind = Literal["acute", "right", "obtuse"]
TrigFunction = Literal["sin", "cos", "tan", "cot"]
RatioDisplay = Literal["acute_ratio", "supplement_ratio", "right_ratio"]
TargetKind = Literal["side", "trig_ratio"]


class ExactSurd(BaseModel):
    """A signed exact value coefficient*sqrt(radicand)."""

    model_config = ConfigDict(extra="forbid")

    coefficient: str
    radicand: int = Field(ge=1)
    latex: str = Field(min_length=1)
    display: str = Field(min_length=1)

    @field_validator("coefficient")
    @classmethod
    def validate_coefficient(cls, value: str) -> str:
        parse_fraction(value)
        return value

    @model_validator(mode="after")
    def validate_normal_form(self) -> "ExactSurd":
        coefficient = self.coefficient_fraction
        if coefficient == 0 and self.radicand != 1:
            raise ValueError("zero must use radicand 1")
        if not squarefree(self.radicand):
            raise ValueError("radicand must be square-free")
        normalized = normalize_length(coefficient, self.radicand)
        if normalized != (coefficient, self.radicand):
            raise ValueError("exact value is not normalized")
        return self

    @property
    def coefficient_fraction(self) -> Fraction:
        return parse_fraction(self.coefficient)

    @property
    def squared(self) -> Fraction:
        return self.coefficient_fraction**2 * self.radicand

    def normalized_pair(self) -> tuple[Fraction, int]:
        return self.coefficient_fraction, self.radicand


class TrigValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sin: ExactSurd
    cos: ExactSurd
    tan: ExactSurd | None
    cot: ExactSurd | None


class AngleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["A", "B", "C"]
    kind: AngleKind
    actual: TrigValues
    reference: TrigValues

    @model_validator(mode="after")
    def validate_signs(self) -> "AngleRecord":
        cosine = self.actual.cos.coefficient_fraction
        reference_cosine = self.reference.cos.coefficient_fraction
        if self.actual.sin.coefficient_fraction <= 0:
            raise ValueError("triangle angle sine must be positive")
        reference_values = [self.reference.sin, self.reference.cos]
        reference_values.extend(value for value in (self.reference.tan, self.reference.cot) if value)
        if any(value.coefficient_fraction < 0 for value in reference_values):
            raise ValueError("assignment reference ratios cannot be negative")
        if self.kind == "acute" and cosine <= 0:
            raise ValueError("acute angle requires positive cosine")
        if self.kind == "right" and cosine != 0:
            raise ValueError("right angle requires zero cosine")
        if self.kind == "obtuse" and cosine >= 0:
            raise ValueError("obtuse angle requires negative cosine")
        expected_reference = -cosine if self.kind == "obtuse" else cosine
        if self.reference.cos.normalized_pair() != (expected_reference, self.actual.cos.radicand):
            raise ValueError("reference cosine does not match the angle kind")
        if self.reference.sin.normalized_pair() != self.actual.sin.normalized_pair():
            raise ValueError("reference sine must equal actual sine")
        if self.kind == "obtuse":
            for name in ("tan", "cot"):
                actual = getattr(self.actual, name)
                reference = getattr(self.reference, name)
                if actual is None or reference is None:
                    raise ValueError("obtuse angle requires tangent and cotangent")
                if reference.normalized_pair() != (-actual.coefficient_fraction, actual.radicand):
                    raise ValueError(f"reference {name} does not match the obtuse angle")
        if self.kind == "right" and self.actual.tan is not None:
            raise ValueError("right angle tangent must be absent")
        if self.kind == "right" and self.reference.tan is not None:
            raise ValueError("right reference tangent must be absent")
        if self.kind == "right" and reference_cosine != 0:
            raise ValueError("right reference cosine must be zero")
        return self


class TrigRatioEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    ratios: TrigValues
    source_number_entry_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_acute_trig(self) -> "TrigRatioEntry":
        if self.ratios.tan is None or self.ratios.cot is None:
            raise ValueError("acute source angle requires all four ratios")
        if min(self.ratios.sin.coefficient_fraction, self.ratios.cos.coefficient_fraction) <= 0:
            raise ValueError("source angle must be acute")
        if self.ratios.sin.squared + self.ratios.cos.squared != 1:
            raise ValueError("source angle fails sin^2+cos^2=1")
        return self


class TrigRatioDatabaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["triangle-acute-trig-ratios"]
    source_number_database_id: str
    source_review_file: str
    generator: str


class TrigRatioDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_triangle_trig_ratio_database/v1"] = Field(alias="schema")
    database: TrigRatioDatabaseMetadata
    entries: list[TrigRatioEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "TrigRatioDatabase":
        ids = [entry.id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("trigonometric-ratio ids must be unique")
        return self


class TriangleSides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: ExactSurd
    b: ExactSurd
    c: ExactSurd

    @model_validator(mode="after")
    def validate_positive(self) -> "TriangleSides":
        if any(
            value.coefficient_fraction <= 0
            for value in (self.a, self.b, self.c)
        ):
            raise ValueError("triangle sides must be positive")
        return self


class TriangleShape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^tri-[a-f0-9]{12}$")
    sides: TriangleSides
    angles: list[AngleRecord] = Field(min_length=3, max_length=3)
    source_trig_ratio_ids: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_angles(self) -> "TriangleShape":
        if [angle.name for angle in self.angles] != ["A", "B", "C"]:
            raise ValueError("triangle angles must be ordered A, B, C")
        return self


class SsaCase(BaseModel):
    """One or two materialized triangles sharing the same SSA givens."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ssa-[a-f0-9]{12}$")
    known_angle_name: Literal["A", "B", "C"]
    known_angle: AngleRecord
    opposite_side_name: Literal["a", "b", "c"]
    opposite_side: ExactSurd
    other_known_side_name: Literal["a", "b", "c"]
    other_known_side: ExactSurd
    missing_side_name: Literal["a", "b", "c"]
    triangle_ids: list[str] = Field(min_length=1, max_length=2)
    missing_side_answers: list[ExactSurd] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_case(self) -> "SsaCase":
        side_names = {
            self.opposite_side_name,
            self.other_known_side_name,
            self.missing_side_name,
        }
        if side_names != {"a", "b", "c"}:
            raise ValueError("SSA case must name each side exactly once")
        if len(self.triangle_ids) != len(set(self.triangle_ids)):
            raise ValueError("SSA triangle ids must be distinct")
        answer_keys = [answer.normalized_pair() for answer in self.missing_side_answers]
        if len(answer_keys) != len(set(answer_keys)):
            raise ValueError("SSA missing-side answers must be distinct")
        if len(self.triangle_ids) != len(self.missing_side_answers):
            raise ValueError("SSA branch count must match missing-side answer count")
        return self


class TriangleDatabaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["triangle-cosine-shapes"]
    source_trig_ratio_database_id: Literal["triangle-acute-trig-ratios"]
    source_trig_ratio_database: str
    generator: str


class TriangleDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_triangle_cosine_database/v1"] = Field(alias="schema")
    database: TriangleDatabaseMetadata
    triangles: list[TriangleShape] = Field(min_length=1)
    ssa_cases: list[SsaCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "TriangleDatabase":
        triangle_ids = [triangle.id for triangle in self.triangles]
        if len(triangle_ids) != len(set(triangle_ids)):
            raise ValueError("triangle ids must be unique")
        case_ids = [case.id for case in self.ssa_cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("SSA case ids must be unique")
        known_triangles = set(triangle_ids)
        for case in self.ssa_cases:
            if not set(case.triangle_ids).issubset(known_triangles):
                raise ValueError(f"{case.id}: unknown triangle id")
        return self

    def validate_trig_references(self, trig_database: TrigRatioDatabase) -> None:
        known_angles = {entry.id for entry in trig_database.entries}
        for triangle in self.triangles:
            if not set(triangle.source_trig_ratio_ids).issubset(known_angles):
                raise ValueError(f"{triangle.id}: unknown source trigonometric-ratio id")


class VisibleAngleFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    angle_name: Literal["A", "B", "C"]
    function: TrigFunction
    display: RatioDisplay
    value: ExactSurd

    @model_validator(mode="after")
    def validate_public_ratio(self) -> "VisibleAngleFact":
        if self.value.coefficient_fraction < 0:
            raise ValueError("assignment ratio facts cannot be negative")
        if self.display == "right_ratio" and self.function == "tan":
            raise ValueError("right-angle tangent is undefined")
        return self


class QuestionAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solution_count: Literal[1, 2]
    givens_reproduced: Literal[True]
    answers_verified: Literal[True]
    printable_values_only: Literal[True]
    no_obtuse_trig_in_assignment: Literal[True]


class CandidateQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^TCQ-[A-F0-9]{12}$")
    problem_type: ProblemType
    target_kind: TargetKind
    target_trig_function: TrigFunction | None = None
    stem_latex: str = Field(min_length=1)
    answers: list[ExactSurd] = Field(min_length=1, max_length=2)
    visible_angle_facts: list[VisibleAngleFact]
    source_triangle_ids: list[str] = Field(min_length=1, max_length=2)
    audit: QuestionAudit
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_answers_and_sources(self) -> "CandidateQuestion":
        answer_keys = [value.normalized_pair() for value in self.answers]
        if len(answer_keys) != len(set(answer_keys)):
            raise ValueError("answers must be distinct")
        if self.audit.solution_count == 1 and len(self.source_triangle_ids) != 1:
            raise ValueError("one-solution question requires one source triangle")
        if (self.target_kind == "trig_ratio") != (self.target_trig_function is not None):
            raise ValueError("trigonometric target kind and function must appear together")
        return self


class CandidateMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["triangle-cosine-question-candidates"]
    triangle_database: str
    generator: str


class CandidateDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_triangle_cosine_candidates/v1"] = Field(alias="schema")
    database: CandidateMetadata
    questions: list[CandidateQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CandidateDatabase":
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate question ids must be unique")
        return self


class ReviewEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["approved", "rejected"]
    reason: str | None = None

    @model_validator(mode="after")
    def validate_reason(self) -> "ReviewEntry":
        if self.decision == "rejected" and not (self.reason or "").strip():
            raise ValueError("rejected question requires a reason")
        return self


class QuestionReview(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_triangle_cosine_review/v1"] = Field(alias="schema")
    candidate_database_id: Literal["triangle-cosine-question-candidates"]
    entries: list[ReviewEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "QuestionReview":
        ids = [entry.question_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("review question ids must be unique")
        return self


class PublishedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["triangle-cosine-question-bank"]
    topic: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    version: str = Field(min_length=1)
    candidate_database: str
    review_file: str


class PublishedQuestionBank(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_triangle_cosine_question_bank/v1"] = Field(alias="schema")
    bank: PublishedMetadata
    questions: list[CandidateQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "PublishedQuestionBank":
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("published question ids must be unique")
        return self
