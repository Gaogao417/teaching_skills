#!/usr/bin/env python3
"""Check diagram gate before rendering.

Validates that all required diagrams are present, policies are correct,
and artifacts are consistent with the plan. Produces a DiagramGateReport
with pass/warn/block status.

Usage:
    python3 scripts/diagram_workflow/check_diagram_gate.py \
        --plan <assignment.plan.yaml> \
        --jobs <diagram_jobs.json> \
        --artifacts <diagram_artifacts.json> \
        [--resolved <assignment.resolved.yaml>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: PyYAML is required") from exc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    AssignmentPlanDiagramView,
    DiagramArtifactsManifest,
    DiagramDisplayProfile,
    DiagramGateCheck,
    DiagramGateReport,
    DiagramKind,
    DiagramJobsManifest,
    DisclosurePolicy,
    DiagramVariant,
)


_ABSOLUTE_DIMENSION_RE = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?|\.\d+)\s*(?P<unit>mm|cm|pt|in)\s*$"
)
_UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "pt": 25.4 / 72.27,
    "in": 25.4,
}


# ---------------------------------------------------------------------------
# Gate checks
# ---------------------------------------------------------------------------

def _check_required_bindable(
    jobs: DiagramJobsManifest,
    artifacts: DiagramArtifactsManifest,
) -> list[DiagramGateCheck]:
    """Check 1: All required slots have bindable artifacts."""
    checks: list[DiagramGateCheck] = []
    for job in jobs.jobs:
        if not job.required:
            continue
        art = artifacts.artifacts.get(job.diagram_ref)
        if not art or not art.bindable:
            checks.append(DiagramGateCheck(
                name="required_bindable",
                status="block",
                message=f"Required slot '{job.slot_id}' has no bindable artifact",
                refs=[job.slot_id],
            ))
    return checks


def _check_image_exists(
    jobs: DiagramJobsManifest,
    artifacts: DiagramArtifactsManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Check 2: All artifact image_path files exist and are non-empty."""
    checks: list[DiagramGateCheck] = []
    for art in artifacts.artifacts.values():
        if not art.image_path:
            continue
        image_path = Path(art.image_path)
        full_path = image_path if image_path.is_absolute() else artifact_dir / image_path
        if not full_path.exists():
            checks.append(DiagramGateCheck(
                name="image_exists",
                status="warn",
                message=f"Image file missing: {art.image_path}",
                refs=[art.slot_id],
            ))
        elif full_path.stat().st_size == 0:
            checks.append(DiagramGateCheck(
                name="image_exists",
                status="block",
                message=f"Image file is empty: {art.image_path}",
                refs=[art.slot_id],
            ))
    return checks


def _check_content_hash(
    jobs: DiagramJobsManifest,
    plan_data: AssignmentPlanDiagramView | dict[str, object],
) -> list[DiagramGateCheck]:
    """Check 3: Job content_hash matches current plan YAML content.

    This is a best-effort check: if the plan YAML has been regenerated
    since the jobs were collected, the hashes will differ.
    """
    checks: list[DiagramGateCheck] = []
    # Re-scan slots from plan to compute current hashes
    import hashlib
    plan_view = (
        plan_data
        if isinstance(plan_data, AssignmentPlanDiagramView)
        else AssignmentPlanDiagramView.model_validate(plan_data)
    )
    current_hashes: dict[str, str] = {}
    for section in plan_view.sections:
        for block in section.blocks:
            slots = []
            if block.diagram_slot is not None:
                slots.append(block.diagram_slot)
            if block.answer_space is not None:
                if block.answer_space.diagram_slot is not None:
                    slots.append(block.answer_space.diagram_slot)
                slots.extend(
                    part.diagram_slot
                    for part in block.answer_space.parts
                    if part.diagram_slot is not None
                )
            for slot in slots:
                slot_data = slot.model_dump(mode="json", by_alias=True)
                canonical = json.dumps(slot_data, sort_keys=True, ensure_ascii=False)
                current_hashes[slot.slot_id] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    for job in jobs.jobs:
        current = current_hashes.get(job.slot_id)
        if current and job.content_hash and current != job.content_hash:
            checks.append(DiagramGateCheck(
                name="content_hash_stale",
                status="warn",
                message=f"Job '{job.job_id}' content_hash is stale (plan YAML has changed)",
                refs=[job.slot_id],
            ))
    return checks


