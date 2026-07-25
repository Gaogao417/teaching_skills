#!/usr/bin/env python3
"""Pydantic contracts for reusable math topic question banks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QuestionType = Literal["choice", "fillin", "problem", "short_answer"]
Difficulty = Literal["foundation", "standard", "challenge"]
DiagramRequirement = Literal["none", "prompt_only", "prompt_and_solution"]


class BankMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    subject: str = "数学"
    source_explanation: str | None = Field(default=None, min_length=1)
    source_archive: str | None = Field(default=None, min_length=1)
    status: Literal["plan", "ready"] = "plan"
    target_count: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def validate_source(self) -> "BankMetadata":
        if (self.source_explanation is None) == (self.source_archive is None):
            raise ValueError("exactly one of source_explanation or source_archive is required")
        return self


class QuestionBankItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = Field(min_length=1)
    question_type: QuestionType
    difficulty: Difficulty
    skill_tags: list[str] = Field(min_length=1)
    variation_dimension: str = Field(min_length=1)
    diagram_requirement: DiagramRequirement = "none"
    student_assignment: str = Field(min_length=1)
    teacher_assignment: str = Field(min_length=1)
    source_ref: str | None = Field(default=None, min_length=1)
    weight: float = Field(default=1.0, gt=0)
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if len(value) != 4 or value[0] != "Q" or not value[1:].isdigit():
            raise ValueError("item id must use Q001-style format")
        return value

    @field_validator("skill_tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("skill_tags cannot contain blank values")
        return values


class QuestionBank(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_topic_question_bank/v1"] = Field(alias="schema")
    bank: BankMetadata
    items: list[QuestionBankItem]

    @model_validator(mode="after")
    def validate_items(self) -> "QuestionBank":
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique")
        if self.bank.status == "ready" and len(self.items) != self.bank.target_count:
            raise ValueError(
                f"ready bank requires {self.bank.target_count} items, got {len(self.items)}"
            )
        if self.bank.source_archive is not None:
            missing = [item.id for item in self.items if item.source_ref is None]
            if missing:
                raise ValueError(
                    "source_archive banks require source_ref for every item; missing "
                    + ", ".join(missing)
                )
        return self
