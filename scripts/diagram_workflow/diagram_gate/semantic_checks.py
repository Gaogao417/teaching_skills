from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from diagram_contracts import (
    AssignmentBlockView,
    AssignmentPlanDiagramView,
    DiagramGateCheck,
    DiagramKind,
    DiagramJobsManifest,
    DiagramSlot,
    DiagramVariant,
    RendererBindingManifest,
)


COORDINATE_STEM_SIGNALS = (
    "坐标",
    "坐标系",
    "横坐标",
    "纵坐标",
    "x轴",
    "y轴",
    "x 轴",
    "y 轴",
    "函数",
    "图像",
    "解析式",
    "抛物线",
    "反比例",
    "一次函数",
    "二次函数",
    "象限",
    "原点",
)

SYNTHETIC_STEM_SIGNALS = (
    "△",
    "三角形",
    "平行",
    "∥",
    r"\parallel",
    "相似",
    "共线",
    "线段",
    "边",
    "角平分线",
    "中点",
)


@dataclass(frozen=True)
class _SlotContext:
    slot: DiagramSlot
    block: AssignmentBlockView

    @property
    def stem(self) -> str:
        slot_context = self.slot.problem_context
        if slot_context.stem_latex:
            return slot_context.stem_latex
        if slot_context.source_problem_text:
            return slot_context.source_problem_text
        return self.block.stem_latex or self.block.stem or ""


def _plan_view(plan_data: AssignmentPlanDiagramView | dict[str, object]) -> AssignmentPlanDiagramView:
    if isinstance(plan_data, AssignmentPlanDiagramView):
        return plan_data
    return AssignmentPlanDiagramView.model_validate(plan_data)


def _slot_contexts(plan_data: AssignmentPlanDiagramView | dict[str, object]) -> dict[str, _SlotContext]:
    """Return plan slots keyed by slot_id, preserving their parent problem stem."""
    plan = _plan_view(plan_data)
    contexts: dict[str, _SlotContext] = {}
    for section in plan.sections:
        for block in section.blocks:
            if block.diagram_slot is not None:
                contexts[block.diagram_slot.slot_id] = _SlotContext(block.diagram_slot, block)
            for step in block.steps:
                if step.diagram_slot is not None:
                    contexts[step.diagram_slot.slot_id] = _SlotContext(step.diagram_slot, block)
            answer_space = block.answer_space
            if answer_space is None:
                continue
            if answer_space.diagram_slot is not None:
                contexts[answer_space.diagram_slot.slot_id] = _SlotContext(answer_space.diagram_slot, block)
            for part in answer_space.parts:
                if part.diagram_slot is not None:
                    contexts[part.diagram_slot.slot_id] = _SlotContext(part.diagram_slot, block)
    return contexts


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _point_fixed_coordinate(scene_code: str, escaped_point: str) -> re.Match[str] | None:
    """Match both infix and full-form Wolfram coordinate assignments."""
    return re.search(
        rf"(?:(?<![A-Za-z0-9_`]){escaped_point}\s*(?:==|->)|"
        rf"Equal\s*\[\s*{escaped_point}\s*,)\s*\{{\s*-?\d",
        scene_code,
    )


def _point_constructor_constraint(scene_code: str, escaped_point: str) -> re.Match[str] | None:
    """Recognize native point constructors, including transformed-image points."""
    constructors = (
        r"Midpoint|TriangleCenter|RegionNearest|RegionCentroid|RegionIntersection|"
        r"RotationTransform|TranslationTransform|ScalingTransform|ReflectionTransform"
    )
    return re.search(
        rf"(?:(?<![A-Za-z0-9_`]){escaped_point}\s*==|"
        rf"Equal\s*\[\s*{escaped_point}\s*,)\s*(?:{constructors})\s*\[",
        scene_code,
    )


def _point_relation_count(scene_code: str, escaped_point: str) -> int:
    """Count native geometric relations that involve a point."""
    return len(re.findall(
        rf"(?:GeometricAssertion|EuclideanDistance|PlanarAngle|Area|RegionDistance)\s*"
        rf"\[[^\]]*\b{escaped_point}\b",
        scene_code,
    ))


