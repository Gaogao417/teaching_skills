#!/usr/bin/env python3
"""Run diagram generation batch from a jobs manifest.

Reads diagram_jobs.json, iterates jobs in topological order, generates
DiagramJobRequest v2 per job, adapts to legacy v1 format for the current
workflow.py, and calls run_diagram_workflow.py + render_geometry_spec.py
per job.

Supports parallel execution with --max-workers, dry-run, and job filtering.

Usage:
    python3 scripts/run_diagram_batch.py <diagram_jobs.json> [options]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    DiagramJob,
    DiagramJobRequest,
    DiagramJobsManifest,
)


SCRIPT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# v2 → v1 adapter
# ---------------------------------------------------------------------------

def job_request_to_legacy_v1(req: DiagramJobRequest) -> dict[str, Any]:
    """Convert DiagramJobRequest v2 to legacy teaching-diagram-request/v1.

    This adapter bridges the new contract to the existing workflow.py input
    format until workflow.py natively supports v2.
    """
    sc = req.semantic_constraints
    return {
        "schema_version": "teaching-diagram-request/v1",
        "needs_diagram": True,
        "diagram_type": req.diagram_kind.value,
        "diagram_intent": req.teaching_intent,
        "diagram_variant": req.variant.value,
        "variant": req.variant.value,
        "disclosure_policy": req.disclosure_policy.value,
        "diagram_job_id": req.job_id,
        "problem_text": req.problem_context.stem_latex,
        "grade_or_topic": req.problem_context.grade_or_topic,
        "objects_hint": {
            "points": sc.given_objects,
            "segments": [],
            "curves": [],
            "constraints": sc.given_constraints,
        },
        "teaching_focus": sc.given_objects,
        "must_not_imply": sc.clean_forbidden,
        "fallback": "textual_diagram_description",
        "reuse_geometry_from": req.reuse.reuse_geometry_from,
        "base_job_dir": req.reuse.base_job_dir,
        **{
            k: v
            for k, v in req.engine_options.model_dump(exclude_none=True, mode="json").items()
            if v is not None and k != "engine_model_config"
        },
    }


# ---------------------------------------------------------------------------
# Request generation
# ---------------------------------------------------------------------------

def build_request(
    job: DiagramJob,
    manifest: DiagramJobsManifest,
    plan_data: dict[str, Any] | None,
) -> DiagramJobRequest:
    """Build a DiagramJobRequest v2 from a DiagramJob.

    Reads semantic constraints from the plan YAML if available,
    otherwise produces a minimal request.
    """
    semantic_constraints: dict[str, Any] = {}
    problem_context: dict[str, Any] = {}
    visual_requirements: dict[str, Any] = {}
    reuse: dict[str, Any] = {"reuse_geometry_from": job.reuse_geometry_from}
    engine_options: dict[str, Any] = {}

    # Try to extract problem context from plan YAML
    if plan_data:
        problem_ctx = _extract_problem_context(plan_data, job)
        problem_context.update(problem_ctx)

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
        problem_context=problem_context,
        semantic_constraints=semantic_constraints,
        visual_requirements=visual_requirements,
        reuse=reuse,
        engine_options=engine_options,
    )


def _extract_problem_context(
    plan_data: dict[str, Any], job: DiagramJob
) -> dict[str, Any]:
    """Best-effort extraction of problem context from plan YAML."""
    for section in plan_data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            block_id = block.get("id", "")
            if block_id == job.problem_id or block_id == job.slot_id.split(".")[0]:
                stem = block.get("stem_latex", "") or block.get("stem", "")
                topic = ""
                meta = plan_data.get("meta")
                if isinstance(meta, dict):
                    topic = meta.get("title", "")
                return {
                    "stem_latex": stem,
                    "grade_or_topic": topic,
                }
    return {}


# ---------------------------------------------------------------------------
# Single-job execution
# ---------------------------------------------------------------------------

def run_one_job(
    job: DiagramJob,
    request: DiagramJobRequest,
    artifact_dir: Path,
    python_executable: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Execute a single diagram job: write request → workflow → renderer.

    Returns a result dict with status, paths, and subprocess output.
    """
    job_id = job.job_id
    # Build directory paths
    build_dir = artifact_dir / "build" / "diagram"
    job_build_dir = build_dir / "jobs" / job_id
    job_public_dir = artifact_dir / "diagram" / "jobs" / job_id / "rendered"

    record: dict[str, Any] = {
        "job_id": job_id,
        "slot_id": job.slot_id,
        "variant": job.variant.value,
        "status": "not_run",
        "workflow_status": "not_run",
        "renderer_status": "not_run",
    }

    # Write v2 request
    request_path = job_build_dir / "request.json"
    write_json(request_path, request.model_dump(mode="json"))

    # Write legacy v1 request for current workflow.py
    legacy_request = job_request_to_legacy_v1(request)
    legacy_request_path = job_build_dir / "diagram-request.json"
    write_json(legacy_request_path, legacy_request)

    if dry_run:
        record["status"] = "dry_run"
        record["workflow_status"] = "dry_run"
        record["renderer_status"] = "dry_run"
        return record

    # Run workflow
    workflow_script = SCRIPT_DIR / "run_diagram_workflow.py"
    workflow_cmd = [
        python_executable,
        str(workflow_script),
        str(legacy_request_path),
        "--job-id", job_id,
        "--out", str(build_dir),
        "--python", python_executable,
    ]
    wf_result = subprocess.run(
        workflow_cmd, cwd=str(SCRIPT_DIR.parent),
        text=True, capture_output=True, check=False,
    )
    record["workflow_returncode"] = wf_result.returncode

    # Read workflow result
    wf_result_path = job_build_dir / "workflow_result.json"
    if wf_result_path.exists():
        wf_data = read_json(wf_result_path)
        record["workflow_status"] = wf_data.get("status", "unknown")
    else:
        record["workflow_status"] = "missing_result"

    if record["workflow_status"] != "ok":
        record["status"] = "workflow_failed"
        record["failure_reason"] = f"workflow status: {record['workflow_status']}"
        return record

    # Run renderer
    renderer_script = SCRIPT_DIR / "render_geometry_spec.py"
    spec_path = job_build_dir / "final_renderer_spec.json"
    if not spec_path.exists():
        record["status"] = "renderer_no_spec"
        record["renderer_status"] = "no_spec"
        return record

    renderer_cmd = [
        python_executable,
        str(renderer_script),
        str(spec_path),
        "--out-dir", str(job_build_dir),
        "--variant", job.variant.value,
    ]
    rr_result = subprocess.run(
        renderer_cmd, cwd=str(SCRIPT_DIR.parent),
        text=True, capture_output=True, check=False,
    )

    # Read renderer result
    rr_result_path = job_build_dir / "renderer_result.json"
    if rr_result_path.exists():
        rr_data = read_json(rr_result_path)
        record["renderer_status"] = rr_data.get("status", "unknown")
    else:
        record["renderer_status"] = "missing_result"

    if record["renderer_status"] == "ok":
        record["status"] = "ok"
        # Copy rendered images to public directory
        image_path = rr_data.get("image_path", "")
        if image_path:
            record["image_path"] = image_path
    else:
        record["status"] = "renderer_failed"
        record["failure_reason"] = f"renderer status: {record['renderer_status']}"

    return record


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
    plan_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Run all jobs in topological order with parallelism within each level."""
    ordered_ids = manifest.topological_job_ids()

    # Filter if requested
    if jobs_filter:
        ordered_ids = [jid for jid in ordered_ids if jid in jobs_filter]

    job_by_id = {job.job_id: job for job in manifest.jobs}

    # Group by dependency level for wave-based parallelism
    levels = _topological_levels(ordered_ids, job_by_id)

    results: list[dict[str, Any]] = []
    completed_ok: set[str] = set()

    for level_idx, level_ids in enumerate(levels):
        # Filter out jobs whose dependencies failed
        runnable: list[DiagramJob] = []
        for jid in level_ids:
            job = job_by_id[jid]
            deps_ok = all(dep in completed_ok for dep in job.depends_on)
            if deps_ok:
                runnable.append(job)
            else:
                results.append({
                    "job_id": jid,
                    "slot_id": job.slot_id,
                    "variant": job.variant.value,
                    "status": "dependency_failed",
                    "failure_reason": "dependency job failed or was skipped",
                })

        if not runnable:
            continue

        # Build requests
        job_requests = [
            (job, build_request(job, manifest, plan_data))
            for job in runnable
        ]

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    run_one_job, job, req, artifact_dir, python_executable, dry_run
                ): job.job_id
                for job, req in job_requests
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result["status"] in ("ok", "dry_run"):
                    completed_ok.add(result["job_id"])

    return sorted(results, key=lambda r: r["job_id"])


def _topological_levels(
    ordered_ids: list[str],
    job_by_id: dict[str, DiagramJob],
) -> list[list[str]]:
    """Group topologically-sorted job IDs into dependency levels.

    All jobs in a level can run concurrently; all deps are in prior levels.
    """
    levels: list[list[str]] = []
    assigned: set[str] = set()

    for jid in ordered_ids:
        job = job_by_id[jid]
        # Find the minimum level where all deps are assigned
        min_level = 0
        for dep in job.depends_on:
            for li, level in enumerate(levels):
                if dep in level:
                    min_level = max(min_level, li + 1)
                    break
        # Extend levels list if needed
        while len(levels) <= min_level:
            levels.append([])
        levels[min_level].append(jid)
        assigned.add(jid)

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

    # Determine artifact dir
    if args.artifact_dir:
        artifact_dir = args.artifact_dir.resolve()
    else:
        # diagram_jobs.json is in <artifact_dir>/build/diagram/
        artifact_dir = jobs_path.parent.parent.parent

    # Load manifest
    raw = read_json(jobs_path)
    manifest = DiagramJobsManifest(**raw)

    # Optionally load plan YAML for problem context
    plan_data: dict[str, Any] | None = None
    if args.plan_yaml and args.plan_yaml.exists():
        try:
            import yaml as _yaml
            plan_data = _yaml.safe_load(args.plan_yaml.read_text(encoding="utf-8"))
        except ImportError:
            pass

    jobs_filter = set(args.jobs_filter) if args.jobs_filter else None

    results = run_batch(
        manifest,
        artifact_dir,
        args.python,
        max(1, args.max_workers),
        args.dry_run,
        jobs_filter,
        plan_data,
    )

    ok_count = sum(1 for r in results if r["status"] in ("ok", "dry_run"))
    fail_count = len(results) - ok_count

    report = {
        "schema_version": "diagram-batch-report/v1",
        "assignment_id": manifest.assignment_id,
        "total_jobs": len(results),
        "ok_count": ok_count,
        "failed_count": fail_count,
        "dry_run": args.dry_run,
        "jobs": results,
    }

    # Write report alongside the manifest
    report_path = jobs_path.parent / "diagram_batch_report.json"
    write_json(report_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if fail_count > 0 and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
