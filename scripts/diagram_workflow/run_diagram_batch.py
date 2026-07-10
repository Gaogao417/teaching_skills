#!/usr/bin/env python3
"""Run diagram generation batch from a jobs manifest.

Reads diagram_jobs.json, iterates jobs in topological order, generates
DiagramJobRequest v2 per job, and calls run_diagram_workflow.py +
render_geometry_spec.py per job.

Supports parallel execution with --max-workers, dry-run, and job filtering.

Usage:
    python3 scripts/diagram_workflow/run_diagram_batch.py <diagram_jobs.json> [options]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    AssignmentPlanDiagramView,
    DiagramBatchJobResult,
    DiagramBatchReport,
    DiagramAnalyticRequirements,
    DiagramJob,
    DiagramJobRequest,
    DiagramJobsManifest,
    DiagramProblemContext,
    DiagramReuseSpec,
    DiagramSlotRef,
    DiagramSemanticConstraints,
    DiagramVisualRequirements,
    DiagramEngineOptions,
)


SCRIPT_DIR = Path(__file__).resolve().parent

# Routing constants mirror run_diagram_workflow.py so the batch runner dispatches
# each job to exactly the same branch as the single-job engine router.
SUPPORTED_GSB_TYPES = {"synthetic_geometry"}
SUPPORTED_ANALYTIC_TYPES = {"coordinate_geometry", "function_graph"}
SUPPORTED_ANALYTIC_ENGINES = {"wolfram_client", "wolfram_plot", "coordinate_renderer"}
SUPPORTED_SPATIAL_TYPES = {"spatial_geometry"}
SUPPORTED_SPATIAL_ENGINES = {"spatial_renderer"}
RENDERER_SPEC_ENGINE = "renderer_spec"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _has_runtime_value(value: object) -> bool:
    return value not in (None, "", [], {})


def _job_engine_value(job: DiagramJob) -> str:
    return str(getattr(job.engine, "value", job.engine))


def request_payload_for_artifact(request: DiagramJobRequest) -> dict[str, object]:
    """Serialize a request while omitting empty runtime model config fields."""
    payload = request.model_dump(mode="json")
    engine_options = payload.get("engine_options")
    if isinstance(engine_options, dict):
        model_config = engine_options.get("engine_model_config")
        if isinstance(model_config, dict):
            pruned_config = {
                key: value
                for key, value in model_config.items()
                if _has_runtime_value(value)
            }
            if pruned_config:
                engine_options["engine_model_config"] = pruned_config
            else:
                engine_options.pop("engine_model_config", None)
    return payload


# ---------------------------------------------------------------------------
# Request generation
# ---------------------------------------------------------------------------

def _plan_view(plan_data: AssignmentPlanDiagramView | dict[str, object] | None) -> AssignmentPlanDiagramView | None:
    if plan_data is None:
        return None
    if isinstance(plan_data, AssignmentPlanDiagramView):
        return plan_data
    return AssignmentPlanDiagramView.model_validate(plan_data)


def _slot_refs(plan: AssignmentPlanDiagramView) -> list[DiagramSlotRef]:
    refs: list[DiagramSlotRef] = []
    for si, section in enumerate(plan.sections):
        for bi, block in enumerate(section.blocks):
            if block.diagram_slot is not None:
                refs.append(DiagramSlotRef(
                    slot_path=f"/sections/{si}/blocks/{bi}/diagram_slot",
                    slot=block.diagram_slot,
                    section_index=si,
                    block_index=bi,
                ))
            for sti, step in enumerate(block.steps):
                if step.diagram_slot is not None:
                    refs.append(DiagramSlotRef(
                        slot_path=f"/sections/{si}/blocks/{bi}/steps/{sti}/diagram_slot",
                        slot=step.diagram_slot,
                        section_index=si,
                        block_index=bi,
                        step_index=sti,
                    ))
            answer_space = block.answer_space
            if answer_space is None:
                continue
            if answer_space.diagram_slot is not None:
                refs.append(DiagramSlotRef(
                    slot_path=f"/sections/{si}/blocks/{bi}/answer_space/diagram_slot",
                    slot=answer_space.diagram_slot,
                    section_index=si,
                    block_index=bi,
                ))
            for pi, part in enumerate(answer_space.parts):
                if part.diagram_slot is not None:
                    refs.append(DiagramSlotRef(
                        slot_path=f"/sections/{si}/blocks/{bi}/answer_space/parts/{pi}/diagram_slot",
                        slot=part.diagram_slot,
                        section_index=si,
                        block_index=bi,
                        part_index=pi,
                    ))
    return refs


def _slot_ref_for_job(
    plan_data: AssignmentPlanDiagramView | dict[str, object] | None,
    job: DiagramJob,
) -> DiagramSlotRef | None:
    plan = _plan_view(plan_data)
    if plan is None:
        return None
    for ref in _slot_refs(plan):
        if ref.slot_path == job.slot_path or ref.slot.slot_id == job.slot_id:
            return ref
    return None

def build_request(
    job: DiagramJob,
    manifest: DiagramJobsManifest,
    plan_data: AssignmentPlanDiagramView | dict[str, object] | None,
) -> DiagramJobRequest:
    """Build a DiagramJobRequest v2 from a DiagramJob.

    Reads semantic constraints from the plan YAML if available,
    otherwise produces a minimal request.
    """
    slot_ref = _slot_ref_for_job(plan_data, job)
    slot = slot_ref.slot if slot_ref else None
    problem_context: dict[str, object] = {}
    reuse = DiagramReuseSpec(reuse_geometry_from=job.reuse_geometry_from)

    if plan_data:
        problem_ctx = _extract_problem_context(plan_data, job)
        problem_context.update(problem_ctx)
    if slot is not None:
        problem_context.update(
            {
                key: value
                for key, value in slot.problem_context.model_dump(mode="json").items()
                if value not in ("", None, [], {})
            }
        )

    semantic_constraints = slot.semantic_constraints if slot else DiagramSemanticConstraints()
    visual_requirements = slot.visual_requirements if slot else DiagramVisualRequirements()
    analytic_requirements = (
        getattr(slot, "analytic_requirements", DiagramAnalyticRequirements())
        if slot else DiagramAnalyticRequirements()
    )
    engine_options = slot.engine_options if slot else DiagramEngineOptions()
    render_profile = slot.resolved_render_profile() if slot else None

    return DiagramJobRequest(
        job_id=job.job_id,
        assignment_id=manifest.assignment_id,
        problem_id=job.problem_id,
        slot_id=job.slot_id,
        variant=job.variant,
        disclosure_policy=job.disclosure_policy,
        engine=job.engine,
        diagram_kind=job.diagram_kind,
        teaching_intent=job.teaching_intent,
        problem_context=DiagramProblemContext(**problem_context),
        semantic_constraints=semantic_constraints,
        analytic_requirements=analytic_requirements,
        visual_requirements=visual_requirements,
        **({"render_profile": render_profile} if render_profile is not None else {}),
        reuse=reuse,
        engine_options=engine_options,
    )


def _extract_problem_context(
    plan_data: AssignmentPlanDiagramView | dict[str, object], job: DiagramJob
) -> dict[str, object]:
    """Best-effort extraction of problem context from plan YAML."""
    plan = _plan_view(plan_data)
    if plan is None:
        return {}
    for section in plan.sections:
        for block in section.blocks:
            block_id = block.id
            if block_id == job.problem_id or block_id == job.slot_id.split(".")[0]:
                return {
                    "stem_latex": block.stem_latex or block.stem,
                    "grade_or_topic": plan.title,
                }
    return {}


# ---------------------------------------------------------------------------
# Single-job execution
# ---------------------------------------------------------------------------

def _is_renderer_spec_route(request: DiagramJobRequest) -> bool:
    return request.engine.value == RENDERER_SPEC_ENGINE


def _is_analytic_route(request: DiagramJobRequest) -> bool:
    diagram_kind = request.diagram_kind.value
    engine = request.engine.value
    return diagram_kind in SUPPORTED_ANALYTIC_TYPES or engine in SUPPORTED_ANALYTIC_ENGINES


def _is_spatial_route(request: DiagramJobRequest) -> bool:
    diagram_kind = request.diagram_kind.value
    engine = request.engine.value
    return diagram_kind in SUPPORTED_SPATIAL_TYPES or engine in SUPPORTED_SPATIAL_ENGINES


def _run_workflow_in_process(
    request: DiagramJobRequest,
    request_path: Path,
    job_build_dir: Path,
    build_dir: Path,
) -> str:
    """Dispatch the workflow stage in-process and return its status string.

    Mirrors the routing in run_diagram_workflow.py:main() for the
    renderer_spec, spatial_renderer, and analytic (coordinate_renderer /
    wolfram_client / wolfram_plot) branches. The geometric_scene / synthetic
    branch is handled by the subprocess path in _run_workflow_subprocess
    instead, so the GeometricScene LLM and Wolfram synthetic-geometry runtime
    stay isolated from the main process.
    """
    # Lazy imports keep the CLI lightweight and avoid importing heavy modules
    # (wolframclient, tikz_renderer) unless a job actually needs them.
    if _is_renderer_spec_route(request):
        from run_diagram_workflow import run_renderer_spec_workflow

        request_payload = read_json(request_path)
        run_renderer_spec_workflow(request_payload, job_build_dir, emit_result=False)
    elif _is_analytic_route(request):
        from analytic_diagram_workflow import run_analytic_workflow

        run_analytic_workflow(request_path, job_build_dir)
    elif _is_spatial_route(request):
        from spatial_diagram_workflow import run_spatial_workflow

        run_spatial_workflow(request_path, job_build_dir)
    else:
        raise ValueError(
            f"in-process workflow dispatch only handles renderer_spec, spatial, and analytic "
            f"routes; engine={request.engine.value} kind={request.diagram_kind.value} "
            f"requires the subprocess path"
        )

    wf_result_path = job_build_dir / "workflow_result.json"
    if wf_result_path.exists():
        return str(read_json(wf_result_path).get("status", "unknown"))
    return "missing_result"


def _run_workflow_subprocess(
    request_path: Path,
    job_id: str,
    build_dir: Path,
    job_build_dir: Path,
    python_executable: str,
) -> tuple[str, str]:
    """Run the GeometricScene/Wolfram workflow via the isolated subprocess.

    Returns (workflow_status, captured_diagnostic). subprocess isolation keeps
    the LLM/Wolfram/runtime state from polluting the main process.
    """
    workflow_script = SCRIPT_DIR / "run_diagram_workflow.py"
    workflow_cmd = [
        python_executable,
        str(workflow_script),
        str(request_path),
        "--job-id", job_id,
        "--out", str(build_dir),
        "--python", python_executable,
    ]
    completed = subprocess.run(
        workflow_cmd, cwd=str(SCRIPT_DIR.parent),
        text=True, capture_output=True, check=False,
    )
    wf_result_path = job_build_dir / "workflow_result.json"
    if wf_result_path.exists():
        status = str(read_json(wf_result_path).get("status", "unknown"))
    else:
        status = "missing_result"
    diagnostic = (completed.stderr or completed.stdout or "")[-500:]
    return status, diagnostic


def _run_tikz_renderer(
    spec_path: Path,
    job_build_dir: Path,
    variant: str,
) -> tuple[str, str, str]:
    """Compile the renderer spec to a TikZ fragment.

    Returns (status, tikz_fragment_path, tikz_source_path). The TikZ compiler
    runs in-process; it still shells out to the TeX/pdf toolchain for previews
    only. If spec compilation raises, returns process_failed with the message.
    """
    rr_result_path = job_build_dir / "renderer_result.json"
    if rr_result_path.exists():
        rr_result_path.unlink()
    try:
        from render_geometry_spec import render_geometry_spec

        rr_data = render_geometry_spec(spec_path, job_build_dir, variant=variant)
    except Exception as exc:  # pragma: no cover - defensive guard for renderer import/compile
        return "process_failed", "", str(exc)[-500:]

    status = str(rr_data.get("status", "unknown"))
    return status, str(rr_data.get("tikz_fragment_path", "")), str(rr_data.get("tikz_source_path", ""))


def run_one_job(
    job: DiagramJob,
    request: DiagramJobRequest,
    artifact_dir: Path,
    python_executable: str,
    dry_run: bool,
) -> DiagramBatchJobResult:
    """Execute a single diagram job: write request → workflow → renderer.

    renderer_spec, spatial_renderer, and analytic (coordinate_renderer /
    wolfram_client / wolfram_plot) jobs run in-process. The geometric_scene /
    synthetic route stays subprocess-isolated to keep the LLM and Wolfram
    runtime out of the main process. All on-disk artifacts are identical to the
    legacy subprocess path.
    """
    job_id = job.job_id
    build_dir = artifact_dir / "build" / "diagram"
    job_build_dir = build_dir / "jobs" / job_id

    # Write v2 request
    request_path = job_build_dir / "request.json"
    write_json(request_path, request_payload_for_artifact(request))

    if dry_run:
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="dry_run",
            workflow_status="dry_run",
            renderer_status="dry_run",
        )

    # Workflow stage
    if _is_renderer_spec_route(request) or _is_analytic_route(request) or _is_spatial_route(request):
        wf_status = _run_workflow_in_process(request, request_path, job_build_dir, build_dir)
    else:
        wf_status, _diag = _run_workflow_subprocess(
            request_path, job_id, build_dir, job_build_dir, python_executable
        )

    if wf_status != "ok":
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="workflow_failed",
            workflow_status=wf_status,
            failure_reason=f"workflow status: {wf_status}",
        )

    # Renderer stage
    spec_path = job_build_dir / "final_renderer_spec.json"
    if not spec_path.exists():
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="renderer_no_spec",
            workflow_status="ok",
            renderer_status="no_spec",
        )

    rr_status, rr_tikz_fragment_path, rr_tikz_source_path = _run_tikz_renderer(
        spec_path, job_build_dir, job.variant.value
    )

    if rr_status == "process_failed":
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="renderer_failed",
            workflow_status="ok",
            renderer_status="process_failed",
            failure_reason=rr_tikz_source_path or "renderer process failed",
        )
    if rr_status == "ok":
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="ok",
            workflow_status="ok",
            renderer_status="ok",
            tikz_fragment_path=rr_tikz_fragment_path,
            tikz_source_path=rr_tikz_source_path,
        )

    return DiagramBatchJobResult(
        job_id=job_id,
        slot_id=job.slot_id,
        variant=job.variant.value,
        status="renderer_failed",
        workflow_status="ok",
        renderer_status=rr_status,
        failure_reason=f"renderer status: {rr_status}",
    )


# ---------------------------------------------------------------------------
# Batch execution
# ---------------------------------------------------------------------------

def run_batch(
    manifest: DiagramJobsManifest,
    artifact_dir: Path,
    python_executable: str,
    max_workers: int,
    dry_run: bool,
    jobs_filter: set[str] | None,
    plan_data: AssignmentPlanDiagramView | dict[str, object] | None,
) -> DiagramBatchReport:
    """Run all jobs in topological order with parallelism within each level."""
    ordered_ids = manifest.topological_job_ids()

    if jobs_filter:
        ordered_ids = [jid for jid in ordered_ids if jid in jobs_filter]

    job_by_id = {job.job_id: job for job in manifest.jobs}
    levels = _topological_levels(ordered_ids, job_by_id)

    results: list[DiagramBatchJobResult] = []
    completed_ok: set[str] = set()

    for level_ids in levels:
        runnable: list[DiagramJob] = []
        for jid in level_ids:
            job = job_by_id[jid]
            deps_ok = all(dep in completed_ok for dep in job.depends_on)
            if deps_ok:
                runnable.append(job)
            else:
                results.append(DiagramBatchJobResult(
                    job_id=jid,
                    slot_id=job.slot_id,
                    variant=job.variant.value,
                    status="dependency_failed",
                    failure_reason="dependency job failed or was skipped",
                ))

        if not runnable:
            continue

        job_requests = [
            (job, build_request(job, manifest, plan_data))
            for job in runnable
        ]

        # Wolfram-backed GeometricScene runs are not stable under concurrent
        # kernel startup in this workflow. Keep those waves serial while still
        # allowing renderer_spec/offline jobs to use the configured parallelism.
        level_workers = max_workers
        if any(_job_engine_value(job) == "geometric_scene" for job in runnable):
            level_workers = 1

        with ThreadPoolExecutor(max_workers=level_workers) as executor:
            futures = {
                executor.submit(
                    run_one_job, job, req, artifact_dir, python_executable, dry_run
                ): job.job_id
                for job, req in job_requests
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result.status in ("ok", "dry_run"):
                    completed_ok.add(result.job_id)

    results.sort(key=lambda r: r.job_id)
    ok_count = sum(1 for r in results if r.status in ("ok", "dry_run"))

    return DiagramBatchReport(
        assignment_id=manifest.assignment_id,
        total_jobs=len(results),
        ok_count=ok_count,
        failed_count=len(results) - ok_count,
        dry_run=dry_run,
        jobs=results,
    )


def _topological_levels(
    ordered_ids: list[str],
    job_by_id: dict[str, DiagramJob],
) -> list[list[str]]:
    """Group topologically-sorted job IDs into dependency levels.

    All jobs in a level can run concurrently; all deps are in prior levels.
    """
    levels: list[list[str]] = []

    for jid in ordered_ids:
        job = job_by_id[jid]
        min_level = 0
        for dep in job.depends_on:
            for li, level in enumerate(levels):
                if dep in level:
                    min_level = max(min_level, li + 1)
                    break
        while len(levels) <= min_level:
            levels.append([])
        levels[min_level].append(jid)

    return levels


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run diagram generation batch from a jobs manifest"
    )
    parser.add_argument(
        "jobs_manifest",
        type=Path,
        help="Path to diagram_jobs.json",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Artifact root directory (defaults to jobs manifest parent's parent)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable for subprocess calls",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum parallel jobs per wave (default: 4)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write requests but do not execute workflow/renderer",
    )
    parser.add_argument(
        "--jobs-filter",
        nargs="*",
        help="Only run these job IDs (space-separated)",
    )
    parser.add_argument(
        "--plan-yaml",
        type=Path,
        help="Optional plan YAML for extracting problem context",
    )
    args = parser.parse_args()

    jobs_path = args.jobs_manifest.resolve()
    if not jobs_path.exists():
        raise SystemExit(f"Jobs manifest not found: {jobs_path}")

    if args.artifact_dir:
        artifact_dir = args.artifact_dir.resolve()
    else:
        artifact_dir = jobs_path.parent.parent.parent

    raw = read_json(jobs_path)
    manifest = DiagramJobsManifest(**raw)

    plan_data: AssignmentPlanDiagramView | None = None
    if args.plan_yaml and args.plan_yaml.exists():
        try:
            import yaml as _yaml
            raw_plan = _yaml.safe_load(args.plan_yaml.read_text(encoding="utf-8"))
            plan_data = AssignmentPlanDiagramView.model_validate(raw_plan)
        except ImportError:
            pass

    jobs_filter = set(args.jobs_filter) if args.jobs_filter else None

    report = run_batch(
        manifest,
        artifact_dir,
        args.python,
        max(1, args.max_workers),
        args.dry_run,
        jobs_filter,
        plan_data,
    )

    # Write report — single serialization point
    report_path = jobs_path.parent / "diagram_batch_report.json"
    write_json(report_path, report.model_dump(mode="json"))

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if report.failed_count > 0 and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
