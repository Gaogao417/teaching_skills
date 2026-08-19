"""按 ``schema`` 字段分派到对应 Pydantic 模型的统一入口。"""
from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ValidationError

from integrations.ai_teaching_contracts import models

SchemaKind = Literal[
    "source-evidence",
    "question-candidate",
    "question-truth",
    "teaching-approach",
    "approach-set",
    "tutor-plan-bundle",
    "tutor-session-event",
    "skill-hypothesis",
    "intervention",
    "sut-config",
    "benchmark-run",
]

_SCHEMA_CONST_TO_MODEL: dict[str, type[BaseModel]] = {
    "ai_teaching_source_evidence/v1": models.SourceEvidence,
    "ai_teaching_question_candidate/v1": models.QuestionCandidate,
    "ai_teaching_question_truth/v1": models.QuestionTruth,
    "ai_teaching_question_truth/v2": models.QuestionTruthV2,
    "ai_teaching_teaching_approach/v1": models.TeachingApproach,
    "ai_teaching_teaching_approach/v2": models.TeachingApproachV2,
    "ai_teaching_approach_set/v1": models.ApproachSet,
    "ai_teaching_tutor_plan_bundle/v1": models.TutorPlanBundle,
    "ai_teaching_tutor_session_event/v1": models.TutorSessionEvent,
    "ai_teaching_skill_hypothesis/v1": models.SkillHypothesis,
    "ai_teaching_intervention/v1": models.Intervention,
    "ai_teaching_sut_config/v1": models.SutConfig,
    "ai_teaching_benchmark_run/v1": models.BenchmarkRun,
}

_KIND_TO_CONST: dict[str, str] = {
    "source-evidence": "ai_teaching_source_evidence/v1",
    "question-candidate": "ai_teaching_question_candidate/v1",
    "question-truth": "ai_teaching_question_truth/v1",
    "teaching-approach": "ai_teaching_teaching_approach/v1",
    "approach-set": "ai_teaching_approach_set/v1",
    "tutor-plan-bundle": "ai_teaching_tutor_plan_bundle/v1",
    "tutor-session-event": "ai_teaching_tutor_session_event/v1",
    "skill-hypothesis": "ai_teaching_skill_hypothesis/v1",
    "intervention": "ai_teaching_intervention/v1",
    "sut-config": "ai_teaching_sut_config/v1",
    "benchmark-run": "ai_teaching_benchmark_run/v1",
}

ValidationOutcome: TypeAlias = tuple[bool, list[str]]


def canonical_schema_for(kind: SchemaKind) -> str:
    return _KIND_TO_CONST[kind]


def validate_payload(payload: object) -> ValidationOutcome:
    """校验单个 canonical 对象；返回 (是否合法, 错误消息列表)。

    分派依据是对象自身的 ``schema`` 常量；未知常量 → invalid。
    与 TypeScript 侧（Zod）对同一 fixture 必须得到相同布尔结果
    （退出门禁 1，两仓 fixture tests 各自对照 fixtures-manifest 断言）。
    """
    if not isinstance(payload, dict):
        return False, ["payload is not a JSON object"]
    schema_const = payload.get("schema")
    model = _SCHEMA_CONST_TO_MODEL.get(schema_const) if isinstance(schema_const, str) else None
    if model is None:
        return False, [f"unknown schema constant: {schema_const!r}"]
    try:
        model.model_validate(payload)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        ]
        return False, errors
    return True, []
