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
import hashlib
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from progress_subprocess import run_subprocess_streaming

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
CACHE_SCHEMA_VERSION = "diagram-artifact-cache/v1"
SCENE_WRITER_SCHEMA_VERSION = "scene-writer-output/v1"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(payload)


@lru_cache(maxsize=1)
def _skill_bundle_version() -> str:
    skill_paths = [
        SCRIPT_DIR.parents[1] / ".codex" / "skills" / "math-geometry-diagram-renderer" / "SKILL.md",
        SCRIPT_DIR / "geometry_diagram_workflow" / ".codex" / "skills" / "wolfram-geometricscene-reference" / "SKILL.md",
        SCRIPT_DIR / "geometry_diagram_workflow" / ".codex" / "skills" / "dimensionless-constraints-library" / "SKILL.md",
    ]
    digest = hashlib.sha256()
    for path in skill_paths:
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


@lru_cache(maxsize=1)
def _workflow_code_version() -> str:
    paths = [
        SCRIPT_DIR / "geometry_diagram_workflow" / "core" / name
        for name in ("agent_prompt.py", "agent_runner.py", "workflow.py", "tools.py", "audit.py")
    ]
    paths.extend(
        [
            SCRIPT_DIR / "render_geometry_spec.py",
            SCRIPT_DIR / "diagram_contracts.py",
            SCRIPT_DIR / "run_diagram_batch.py",
        ]
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def _effective_model_cache_config(request: DiagramJobRequest) -> dict[str, object]:
    config = request.engine_options.engine_model_config.model_dump(mode="json")
    service_tier = str(config.get("service_tier") or "fast")
    return {
        "model": str(config.get("codex_model") or config.get("model") or "gpt-5.5"),
        "model_reasoning_effort": str(config.get("model_reasoning_effort") or "medium"),
        "service_tier": service_tier,
        "fast_mode": bool(
            config.get("fast_mode")
            if config.get("fast_mode") is not None
            else service_tier == "fast"
        ),
    }


def _base_geometry_hash(request: DiagramJobRequest, artifact_dir: Path) -> str:
    base_job_id = request.reuse.reuse_geometry_from
    if not base_job_id:
        return ""
    path = artifact_dir / "build" / "diagram" / "jobs" / base_job_id / "final_renderer_spec.json"
    if not path.is_file():
        return ""
    return _sha256_file(path)


def _cache_identity(
    job: DiagramJob,
    request: DiagramJobRequest,
    artifact_dir: Path,
) -> tuple[str, dict[str, object]]:
    identity = {
        "request": request_payload_for_artifact(request),
        "job_content_hash": job.content_hash,
        "base_geometry_hash": _base_geometry_hash(request, artifact_dir),
        "scene_writer_schema": SCENE_WRITER_SCHEMA_VERSION,
        "model_config": _effective_model_cache_config(request),
        "skill_bundle_version": _skill_bundle_version(),
        "workflow_code_version": _workflow_code_version(),
    }
    return _canonical_hash(identity).removeprefix("sha256:"), identity


def _cache_manifest(cache_dir: Path) -> dict[str, object]:
    path = cache_dir / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return data if data.get("schema_version") == CACHE_SCHEMA_VERSION else {}


def _valid_cache_artifacts(cache_dir: Path, cache_key: str) -> bool:
    manifest = _cache_manifest(cache_dir)
    if manifest.get("cache_key") != cache_key:
        return False
    artifacts = cache_dir / "artifacts"
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return False
    for rel, expected in files.items():
        path = artifacts / str(rel)
        if not path.is_file() or _sha256_file(path) != expected:
            return False
    try:
        workflow_result = read_json(artifacts / "workflow_result.json")
        renderer_result = read_json(artifacts / "renderer_result.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if workflow_result.get("status") != "ok" or renderer_result.get("status") != "ok":
        return False
    fragment_rel = str(
        renderer_result.get("tikz_fragment_path")
        or renderer_result.get("tikz_source_path")
        or ""
    )
    return bool(
        (artifacts / "final_renderer_spec.json").is_file()
        and fragment_rel
        and (artifacts / fragment_rel).is_file()
        and (artifacts / fragment_rel).stat().st_size > 0
    )


def _append_cache_event(job_dir: Path, event: str, cache_key: str) -> None:
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "cache_key": cache_key,
    }
    job_dir.mkdir(parents=True, exist_ok=True)
    with (job_dir / "workflow_events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _restore_cached_job(
    cache_dir: Path,
    cache_key: str,
    job_dir: Path,
    request_payload: dict[str, object],
) -> bool:
    if not _valid_cache_artifacts(cache_dir, cache_key):
        return False
    job_parent = job_dir.parent
    job_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{job_dir.name}.cache-", dir=job_parent))
    backup = job_parent / f".{job_dir.name}.previous-{os.getpid()}"
    try:
        shutil.copytree(cache_dir / "artifacts", stage, dirs_exist_ok=True)
        write_json(stage / "request.json", request_payload)
        _append_cache_event(stage, "cache.hit", cache_key)
        profile_path = stage / "performance_profile.json"
        try:
            profile = read_json(profile_path) if profile_path.exists() else {}
        except (OSError, ValueError, json.JSONDecodeError):
            profile = {}
        profile["cache"] = {"hit": True, "cache_key": cache_key}
        write_json(profile_path, profile)
        if backup.exists():
            shutil.rmtree(backup)
        if job_dir.exists():
            os.replace(job_dir, backup)
        os.replace(stage, job_dir)
        shutil.rmtree(backup, ignore_errors=True)
        return True
    except Exception:
        if backup.exists() and not job_dir.exists():
            os.replace(backup, job_dir)
        shutil.rmtree(stage, ignore_errors=True)
        return False


def _store_cached_job(
    cache_dir: Path,
    cache_key: str,
    identity: dict[str, object],
    job_dir: Path,
) -> None:
    cache_root = cache_dir.parent
    cache_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{cache_key[:12]}-", dir=cache_root))
    artifacts = temporary / "artifacts"
    try:
        shutil.copytree(job_dir, artifacts)
        files = {
            path.relative_to(artifacts).as_posix(): _sha256_file(path)
            for path in sorted(artifacts.rglob("*"))
            if path.is_file()
        }
        write_json(
            temporary / "manifest.json",
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "cache_key": cache_key,
                "identity": identity,
                "files": files,
            },
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


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


def _is_scene_payload_route(request: DiagramJobRequest) -> bool:
    return request.engine.value == "geometric_scene" and bool(request.engine_options.scene_payload)


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
    if _is_scene_payload_route(request):
        from run_diagram_workflow import run_scene_payload_workflow

        request_payload = read_json(request_path)
        run_scene_payload_workflow(request_payload, job_build_dir, emit_result=False)
    elif _is_renderer_spec_route(request):
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
            f"in-process workflow dispatch only handles scene_payload, renderer_spec, spatial, and analytic "
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
    completed = run_subprocess_streaming(
        workflow_cmd,
        cwd=SCRIPT_DIR.parent,
        event_context={"job_id": job_id},
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
    request_payload = request_payload_for_artifact(request)
    cache_key, cache_identity = _cache_identity(job, request, artifact_dir)
    cache_dir = build_dir / "cache" / cache_key

    if not dry_run and request.human_revision is None and _restore_cached_job(
        cache_dir,
        cache_key,
        job_build_dir,
        request_payload,
    ):
        renderer_result = read_json(job_build_dir / "renderer_result.json")
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="ok",
            workflow_status="ok",
            renderer_status="ok",
            tikz_fragment_path=str(renderer_result.get("tikz_fragment_path") or ""),
            tikz_source_path=str(renderer_result.get("tikz_source_path") or ""),
            cache_hit=True,
            cache_key=cache_key,
        )

    # Write v2 request
    request_path = job_build_dir / "request.json"
    write_json(request_path, request_payload)

    if dry_run:
        return DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="dry_run",
            workflow_status="dry_run",
            renderer_status="dry_run",
            cache_key=cache_key,
        )

    _append_cache_event(job_build_dir, "cache.miss", cache_key)

    # Workflow stage
    if _is_scene_payload_route(request) or _is_renderer_spec_route(request) or _is_analytic_route(request) or _is_spatial_route(request):
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
        result = DiagramBatchJobResult(
            job_id=job_id,
            slot_id=job.slot_id,
            variant=job.variant.value,
            status="ok",
            workflow_status="ok",
            renderer_status="ok",
            tikz_fragment_path=rr_tikz_fragment_path,
            tikz_source_path=rr_tikz_source_path,
            cache_key=cache_key,
        )
        if request.human_revision is None:
            _store_cached_job(
                cache_dir,
                cache_key,
                cache_identity,
                job_build_dir,
            )
        return result

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
    if jobs_filter:
        # A filtered repair run may intentionally omit an already-finalized
        # dependency (for example, rerunning only solution diagrams after the
        # prompt geometry has stabilized). Treat it as satisfied only when its
        # durable workflow result and renderer spec are both present.
        for job in manifest.jobs:
            if job.job_id in jobs_filter:
                continue
            job_dir = artifact_dir / job.out_dir
            workflow_result_path = job_dir / "workflow_result.json"
            if not workflow_result_path.is_file():
                continue
            workflow_result = read_json(workflow_result_path)
            if (
                isinstance(workflow_result, dict)
                and workflow_result.get("status") == "ok"
                and (job_dir / "final_renderer_spec.json").exists()
            ):
                completed_ok.add(job.job_id)

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
