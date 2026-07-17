from __future__ import annotations

from pathlib import Path

from diagram_contracts import (
    AssignmentPlanDiagramView,
    DiagramGateCheck,
    DiagramGateReport,
    DiagramJobsManifest,
    RendererBindingManifest,
)

from .analytic_checks import _check_analytic_renderer_specs
from .artifact_checks import (
    _check_content_hash,
    _check_diagram_ref_consistency,
    _check_required_bindable,
    _check_tikz_path_accessible,
    _check_tikz_payload_exists,
)
from .layout_checks import _check_slot_layout_profiles
from .policy_checks import (
    _check_prompt_clean,
    _check_resolved_binding_integrity,
    _check_resolved_no_slots,
    _check_student_no_solution,
)
from .semantic_checks import check_semantic_diagram_policy
from .spatial_checks import _check_spatial_renderer_specs
from .svg_preview_checks import _check_svg_readability


def run_gate(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
    resolved_path: Path | None,
) -> DiagramGateReport:
    """Backward-compatible combined gate entry point."""
    return run_resolved_assignment_gate(
        plan_data,
        jobs,
        artifacts,
        artifact_dir,
        resolved_path,
    )


def _report(assignment_id: str, checks: list[DiagramGateCheck]) -> DiagramGateReport:
    statuses = [check.status for check in checks]
    overall = "block" if "block" in statuses else "warn" if "warn" in statuses else "pass"
    return DiagramGateReport(
        assignment_id=assignment_id,
        status=overall,
        checks=checks,
    )


def run_resolved_assignment_gate(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
    resolved_path: Path | None,
) -> DiagramGateReport:
    """Validate binding, disclosure, layout, and final resolved-assignment policy."""
    all_checks: list[DiagramGateCheck] = []

    all_checks.extend(_check_required_bindable(jobs, artifacts))
    all_checks.extend(_check_tikz_payload_exists(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_content_hash(jobs, plan_data))
    all_checks.extend(_check_prompt_clean(artifacts))
    all_checks.extend(_check_student_no_solution(resolved_path))
    all_checks.extend(_check_resolved_no_slots(resolved_path))
    all_checks.extend(_check_resolved_binding_integrity(resolved_path, artifacts))
    all_checks.extend(_check_tikz_path_accessible(artifacts, artifact_dir))
    all_checks.extend(_check_diagram_ref_consistency(jobs, artifacts))
    all_checks.extend(_check_slot_layout_profiles(plan_data))
    all_checks.extend(_check_svg_readability(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_analytic_renderer_specs(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_spatial_renderer_specs(jobs, artifacts, artifact_dir))
    all_checks.extend(check_semantic_diagram_policy(plan_data, jobs, artifacts, artifact_dir))

    return _report(jobs.assignment_id, all_checks)
