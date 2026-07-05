#!/usr/bin/env python3
"""Pydantic contracts for skill trace ingestion drafts."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]


class CognitiveLayer(str, Enum):
    L3_STRATEGY = "L3_strategy"
    L0_STRUCTURE = "L0_structure"
    L1_ENCODING = "L1_encoding"
    L2_EXECUTION = "L2_execution"


class ReuseLevel(str, Enum):
    GENERIC_ACTION = "generic_action"
    DOMAIN_ACTION = "domain_action"
    PATTERN_STEP = "pattern_step"
    INSTANCE_STEP = "instance_step"


class SkillTraceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProblemCase(SkillTraceModel):
    title: str
    raw_problem: NonEmptyStr
    provided_solution: str = ""
    expected_thinking: str = ""
    topic_tags: list[str] = Field(default_factory=list)
    target_student_level: str = ""

    @field_validator("raw_problem")
    @classmethod
    def validate_raw_problem_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_problem must not be blank")
        return value


class SkillTraceStep(SkillTraceModel):
    step_id: NonEmptyStr
    order: int
    name: str
    cognitive_layer: CognitiveLayer
    reuse_level: ReuseLevel
    domain: str = "general"
    student_action_norm: NonEmptyStr
    teacher_rationale: str = ""
    input_state: str = ""
    output_state: str = ""
    source_evidence: str = ""
    common_errors: list[str] = Field(default_factory=list)
    hint_intent: str = ""
    is_core_step: bool = True

    @field_validator("step_id", "student_action_norm")
    @classmethod
    def validate_required_text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required text fields must not be blank")
        return value


class SkillTraceValidation(SkillTraceModel):
    warnings: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class SkillTraceDraft(SkillTraceModel):
    draft_id: NonEmptyStr
    schema_version: str = "skill_trace_draft.v0"
    codex_thread_id: NonEmptyStr
    problem_case: ProblemCase
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    steps: list[SkillTraceStep] = Field(min_length=1)
    validation: SkillTraceValidation = Field(default_factory=SkillTraceValidation)

    @field_validator("draft_id", "codex_thread_id")
    @classmethod
    def validate_required_ids_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required id fields must not be blank")
        return value

    @model_validator(mode="after")
    def validate_semantic_contract(self) -> SkillTraceDraft:
        orders = [step.order for step in self.steps]
        if len(orders) != len(set(orders)):
            raise ValueError("step order values must be unique")

        layers = {step.cognitive_layer for step in self.steps}
        if CognitiveLayer.L3_STRATEGY not in layers:
            raise ValueError("trace must include at least one L3_strategy step")
        if not ({CognitiveLayer.L0_STRUCTURE, CognitiveLayer.L1_ENCODING} & layers):
            raise ValueError("trace must include at least one L0_structure or L1_encoding step")

        return self


_COMPOUND_ACTION_PATTERNS = [
    re.compile(r"(找|识别|判断|确定).{0,12}(并|并且|同时|然后|再).{0,12}(算|计算|求|列|写|代入|解)"),
    re.compile(r"(列|写|建立).{0,12}(并|并且|同时|然后|再).{0,12}(算|计算|求|解|筛选)"),
    re.compile(r"(代入).{0,12}(并|并且|同时|然后|再).{0,12}(化简|计算|求|解)"),
]


def find_compound_action_warnings(draft: SkillTraceDraft) -> list[str]:
    warnings: list[str] = []
    for step in draft.steps:
        action = step.student_action_norm.strip()
        if any(pattern.search(action) for pattern in _COMPOUND_ACTION_PATTERNS):
            warnings.append(
                f"{step.step_id}: student_action_norm may contain multiple actions; split it into separate steps"
            )
    return warnings


def validate_skill_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    draft = SkillTraceDraft.model_validate(payload)
    warnings = list(draft.validation.warnings)
    warnings.extend(find_compound_action_warnings(draft))
    return {"ok": True, "errors": [], "warnings": warnings}

