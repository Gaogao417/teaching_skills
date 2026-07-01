#!/usr/bin/env python3
"""Thin CLI router for the agentic GeometricScene workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict

CORE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = CORE_DIR.parents[1]
sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from agent_runner import run_codex_diagram_agent  # noqa: E402
from audit import audit_diagram_action  # noqa: E402
from runtime import configure_utf8_stdio, redact_secrets  # noqa: E402
from tools import (  # noqa: E402
    _agent_cwd,
    _all_skill_inputs,
    _default_out_dir,
    _emit_event,
    _json_default,
    _normalize_workflow_request,
    _read_json,
    _validate_final_agent_artifacts,
    _write_failed_workflow_result,
    _write_json,
    compile_spec_action,
    finalize_round_action,
    render_candidate_action,
    skill_context_action,
)

configure_utf8_stdio()


def run_workflow(request: Dict[str, object], out_dir: Path, request_path: Path) -> Dict[str, object]:
    """Start the Codex diagram subagent and validate its final artifacts."""

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rounds").mkdir(exist_ok=True)
    shutil.copy2(request_path, out_dir / "request.json")
    _emit_event(
        out_dir,
        "agent.start",
        cwd=str(_agent_cwd()),
        skills=[item["name"] for item in _all_skill_inputs()],
    )
    try:
        agent_result = run_codex_diagram_agent(
            request=request,
            out_dir=out_dir.resolve(),
            request_path=(out_dir / "request.json").resolve(),
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
