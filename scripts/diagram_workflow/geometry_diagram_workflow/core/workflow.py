#!/usr/bin/env python3
"""Thin CLI router for the agentic GeometricScene workflow."""

from __future__ import annotations

import argparse
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
from diagram_contracts import ScenePayload, SceneRepairRequest  # noqa: E402
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

    audit_result_path = round_dir / "audit_result.json"
    return _run_host_stage(
        out_dir,
        timer,
        "finalize_round",
        round_index,
        lambda: finalize_round_action(
            request,
            scene_payload_path,
            render_result_path,
            renderer_spec_path,
            renderer_result_path,
            audit_result_path,
            out_dir,
            round_index,
        ),
    )


def _run_human_revision_workflow(
    request: Dict[str, object],
    out_dir: Path,
    request_path: Path,
) -> Dict[str, object]:
    """Preserve the existing full-loop Agent contract for human revisions."""

    agent_result = run_codex_diagram_agent(
        request=request,
        out_dir=out_dir.resolve(),
        request_path=request_path,
    )
    _write_json(out_dir / "agent_result.json", agent_result)
    _emit_event(
        out_dir,
        "agent.end",
        status=agent_result.get("status", ""),
        selected_round=agent_result.get("selected_round", ""),
        agent_thread_id=agent_result.get("agent_thread_id", ""),
        agent_turn_id=agent_result.get("agent_turn_id", ""),
        message=agent_result.get("message", ""),
    )
    result = _validate_final_agent_artifacts(out_dir)
    result["agent"] = {
        "thread_id": agent_result.get("agent_thread_id", ""),
        "turn_id": agent_result.get("agent_turn_id", ""),
        "duration_ms": agent_result.get("agent_duration_ms"),
        "selected_round": agent_result.get("selected_round"),
        "message": agent_result.get("message", ""),
    }
    _write_json(out_dir / "workflow_result.json", result)
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
        repair_payload: Dict[str, object] | None = None
        last_error: WorkflowStageError | None = None
        for round_index in (0, 1):
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
            try:
                _run_candidate_round(request, out_dir, round_index, scene_payload, timer)
            except WorkflowStageError as exc:
                last_error = exc
                if round_index == 0 and exc.repairable:
                    repair_payload = _repair_request(scene_payload, exc)
                    repair_path = out_dir / "rounds" / "round_1" / "repair_request.json"
                    _write_json(repair_path, repair_payload)
                    _emit_event(
                        out_dir,
                        "workflow.repair.requested",
                        round_index=1,
                        failed_stage=exc.stage,
                        fail_type=exc.fail_type,
                        repair_request=str(repair_path.relative_to(out_dir)),
                    )
                    continue
                raise

            agent_summary = {
                "status": "ok",
                "selected_round": round_index,
                "attempts": agent_attempts,
                "agent_thread_id": agent_attempts[-1].get("thread_id", ""),
                "agent_turn_id": agent_attempts[-1].get("turn_id", ""),
                "agent_duration_ms": agent_attempts[-1].get("duration_ms"),
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