def _resolve_artifact_path(artifact_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else artifact_dir / path


def _slot_fingerprint(slot: DiagramSlot) -> str:
    data = slot.model_dump(mode="json", by_alias=True, exclude_none=True)
    focused = {
        "engine": data.get("engine"),
        "diagram_kind": data.get("diagram_kind"),
        "semantic_constraints": data.get("semantic_constraints") or {},
        "analytic_requirements": data.get("analytic_requirements") or {},
        "renderer_spec": ((data.get("engine_options") or {}).get("renderer_spec") if isinstance(data.get("engine_options"), dict) else {}),
        "scene_payload": ((data.get("engine_options") or {}).get("scene_payload") if isinstance(data.get("engine_options"), dict) else {}),
        "spatial_spec": ((data.get("engine_options") or {}).get("spatial_spec") if isinstance(data.get("engine_options"), dict) else {}),
    }
    return _canonical_hash(focused)


def _spec_fingerprint(artifact_dir: Path, spec_path: str) -> str:
    data = _read_json(_resolve_artifact_path(artifact_dir, spec_path))
    return _canonical_hash(data) if data is not None else ""


def _tikz_fingerprint(artifact_dir: Path, tikz_fragment: str, tikz_path: str) -> str:
    if tikz_fragment:
        return _canonical_hash(tikz_fragment)
    if tikz_path:
        text = _read_text(_resolve_artifact_path(artifact_dir, tikz_path))
        if text:
            return _canonical_hash(text)
    return ""


def _duplicate_check(
    name: str,
    fingerprints: dict[str, str],
    jobs: DiagramJobsManifest,
) -> list[DiagramGateCheck]:
    grouped: dict[str, list[str]] = {}
    eligible_jobs = {
        job.slot_id: job
        for job in jobs.jobs
        if job.required
        and job.variant == DiagramVariant.PROMPT
        and not job.reuse_geometry_from
    }
    for slot_id, fingerprint in fingerprints.items():
        if not fingerprint or slot_id not in eligible_jobs:
            continue
        grouped.setdefault(fingerprint, []).append(slot_id)

    checks: list[DiagramGateCheck] = []
    for slot_ids in grouped.values():
        if len(slot_ids) < 2:
            continue
        checks.append(DiagramGateCheck(
            name=name,
            status="block",
            message=(
                "Required prompt diagram jobs have identical geometry fingerprints "
                "without explicit reuse_geometry_from"
            ),
            refs=sorted(slot_ids),
        ))
    return checks


def _has_coordinate_signal(stem: str) -> bool:
    compact = stem.replace(" ", "")
    if any(signal in stem or signal in compact for signal in COORDINATE_STEM_SIGNALS):
        return True
    return bool(re.search(r"[A-Z]\s*\(\s*-?\d", stem) or re.search(r"\by\s*=", stem) or re.search(r"\bx\s*=", stem))


def _has_synthetic_signal(stem: str) -> bool:
    return any(signal in stem for signal in SYNTHETIC_STEM_SIGNALS) or bool(
        re.search(r"[A-Z]{2}\s*[:=]", stem)
    )


def _flatten_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(f"{k} {_flatten_text(v)}" for k, v in value.items())
    if isinstance(value, Iterable):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _evidence_for_slot(
    slot: DiagramSlot,
    request_data: object | None,
    spec_data: object | None,
) -> str:
    return _flatten_text([
        slot.model_dump(mode="json", by_alias=True, exclude_none=True),
        request_data,
        spec_data,
    ])


def _segment_tokens(stem: str) -> set[str]:
    return set(re.findall(r"\b[A-Z]{2}\b", stem))


def _point_tokens(stem: str) -> set[str]:
    return {token for token in re.findall(r"\b[A-Z]\b", stem) if token not in {"O"}}


def _number_tokens(stem: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])-?\d+(?:\.\d+)?", stem))


def _semantic_missing_tokens(stem: str, evidence: str) -> list[str]:
    missing: list[str] = []
    normalized_evidence = evidence.replace(" ", "")
    for token in sorted(_point_tokens(stem) | _segment_tokens(stem)):
        if token not in normalized_evidence:
            missing.append(token)
    if ("∥" in stem or r"\parallel" in stem or "平行" in stem) and not any(
        token in evidence for token in ("∥", r"\parallel", "parallel", "平行")
    ):
        missing.append("parallel")
    for number in sorted(_number_tokens(stem), key=lambda item: (len(item), item)):
        if number not in normalized_evidence:
            missing.append(number)
    return missing


def _request_for_job(artifact_dir: Path, request_path: str) -> object | None:
    if not request_path:
        return None
    return _read_json(_resolve_artifact_path(artifact_dir, request_path))


def _spec_for_binding(artifact_dir: Path, spec_path: str) -> object | None:
    if not spec_path:
        return None
    return _read_json(_resolve_artifact_path(artifact_dir, spec_path))


