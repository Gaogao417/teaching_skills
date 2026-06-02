#!/usr/bin/env python3
"""Pydantic contracts for the two-stage diagram workflow.

The models in this module mirror docs/diagram-workflow-architecture.md:
assignment plan YAML declares diagram slots, the batch layer turns those slots
into single-image jobs, workflow.py executes one job, renderer produces images,
and resolver binds artifacts back into assignment.resolved.yaml.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]


class DiagramVariant(str, Enum):
    PROMPT = "prompt"
    SOLUTION = "solution"


class DisclosurePolicy(str, Enum):
    CLEAN = "clean"
    ANNOTATED = "annotated"


class DiagramEngine(str, Enum):
    GEOMETRIC_SCENE = "geometric_scene"


class DiagramKind(str, Enum):
    SYNTHETIC_GEOMETRY = "synthetic_geometry"
    COORDINATE_GEOMETRY = "coordinate_geometry"
    AUTO = "auto"


class DiagramOnFailure(str, Enum):
    FAIL_ASSIGNMENT = "fail_assignment"
    OMIT_DIAGRAM = "omit_diagram"
    TEXTUAL_FALLBACK = "textual_fallback"


class DiagramLayoutRole(str, Enum):
    QUESTION_SIDECAR = "question_sidecar"
    ANSWER_AREA_SIDECAR = "answer_area_sidecar"
    DIAGRAM_ROW_ITEM = "diagram_row_item"
    CENTER_BLOCK = "center_block"
    SOLUTION_ANNOTATION = "solution_annotation"


class DiagramOrientation(str, Enum):
    AUTO = "auto"
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


class DiagramRunStatus(str, Enum):
    PLANNED = "planned"
    COLLECTED = "collected"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    BOUND = "bound"


class DiagramSlotStatus(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    FAILED = "failed"
    OMITTED = "omitted"
    FALLBACK = "fallback"
    BLOCKED = "blocked"


class DiagramModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DiagramLooseModel(BaseModel):
    """Contract for external tool outputs where legacy fields may still appear."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class DiagramSemanticConstraints(DiagramModel):
    given_objects: list[str] = Field(default_factory=list)
    given_constraints: list[str] = Field(default_factory=list)
    derived_objects: list[str] = Field(default_factory=list)
    derived_constraints: list[str] = Field(default_factory=list)
    clean_forbidden: list[str] = Field(default_factory=list)
    solution_allowed_annotations: list[str] = Field(default_factory=list)


class DiagramProblemContext(DiagramModel):
    stem_latex: str = ""
    subquestion_latex: str = ""
    grade_or_topic: str = ""
    source_problem_text: str = ""


class DiagramVisualRequirements(DiagramModel):
    show_labels: bool = True
    show_given_markers: bool = True
    show_axes: bool = False
    preferred_orientation: DiagramOrientation = DiagramOrientation.AUTO
    caption: str = ""


class DiagramReuseSpec(DiagramModel):
    reuse_geometry_from: str = ""
    base_job_dir: str = ""


class DiagramEngineOptions(DiagramModel):
    seed: int | None = None
    max_retries: int = Field(default=3, ge=0)
    wolfram_timeout_s: int = Field(default=30, ge=1)
    wolfram_hard_timeout_s: int = Field(default=60, ge=1)
    engine_model_config: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("engine_model_config", "model_config"),
    )

    @model_validator(mode="after")
    def hard_timeout_not_shorter(self) -> DiagramEngineOptions:
        if self.wolfram_hard_timeout_s < self.wolfram_timeout_s:
            raise ValueError("wolfram_hard_timeout_s must be >= wolfram_timeout_s")
        return self