def _extract_slot_data(block: dict) -> list[dict]:
    """Extract all diagram_slot dicts from a block."""
    found = []
    if isinstance(block.get("diagram_slot"), dict):
        found.append(block["diagram_slot"])
    answer_space = block.get("answer_space")
    if isinstance(answer_space, dict):
        if isinstance(answer_space.get("diagram_slot"), dict):
            found.append(answer_space["diagram_slot"])
        for part in answer_space.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("diagram_slot"), dict):
                found.append(part["diagram_slot"])
    return found


def _check_prompt_clean(
    artifacts: DiagramArtifactsManifest,
) -> list[DiagramGateCheck]:
    """Check 4: All prompt artifacts have clean disclosure_policy."""
    checks: list[DiagramGateCheck] = []
    for art in artifacts.artifacts.values():
        if art.variant == DiagramVariant.PROMPT and art.disclosure_policy != DisclosurePolicy.CLEAN:
            checks.append(DiagramGateCheck(
                name="prompt_clean_policy",
                status="block",
                message=f"Prompt artifact '{art.slot_id}' has disclosure_policy='{art.disclosure_policy.value}', expected 'clean'",
                refs=[art.slot_id],
            ))
    return checks


def _check_student_no_solution(
    resolved_path: Path | None,
) -> list[DiagramGateCheck]:
    """Check 5: Student resolved YAML does not reference solution/annotated images."""
    checks: list[DiagramGateCheck] = []
    if resolved_path is None or not resolved_path.exists():
        return checks

    data = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return checks

    # Check meta.version for "student" indication
    meta = data.get("meta")
    is_student = False
    if isinstance(meta, dict):
        version = str(meta.get("version", "")).lower()
        is_student = "student" in version

    if not is_student:
        return checks  # Only applies to student versions

    # Walk all diagram objects in resolved YAML
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            for obj in _collect_resolved_diagrams(block):
                variant = obj.get("variant", "")
                policy = obj.get("disclosure_policy", "")
                if variant == "solution":
                    checks.append(DiagramGateCheck(
                        name="student_no_solution",
                        status="block",
                        message=f"Student resolved YAML references variant='solution' diagram",
                        refs=[obj.get("diagram_ref", "")],
                    ))
                if policy == "annotated":
                    checks.append(DiagramGateCheck(
                        name="student_no_annotated",
                        status="block",
                        message=f"Student resolved YAML references disclosure_policy='annotated' diagram",
                        refs=[obj.get("diagram_ref", "")],
                    ))
    return checks


def _collect_resolved_diagrams(block: dict) -> list[dict]:
    """Collect all resolved diagram objects from a block."""
    found = []
    for key in ("diagram_col", "prompt_diagram"):
        obj = block.get(key)
        if isinstance(obj, dict) and obj.get("image_path"):
            found.append(obj)
    answer_space = block.get("answer_space")
    if isinstance(answer_space, dict):
        for key in ("diagram_col",):
            obj = answer_space.get(key)
            if isinstance(obj, dict) and obj.get("image_path"):
                found.append(obj)
        for part in answer_space.get("parts") or []:
            if not isinstance(part, dict):
                continue
            for key in ("diagram_col",):
                obj = part.get(key)
                if isinstance(obj, dict) and obj.get("image_path"):
                    found.append(obj)
    return found


