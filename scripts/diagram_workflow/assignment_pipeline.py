#!/usr/bin/env python3
"""In-process orchestrator for the assignment diagram pipeline.

The default main entry point (:mod:`run_assignment_diagrams`) drives the four
pipeline stages (collect → batch → gate → resolve) by calling library functions
directly inside one Python process instead of spawning one interpreter per
stage. The external artifacts on disk are identical to the legacy
script-chained path:

- ``build/diagram/diagram_jobs.json``
- per-job ``request.json`` / ``workflow_result.json`` / ``renderer_result.json``
  and ``rendered/<variant>.fragment.tex``
- ``build/diagram/diagram_batch_report.json``
- the final ``*.resolved.assignment.yaml``

The single-stage CLIs (``collect_diagram_jobs.py``, ``run_diagram_batch.py``,
``check_diagram_gate.py``, ``resolve_assignment_diagrams.py``) remain available
for debugging, localization, and temporary rollback.

The GeometricScene / Wolfram synthetic-geometry route keeps its subprocess
isolation: those engines are owned by :mod:`run_diagram_workflow` and the
per-job batch runner, not by this orchestrator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import yaml  # noqa: E402

from check_diagram_gate import run_gate as _run_gate  # noqa: E402
from collect_diagram_jobs import collect_jobs  # noqa: E402
from diagram_contracts import AssignmentPlanDiagramView  # noqa: E402
from renderer_bindings import manifest_from_paths  # noqa: E402
from resolve_assignment_diagrams import (  # noqa: E402
    resolve_assignment,
    validate_batch_report_allows_resolution,
    write_yaml,
)
from run_diagram_batch import (  # noqa: E402
    run_batch,
    write_json as write_batch_json,
)


# ---------------------------------------------------------------------------
# Path helpers (kept byte-for-byte compatible with run_assignment_diagrams.py)
# ---------------------------------------------------------------------------

def default_resolved_path(plan_yaml: Path) -> Path:
    name = plan_yaml.name
    if ".plan.assignment.yaml" in name:
        return plan_yaml.with_name(name.replace(".plan.assignment.yaml", ".resolved.assignment.yaml"))
    if name.endswith(".plan.yaml"):
        return plan_yaml.with_name(name[: -len(".plan.yaml")] + ".resolved.yaml")
    return plan_yaml.with_suffix(".resolved.yaml")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_assignment_diagram_pipeline(
    plan_yaml: Path,
    *,
    out: Path | None = None,
    max_workers: int = 4,
    python: str = sys.executable,
    skip_gate: bool = False,
    dry_run: bool = False,
) -> Path:
    """Run collect → batch → gate → resolve in one Python process.

    Arguments mirror the legacy CLI flags. Returns the resolved YAML path so
    callers (the thin CLI, tests) can assert on the final artifact.

    ``dry_run`` only prints the phases that *would* run and their output paths;
    it does not write the manifest, batch report, gate report, or resolved YAML,
    preserving the top-level dry-run semantics of the legacy wrapper.
    """
    plan_yaml = plan_yaml.resolve()
    if not plan_yaml.exists():
        raise SystemExit(f"Plan YAML not found: {plan_yaml}")

    artifact_dir = plan_yaml.parent
    build_dir = artifact_dir / "build" / "diagram"
    jobs_json = build_dir / "diagram_jobs.json"
    jobs_dir = build_dir / "jobs"
    out_yaml = (out.resolve() if out else default_resolved_path(plan_yaml).resolve())

    print(f"+ collect: {plan_yaml} -> {jobs_json}")
    print(f"+ batch:   {jobs_json} -> {build_dir / 'diagram_batch_report.json'}")
    if not skip_gate:
        print(f"+ gate:    plan + {jobs_json} + {jobs_dir}")
    print(f"+ resolve: -> {out_yaml}")

    if dry_run:
        return out_yaml

    # Stage 1: collect
    raw_plan = yaml.safe_load(plan_yaml.read_text(encoding="utf-8"))
    if not isinstance(raw_plan, dict):
        raise ValueError(f"{plan_yaml} must contain a YAML mapping")
    plan_view = AssignmentPlanDiagramView.model_validate(raw_plan)
    manifest = collect_jobs(plan_view, plan_yaml, build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    jobs_json.write_text(
        json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Stage 2: batch (in-process for renderer_spec / coordinate_renderer /
    # analytic; subprocess-isolated for geometric_scene / Wolfram)
    report = run_batch(
        manifest,
        artifact_dir,
        python,
        max(1, max_workers),
        dry_run=False,
        jobs_filter=None,
        plan_data=plan_view,
    )
    report_path = jobs_json.parent / "diagram_batch_report.json"
    write_batch_json(report_path, report.model_dump(mode="json"))
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if report.failed_count > 0:
        raise SystemExit(1)

    # Stage 3: gate
    if not skip_gate:
        gate_report = _run_gate(
            plan_view,
            manifest,
            manifest_from_paths(jobs_json, jobs_dir, artifact_dir),
            artifact_dir,
            None,
        )
        print(json.dumps(gate_report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        if gate_report.status == "block":
            print(
                f"\nGATE BLOCKED: "
                f"{sum(1 for c in gate_report.checks if c.status == 'block')} blocking issue(s)",
                file=sys.stderr,
            )
            raise SystemExit(2)

    # Stage 4: resolve
    validate_batch_report_allows_resolution(report_path)
    artifacts_manifest = manifest_from_paths(jobs_json, jobs_dir, artifact_dir)
    # Resolve from the original YAML mapping so the final document preserves
    # non-diagram fields exactly as the standalone resolver CLI does.
    resolved = resolve_assignment(raw_plan, artifacts_manifest)
    write_yaml(out_yaml, resolved)
    print(f"Resolved YAML: {out_yaml}")
    return out_yaml
