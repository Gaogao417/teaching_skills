#!/usr/bin/env python3
"""Check diagram gate before resolving assignment diagram slots.

This CLI validates generated diagram job results before
resolve_assignment_diagrams.py writes them back into the resolved YAML.
Concrete checks live under diagram_gate/ by responsibility.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: PyYAML is required") from exc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import AssignmentPlanDiagramView, DiagramJobsManifest  # noqa: E402
from diagram_gate.analytic_checks import (  # noqa: E402
    _analytic_spec_errors,
    _check_analytic_renderer_specs,
)
from diagram_gate.artifact_checks import (  # noqa: E402
    _check_content_hash,
    _check_diagram_ref_consistency,
    _check_required_bindable,
    _check_tikz_path_accessible,
    _check_tikz_payload_exists,
)
from diagram_gate.layout_checks import _check_slot_layout_profiles  # noqa: E402
from diagram_gate.policy_checks import (  # noqa: E402
    _check_prompt_clean,
    _check_student_no_solution,
    _collect_resolved_diagrams,
)
from diagram_gate.runner import run_gate  # noqa: E402
from diagram_gate.svg_preview_checks import _check_svg_readability  # noqa: E402
from renderer_bindings import manifest_from_paths  # noqa: E402


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
        "--jobs-dir",
        type=Path,
        required=True,
        help="Path to build/diagram/jobs/ directory",
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
    jobs_dir = args.jobs_dir.resolve()

    for path in (plan_path, jobs_path):
        if not path.exists():
            raise SystemExit(f"File not found: {path}")
    if not jobs_dir.exists():
        raise SystemExit(f"Jobs directory not found: {jobs_dir}")

    plan_data = AssignmentPlanDiagramView.model_validate(
        yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    )
    jobs_manifest = DiagramJobsManifest(**json.loads(jobs_path.read_text(encoding="utf-8")))
    artifact_dir = args.artifact_dir.resolve() if args.artifact_dir else plan_path.parent
    resolved_path = args.resolved.resolve() if args.resolved else None
    binding_manifest = manifest_from_paths(jobs_path, jobs_dir, artifact_dir)

    report = run_gate(
        plan_data,
        jobs_manifest,
        binding_manifest,
        artifact_dir,
        resolved_path,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if report.status == "block":
        print(
            f"\nGATE BLOCKED: {sum(1 for c in report.checks if c.status == 'block')} blocking issue(s)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if report.status == "warn":
        print(
            f"\nGATE PASSED WITH WARNINGS: {sum(1 for c in report.checks if c.status == 'warn')} warning(s)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