def _check_image_path_accessible(
    artifacts: DiagramArtifactsManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Check 6: image_path is accessible relative to expected .tex location."""
    checks: list[DiagramGateCheck] = []
    # The .tex file will be at <artifact_dir>/<name>.tex
    # image_path should be relative and accessible from there
    for art in artifacts.artifacts.values():
        if not art.image_path:
            continue
        p = Path(art.image_path)
        if p.is_absolute():
            if not p.exists():
                checks.append(DiagramGateCheck(
                    name="image_path_accessible",
                    status="block",
                    message=f"Absolute image_path does not exist: {art.image_path}",
                    refs=[art.slot_id],
                ))
        else:
            full = artifact_dir / p
            if not full.exists():
                checks.append(DiagramGateCheck(
                    name="image_path_accessible",
                    status="warn",
                    message=f"Relative image_path not found from artifact dir: {art.image_path}",
                    refs=[art.slot_id],
                ))
    return checks


def _check_diagram_ref_consistency(
    jobs: DiagramJobsManifest,
    artifacts: DiagramArtifactsManifest,
) -> list[DiagramGateCheck]:
    """Check 7: All diagram_ref in artifacts match slots in jobs."""
    checks: list[DiagramGateCheck] = []
    job_refs = {job.diagram_ref for job in jobs.jobs}
    for diagram_ref in artifacts.artifacts:
        if diagram_ref not in job_refs:
            checks.append(DiagramGateCheck(
                name="diagram_ref_consistency",
                status="warn",
                message=f"Artifact with ref '{diagram_ref}' has no matching job slot",
                refs=[diagram_ref],
            ))
    return checks


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _check_analytic_renderer_specs(
    jobs: DiagramJobsManifest,
    artifacts: DiagramArtifactsManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Check 8: coordinate/function specs contain renderable analytic payload."""
    checks: list[DiagramGateCheck] = []
    analytic_kinds = {DiagramKind.COORDINATE_GEOMETRY, DiagramKind.FUNCTION_GRAPH}
    for job in jobs.jobs:
        if job.diagram_kind not in analytic_kinds:
            continue
        art = artifacts.artifacts.get(job.diagram_ref)
        if not art or not art.final_renderer_spec:
            checks.append(DiagramGateCheck(
                name="analytic_renderer_spec",
                status="block" if job.required else "warn",
                message=f"Analytic job '{job.job_id}' has no final_renderer_spec",
                refs=[job.slot_id],
            ))
            continue

        spec_path = Path(art.final_renderer_spec)
        if not spec_path.is_absolute():
            spec_path = artifact_dir / spec_path
        spec = _read_json(spec_path)
        if spec is None:
            checks.append(DiagramGateCheck(
                name="analytic_renderer_spec",
                status="block" if job.required else "warn",
                message=f"Analytic renderer spec is missing or invalid JSON: {art.final_renderer_spec}",
                refs=[job.slot_id],
            ))
            continue

        errors = _analytic_spec_errors(spec)
        if errors:
            checks.append(DiagramGateCheck(
                name="analytic_renderer_spec",
                status="block" if job.required else "warn",
                message="; ".join(errors),
                refs=[job.slot_id],
            ))
    return checks


def _analytic_spec_errors(spec: dict[str, object]) -> list[str]:
    errors: list[str] = []
    viewport = spec.get("viewport")
    if not isinstance(viewport, dict):
        errors.append("analytic spec requires viewport")
    else:
        for low, high in (("x_min", "x_max"), ("y_min", "y_max")):
            if low not in viewport or high not in viewport:
                errors.append(f"viewport requires {low} and {high}")
                continue
            try:
                if float(viewport[low]) >= float(viewport[high]):
                    errors.append(f"viewport {low} must be < {high}")
            except (TypeError, ValueError):
                errors.append(f"viewport {low}/{high} must be numeric")

    has_payload = bool(spec.get("points") or spec.get("objects") or spec.get("functions") or spec.get("curves") or spec.get("samples"))
    if not has_payload:
        errors.append("analytic spec requires points, objects, functions, curves, or samples")

    samples = spec.get("samples") if isinstance(spec.get("samples"), dict) else {}
    for func in spec.get("functions") or []:
        if not isinstance(func, dict):
            errors.append("function entry must be an object")
            continue
        fid = str(func.get("id", ""))
        if not fid:
            errors.append("function requires id")
        elif not samples.get(fid):
            errors.append(f"function '{fid}' has no samples")

    for index, obj in enumerate(spec.get("objects") or []):
        if not isinstance(obj, dict):
            errors.append(f"objects[{index}] must be an object")
            continue
        kind = obj.get("type")
        if kind == "point" and not {"x", "y"} <= set(obj):
            errors.append(f"objects[{index}] point requires x and y")
        elif kind == "line" and not (obj.get("equation") or {"slope", "intercept"} <= set(obj)):
            errors.append(f"objects[{index}] line requires equation or slope/intercept")
        elif kind == "circle":
            if "radius" not in obj:
                errors.append(f"objects[{index}] circle requires radius")
            else:
                try:
                    if float(obj["radius"]) <= 0:
                        errors.append(f"objects[{index}] circle radius must be positive")
                except (TypeError, ValueError):
                    errors.append(f"objects[{index}] circle radius must be numeric")
        elif kind == "polyline" and len(obj.get("points") or []) < 2:
            errors.append(f"objects[{index}] polyline requires at least two points")
        elif kind == "polygon" and len(obj.get("points") or []) < 3:
            errors.append(f"objects[{index}] polygon requires at least three points")
    return errors


def _dimension_to_mm(value: str) -> float | None:
    match = _ABSOLUTE_DIMENSION_RE.match(value)
    if not match:
        return None
    return float(match.group("value")) * _UNIT_TO_MM[match.group("unit")]


def _iter_slots(plan_data: AssignmentPlanDiagramView | dict[str, object]):
    plan = (
        plan_data
        if isinstance(plan_data, AssignmentPlanDiagramView)
        else AssignmentPlanDiagramView.model_validate(plan_data)
    )
    for section in plan.sections:
        for block in section.blocks:
            if block.diagram_slot is not None:
                yield block.diagram_slot
            for step in block.steps:
                if step.diagram_slot is not None:
                    yield step.diagram_slot
            answer_space = block.answer_space
            if answer_space is None:
                continue
            if answer_space.diagram_slot is not None:
                yield answer_space.diagram_slot
            for part in answer_space.parts:
                if part.diagram_slot is not None:
                    yield part.diagram_slot


def _check_slot_layout_profiles(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
) -> list[DiagramGateCheck]:
    checks: list[DiagramGateCheck] = []
    assumed_text_width_mm = 160.0
    min_left_width_mm = 80.0

    for slot in _iter_slots(plan_data):
        profile = slot.resolved_render_profile()
        width = slot.width_hint or profile.width
        width_mm = _dimension_to_mm(width)
        display_profile = profile.display_profile

        if display_profile == DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR and width_mm is not None:
            if width_mm < 55:
                checks.append(DiagramGateCheck(
                    name="diagram_sidecar_width",
                    status="block",
                    message=f"Sidecar diagram '{slot.slot_id}' is {width}; use at least 55mm or center placement",
                    refs=[slot.slot_id],
                ))
            left_width = assumed_text_width_mm - width_mm - 6
            if left_width < min_left_width_mm:
                checks.append(DiagramGateCheck(
                    name="diagram_sidecar_left_width",
                    status="warn",
                    message=f"Sidecar diagram '{slot.slot_id}' leaves about {left_width:.1f}mm for text",
                    refs=[slot.slot_id],
                ))

        if display_profile == DiagramDisplayProfile.WORKSHEET_GEOMETRY_CENTER and width_mm is not None and width_mm < 68:
            checks.append(DiagramGateCheck(
                name="diagram_center_width",
                status="block",
                message=f"Centered diagram '{slot.slot_id}' is {width}; use at least 68mm",
                refs=[slot.slot_id],
            ))
    return checks


def _artifact_path(artifact_dir: Path, job_id: str, path_value: str) -> Path | None:
    if not path_value:
        return None
    raw = Path(path_value)
    candidates = [raw] if raw.is_absolute() else [
        artifact_dir / raw,
        artifact_dir / "build" / "diagram" / "jobs" / job_id / raw,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1] if candidates else None


def _svg_text_tags(svg_text: str, label_kind: str) -> list[str]:
    tags = re.findall(r"<text\b[^>]*>", svg_text)
    return [tag for tag in tags if f'data-label-kind="{label_kind}"' in tag]


def _font_size_from_tag(tag: str) -> float | None:
    match = re.search(r'font-size="(?P<size>\d+(?:\.\d+)?)"', tag)
    return float(match.group("size")) if match else None


def _check_svg_readability(
    jobs: DiagramJobsManifest,
    artifacts: DiagramArtifactsManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    checks: list[DiagramGateCheck] = []
    job_by_ref = {job.diagram_ref: job for job in jobs.jobs}
    for diagram_ref, art in artifacts.artifacts.items():
        if not art.preview_svg:
            continue
        svg_path = _artifact_path(artifact_dir, art.job_id, art.preview_svg)
        if svg_path is None or not svg_path.exists():
            continue
        try:
            svg_text = svg_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        font_weights = re.findall(r'font-weight="([^"]+)"', svg_text)
        bad_weights = [w for w in font_weights if w.lower() not in {"normal", "400"}]
        if bad_weights:
            checks.append(DiagramGateCheck(
                name="diagram_svg_font_weight",
                status="block",
                message=f"SVG for '{diagram_ref}' uses bold/heavy font-weight values: {sorted(set(bad_weights))}",
                refs=[diagram_ref],
            ))

        if "Arial" in svg_text and bad_weights:
            checks.append(DiagramGateCheck(
                name="diagram_svg_arial_bold",
                status="block",
                message=f"SVG for '{diagram_ref}' still uses Arial with bold/heavy point labels",
                refs=[diagram_ref],
            ))

        point_tags = _svg_text_tags(svg_text, "point")
        point_sizes = [size for tag in point_tags if (size := _font_size_from_tag(tag)) is not None]
        if point_sizes and min(point_sizes) < 44:
            checks.append(DiagramGateCheck(
                name="diagram_svg_point_label_size",
                status="block",
                message=f"Point labels for '{diagram_ref}' are too small: min {min(point_sizes):g}px, expected at least 44px",
                refs=[diagram_ref],
            ))

        job = job_by_ref.get(diagram_ref)
        if job and re.search(r">\s*[A-Z]{1,3}\s*=\s*[^<]*\d[^<]*<", svg_text):
            checks.append(DiagramGateCheck(
                name="diagram_svg_condition_label_style",
                status="block",
                message=f"Length condition labels for '{diagram_ref}' should be value-only, e.g. 7 instead of AB=7",
                refs=[job.slot_id],
            ))
    return checks


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------

def run_gate(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
    artifacts: DiagramArtifactsManifest,
    artifact_dir: Path,
    resolved_path: Path | None,
) -> DiagramGateReport:
    """Run all gate checks and produce a DiagramGateReport."""
    all_checks: list[DiagramGateCheck] = []

    all_checks.extend(_check_required_bindable(jobs, artifacts))
    all_checks.extend(_check_image_exists(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_content_hash(jobs, plan_data))
    all_checks.extend(_check_prompt_clean(artifacts))
    all_checks.extend(_check_student_no_solution(resolved_path))
    all_checks.extend(_check_image_path_accessible(artifacts, artifact_dir))
    all_checks.extend(_check_diagram_ref_consistency(jobs, artifacts))
    all_checks.extend(_check_slot_layout_profiles(plan_data))
    all_checks.extend(_check_svg_readability(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_analytic_renderer_specs(jobs, artifacts, artifact_dir))

    # Determine overall status
    statuses = [c.status for c in all_checks]
    if "block" in statuses:
        overall = "block"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "pass"

    return DiagramGateReport(
        assignment_id=jobs.assignment_id,
        status=overall,
        checks=all_checks,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check diagram gate before rendering"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="Path to assignment.plan.yaml",
    )
    parser.add_argument(
        "--jobs",
        type=Path,
        required=True,
        help="Path to diagram_jobs.json",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        required=True,
        help="Path to diagram_artifacts.json",
    )
    parser.add_argument(
        "--resolved",
        type=Path,
        help="Optional path to assignment.resolved.yaml (for student version checks)",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Artifact root directory (for resolving relative paths)",
    )
    args = parser.parse_args()

    plan_path = args.plan.resolve()
    jobs_path = args.jobs.resolve()
    artifacts_path = args.artifacts.resolve()

    for p in (plan_path, jobs_path, artifacts_path):
        if not p.exists():
            raise SystemExit(f"File not found: {p}")

    plan_data = AssignmentPlanDiagramView.model_validate(
        yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    )
    jobs_raw = json.loads(jobs_path.read_text(encoding="utf-8"))
    artifacts_raw = json.loads(artifacts_path.read_text(encoding="utf-8"))

    jobs_manifest = DiagramJobsManifest(**jobs_raw)
    artifacts_manifest = DiagramArtifactsManifest(**artifacts_raw)

    artifact_dir = args.artifact_dir.resolve() if args.artifact_dir else plan_path.parent
    resolved_path = args.resolved.resolve() if args.resolved else None

    report = run_gate(
        plan_data, jobs_manifest, artifacts_manifest,
        artifact_dir, resolved_path,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if report.status == "block":
        print(f"\nGATE BLOCKED: {sum(1 for c in report.checks if c.status == 'block')} blocking issue(s)", file=sys.stderr)
        raise SystemExit(2)
    elif report.status == "warn":
        print(f"\nGATE PASSED WITH WARNINGS: {sum(1 for c in report.checks if c.status == 'warn')} warning(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
