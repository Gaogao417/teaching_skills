#!/usr/bin/env python3
"""Thin CLI router for the agentic GeometricScene workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Dict

CORE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = CORE_DIR.parents[1]
sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from agent_runner import run_codex_diagram_agent  # noqa: E402
from audit import audit_diagram_action  # noqa: E402
from diagram_contracts import (  # noqa: E402
    SceneDiagramSpec,
    ScenePayload,
    SceneRepairRequest,
    VisualDecision,
)
from render_geometry_spec import render_geometry_spec  # noqa: E402
from runtime import configure_utf8_stdio, redact_secrets  # noqa: E402
from tools import (  # noqa: E402
    _agent_cwd,
    _all_skill_inputs,
    _default_out_dir,
    _emit_event,
    _json_default,
    _normalize_workflow_request,
    _prepare_solution_reuse_context,
    _read_json,
    _validate_final_agent_artifacts,
    _write_failed_workflow_result,
    _write_json,
    apply_visual_patch_action,
    compile_spec_action,
    finalize_round_action,
    render_candidate_action,
    skill_context_action,
)
from workflow_timing import StageTimer, write_profile_section  # noqa: E402

configure_utf8_stdio()


class WorkflowStageError(RuntimeError):
    def __init__(
        self,
        stage: str,
        fail_type: str,
        message: str,
        *,
        evidence: Dict[str, object] | None = None,
        repairable: bool = False,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.fail_type = fail_type
        self.evidence = evidence or {}
        self.repairable = repairable


def _run_host_stage(
    out_dir: Path,
    timer: StageTimer,
    stage: str,
    round_index: int,
    action: Callable[[], Dict[str, object]],
) -> Dict[str, object]:
    _emit_event(out_dir, "host.stage.started", stage=stage, round_index=round_index)
    started_at = time.perf_counter()
    try:
        with timer.measure(stage):
            result = action()
    except WorkflowStageError:
        raise
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        payload_error = isinstance(exc, ValueError) and stage in {
            "wolfram_render",
            "tikz_compile",
            "audit",
        }
        solution_lock_error = payload_error and (
            "locked base point" in str(exc) or "base point lock" in str(exc)
        )
        fail_type = (
            "solution_base_lock_missing"
            if solution_lock_error
            else "invalid_scene_code"
            if payload_error and stage == "wolfram_render"
            else "invalid_scene_or_renderer_payload"
            if payload_error
            else "host_environment_or_invariant_failed"
        )
        _emit_event(
            out_dir,
            "host.stage.completed",
            stage=stage,
            round_index=round_index,
            status="failed",
            duration_ms=elapsed_ms,
            error=redact_secrets(exc),
        )
        raise WorkflowStageError(
            stage,
            fail_type,
            str(exc),
            repairable=payload_error,
        ) from exc
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
    _emit_event(
        out_dir,
        "host.stage.completed",
        stage=stage,
        round_index=round_index,
        status=str(result.get("status") or "ok"),
        duration_ms=elapsed_ms,
    )
    return result


def _scene_payload_from_agent(
    request: Dict[str, object],
    agent_result: Dict[str, object],
) -> Dict[str, object]:
    if agent_result.get("status") == "needs_human_confirmation":
        question = str(agent_result.get("confirmation_question") or "").strip()
        raise WorkflowStageError(
            "scene_generation",
            "human_confirmation_required",
            question or "scene writer requires human confirmation",
            evidence={
                "confirmation_question": question,
                "rationale": str(agent_result.get("rationale") or ""),
            },
            repairable=False,
        )
    payload = {
        key: agent_result.get(key)
        for key in ("scene_code", "points", "point_roles", "diagram_spec", "rationale")
    }
    locked_base_points = request.get("locked_base_points")
    payload.update(
        {
            "solution_reuse": {
                "reuse_geometry_from": request.get("reuse_geometry_from", ""),
                "lock_strategy": "host_injected_exact_coordinates",
                "locked_base_points": locked_base_points,
            }
            if request.get("reuse_geometry_from")
            else {},
            "model_used": agent_result.get("model_used", ""),
            "raw_response": agent_result.get("raw_response", ""),
            "model_attempts": agent_result.get("model_attempts", []),
        }
    )
    return ScenePayload.model_validate(payload).model_dump(mode="json", by_alias=True)


def _audit_failure_is_repairable(issues: object) -> bool:
    if not isinstance(issues, list) or not issues:
        return False
    repairable_prefixes = (
        "invalid_scene_code:",
        "wolfram_failed:",
        "invalid_renderer_spec:",
        "renderer_spec_not_ready:",
        "invalid_point_label:",
        "bad serialized label text:",
        "label text too long:",
    )
    return any(str(issue).startswith(repairable_prefixes) for issue in issues)


def _run_candidate_round(
    request: Dict[str, object],
    out_dir: Path,
    round_index: int,
    scene_payload: Dict[str, object],
    timer: StageTimer,
) -> Dict[str, object]:
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    scene_payload_path = round_dir / "scene_payload.json"
    _write_json(scene_payload_path, scene_payload)

    render_action = _run_host_stage(
        out_dir,
        timer,
        "wolfram_render",
        round_index,
        lambda: render_candidate_action(request, scene_payload_path, out_dir, round_index),
    )
    render_result = render_action.get("render_result")
    if not isinstance(render_result, dict):
        render_result = {}
    if render_action.get("status") != "ok":
        fail_type = str(render_result.get("fail_type") or "wolfram_scene_failed")
        raise WorkflowStageError(
            "wolfram_render",
            fail_type,
            str(render_result.get("message") or "Wolfram GeometricScene solve failed"),
            evidence=render_result,
            repairable=fail_type in {
                "timeout",
                "runtime_error",
                "invalid_head",
                "random_instance_failed",
                "no_solution",
                "solution_base_point_drift",
                "wolfram_scene_failed",
            },
        )

    render_result_path = round_dir / "render_result.json"
    compile_action = _run_host_stage(
        out_dir,
        timer,
        "tikz_compile",
        round_index,
        lambda: compile_spec_action(
            request,
            scene_payload_path,
            render_result_path,
            out_dir,
            round_index,
        ),
    )
    if compile_action.get("status") != "ok":
        raise WorkflowStageError(
            "tikz_compile",
            "scene_spec_compile_failed",
            "Wolfram solved the scene but renderer spec compilation failed",
            evidence=compile_action,
            repairable=True,
        )

    renderer_spec_path = round_dir / "final_renderer_spec.json"
    variant = str(request.get("diagram_variant") or request.get("variant") or "prompt")
    renderer_result = _run_host_stage(
        out_dir,
        timer,
        "preview_render",
        round_index,
        lambda: render_geometry_spec(
            renderer_spec_path,
            round_dir,
            variant=variant if variant in {"prompt", "solution"} else "prompt",
        ),
    )
    if renderer_result.get("status") != "ok":
        fail_type = str(renderer_result.get("fail_type") or "renderer_failed")
        raise WorkflowStageError(
            "preview_render",
            fail_type,
            str(renderer_result.get("message") or "TikZ renderer failed"),
            evidence=renderer_result,
            repairable=fail_type in {"invalid_renderer_spec", "tikz_compile_failed"},
        )

    renderer_result_path = round_dir / "renderer_result.json"
    audit_action = _run_host_stage(
        out_dir,
        timer,
        "audit",
        round_index,
        lambda: audit_diagram_action(
            request,
            scene_payload_path,
            render_result_path,
            renderer_spec_path,
            renderer_result_path,
            out_dir,
            round_index,
        ),
    )
    audit_result = audit_action.get("audit_result")
    if not isinstance(audit_result, dict):
        audit_result = {}
    if audit_action.get("status") != "ok":
        issues = audit_result.get("issues", [])
        raise WorkflowStageError(
            "audit",
            "deterministic_audit_failed",
            "; ".join(str(issue) for issue in issues) or "deterministic audit failed",
            evidence=audit_result,
            repairable=_audit_failure_is_repairable(issues),
        )

    return {
        "status": "ok",
        "scene_payload_path": scene_payload_path,
        "render_result_path": render_result_path,
        "renderer_spec_path": renderer_spec_path,
        "renderer_result_path": renderer_result_path,
        "audit_result_path": round_dir / "audit_result.json",
        "audit_result": audit_result,
        "renderer_result": renderer_result,
    }


def _finalize_candidate(
    request: Dict[str, object],
    out_dir: Path,
    round_index: int,
    candidate: Dict[str, object],
    timer: StageTimer,
) -> Dict[str, object]:
    return _run_host_stage(
        out_dir,
        timer,
        "finalize_round",
        round_index,
        lambda: finalize_round_action(
            request,
            Path(candidate["scene_payload_path"]),
            Path(candidate["render_result_path"]),
            Path(candidate["renderer_spec_path"]),
            Path(candidate["renderer_result_path"]),
            Path(candidate["audit_result_path"]),
            out_dir,
            round_index,
        ),
    )


def preview_candidate_action(
    request: Dict[str, object],
    scene_payload_path: Path,
    render_result_path: Path,
    out_dir: Path,
    round_index: int,
    visual_patch_path: Path | None = None,
) -> Dict[str, object]:
    """Compile, render and audit one already-solved candidate without invoking an Agent."""

    round_dir = out_dir / "rounds" / f"round_{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = round_dir / "preview_attempts.json"
    attempts: list[object] = []
    if attempts_path.is_file():
        loaded = _read_json(attempts_path)
        if isinstance(loaded.get("attempts"), list):
            attempts = list(loaded["attempts"])
    if len(attempts) >= 2:
        result = {
            "status": "needs_human_confirmation",
            "action": "preview",
            "round_index": round_index,
            "fail_type": "preview_revision_budget_exhausted",
            "message": "preview remained invalid after one visual adjustment",
            "attempt_count": len(attempts),
        }
        _write_json(round_dir / "preview_result.json", result)
        return result

    result: Dict[str, object]
    try:
        compile_result = compile_spec_action(
            request,
            scene_payload_path,
            render_result_path,
            out_dir,
            round_index,
        )
        renderer_spec_path = round_dir / "final_renderer_spec.json"
        patch_result: Dict[str, object] = {}
        if visual_patch_path is not None:
            patch_result = apply_visual_patch_action(
                renderer_spec_path,
                visual_patch_path,
                out_dir,
                round_index,
            )
        variant = str(request.get("diagram_variant") or request.get("variant") or "prompt")
        renderer_result = render_geometry_spec(
            renderer_spec_path,
            round_dir,
            variant=variant if variant in {"prompt", "solution"} else "prompt",
        )
        renderer_result_path = round_dir / "renderer_result.json"
        audit_result = audit_diagram_action(
            request,
            scene_payload_path,
            render_result_path,
            renderer_spec_path,
            renderer_result_path,
            out_dir,
            round_index,
        )
        preview_png_path = str(renderer_result.get("preview_png_path") or "")
        result = {
            "status": "ok" if audit_result.get("status") == "ok" else "failed",
            "action": "preview",
            "round_index": round_index,
            "compile_spec": compile_result,
            "visual_patch": patch_result,
            "renderer_result": renderer_result,
            "audit_result": audit_result.get("audit_result", {}),
            "renderer_spec_path": str(renderer_spec_path),
            "renderer_result_path": str(renderer_result_path),
            "audit_result_path": str(round_dir / "audit_result.json"),
            "preview_png_path": str(round_dir / preview_png_path) if preview_png_path else "",
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "action": "preview",
            "round_index": round_index,
            "fail_type": "preview_pipeline_failed",
            "message": redact_secrets(exc),
        }

    attempts.append(
        {
            "attempt": len(attempts) + 1,
            "status": result.get("status", "failed"),
            "used_visual_patch": visual_patch_path is not None,
            "fail_type": result.get("fail_type", ""),
        }
    )
    _write_json(attempts_path, {"attempts": attempts})
    result["attempt_count"] = len(attempts)
    if result.get("status") != "ok" and len(attempts) >= 2:
        result["status"] = "needs_human_confirmation"
        result["fail_type"] = "preview_revision_budget_exhausted"
    _write_json(round_dir / "preview_result.json", result)
    return result


def _execution_policy(request: Dict[str, object]) -> tuple[int, bool]:
    plan = request.get("execution_plan")
    if not isinstance(plan, dict):
        return 2, False
    return (
        max(1, min(4, int(plan.get("max_candidate_rounds", 2)))),
        bool(plan.get("requires_visual_decision", False)),
    )


def _preview_path(out_dir: Path, round_index: int, renderer_result: Dict[str, object]) -> Path:
    value = str(renderer_result.get("preview_png_path") or "")
    if not value:
        raise WorkflowStageError(
            "visual_decision",
            "preview_missing",
            "visual decision requires renderer_result.preview_png_path",
            repairable=False,
        )
    path = Path(value)
    if not path.is_absolute():
        path = out_dir / "rounds" / f"round_{round_index}" / path
    if not path.is_file():
        raise WorkflowStageError(
            "visual_decision",
            "preview_missing",
            f"visual decision preview does not exist: {path}",
            repairable=False,
        )
    return path


def _visual_decision_from_agent_result(
    agent_result: Dict[str, object],
) -> VisualDecision:
    """Validate only the visual contract, leaving SDK telemetry out of it."""

    contract_payload = {
        field: agent_result[field]
        for field in VisualDecision.model_fields
        if field in agent_result
    }
    return VisualDecision.model_validate(contract_payload)


def _apply_visual_patch(
    scene_payload: Dict[str, object],
    decision_payload: Dict[str, object],
) -> Dict[str, object]:
    decision = _visual_decision_from_agent_result(decision_payload)
    if decision.decision != "revise":
        return scene_payload
    updated = dict(scene_payload)
    if decision.patch.scene_code:
        updated["scene_code"] = decision.patch.scene_code
    if decision.patch.diagram_spec_json:
        raw_spec = json.loads(decision.patch.diagram_spec_json)
        if not isinstance(raw_spec, dict):
            raise ValueError("visual diagram_spec patch must decode to an object")
        forbidden = {"engine", "coordinate_policy", "points", "paths", "round_index"}
        # Visual turns often echo a complete renderer schema. Ignore fields
        # outside their authority while retaining safe label/marker changes.
        for field in forbidden:
            raw_spec.pop(field, None)
        updated["diagram_spec"] = SceneDiagramSpec.model_validate(raw_spec).model_dump(
            mode="json",
            by_alias=True,
        )
    return ScenePayload.model_validate(updated).model_dump(mode="json", by_alias=True)


def _run_human_revision_workflow(
    request: Dict[str, object],
    out_dir: Path,
    request_path: Path,
) -> Dict[str, object]:
    """Run a fixed human revision through the same Host-owned candidate tail."""

    revision = request.get("human_revision")
    if not isinstance(revision, dict):
        raise ValueError("human revision payload is required")
    base_round = int(revision.get("base_round", -1))
    requested_round = int(revision.get("requested_round", -1))
    if requested_round <= base_round:
        raise ValueError("requested human revision Round must follow the base Round")
    base_dir = out_dir / "rounds" / f"round_{base_round}"
    base_scene_path = base_dir / "scene_payload.json"
    base_preview = base_dir / "rendered" / "prompt.preview.png"
    if not base_scene_path.is_file() or not base_preview.is_file():
        raise WorkflowStageError(
            "scene_generation",
            "human_revision_base_missing",
            f"human revision base Round {base_round} is incomplete",
            repairable=False,
        )
    base_scene = _read_json(base_scene_path)
    timer = StageTimer()
    repair_payload = {
        "schema_version": "diagram-human-revision-authoring/v1",
        "failure_type": "human_feedback",
        "message": str(revision.get("feedback") or ""),
        "failed_checks": [str(revision.get("feedback") or "")],
        "previous_scene_payload": base_scene,
        "repair_instruction": (
            "Preserve the base construction and make only the change requested by the teacher. "
            "Return scene data only; the Host owns solve, render, audit, visual review, and publish."
        ),
    }
    _emit_event(
        out_dir,
        "workflow.state.changed",
        state="authoring",
        mode="human_revision",
        round_index=requested_round,
    )
    with timer.measure("scene_generation"):
        agent_result = run_codex_diagram_agent(
            request=request,
            out_dir=out_dir.resolve(),
            request_path=request_path,
            repair_request=repair_payload,
            force_scene_writer=True,
            authoring_preview_path=base_preview,
        )
    scene_payload = _scene_payload_from_agent(request, agent_result)
    candidate = _run_candidate_round(
        request,
        out_dir,
        requested_round,
        scene_payload,
        timer,
    )
    current_preview = _preview_path(
        out_dir,
        requested_round,
        candidate["renderer_result"],
    )
    _emit_event(
        out_dir,
        "workflow.state.changed",
        state="visual_decision",
        mode="human_revision",
        round_index=requested_round,
    )
    visual = _run_host_stage(
        out_dir,
        timer,
        "visual_decision",
        requested_round,
        lambda: run_codex_diagram_agent(
            request=request,
            out_dir=out_dir.resolve(),
            request_path=request_path,
            visual_context={
                "scene_payload": scene_payload,
                "audit_result": candidate["audit_result"],
                "preview_image_path": str(current_preview),
            },
        ),
    )
    decision = _visual_decision_from_agent_result(visual)
    visual_path = out_dir / "rounds" / f"round_{requested_round}" / "visual_decision.json"
    _write_json(visual_path, decision.model_dump(mode="json", by_alias=True))
    if decision.decision != "accept":
        raise WorkflowStageError(
            "visual_decision",
            "visual_revision_budget_exhausted",
            decision.reason,
            repairable=False,
        )
    _write_json(
        out_dir / "rounds" / f"round_{requested_round}" / "visual_inspection.json",
        {
            "schema_version": "diagram-visual-inspection/v1",
            "status": "pass",
            "base_round": base_round,
            "requested_round": requested_round,
            "inspection_count": 2,
            "base_preview_sha256": hashlib.sha256(base_preview.read_bytes()).hexdigest(),
            "current_preview_sha256": hashlib.sha256(current_preview.read_bytes()).hexdigest(),
            "source": "host_attached_visual_turns",
        },
    )
    _finalize_candidate(request, out_dir, requested_round, candidate, timer)
    summary = {
        "status": "ok",
        "selected_round": requested_round,
        "agent_thread_id": agent_result.get("agent_thread_id", ""),
        "agent_turn_id": agent_result.get("agent_turn_id", ""),
        "agent_duration_ms": agent_result.get("agent_duration_ms"),
        "message": "human revision authored by Agent and finalized by Host",
    }
    _write_json(out_dir / "agent_result.json", summary)
    result = _validate_final_agent_artifacts(out_dir)
    result["agent"] = summary
    _write_json(out_dir / "workflow_result.json", result)
    write_profile_section(
        out_dir,
        "host_workflow",
        timer,
        job_id=str(request.get("diagram_job_id") or request.get("job_id") or ""),
        route="geometric_scene_host_human_revision",
    )
    return result


def _normal_agent_record(agent_result: Dict[str, object], round_index: int) -> Dict[str, object]:
    return {
        "round_index": round_index,
        "thread_id": agent_result.get("agent_thread_id", ""),
        "turn_id": agent_result.get("agent_turn_id", ""),
        "duration_ms": agent_result.get("agent_duration_ms"),
        "model": agent_result.get("model_used", ""),
        "status": "ok",
    }


def _repair_request(
    scene_payload: Dict[str, object],
    error: WorkflowStageError,
) -> Dict[str, object]:
    evidence_checks = error.evidence.get("issues", [])
    if not isinstance(evidence_checks, list):
        evidence_checks = []
    if not evidence_checks:
        evidence_checks = [f"{error.stage}: {error.fail_type}: {error}"]
    payload = SceneRepairRequest(
        failure_type=error.fail_type,
        message=str(error),
        failed_checks=[str(item) for item in evidence_checks],
        previous_scene_payload=ScenePayload.model_validate(scene_payload),
        repair_instruction=(
            "Preserve all correct givens and visible objects. Change only the scene constraints "
            "or diagram_spec fields implicated by the deterministic failure evidence."
        ),
    )
    return payload.model_dump(mode="json", by_alias=True)


def run_workflow(request: Dict[str, object], out_dir: Path, request_path: Path) -> Dict[str, object]:
    """Run normal scene authoring with a deterministic Host-owned lifecycle."""

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rounds").mkdir(exist_ok=True)
    shutil.copy2(request_path, out_dir / "request.json")
    _emit_event(
        out_dir,
        "agent.start",
        cwd=str(_agent_cwd()),
        skills=[
            item["name"]
            for item in _all_skill_inputs(
                include_revision=isinstance(request.get("human_revision"), dict)
            )
        ],
    )
    copied_request_path = (out_dir / "request.json").resolve()
    timer: StageTimer | None = None
    agent_attempts: list[Dict[str, object]] = []
    try:
        if isinstance(request.get("human_revision"), dict):
            return _run_human_revision_workflow(
                request,
                out_dir,
                copied_request_path,
            )

        timer = StageTimer()
        try:
            request = _prepare_solution_reuse_context(request, out_dir)
        except (OSError, ValueError) as exc:
            raise WorkflowStageError(
                "solution_reuse_prepare",
                "host_environment_or_invariant_failed",
                str(exc),
                repairable=False,
            ) from exc
        if request.get("locked_base_points"):
            _emit_event(
                out_dir,
                "host.solution_reuse.prepared",
                reuse_geometry_from=request.get("reuse_geometry_from", ""),
                locked_point_count=len(request["locked_base_points"]),
            )
        max_candidates, requires_visual_decision = _execution_policy(request)
        repair_payload: Dict[str, object] | None = None
        patched_scene_payload: Dict[str, object] | None = None
        last_error: WorkflowStageError | None = None
        for round_index in range(max_candidates):
            _emit_event(
                out_dir,
                "workflow.state.changed",
                state="authoring",
                round_index=round_index,
            )
            if patched_scene_payload is None:
                _emit_event(
                    out_dir,
                    "agent.stage.started",
                    stage="scene_generation",
                    round_index=round_index,
                )
                started_at = time.perf_counter()
                try:
                    with timer.measure("scene_generation"):
                        agent_result = run_codex_diagram_agent(
                            request=request,
                            out_dir=out_dir.resolve(),
                            request_path=copied_request_path,
                            repair_request=repair_payload,
                        )
                except Exception as exc:
                    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
                    _emit_event(
                        out_dir,
                        "agent.stage.completed",
                        stage="scene_generation",
                        round_index=round_index,
                        status="failed",
                        duration_ms=elapsed_ms,
                        error=redact_secrets(exc),
                    )
                    raise WorkflowStageError(
                        "scene_generation",
                        "codex_scene_writer_failed",
                        str(exc),
                        repairable=False,
                    ) from exc
                elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
                _emit_event(
                    out_dir,
                    "agent.stage.completed",
                    stage="scene_generation",
                    round_index=round_index,
                    status="ok",
                    duration_ms=elapsed_ms,
                    agent_thread_id=agent_result.get("agent_thread_id", ""),
                    agent_turn_id=agent_result.get("agent_turn_id", ""),
                )
                agent_attempts.append(_normal_agent_record(agent_result, round_index))
                scene_payload = _scene_payload_from_agent(request, agent_result)
            else:
                scene_payload = patched_scene_payload
                patched_scene_payload = None
                repair_payload = None

            try:
                candidate = _run_candidate_round(
                    request,
                    out_dir,
                    round_index,
                    scene_payload,
                    timer,
                )
            except WorkflowStageError as exc:
                last_error = exc
                syntax_repair_types = {
                    "invalid_scene_code",
                    "runtime_error",
                    "invalid_head",
                }
                if (
                    exc.fail_type in syntax_repair_types
                    and round_index == 0
                    and round_index + 1 < max_candidates
                ):
                    repair_payload = _repair_request(scene_payload, exc)
                    repair_path = (
                        out_dir
                        / "rounds"
                        / f"round_{round_index + 1}"
                        / "repair_request.json"
                    )
                    _write_json(repair_path, repair_payload)
                    _emit_event(
                        out_dir,
                        "workflow.syntax_repair.requested",
                        round_index=round_index + 1,
                        failed_stage=exc.stage,
                        fail_type=exc.fail_type,
                        repair_request=str(repair_path.relative_to(out_dir)),
                    )
                    continue
                if exc.repairable:
                    _emit_event(
                        out_dir,
                        "workflow.human_confirmation.required",
                        round_index=round_index,
                        failed_stage=exc.stage,
                        original_fail_type=exc.fail_type,
                        question=(
                            "Please confirm or simplify the supplied geometry/Wolfram "
                            f"condition after {exc.fail_type}: {exc}"
                        ),
                    )
                    raise WorkflowStageError(
                        exc.stage,
                        "human_confirmation_required",
                        (
                            "geometry authoring stopped without semantic repair; "
                            f"original failure {exc.fail_type}: {exc}"
                        ),
                        evidence={
                            "original_fail_type": exc.fail_type,
                            "original_evidence": exc.evidence,
                        },
                        repairable=False,
                    ) from exc
                raise

            if requires_visual_decision:
                preview = _preview_path(
                    out_dir,
                    round_index,
                    candidate["renderer_result"],
                )
                _emit_event(
                    out_dir,
                    "workflow.state.changed",
                    state="visual_decision",
                    round_index=round_index,
                )
                visual = _run_host_stage(
                    out_dir,
                    timer,
                    "visual_decision",
                    round_index,
                    lambda: run_codex_diagram_agent(
                        request=request,
                        out_dir=out_dir.resolve(),
                        request_path=copied_request_path,
                        visual_context={
                            "scene_payload": scene_payload,
                            "audit_result": candidate["audit_result"],
                            "preview_image_path": str(preview),
                        },
                    ),
                )
                decision = _visual_decision_from_agent_result(visual)
                visual_path = out_dir / "rounds" / f"round_{round_index}" / "visual_decision.json"
                _write_json(visual_path, decision.model_dump(mode="json", by_alias=True))
                if decision.decision == "revise":
                    if round_index + 1 >= max_candidates:
                        raise WorkflowStageError(
                            "visual_decision",
                            "visual_revision_budget_exhausted",
                            decision.reason,
                            evidence=decision.model_dump(mode="json"),
                            repairable=False,
                        )
                    try:
                        patched_scene_payload = _apply_visual_patch(scene_payload, visual)
                    except ValueError as exc:
                        _emit_event(
                            out_dir,
                            "workflow.human_confirmation.required",
                            round_index=round_index,
                            failed_stage="visual_decision",
                            original_fail_type="invalid_visual_patch",
                            question=str(exc),
                        )
                        raise WorkflowStageError(
                            "visual_decision",
                            "human_confirmation_required",
                            f"visual patch was invalid and was not semantically repaired: {exc}",
                            evidence=decision.model_dump(mode="json"),
                            repairable=False,
                        )
                    _emit_event(
                        out_dir,
                        "workflow.visual_revision.requested",
                        round_index=round_index + 1,
                        reason=decision.reason,
                    )
                    continue

            _finalize_candidate(request, out_dir, round_index, candidate, timer)
            _emit_event(
                out_dir,
                "workflow.state.changed",
                state="finalized",
                round_index=round_index,
            )
            latest_attempt = agent_attempts[-1] if agent_attempts else {}
            agent_summary = {
                "status": "ok",
                "selected_round": round_index,
                "attempts": agent_attempts,
                "agent_thread_id": latest_attempt.get("thread_id", ""),
                "agent_turn_id": latest_attempt.get("turn_id", ""),
                "agent_duration_ms": latest_attempt.get("duration_ms"),
                "message": "scene authored by Agent and finalized by Host",
            }
            _write_json(out_dir / "agent_result.json", agent_summary)
            _emit_event(
                out_dir,
                "agent.end",
                status="ok",
                selected_round=round_index,
                attempt_count=len(agent_attempts),
            )
            result = _validate_final_agent_artifacts(out_dir)
            result["agent"] = agent_summary
            _write_json(out_dir / "workflow_result.json", result)
            write_profile_section(
                out_dir,
                "host_workflow",
                timer,
                job_id=str(request.get("diagram_job_id") or request.get("job_id") or ""),
                route="geometric_scene_host",
            )
            return result
        if last_error is not None:
            raise last_error
        raise WorkflowStageError(
            "scene_generation",
            "scene_writer_exhausted",
            "scene writer exhausted without a finalized round",
        )
    except WorkflowStageError as exc:
        _emit_event(
            out_dir,
            "agent.end",
            status="failed",
            failed_stage=exc.stage,
            fail_type=exc.fail_type,
            error=redact_secrets(exc),
        )
        result = _write_failed_workflow_result(
            out_dir,
            request,
            exc.fail_type,
            str(exc),
        )
        _write_json(
            out_dir / "agent_result.json",
            {
                "status": "failed",
                "selected_round": max(0, len(agent_attempts) - 1),
                "attempts": agent_attempts,
                "agent_thread_id": agent_attempts[-1].get("thread_id", "")
                if agent_attempts
                else "",
                "agent_turn_id": agent_attempts[-1].get("turn_id", "")
                if agent_attempts
                else "",
                "agent_duration_ms": agent_attempts[-1].get("duration_ms")
                if agent_attempts
                else None,
                "failed_stage": exc.stage,
                "fail_type": exc.fail_type,
                "message": redact_secrets(exc),
            },
        )
        if timer is not None:
            write_profile_section(
                out_dir,
                "host_workflow",
                timer,
                job_id=str(request.get("diagram_job_id") or request.get("job_id") or ""),
                route="geometric_scene_host",
            )
        return result
    except Exception as exc:
        _emit_event(out_dir, "agent.end", status="failed", error=redact_secrets(exc))
        return _write_failed_workflow_result(
            out_dir,
            request,
            "codex_diagram_agent_failed",
            str(exc),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agentic GeometricScene workflow")
    parser.add_argument(
        "--action",
        choices=[
            "run",
            "render",
            "preview",
            "compile_spec",
            "audit",
            "finalize_round",
            "skill_context",
        ],
        default="run",
        help="workflow action; run starts the Codex diagram subagent",
    )
    parser.add_argument("--request", help="workflow request JSON path")
    parser.add_argument("--out", help="output directory")
    parser.add_argument("--round-index", type=int, default=0, help="round index for single-step actions")
    parser.add_argument("--scene-payload", help="scene_payload.json path for render action")
    parser.add_argument("--render-result", help="render_result.json path for compile/audit/finalize actions")
    parser.add_argument("--renderer-spec", help="final_renderer_spec.json path for audit/finalize actions")
    parser.add_argument("--renderer-result", help="renderer_result.json path for audit/finalize actions")
    parser.add_argument("--audit-result", help="audit_result.json path for finalize action")
    parser.add_argument("--visual-patch", help="visual_patch.json path for preview action")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else _default_out_dir("workflow")

    try:
        if args.action == "skill_context":
            result = skill_context_action(out_dir)
        else:
            if not args.request:
                raise ValueError("--request is required for this action")
            request_path = Path(args.request)
            if not request_path.exists():
                raise FileNotFoundError(f"Request file not found: {request_path}")
            request = _normalize_workflow_request(_read_json(request_path))

            if args.action == "run":
                result = run_workflow(request, out_dir, request_path)
            elif args.action == "render":
                if not args.scene_payload:
                    raise ValueError("--scene-payload is required for render action")
                result = render_candidate_action(
                    request,
                    Path(args.scene_payload),
                    out_dir,
                    args.round_index,
                )
            elif args.action == "compile_spec":
                if not args.scene_payload or not args.render_result:
                    raise ValueError("--scene-payload and --render-result are required for compile_spec action")
                result = compile_spec_action(
                    request,
                    Path(args.scene_payload),
                    Path(args.render_result),
                    out_dir,
                    args.round_index,
                )
            elif args.action == "preview":
                if not args.scene_payload or not args.render_result:
                    raise ValueError(
                        "--scene-payload and --render-result are required for preview action"
                    )
                result = preview_candidate_action(
                    request,
                    Path(args.scene_payload),
                    Path(args.render_result),
                    out_dir,
                    args.round_index,
                    Path(args.visual_patch) if args.visual_patch else None,
                )
            elif args.action == "audit":
                if not (
                    args.scene_payload
                    and args.render_result
                    and args.renderer_spec
                    and args.renderer_result
                ):
                    raise ValueError(
                        "--scene-payload, --render-result, --renderer-spec, and "
                        "--renderer-result are required for audit action"
                    )
                result = audit_diagram_action(
                    request,
                    Path(args.scene_payload),
                    Path(args.render_result),
                    Path(args.renderer_spec),
                    Path(args.renderer_result),
                    out_dir,
                    args.round_index,
                )
            elif args.action == "finalize_round":
                if not (
                    args.scene_payload
                    and args.render_result
                    and args.renderer_spec
                    and args.renderer_result
                    and args.audit_result
                ):
                    raise ValueError(
                        "--scene-payload, --render-result, --renderer-spec, "
                        "--renderer-result, and --audit-result are required for "
                        "finalize_round action"
                    )
                result = finalize_round_action(
                    request,
                    Path(args.scene_payload),
                    Path(args.render_result),
                    Path(args.renderer_spec),
                    Path(args.renderer_result),
                    Path(args.audit_result),
                    out_dir,
                    args.round_index,
                )
            else:
                raise ValueError(f"Unknown action: {args.action}")
    except Exception as exc:
        print(json.dumps({"status": "error", "message": redact_secrets(exc)}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, default=_json_default))


if __name__ == "__main__":
    main()