class DiagramSlot(DiagramModel):
    """Plan-stage declaration embedded under assignment.plan.yaml."""

    slot_id: NonEmptyStr
    diagram_ref: str = ""
    problem_id: str = ""
    source_problem_ref: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    required: bool = True
    on_failure: DiagramOnFailure = DiagramOnFailure.FAIL_ASSIGNMENT
    placement: NonEmptyStr
    layout_role: DiagramLayoutRole
    width_hint: str = ""
    caption: str = ""
    engine: DiagramEngine = DiagramEngine.GEOMETRIC_SCENE
    diagram_kind: DiagramKind = DiagramKind.SYNTHETIC_GEOMETRY
    teaching_intent: str = "practice_prompt"
    problem_context: DiagramProblemContext = Field(default_factory=DiagramProblemContext)
    semantic_constraints: DiagramSemanticConstraints = Field(default_factory=DiagramSemanticConstraints)
    visual_requirements: DiagramVisualRequirements = Field(default_factory=DiagramVisualRequirements)
    reuse_geometry_from: str = ""
    engine_options: DiagramEngineOptions = Field(default_factory=DiagramEngineOptions)

    @model_validator(mode="after")
    def enforce_slot_policy(self) -> DiagramSlot:
        if not self.diagram_ref:
            self.diagram_ref = self.slot_id
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt diagrams must use disclosure_policy='clean'")
        if self.required and self.on_failure != DiagramOnFailure.FAIL_ASSIGNMENT:
            raise ValueError("required diagrams must use on_failure='fail_assignment'")
        if self.variant == DiagramVariant.SOLUTION and not self.reuse_geometry_from:
            raise ValueError("solution diagram slots must declare reuse_geometry_from")
        if self.caption and not self.visual_requirements.caption:
            self.visual_requirements.caption = self.caption
        return self


class DiagramJob(DiagramModel):
    """Executable single-image job collected from one DiagramSlot."""

    job_id: NonEmptyStr = Field(validation_alias=AliasChoices("job_id", "diagram_job_id"))
    slot_id: NonEmptyStr
    diagram_ref: NonEmptyStr
    slot_path: NonEmptyStr
    problem_id: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    required: bool = True
    on_failure: DiagramOnFailure = DiagramOnFailure.FAIL_ASSIGNMENT
    engine: DiagramEngine = DiagramEngine.GEOMETRIC_SCENE
    diagram_kind: DiagramKind = DiagramKind.SYNTHETIC_GEOMETRY
    teaching_intent: str = "practice_prompt"
    request_path: NonEmptyStr
    out_dir: NonEmptyStr
    public_image_dir: NonEmptyStr
    depends_on: list[str] = Field(default_factory=list)
    content_hash: str = ""
    reuse_geometry_from: str = ""

    @model_validator(mode="after")
    def enforce_job_policy(self) -> DiagramJob:
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt jobs must use disclosure_policy='clean'")
        if self.required and self.on_failure != DiagramOnFailure.FAIL_ASSIGNMENT:
            raise ValueError("required jobs must use on_failure='fail_assignment'")
        if self.variant == DiagramVariant.SOLUTION:
            if not self.reuse_geometry_from:
                raise ValueError("solution jobs must declare reuse_geometry_from")
            if self.reuse_geometry_from not in self.depends_on:
                self.depends_on.append(self.reuse_geometry_from)
        if self.job_id in self.depends_on:
            raise ValueError("job cannot depend on itself")
        return self


