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
from .policy_checks import _check_prompt_clean, _check_student_no_solution
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
    """Run all diagram gate checks and summarize pass/warn/block status."""
    all_checks: list[DiagramGateCheck] = []

    all_checks.extend(_check_required_bindable(jobs, artifacts))
    all_checks.extend(_check_tikz_payload_exists(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_content_hash(jobs, plan_data))
    all_checks.extend(_check_prompt_clean(artifacts))
    all_checks.extend(_check_student_no_solution(resolved_path))
    all_checks.extend(_check_tikz_path_accessible(artifacts, artifact_dir))
    all_checks.extend(_check_diagram_ref_consistency(jobs, artifacts))
    all_checks.extend(_check_slot_layout_profiles(plan_data))
    all_checks.extend(_check_svg_readability(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_analytic_renderer_specs(jobs, artifacts, artifact_dir))
    all_checks.extend(_check_spatial_renderer_specs(jobs, artifacts, artifact_dir))
    all_checks.extend(check_semantic_diagram_policy(plan_data, jobs, artifacts, artifact_dir))

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
