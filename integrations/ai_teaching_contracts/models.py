"""canonical 对象的 Pydantic 模型，逐字段对应 PRD 仓 contracts/schemas/*/v1、v2。

规则来源是 JSON Schema；模型是它的可执行化。改 schema 必须同步改这里并
重跑两仓 fixture tests（退出门禁 1）。字段名与 JSON 键一致（全 snake_case）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# 公共标量（regex 与 JSON Schema 逐字相同，保证双语言判定一致）
# --------------------------------------------------------------------------- #
NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
VersionTag = Annotated[str, Field(pattern=r"^v[0-9]+$")]

QuestionId = Annotated[str, Field(pattern=r"^QT-[A-Z0-9]+-[0-9]{3,}$")]
CandidateId = Annotated[str, Field(pattern=r"^QC-[A-Z0-9]+-[0-9]{3,}$")]
EvidenceId = Annotated[str, Field(pattern=r"^SE-[A-Z0-9]+-[0-9]{3,}$")]
ApproachId = Annotated[str, Field(pattern=r"^TA-[A-Z0-9]+-[0-9]{3,}$")]
ApproachSetId = Annotated[str, Field(pattern=r"^AS-[A-Z0-9]+-[0-9]{3,}$")]
PlanId = Annotated[str, Field(pattern=r"^TP-[A-Z0-9]+-[0-9]{3,}$")]
SessionId = Annotated[str, Field(pattern=r"^TS-[0-9]{4,}$")]
SkillId = Annotated[str, Field(pattern=r"^SKILL-[A-Z0-9]+-[0-9]{3,}$")]
HypothesisId = Annotated[str, Field(pattern=r"^SH-[0-9]{4,}$")]
InterventionId = Annotated[str, Field(pattern=r"^IV-[0-9]{4,}$")]
RunId = Annotated[str, Field(pattern=r"^BR-[0-9]{4,}$")]
CaseId = Annotated[str, Field(pattern=r"^C-(INT|TRU|APP|PLN|RT)-[0-9]{2,}$")]

Status = Literal["Draft", "InReview", "Approved", "Stale", "Disabled", "Superseded"]
QuestionType = Literal["choice", "fill_blank", "solution"]

# 与 source-evidence.schema.json 的 artifact_uri pattern 逐字相同（id/path 段禁 @，避免吞并版本段）。
_ArtifactUriPattern = r"^artifact://[a-z][a-z0-9-]*/[A-Za-z0-9._~!$&'()*+,;=:%-]+(@v[0-9]+)?(/[A-Za-z0-9._~!$&'()*+,;=:%-]+)*$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactRef(_Strict):
    artifact_id: str
    version: VersionTag
    content_hash: Sha256


class EvidenceRef(_Strict):
    evidence_id: EvidenceId
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://")]


class ParserProvenance(_Strict):
    parser_id: NonEmptyStr
    parser_version: NonEmptyStr
    harness: NonEmptyStr
    model: "ModelRef | None" = None


class ModelRef(_Strict):
    provider: NonEmptyStr
    model_id: NonEmptyStr


# --------------------------------------------------------------------------- #
# authoring/v1/source-evidence
# --------------------------------------------------------------------------- #
class PageLocator(_Strict):
    kind: Literal["page"]
    page: int = Field(ge=1)
    note: str | None = None


class PageRegionLocator(_Strict):
    kind: Literal["page_region"]
    page: int = Field(ge=1)
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)]
    note: str | None = None


class DocxRangeLocator(_Strict):
    kind: Literal["docx_range"]
    paragraph_start: int = Field(ge=0)
    paragraph_end: int = Field(ge=0)
    note: str | None = None


Locator = Union[PageLocator, PageRegionLocator, DocxRangeLocator]


class SourceEvidence(_Strict):
    schema_: Literal["ai_teaching_source_evidence/v1"] = Field(alias="schema")
    evidence_id: EvidenceId
    source_pack_id: Annotated[str, Field(pattern=r"^pack-[A-Za-z0-9-]+$")]
    artifact_uri: Annotated[str, Field(pattern=_ArtifactUriPattern)]
    content_hash: Sha256
    locator: Locator
    parser_provenance: ParserProvenance
    extracted_at: datetime
    notes: str | None = None


# --------------------------------------------------------------------------- #
# authoring/v1/question-candidate
# --------------------------------------------------------------------------- #
class CandidateReviewState(_Strict):
    status: Literal["Draft", "InReview", "Approved", "Disabled"]
    reviewer_id: str | None = None
    note: str | None = None
    edited_by_reviewer: bool | None = None


class CandidateExtraction(_Strict):
    extracted_at: datetime
    parser_provenance: ParserProvenance


class Subquestion(_Strict):
    part_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")]
    prompt: NonEmptyStr
    points: float | None = Field(default=None, gt=0)


class QuestionCandidate(_Strict):
    schema_: Literal["ai_teaching_question_candidate/v1"] = Field(alias="schema")
    candidate_id: CandidateId
    source_evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1)]
    question_type: QuestionType
    stem: NonEmptyStr
    subquestions: list[Subquestion] = Field(default_factory=list)
    figure_refs: list[Annotated[str, Field(pattern=r"^artifact://")]] = Field(default_factory=list)
    review_state: CandidateReviewState
    extraction: CandidateExtraction
    content_hash: Sha256


# --------------------------------------------------------------------------- #
# authoring/v1/question-truth
# --------------------------------------------------------------------------- #
class CanonicalAnswer(_Strict):
    kind: Literal["numeric", "expression", "text", "proof", "choice_option"]
    value: NonEmptyStr
    acceptance: list[
        Literal[
            "numeric_equivalence",
            "radical_simplification",
            "vertex_cyclic_permutation",
            "answer_normalization",
            "unit_conversion",
            "manual_review",
        ]
    ] = Field(default_factory=list)
    range_constraint: str | None = None


class Approval(_Strict):
    reviewer_id: NonEmptyStr
    approved_at: datetime
    review_note: str | None = None
    edits_applied: bool | None = None


class SupersededBy(_Strict):
    artifact_id: str
    version: VersionTag


class QuestionTruth(_Strict):
    schema_: Literal["ai_teaching_question_truth/v1"] = Field(alias="schema")
    artifact_id: QuestionId
    version: VersionTag
    status: Status
    question_type: QuestionType
    stem: NonEmptyStr
    subquestions: list[Subquestion] = Field(default_factory=list)
    canonical_answer: CanonicalAnswer
    reviewed_solution: NonEmptyStr
    source_evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1)]
    origin_candidate_id: CandidateId | None = None
    approval: Approval | None = None
    superseded_by: SupersededBy | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://question-truth/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _status_requirements(self) -> "QuestionTruth":
        if self.status == "Approved" and self.approval is None:
            raise ValueError("status=Approved requires approval (schema allOf)")
        if self.status == "Superseded" and self.superseded_by is None:
            raise ValueError("status=Superseded requires superseded_by (schema allOf)")
        return self


# --------------------------------------------------------------------------- #
# authoring/v2/question-truth（ADR-005 小问粒度）
# --------------------------------------------------------------------------- #
class SubquestionV2(_Strict):
    part_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")]
    prompt: NonEmptyStr
    points: float | None = Field(default=None, gt=0)
    canonical_answer: CanonicalAnswer
    reviewed_solution: NonEmptyStr


class QuestionTruthV2(_Strict):
    schema_: Literal["ai_teaching_question_truth/v2"] = Field(alias="schema")
    artifact_id: QuestionId
    version: VersionTag
    status: Status
    question_type: QuestionType
    stem: NonEmptyStr
    subquestions: list[SubquestionV2] = Field(default_factory=list)
    canonical_answer: CanonicalAnswer | None = None
    reviewed_solution: str | None = None
    source_evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1)]
    origin_candidate_id: CandidateId | None = None
    approval: Approval | None = None
    superseded_by: SupersededBy | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://question-truth/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _scope_requirements(self) -> "QuestionTruthV2":
        if self.status == "Approved" and self.approval is None:
            raise ValueError("status=Approved requires approval (schema allOf)")
        if self.status == "Superseded" and self.superseded_by is None:
            raise ValueError("status=Superseded requires superseded_by (schema allOf)")
        if self.subquestions:
            # 有小问：小问级真值为单一事实源，顶层不得重复存整题答案/解答。
            if self.canonical_answer is not None or self.reviewed_solution is not None:
                raise ValueError(
                    "subquestions present: top-level canonical_answer/reviewed_solution forbidden"
                )
        else:
            if self.canonical_answer is None or self.reviewed_solution is None:
                raise ValueError(
                    "no subquestions: top-level canonical_answer/reviewed_solution required"
                )
        return self


# --------------------------------------------------------------------------- #
# authoring/v1/teaching-approach
# --------------------------------------------------------------------------- #
class QuestionRef(_Strict):
    artifact_id: QuestionId
    version: VersionTag
    content_hash: Sha256


class TeachingStep(_Strict):
    step_id: Annotated[str, Field(pattern=r"^S[0-9]{1,3}$")]
    intent: NonEmptyStr
    narration: NonEmptyStr
    expected_student_reasoning: NonEmptyStr
    accepted_alternatives: list[NonEmptyStr] = Field(default_factory=list)
    common_errors: list[NonEmptyStr] = Field(default_factory=list)
    skill_ids: Annotated[list[SkillId], Field(min_length=1)]


class AudioEvidence(_Strict):
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://audio/")]
    content_hash: Sha256
    recorded_at: datetime
    duration_seconds: float | None = Field(default=None, gt=0)


class AsrProvenance(_Strict):
    provider: NonEmptyStr
    model_id: NonEmptyStr


class TranscriptEvidence(_Strict):
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://transcript/")]
    asr_provenance: AsrProvenance
    revision: int | None = Field(default=None, ge=1)


class PolishProvenance(_Strict):
    provider: NonEmptyStr
    model_id: NonEmptyStr
    prompt_version: NonEmptyStr


class PolishedEvidence(_Strict):
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://transcript/")]
    polish_provenance: PolishProvenance


class ApproachEvidence(_Strict):
    audio: list[AudioEvidence] = Field(default_factory=list)
    transcripts: list[TranscriptEvidence] = Field(default_factory=list)
    polished: list[PolishedEvidence] = Field(default_factory=list)
    manual_edit_notes: list[str] = Field(default_factory=list)


class TeachingApproach(_Strict):
    schema_: Literal["ai_teaching_teaching_approach/v1"] = Field(alias="schema")
    artifact_id: ApproachId
    version: VersionTag
    status: Status
    question_ref: QuestionRef
    title: NonEmptyStr
    goal: NonEmptyStr
    entry_signal: str | None = None
    steps: Annotated[list[TeachingStep], Field(min_length=3)]
    evidence: ApproachEvidence
    approval: Approval | None = None
    superseded_by: SupersededBy | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://teaching-approach/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _status_requirements(self) -> "TeachingApproach":
        if self.status == "Approved" and self.approval is None:
            raise ValueError("status=Approved requires approval (schema allOf)")
        if self.status == "Superseded" and self.superseded_by is None:
            raise ValueError("status=Superseded requires superseded_by (schema allOf)")
        return self


# --------------------------------------------------------------------------- #
# authoring/v2/teaching-approach（ADR-005：一个小问 × 一种解法）
# --------------------------------------------------------------------------- #
class PartQuestionRef(_Strict):
    artifact_id: QuestionId
    version: VersionTag
    content_hash: Sha256
    # QT 含 subquestions 时必填（跨对象校验在冻结/评测层 fail closed）；无小问时省略即整题。
    part_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")] | None = None


class TeachingApproachV2(_Strict):
    schema_: Literal["ai_teaching_teaching_approach/v2"] = Field(alias="schema")
    artifact_id: ApproachId
    version: VersionTag
    status: Status
    question_ref: PartQuestionRef
    title: NonEmptyStr
    goal: NonEmptyStr
    entry_signal: str | None = None
    steps: Annotated[list[TeachingStep], Field(min_length=3)]
    evidence: ApproachEvidence
    approval: Approval | None = None
    superseded_by: SupersededBy | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://teaching-approach/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _status_requirements(self) -> "TeachingApproachV2":
        if self.status == "Approved" and self.approval is None:
            raise ValueError("status=Approved requires approval (schema allOf)")
        if self.status == "Superseded" and self.superseded_by is None:
            raise ValueError("status=Superseded requires superseded_by (schema allOf)")
        return self


# --------------------------------------------------------------------------- #
# authoring/v3/teaching-approach（ADR-006：步骤不再强制 skill_ids）
# --------------------------------------------------------------------------- #
class RequiredPartQuestionRef(_Strict):
    artifact_id: QuestionId
    version: VersionTag
    content_hash: Sha256
    # v3：part_id 必填（小问粒度是 v2 起的固定边界）。
    part_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")]


class TeachingStepV3(_Strict):
    step_id: Annotated[str, Field(pattern=r"^S[0-9]{1,3}$")]
    intent: NonEmptyStr
    narration: NonEmptyStr
    expected_student_reasoning: NonEmptyStr
    accepted_alternatives: list[NonEmptyStr] | None = None
    common_errors: list[NonEmptyStr] | None = None
    source_trace_refs: list[NonEmptyStr] | None = None


class TeachingApproachV3(_Strict):
    schema_: Literal["ai_teaching_teaching_approach/v3"] = Field(alias="schema")
    artifact_id: ApproachId
    version: VersionTag
    status: Status
    question_ref: RequiredPartQuestionRef
    title: NonEmptyStr
    goal: NonEmptyStr
    entry_signal: str | None = None
    steps: Annotated[list[TeachingStepV3], Field(min_length=3)]
    evidence: ApproachEvidence
    approval: Approval | None = None
    superseded_by: SupersededBy | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://teaching-approach/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _status_requirements(self) -> "TeachingApproachV3":
        if self.status == "Approved" and self.approval is None:
            raise ValueError("status=Approved requires approval (schema allOf)")
        if self.status == "Superseded" and self.superseded_by is None:
            raise ValueError("status=Superseded requires superseded_by (schema allOf)")
        return self


# --------------------------------------------------------------------------- #
# authoring/v1/approach-set（ADR-005 §5 跨小问组合层）
# --------------------------------------------------------------------------- #
class ApproachSetPart(_Strict):
    part_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")] | None = None
    approach: "ApproachRef"
    alternates: list["ApproachRef"] = Field(default_factory=list)
    note: str | None = None


class ApproachSetSupersededBy(_Strict):
    artifact_id: ApproachSetId
    version: VersionTag


class ApproachSet(_Strict):
    schema_: Literal["ai_teaching_approach_set/v1"] = Field(alias="schema")
    artifact_id: ApproachSetId
    version: VersionTag
    status: Status
    question_ref: QuestionRef
    parts: Annotated[list[ApproachSetPart], Field(min_length=1)]
    cross_part_rhythm: str | None = None
    approval: Approval | None = None
    superseded_by: ApproachSetSupersededBy | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://approach-set/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _status_requirements(self) -> "ApproachSet":
        if self.status == "Approved" and self.approval is None:
            raise ValueError("status=Approved requires approval (schema allOf)")
        if self.status == "Superseded" and self.superseded_by is None:
            raise ValueError("status=Superseded requires superseded_by (schema allOf)")
        return self


# --------------------------------------------------------------------------- #
# planning/v1/tutor-plan-bundle
# --------------------------------------------------------------------------- #
ActionKind = Literal[
    "make-parallel",
    "intersect-carriers",
    "mark-segment-values",
    "pair-segments",
    "ratio-scratch",
    "convert-collinear",
    "enter-equation",
    "select-option",
    "enter-text",
]
DomainCommand = Literal[
    "construct-parallel",
    "construct-carrier",
    "intersect-lines",
    "set-segment-label",
    "set-correspondence-mark",
    "set-emphasis",
]


class TutorActionRef(_Strict):
    action_kind: ActionKind
    step_id: Annotated[str, Field(pattern=r"^S[0-9]{1,3}$")] | None = None
    domain_commands: list[DomainCommand] = Field(default_factory=list)


class TeachPlan(_Strict):
    fast_explanation: NonEmptyStr
    narration_segments: Annotated[list[NonEmptyStr], Field(min_length=1)]
    tutor_action_refs: list[TutorActionRef] = Field(default_factory=list)
    repair_guidance: list[NonEmptyStr] = Field(default_factory=list)


class HintRung(_Strict):
    level: int = Field(ge=0, le=5)
    hint: NonEmptyStr


class ReasoningCheckpoint(_Strict):
    checkpoint_id: Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")]
    expected_reasoning: NonEmptyStr
    accepted_alternatives: list[NonEmptyStr] = Field(default_factory=list)
    common_deviations: list[NonEmptyStr] = Field(default_factory=list)
    skill_ids: Annotated[list[SkillId], Field(min_length=1)]
    hint_ladder: Annotated[list[HintRung], Field(min_length=2)]

    @field_validator("hint_ladder")
    @classmethod
    def _ladder_levels_unique_ascending(cls, value: list[HintRung]) -> list[HintRung]:
        levels = [rung.level for rung in value]
        if len(set(levels)) != len(levels) or sorted(levels) != levels:
            raise ValueError("hint_ladder levels must be unique and ascending")
        return value


class GuidedSolvePlan(_Strict):
    opening_prompt: NonEmptyStr
    checkpoints: Annotated[list[ReasoningCheckpoint], Field(min_length=1)]


class DiagnosticProbe(_Strict):
    probe_id: Annotated[str, Field(pattern=r"^DP[0-9]{1,3}$")]
    target_skill_ids: Annotated[list[SkillId], Field(min_length=1)]
    prompt: NonEmptyStr
    expected_evidence: NonEmptyStr


class CapabilityValidation(_Strict):
    catalog_version: NonEmptyStr
    required_capabilities: Annotated[
        list[Annotated[str, Field(pattern=r"^similarity\.[a-z-]+$")]], Field(min_length=1)
    ]
    satisfied: Literal[True]


class AnswerLeakScan(_Strict):
    status: Literal["passed", "not_applicable"]
    scanned_fields: list[str] = Field(default_factory=list)


class AssessmentMode(_Strict):
    enabled: bool
    answer_leak_scan: AnswerLeakScan
    tutor_tools: Annotated[list, Field(max_length=0)]


class ApproachRef(_Strict):
    artifact_id: ApproachId
    version: VersionTag
    content_hash: Sha256


class TutorPlanBundle(_Strict):
    schema_: Literal["ai_teaching_tutor_plan_bundle/v1"] = Field(alias="schema")
    artifact_id: PlanId
    version: VersionTag
    status: Status
    question_ref: QuestionRef
    approach_ref: ApproachRef
    compiler_version: NonEmptyStr
    input_hash: Sha256
    teach: TeachPlan
    guided_solve: GuidedSolvePlan
    diagnostic_probes: list[DiagnosticProbe] = Field(default_factory=list)
    capability_validation: CapabilityValidation
    assessment_mode: AssessmentMode | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://tutor-plan/[A-Za-z0-9-]+@v[0-9]+$")]


# --------------------------------------------------------------------------- #
# planning/v2/tutor-plan-bundle（ADR-006 备课资源包）
# --------------------------------------------------------------------------- #
PartId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}$")]
CheckpointId = Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")]
ResourceId = Annotated[str, Field(pattern=r"^RES[0-9]{1,3}$")]


class PartBoundApproachRef(_Strict):
    artifact_id: ApproachId
    version: VersionTag
    content_hash: Sha256
    part_id: PartId


class RecommendedRoute(_Strict):
    route_id: Annotated[str, Field(pattern=r"^R[0-9]{1,3}$")]
    role: Literal["primary", "alternate"]
    part_id: PartId | None = None
    entry_condition: str | None = None
    checkpoint_ids: Annotated[list[CheckpointId], Field(min_length=1)]
    completion_condition: NonEmptyStr


class SkillAnnotation(_Strict):
    skill_id: SkillId
    rationale: NonEmptyStr
    evidence_refs: Annotated[list[NonEmptyStr], Field(min_length=1)]


class PlanCheckpoint(_Strict):
    checkpoint_id: CheckpointId
    part_id: PartId
    expected_reasoning: NonEmptyStr
    accepted_alternatives: list[NonEmptyStr] | None = None
    common_deviations: list[NonEmptyStr] | None = None
    skippable: bool | None = None
    skill_annotations: Annotated[list[SkillAnnotation], Field(max_length=2)] | None = None
    unmapped_skill_reason: str | None = None
    resource_ids: list[ResourceId] | None = None


class PlanResource(_Strict):
    resource_id: ResourceId
    kind: Literal[
        "explanation",
        "hint",
        "diagnostic_probe",
        "repair",
        "action_template",
        "workspace",
        "voice_seed",
    ]
    checkpoint_id: CheckpointId | None = None
    assistance_level: int | None = Field(default=None, ge=0, le=5)
    source: Literal["authored", "reused", "agent_generated"]
    content: NonEmptyStr | None = None
    action_ref: NonEmptyStr | None = None
    capability: NonEmptyStr | None = None
    target_ids: list[NonEmptyStr] | None = None


class PolicyConstraints(_Strict):
    allowed_move_types: Annotated[
        list[Literal["explain", "prompt", "hint", "confirm", "wait", "repair"]],
        Field(min_length=1),
    ]
    allowed_capabilities: list[NonEmptyStr]
    forbidden_content_kinds: list[
        Literal["canonical_answer", "reviewed_solution", "hidden_truth", "unapproved_tool"]
    ]
    maximum_assistance_level: int = Field(ge=0, le=5)
    # ADR-006：资源包永不用于 Assessment（隔离投影不在此合同内）。
    assessment_enabled: Literal[False]


class BuildProvenance(_Strict):
    provider: NonEmptyStr
    model_id: NonEmptyStr
    workflow_version: NonEmptyStr
    run_id: NonEmptyStr
    built_at: datetime
    runtime_registry_version: NonEmptyStr


class RuntimeProjection(_Strict):
    materializer_version: NonEmptyStr
    runtime_registry_version: NonEmptyStr
    projection_hash: Sha256
    validation_status: Literal["passed"]


class PlanApproval(_Strict):
    reviewer_id: NonEmptyStr
    approved_at: datetime
    review_note: str | None = None


class TutorPlanBundleV2(_Strict):
    schema_: Literal["ai_teaching_tutor_plan_bundle/v2"] = Field(alias="schema")
    artifact_id: PlanId
    version: VersionTag
    status: Status
    question_ref: QuestionRef
    approach_refs: Annotated[list[PartBoundApproachRef], Field(min_length=1)]
    recommended_routes: Annotated[list[RecommendedRoute], Field(min_length=1)]
    checkpoints: Annotated[list[PlanCheckpoint], Field(min_length=1)]
    resources: Annotated[list[PlanResource], Field(min_length=1)]
    policy_constraints: PolicyConstraints
    build_provenance: BuildProvenance
    runtime_projection: RuntimeProjection | None = None
    approval: PlanApproval | None = None
    content_hash: Sha256
    artifact_uri: Annotated[str, Field(pattern=r"^artifact://tutor-plan/[A-Za-z0-9-]+@v[0-9]+$")]

    @model_validator(mode="after")
    def _approved_requirements(self) -> "TutorPlanBundleV2":
        if self.status == "Approved" and (
            self.approval is None or self.runtime_projection is None
        ):
            raise ValueError(
                "status=Approved requires approval and runtime_projection (schema allOf)"
            )
        return self


# --------------------------------------------------------------------------- #
# runtime/v1/tutor-session-event
# --------------------------------------------------------------------------- #
SessionMode = Literal["teach", "guided_solve", "repair"]
HintLevel = int  # 0..5，payload 模型里约束


class PlanPinnedRef(_Strict):
    artifact_id: PlanId
    version: VersionTag
    content_hash: Sha256


class SessionStartedPayload(_Strict):
    plan: PlanPinnedRef


class ModeChangedPayload(_Strict):
    from_mode: SessionMode
    to_mode: SessionMode


class NarratedPayload(_Strict):
    segment_id: NonEmptyStr


class UtterancePayload(_Strict):
    input_kind: Literal[
        "reasoning_utterance", "question_asked", "pointing_evidence", "structured_action_evidence"
    ]
    text: str | None = None
    object_id: str | None = None
    action_id: str | None = None
    action_payload: str | None = None


class ReasoningAlignedPayload(_Strict):
    alignment: Literal[
        "expected_checkpoint", "alternate_valid_path", "incorrect_reasoning", "unclear"
    ]
    checkpoint_id: Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")] | None = None
    alternate_description: str | None = None


class HintIssuedPayload(_Strict):
    checkpoint_id: Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")]
    level: int = Field(ge=0, le=5)


class StudentProgressedPayload(_Strict):
    checkpoint_id: Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")]
    after_level: int = Field(ge=0, le=5)


class SelfCorrectedPayload(_Strict):
    checkpoint_id: Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")]
    before_hint: bool


class ToolExecutedPayload(_Strict):
    command_id: NonEmptyStr
    capability: NonEmptyStr
    target_ids: list[NonEmptyStr]
    command_payload: str | None = None
    outcome: Literal["executed", "rejected"]
    rejection_reason: str | None = None


class RepairDeliveredPayload(_Strict):
    checkpoint_id: Annotated[str, Field(pattern=r"^CP[0-9]{1,3}$")]


class RuntimeFailurePayload(_Strict):
    failure_class: NonEmptyStr
    message: str | None = None
    related_event_sequence: int | None = Field(default=None, ge=1)


class SessionCompletedPayload(_Strict):
    final_mode: SessionMode | None = None


_EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "session_started": SessionStartedPayload,
    "mode_changed": ModeChangedPayload,
    "tutor_narrated": NarratedPayload,
    "student_utterance_recorded": UtterancePayload,
    "reasoning_aligned": ReasoningAlignedPayload,
    "hint_issued": HintIssuedPayload,
    "student_progressed": StudentProgressedPayload,
    "student_self_corrected": SelfCorrectedPayload,
    "tutor_tool_executed": ToolExecutedPayload,
    "repair_delivered": RepairDeliveredPayload,
    "runtime_failure": RuntimeFailurePayload,
    "session_completed": SessionCompletedPayload,
}

EventType = Literal[tuple(_EVENT_PAYLOAD_MODELS.keys())]  # type: ignore[valid-type]


class TutorSessionEvent(_Strict):
    schema_: Literal["ai_teaching_tutor_session_event/v1"] = Field(alias="schema")
    session_id: SessionId
    sequence: int = Field(ge=1)
    occurred_at: datetime
    event_type: EventType
    payload: dict
    idempotency_key: Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")]

    @model_validator(mode="after")
    def _payload_matches_type(self) -> "TutorSessionEvent":
        model = _EVENT_PAYLOAD_MODELS[self.event_type]
        model.model_validate(self.payload)
        return self


# --------------------------------------------------------------------------- #
# runtime/v2/tutor-session-event（ADR-006 因果链）
# --------------------------------------------------------------------------- #
DecisionId = Annotated[str, Field(pattern=r"^TD-[A-Za-z0-9._:-]{4,}$")]
VoiceActionId = Annotated[str, Field(pattern=r"^VA-[A-Za-z0-9._:-]{4,}$")]
WorkspaceActionId = Annotated[str, Field(pattern=r"^WA-[A-Za-z0-9._:-]{4,}$")]
PurposeCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9._-]*$")]
MoveType = Literal["explain", "prompt", "hint", "confirm", "wait", "repair"]
AlignmentV2 = Literal[
    "expected_checkpoint", "alternate_valid", "incorrect", "unclear", "no_progress"
]


class V2SessionStartedPayload(_Strict):
    plan: PlanPinnedRef
    initial_mode: SessionMode


class V2ModeChangedPayload(_Strict):
    from_mode: SessionMode
    to_mode: SessionMode


class V2StudentInputPayload(_Strict):
    input_kind: Literal[
        "reasoning_utterance",
        "question_asked",
        "pointing_evidence",
        "structured_action_evidence",
        "silence_observed",
        "student_interrupted",
    ]
    text: str | None = None
    object_id: str | None = None
    action_id: str | None = None
    action_payload: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class V2ReasoningAlignedPayload(_Strict):
    alignment: AlignmentV2
    checkpoint_id: CheckpointId | None = None
    alternate_description: str | None = None


class V2TutorMovePayload(_Strict):
    decision_id: DecisionId
    move_type: MoveType
    purpose_code: PurposeCode
    policy_version: NonEmptyStr
    source_event_sequence: int = Field(ge=1)
    source_state_revision: int = Field(ge=0)
    checkpoint_id: CheckpointId | None = None
    assistance_level: int | None = Field(default=None, ge=0, le=5)
    resource_ids: list[ResourceId] | None = None
    fallback: bool | None = None

    @model_validator(mode="after")
    def _hint_requirements(self) -> "V2TutorMovePayload":
        if self.move_type == "hint" and (
            self.assistance_level is None or self.checkpoint_id is None
        ):
            raise ValueError("move_type=hint requires assistance_level and checkpoint_id (allOf)")
        return self


class V2VoiceActionIssuedPayload(_Strict):
    action_id: VoiceActionId
    decision_id: DecisionId
    text: NonEmptyStr
    interruptible: bool | None = None


class V2ActionCompletedPayload(_Strict):
    action_id: NonEmptyStr
    outcome: Literal["completed", "interrupted", "rejected", "failed"]
    failure_class: str | None = None
    message: str | None = None


class V2WorkspaceActionIssuedPayload(_Strict):
    action_id: WorkspaceActionId
    decision_id: DecisionId
    capability: NonEmptyStr
    target_ids: list[NonEmptyStr]
    command_payload: str | None = None


class V2HintIssuedPayload(_Strict):
    decision_id: DecisionId
    checkpoint_id: CheckpointId
    level: int = Field(ge=0, le=5)


class V2WorkingDiagnosisPayload(_Strict):
    summary_code: PurposeCode
    candidate_skill_ids: Annotated[list[SkillId], Field(max_length=3)] | None = None
    evidence_sequences: Annotated[list[int], Field(min_length=1)]


class V2PolicyFailedPayload(_Strict):
    policy_version: NonEmptyStr
    failure_class: NonEmptyStr
    fallback_used: bool
    fallback_resource_id: ResourceId | None = None


class V2RuntimeFailurePayload(_Strict):
    failure_class: NonEmptyStr
    message: str
    related_event_sequence: int | None = Field(default=None, ge=1)


_V2_EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "session_started": V2SessionStartedPayload,
    "mode_changed": V2ModeChangedPayload,
    "student_input_recorded": V2StudentInputPayload,
    "reasoning_aligned": V2ReasoningAlignedPayload,
    "tutor_move_decided": V2TutorMovePayload,
    "voice_action_issued": V2VoiceActionIssuedPayload,
    "voice_action_completed": V2ActionCompletedPayload,
    "workspace_action_issued": V2WorkspaceActionIssuedPayload,
    "workspace_action_completed": V2ActionCompletedPayload,
    "hint_issued": V2HintIssuedPayload,
    "working_diagnosis_updated": V2WorkingDiagnosisPayload,
    "policy_failed": V2PolicyFailedPayload,
    "runtime_failure": V2RuntimeFailurePayload,
}

# JSON Schema allOf 中显式 required: ["causation_sequence"] 的事件类型。
_V2_CAUSATION_REQUIRED = frozenset(
    {
        "mode_changed",
        "reasoning_aligned",
        "tutor_move_decided",
        "voice_action_issued",
        "workspace_action_issued",
        "voice_action_completed",
        "workspace_action_completed",
        "hint_issued",
        "working_diagnosis_updated",
        "policy_failed",
    }
)

EventTypeV2 = Literal[
    "session_started",
    "mode_changed",
    "student_input_recorded",
    "reasoning_aligned",
    "tutor_move_decided",
    "voice_action_issued",
    "voice_action_completed",
    "workspace_action_issued",
    "workspace_action_completed",
    "hint_issued",
    "student_progressed",
    "student_self_corrected",
    "working_diagnosis_updated",
    "repair_delivered",
    "policy_failed",
    "runtime_failure",
    "session_completed",
]


class TutorSessionEventV2(_Strict):
    schema_: Literal["ai_teaching_tutor_session_event/v2"] = Field(alias="schema")
    session_id: SessionId
    sequence: int = Field(ge=1)
    state_revision: int = Field(ge=0)
    occurred_at: datetime
    event_type: EventTypeV2
    payload: dict
    causation_sequence: int | None = Field(default=None, ge=1)
    idempotency_key: Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")]

    @model_validator(mode="after")
    def _payload_and_causation(self) -> "TutorSessionEventV2":
        model = _V2_EVENT_PAYLOAD_MODELS.get(self.event_type)
        if model is not None:
            model.model_validate(self.payload)
        if self.event_type in _V2_CAUSATION_REQUIRED and self.causation_sequence is None:
            raise ValueError(
                f"event_type={self.event_type} requires causation_sequence (schema allOf)"
            )
        return self


# --------------------------------------------------------------------------- #
# learning/v1/skill-hypothesis
# --------------------------------------------------------------------------- #
class EventEvidenceRef(_Strict):
    session_id: SessionId
    sequence: int = Field(ge=1)


class SkillHypothesis(_Strict):
    schema_: Literal["ai_teaching_skill_hypothesis/v1"] = Field(alias="schema")
    hypothesis_id: HypothesisId
    student_id: NonEmptyStr
    session_id: SessionId
    skill_id: SkillId
    direction: Literal["supports_strength", "supports_weakness", "ambiguous"]
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[EventEvidenceRef] = Field(default_factory=list)
    contradictory_evidence: list[EventEvidenceRef] = Field(default_factory=list)
    inference_version: NonEmptyStr
    supersedes: HypothesisId | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# learning/v1/intervention
# --------------------------------------------------------------------------- #
class InterventionDecision(_Strict):
    kind: Literal[
        "continue_lesson",
        "confirmation_probe",
        "single_diagnostic_question",
        "repair_explanation",
        "near_transfer_practice",
        "far_transfer_practice",
        "review_later",
    ]
    target_skill_ids: Annotated[list[SkillId], Field(min_length=1)]
    question_id: QuestionId | None = None
    probe_id: Annotated[str, Field(pattern=r"^DP[0-9]{1,3}$")] | None = None
    review_after_minutes: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _question_required_for_question_kinds(self) -> "InterventionDecision":
        if (
            self.kind
            in ("near_transfer_practice", "far_transfer_practice", "single_diagnostic_question")
            and self.question_id is None
        ):
            raise ValueError(f"decision.kind={self.kind} requires question_id (schema allOf)")
        return self


class InterventionOutcome(_Strict):
    event_refs: Annotated[list[EventEvidenceRef], Field(min_length=1)]
    observed_at: datetime
    summary: NonEmptyStr


class Intervention(_Strict):
    schema_: Literal["ai_teaching_intervention/v1"] = Field(alias="schema")
    intervention_id: InterventionId
    student_id: NonEmptyStr
    source_session_id: SessionId | None = None
    source_hypothesis_ids: Annotated[list[HypothesisId], Field(min_length=1)]
    decision: InterventionDecision
    why: NonEmptyStr
    expected_evidence: NonEmptyStr
    stop_condition: NonEmptyStr
    max_dose: int | None = Field(default=None, ge=1, le=1)
    status: Literal["planned", "executed", "completed", "aborted"]
    outcome: InterventionOutcome | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _outcome_required_when_finished(self) -> "Intervention":
        if self.status in ("completed", "aborted") and self.outcome is None:
            raise ValueError(f"status={self.status} requires outcome (schema allOf)")
        return self


# --------------------------------------------------------------------------- #
# evaluation/v1/sut-config
# --------------------------------------------------------------------------- #
class SutComponent(_Strict):
    provider: NonEmptyStr
    model: NonEmptyStr | None = None
    harness: str | None = None
    engine: str | None = None
    params: dict | None = None
    status: Literal["active", "not_executed"] | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _model_or_note(self) -> "SutComponent":
        if self.model is None and self.note is None:
            raise ValueError("component requires model or note (schema anyOf)")
        return self


class RepoState(_Strict):
    commit: Annotated[str, Field(min_length=7)]
    diff_sha256: Sha256 | None = None
    dirty: bool


class CodeBaseline(_Strict):
    repos: dict[str, RepoState] = Field(min_length=1)


class SutEnvironment(_Strict):
    runtime: NonEmptyStr
    os: str | None = None
    notes: str | None = None


class SutConfig(_Strict):
    schema_: Literal["ai_teaching_sut_config/v1"] = Field(alias="schema")
    sut_id: Annotated[str, Field(pattern=r"^sut-[a-z0-9-]+$")]
    label: NonEmptyStr
    components: dict[
        Literal["intake_ocr", "asr", "polish", "tutor_coach", "realtime_voice", "tts"],
        SutComponent,
    ] = Field(min_length=1)
    code_baseline: CodeBaseline
    prompt_workflow_versions: dict | None = None
    environment: SutEnvironment
    price_table_version: NonEmptyStr
    registered_at: datetime


# --------------------------------------------------------------------------- #
# evaluation/v1/benchmark-run
# --------------------------------------------------------------------------- #
class CaseMetrics(_Strict):
    latency_ms_p50: float | None = Field(default=None, ge=0)
    latency_ms_p95: float | None = Field(default=None, ge=0)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    detail: str | None = None


class CaseCost(_Strict):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    price_table_version: str | None = None
    estimated_cost: float | None = Field(default=None, ge=0)


class CaseResult(_Strict):
    case_id: CaseId
    stage: Literal["intake", "truth", "approach", "plan", "realtime"]
    status: Literal["pass", "fail", "error", "not_executed"]
    failure_class: NonEmptyStr | None = None
    metrics: CaseMetrics | None = None
    cost: CaseCost | None = None
    raw_output_ref: Annotated[str, Field(pattern=r"^artifact://benchmark-output/")] | None = None

    @model_validator(mode="after")
    def _failure_class_required_when_failed(self) -> "CaseResult":
        if self.status == "fail" and self.failure_class is None:
            raise ValueError("case status=fail requires failure_class (schema allOf)")
        return self


class RunSummary(_Strict):
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errored: int = Field(ge=0)
    not_executed: int = Field(ge=0)


class RunCostTotal(_Strict):
    price_table_version: NonEmptyStr
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)


class SutRef(_Strict):
    sut_id: Annotated[str, Field(pattern=r"^sut-[a-z0-9-]+$")]
    config_hash: Sha256
    config_artifact_uri: Annotated[
        str, Field(pattern=r"^artifact://sut-config/[a-z0-9-]+@v[0-9]+$")
    ]


class BenchmarkRun(_Strict):
    schema_: Literal["ai_teaching_benchmark_run/v1"] = Field(alias="schema")
    run_id: RunId
    dataset_id: NonEmptyStr
    dataset_version: VersionTag
    sut: SutRef
    status: Literal["running", "completed", "failed", "aborted"]
    case_results: Annotated[list[CaseResult], Field(min_length=1)]
    summary: RunSummary | None = None
    cost_total: RunCostTotal | None = None
    runner_version: NonEmptyStr
    environment: NonEmptyStr
    started_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def _summary_required_when_completed(self) -> "BenchmarkRun":
        if self.status == "completed":
            if self.summary is None or self.completed_at is None:
                raise ValueError("status=completed requires summary and completed_at (schema allOf)")
        return self


ParserProvenance.model_rebuild()
ApproachSetPart.model_rebuild()