class DiagramJobsManifest(DiagramModel):
    schema_version: Literal["diagram-jobs/v1"] = "diagram-jobs/v1"
    assignment_id: NonEmptyStr
    source_assignment: NonEmptyStr
    jobs: list[DiagramJob] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_job_graph(self) -> DiagramJobsManifest:
        job_ids = [job.job_id for job in self.jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("diagram job ids must be unique")

        slot_ids = [job.slot_id for job in self.jobs]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("diagram slot ids must be unique in one jobs manifest")

        known = set(job_ids)
        graph = {job.job_id: list(job.depends_on) for job in self.jobs}
        for job in self.jobs:
            missing = [dep for dep in job.depends_on if dep not in known]
            if missing:
                raise ValueError(f"job '{job.job_id}' depends on unknown job(s): {missing}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(job_id: str) -> None:
            if job_id in visited:
                return
            if job_id in visiting:
                raise ValueError(f"diagram job graph contains a cycle at '{job_id}'")
            visiting.add(job_id)
            for dep in graph.get(job_id, []):
                visit(dep)
            visiting.remove(job_id)
            visited.add(job_id)

        for job_id in job_ids:
            visit(job_id)
        return self

    def topological_job_ids(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        graph = {job.job_id: list(job.depends_on) for job in self.jobs}

        def visit(job_id: str) -> None:
            if job_id in seen:
                return
            for dep in graph.get(job_id, []):
                visit(dep)
            seen.add(job_id)
            ordered.append(job_id)

        for job in self.jobs:
            visit(job.job_id)
        return ordered


class DiagramJobRequest(DiagramModel):
    """workflow.py input. It describes one image, never a whole assignment."""

    schema_version: Literal["diagram-job-request/v2"] = "diagram-job-request/v2"
    job_id: NonEmptyStr = Field(validation_alias=AliasChoices("job_id", "diagram_job_id"))
    assignment_id: NonEmptyStr
    problem_id: str = ""
    slot_id: NonEmptyStr
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    engine: DiagramEngine = DiagramEngine.GEOMETRIC_SCENE
    diagram_kind: DiagramKind = DiagramKind.SYNTHETIC_GEOMETRY
    teaching_intent: str = "practice_prompt"
    problem_context: DiagramProblemContext = Field(default_factory=DiagramProblemContext)
    semantic_constraints: DiagramSemanticConstraints = Field(default_factory=DiagramSemanticConstraints)
    visual_requirements: DiagramVisualRequirements = Field(default_factory=DiagramVisualRequirements)
    reuse: DiagramReuseSpec = Field(default_factory=DiagramReuseSpec)
    engine_options: DiagramEngineOptions = Field(default_factory=DiagramEngineOptions)

    @model_validator(mode="after")
    def enforce_request_policy(self) -> DiagramJobRequest:
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt requests must use disclosure_policy='clean'")
        if self.variant == DiagramVariant.SOLUTION and not self.reuse.reuse_geometry_from:
            raise ValueError("solution requests must declare reuse.reuse_geometry_from")
        return self


class DiagramWolframSummary(DiagramLooseModel):
    success: bool = False
    solve_time_s: float = Field(default=0, ge=0)
    seed: int | None = None


class DiagramModelSummary(DiagramLooseModel):
    text_model_used: str = ""
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class DiagramJobResult(DiagramLooseModel):
    schema_version: Literal["diagram-job-result/v2"] = "diagram-job-result/v2"
    job_id: str = Field(default="", validation_alias=AliasChoices("job_id", "diagram_job_id"))
    status: DiagramRunStatus = DiagramRunStatus.FAILED
    fail_type: str = ""
    message: str = ""
    request: str = "request.json"
    workflow_events: str = "workflow_events.jsonl"
    scene_payload: str = "scene_payload.json"
    final_renderer_spec: str = "final_renderer_spec.json"
    wolfram: DiagramWolframSummary = Field(default_factory=DiagramWolframSummary)
    model: DiagramModelSummary = Field(default_factory=DiagramModelSummary)
    policy_warnings: list[str] = Field(default_factory=list)


class GeometryRenderSpec(DiagramLooseModel):
    schema_version: Literal["geometry-render-spec/v1"] = "geometry-render-spec/v1"
    job_id: str = ""
    variant: DiagramVariant | None = None
    disclosure_policy: DisclosurePolicy | None = None
    type: str = "synthetic_geometry"
    points: dict[str, tuple[float, float]]
    segments: list[dict[str, Any]] = Field(default_factory=list)
    polygons: list[dict[str, Any]] = Field(default_factory=list)
    markers: list[dict[str, Any]] = Field(default_factory=list)
    labels: dict[str, Any] = Field(default_factory=dict)
    teaching_focus: list[str] = Field(default_factory=list)


class RendererChecks(DiagramLooseModel):
    references_valid: bool = False
    svg_exists: bool = False
    image_exists: bool = False


class GeometryRendererResult(DiagramLooseModel):
    schema_version: Literal["geometry-renderer-result/v1"] = "geometry-renderer-result/v1"
    job_id: str = Field(default="", validation_alias=AliasChoices("job_id", "diagram_job_id"))
    status: DiagramRunStatus = DiagramRunStatus.FAILED
    fail_type: str = ""
    message: str = ""
    renderer: str = "teaching-svg-geometry-renderer"
    diagram_variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    renderer_spec: str = "final_renderer_spec.json"
    image_path: str = ""
    preview_svg: str = ""
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    checks: RendererChecks = Field(default_factory=RendererChecks)


class DiagramArtifact(DiagramModel):
    slot_id: NonEmptyStr
    job_id: NonEmptyStr = Field(validation_alias=AliasChoices("job_id", "diagram_job_id"))
    status: DiagramRunStatus
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    image_path: str = ""
    preview_svg: str = ""
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    aspect_ratio: float | None = Field(default=None, gt=0)
    artifact_hash: str = Field(
        default="",
        validation_alias=AliasChoices("hash", "artifact_hash"),
        serialization_alias="hash",
    )
    renderer_result: str = ""
    workflow_result: str = ""
    final_renderer_spec: str = ""
    bindable: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_artifact_policy(self) -> DiagramArtifact:
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt artifacts must use disclosure_policy='clean'")
        if self.aspect_ratio is None and self.width_px and self.height_px:
            self.aspect_ratio = round(self.width_px / self.height_px, 4)
        if self.bindable:
            if self.status != DiagramRunStatus.OK:
                raise ValueError("bindable artifacts must have status='ok'")
            if not self.image_path:
                raise ValueError("bindable artifacts must have image_path")
            if not self.artifact_hash:
                raise ValueError("bindable artifacts must have a hash")
        return self


class DiagramArtifactsManifest(DiagramModel):
    schema_version: Literal["diagram-artifacts/v1"] = "diagram-artifacts/v1"
    assignment_id: NonEmptyStr
    source_jobs: NonEmptyStr
    artifacts: dict[str, DiagramArtifact] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_artifact_keys(self) -> DiagramArtifactsManifest:
        for diagram_ref, artifact in self.artifacts.items():
            if diagram_ref != artifact.slot_id:
                raise ValueError(
                    f"artifact key '{diagram_ref}' must match artifact.slot_id '{artifact.slot_id}'"
                )
        return self


class ResolvedDiagramImage(DiagramModel):
    """Resolved YAML image object consumed by math-assignment-latex templates."""

    image_path: NonEmptyStr
    diagram_ref: NonEmptyStr
    diagram_job_id: NonEmptyStr = Field(validation_alias=AliasChoices("diagram_job_id", "job_id"))
    width: str = ""
    caption: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    artifact_hash: str = Field(default="", validation_alias=AliasChoices("artifact_hash", "hash"))

    @model_validator(mode="after")
    def enforce_resolved_policy(self) -> ResolvedDiagramImage:
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt resolved images must use disclosure_policy='clean'")
        return self


class DiagramGateCheck(DiagramModel):
    name: NonEmptyStr
    status: Literal["pass", "warn", "block"]
    message: str = ""
    refs: list[str] = Field(default_factory=list)


class DiagramGateReport(DiagramModel):
    schema_version: Literal["diagram-gate-report/v1"] = "diagram-gate-report/v1"
    assignment_id: NonEmptyStr
    status: Literal["pass", "warn", "block"]
    checks: list[DiagramGateCheck] = Field(default_factory=list)