def _check_duplicate_prompt_geometry(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    contexts = _slot_contexts(plan_data)
    checks: list[DiagramGateCheck] = []

    slot_fingerprints = {
        slot_id: _slot_fingerprint(context.slot)
        for slot_id, context in contexts.items()
    }
    checks.extend(_duplicate_check("duplicate_prompt_geometry_slot", slot_fingerprints, jobs))

    spec_fingerprints: dict[str, str] = {}
    tikz_fingerprints: dict[str, str] = {}
    for job in jobs.jobs:
        art = artifacts.bindings.get(job.diagram_ref)
        if not art:
            continue
        if art.final_renderer_spec:
            spec_fingerprints[job.slot_id] = _spec_fingerprint(artifact_dir, art.final_renderer_spec)
        tikz_path = art.tikz_fragment_path or art.tikz_source_path
        tikz_fingerprints[job.slot_id] = _tikz_fingerprint(artifact_dir, art.tikz_fragment, tikz_path)
    checks.extend(_duplicate_check("duplicate_prompt_geometry_spec", spec_fingerprints, jobs))
    checks.extend(_duplicate_check("duplicate_prompt_geometry_tikz", tikz_fingerprints, jobs))
    return checks


def _check_coordinate_geometry_scope(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
) -> list[DiagramGateCheck]:
    contexts = _slot_contexts(plan_data)
    checks: list[DiagramGateCheck] = []
    for job in jobs.jobs:
        if job.diagram_kind != DiagramKind.COORDINATE_GEOMETRY:
            continue
        context = contexts.get(job.slot_id)
        if context is None:
            continue
        stem = context.stem
        if _has_synthetic_signal(stem) and not _has_coordinate_signal(stem):
            checks.append(DiagramGateCheck(
                name="coordinate_geometry_scope",
                status="block" if job.required else "warn",
                message=(
                    "Ordinary Euclidean geometry was routed as coordinate_geometry; "
                    "use geometric_scene + synthetic_geometry unless the stem is a coordinate-plane/function task"
                ),
                refs=[job.slot_id],
            ))
    return checks


def _check_slot_semantic_coverage(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    contexts = _slot_contexts(plan_data)
    checks: list[DiagramGateCheck] = []
    for job in jobs.jobs:
        if not job.required or job.variant != DiagramVariant.PROMPT:
            continue
        context = contexts.get(job.slot_id)
        if context is None:
            continue
        stem = context.stem
        if not stem or not _has_synthetic_signal(stem):
            continue
        art = artifacts.bindings.get(job.diagram_ref)
        request_data = _request_for_job(artifact_dir, job.request_path)
        spec_data = _spec_for_binding(artifact_dir, art.final_renderer_spec) if art else None
        evidence = _evidence_for_slot(context.slot, request_data, spec_data)
        missing = _semantic_missing_tokens(stem, evidence)
        if missing:
            checks.append(DiagramGateCheck(
                name="slot_semantic_coverage",
                status="block",
                message=(
                    "Diagram slot/request/spec does not cover required stem tokens: "
                    + ", ".join(missing[:12])
                ),
                refs=[job.slot_id],
            ))
    return checks


def _check_solution_auxiliary_geometry(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Require Wolfram construction constraints for solution-only points."""
    checks: list[DiagramGateCheck] = []
    job_by_id = {job.job_id: job for job in jobs.jobs}
    for job in jobs.jobs:
        if job.variant != DiagramVariant.SOLUTION or not job.reuse_geometry_from:
            continue
        base_job = job_by_id.get(job.reuse_geometry_from)
        solution_art = artifacts.bindings.get(job.diagram_ref)
        base_art = artifacts.bindings.get(base_job.diagram_ref) if base_job else None
        if not solution_art or not base_art:
            continue
        solution_spec = _spec_for_binding(artifact_dir, solution_art.final_renderer_spec)
        base_spec = _spec_for_binding(artifact_dir, base_art.final_renderer_spec)
        if not isinstance(solution_spec, dict) or not isinstance(base_spec, dict):
            continue
        solution_points = solution_spec.get("points")
        base_points = base_spec.get("points")
        if not isinstance(solution_points, dict) or not isinstance(base_points, dict):
            continue
        auxiliary_points = sorted(set(solution_points) - set(base_points))
        if not auxiliary_points:
            continue

        scene_path = artifact_dir / "build" / "diagram" / "jobs" / job.job_id / "scene_payload.json"
        scene_payload = _read_json(scene_path)
        scene_code = str(scene_payload.get("scene_code") or "") if isinstance(scene_payload, dict) else ""
        if not scene_code:
            checks.append(DiagramGateCheck(
                name="solution_auxiliary_geometric_scene",
                status="block",
                message="Solution-only points require a GeometricScene scene_payload",
                refs=[job.slot_id, *auxiliary_points],
            ))
            continue

        for point in auxiliary_points:
            escaped = re.escape(point)
            fixed_coordinate = _point_fixed_coordinate(scene_code, escaped)
            constructor_constraint = _point_constructor_constraint(scene_code, escaped)
            relation_count = _point_relation_count(scene_code, escaped)
            structural_constraint = re.search(
                rf"Element\s*\[\s*{escaped}\s*,|"
                rf"(?:(?<![A-Za-z0-9_`]){escaped}\s*==|Equal\s*\[\s*{escaped}\s*,)\s*"
                rf"(?:Midpoint|TriangleCenter|RegionNearest|RegionCentroid|RegionIntersection|"
                rf"RotationTransform|TranslationTransform|ScalingTransform|ReflectionTransform)\s*\[",
                scene_code,
            ) or (relation_count >= 2)
            incidence_count = len(re.findall(rf"Element\s*\[\s*{escaped}\s*,", scene_code))
            relation_constraint = relation_count > 0
            if fixed_coordinate:
                checks.append(DiagramGateCheck(
                    name="solution_auxiliary_fixed_coordinates",
                    status="block",
                    message=(
                        f"Solution-only point {point} is fixed by coordinates; "
                        "derive it with Element/GeometricScene construction constraints"
                    ),
                    refs=[job.slot_id, point],
                ))
            elif not structural_constraint:
                checks.append(DiagramGateCheck(
                    name="solution_auxiliary_missing_constraint",
                    status="block",
                    message=(
                        f"Solution-only point {point} has no recognized GeometricScene "
                        "incidence or construction constraint"
                    ),
                    refs=[job.slot_id, point],
                ))
            elif not constructor_constraint and incidence_count < 2 and not relation_constraint:
                checks.append(DiagramGateCheck(
                    name="solution_auxiliary_underconstrained",
                    status="block",
                    message=(
                        f"Solution-only point {point} needs a second independent GeometricScene "
                        "relation such as parallel, perpendicular, another incidence, or a metric constraint"
                    ),
                    refs=[job.slot_id, point],
                ))
    return checks


def _check_scene_point_roles(
    jobs: DiagramJobsManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Prevent prompt or solution constructed points from becoming fixed coordinates."""
    checks: list[DiagramGateCheck] = []
    for job in jobs.jobs:
        scene_path = artifact_dir / "build" / "diagram" / "jobs" / job.job_id / "scene_payload.json"
        scene_payload = _read_json(scene_path)
        if not isinstance(scene_payload, dict):
            continue
        scene_code = str(scene_payload.get("scene_code") or "")
        point_roles = scene_payload.get("point_roles")
        if not scene_code or not isinstance(point_roles, dict):
            continue
        for role in ("constructed", "auxiliary"):
            role_points = point_roles.get(role)
            if not isinstance(role_points, list):
                continue
            for raw_point in role_points:
                point = str(raw_point).strip()
                if not point:
                    continue
                escaped = re.escape(point)
                fixed_coordinate = _point_fixed_coordinate(scene_code, escaped)
                constructor_constraint = _point_constructor_constraint(scene_code, escaped)
                incidence_count = len(re.findall(rf"Element\s*\[\s*{escaped}\s*,", scene_code))
                relation_count = _point_relation_count(scene_code, escaped)
                relation_constraint = relation_count > 0
                if fixed_coordinate:
                    checks.append(DiagramGateCheck(
                        name="constructed_point_fixed_coordinates",
                        status="block",
                        message=(
                            f"{role} point {point} is fixed by coordinates; only point_roles.anchors "
                            "may be coordinate anchors"
                        ),
                        refs=[job.slot_id, point],
                    ))
                elif not constructor_constraint and incidence_count == 0 and relation_count < 2:
                    checks.append(DiagramGateCheck(
                        name="constructed_point_missing_constraint",
                        status="block",
                        message=f"{role} point {point} has no native GeometricScene construction constraint",
                        refs=[job.slot_id, point],
                    ))
                elif not constructor_constraint and incidence_count < 2 and not relation_constraint:
                    checks.append(DiagramGateCheck(
                        name="constructed_point_underconstrained",
                        status="block",
                        message=f"{role} point {point} needs a second independent GeometricScene constraint",
                        refs=[job.slot_id, point],
                    ))
    return checks


def check_semantic_diagram_policy(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Policy checks for duplicate geometry and route/semantic mismatches."""
    checks: list[DiagramGateCheck] = []
    checks.extend(_check_duplicate_prompt_geometry(plan_data, jobs, artifacts, artifact_dir))
    checks.extend(_check_coordinate_geometry_scope(plan_data, jobs))
    checks.extend(_check_slot_semantic_coverage(plan_data, jobs, artifacts, artifact_dir))
    checks.extend(_check_scene_point_roles(jobs, artifact_dir))
    checks.extend(_check_solution_auxiliary_geometry(jobs, artifacts, artifact_dir))
    return checks
