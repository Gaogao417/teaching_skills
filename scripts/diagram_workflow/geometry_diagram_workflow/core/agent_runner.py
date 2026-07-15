from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import shutil
import tempfile
import time
from pathlib import Path
from queue import Empty
from typing import Dict, List

from agent_prompt import agent_result_schema, diagram_agent_prompt
from runtime import redact_secrets
from tools import (
    _agent_cwd,
    _all_skill_names,
    _extract_json_object,
    _float_config,
    _emit_event,
    _resolved_codex_config,
    _skill_inputs_for_request,
)


def _value(value: object) -> object:
    return getattr(value, "value", value)


def _item_root(item: object) -> object:
    return getattr(item, "root", item)


def _stage_for_item(item: object) -> str:
    item_type = str(_value(getattr(item, "type", "unknown")))
    if item_type == "commandExecution":
        command = str(getattr(item, "command", ""))
        if "--action render" in command:
            return "wolfram_render"
        if "--action compile_spec" in command:
            return "tikz_compile"
        if "--action audit" in command:
            return "audit"
        if "--action finalize_round" in command:
            return "finalize_round"
        if "render_geometry_spec.py" in command:
            return "preview_render"
        return "tool_execution"
    return {
        "reasoning": "agent_reasoning",
        "agentMessage": "agent_message",
        "mcpToolCall": "mcp_tool",
        "dynamicToolCall": "dynamic_tool",
        "fileChange": "file_change",
        "webSearch": "web_search",
        "imageView": "preview_inspection",
        "imageGeneration": "image_generation",
        "plan": "agent_plan",
    }.get(item_type, item_type or "unknown")


def _notification_progress_event(notification: object) -> Dict[str, object] | None:
    """Translate SDK lifecycle notifications into safe operational events.

    Reasoning text, command strings, tool arguments, and command output are
    deliberately excluded.  The event stream is for progress monitoring, not
    for replaying the subagent's private working context.
    """

    method = str(getattr(notification, "method", ""))
    if method not in {"item/started", "item/completed"}:
        return None
    payload = getattr(notification, "payload", None)
    item = _item_root(getattr(payload, "item", None))
    item_type = str(_value(getattr(item, "type", "unknown")))
    lifecycle = "started" if method == "item/started" else "completed"
    event: Dict[str, object] = {
        "event": f"agent.stage.{lifecycle}",
        "stage": _stage_for_item(item),
        "item_type": item_type,
        "item_id": str(getattr(item, "id", "")),
    }
    if lifecycle == "completed":
        status = _value(getattr(item, "status", "completed"))
        event["status"] = str(status or "completed")
        for source, target in (("duration_ms", "duration_ms"), ("exit_code", "exit_code")):
            value = getattr(item, source, None)
            if value is not None:
                event[target] = value
    return event


def _heartbeat_fields(
    *,
    started_at: float,
    last_progress_at: float,
    now: float,
    process_pid: int | None,
    stage: str,
) -> Dict[str, object]:
    idle_s = max(0.0, now - last_progress_at)
    if idle_s >= 300:
        health = "suspected_stall"
    elif idle_s >= 120:
        health = "quiet"
    else:
        health = "active"
    return {
        "elapsed_s": round(max(0.0, now - started_at), 1),
        "idle_s": round(idle_s, 1),
        "pid": process_pid,
        "stage": stage,
        "status": "running",
        "health": health,
    }


def _final_agent_response(items: List[object]) -> str | None:
    unknown_phase_response: str | None = None
    for wrapped in reversed(items):
        item = _item_root(wrapped)
        if str(_value(getattr(item, "type", ""))) != "agentMessage":
            continue
        text = str(getattr(item, "text", ""))
        phase = _value(getattr(item, "phase", None))
        if phase == "final_answer":
            return text
        if phase in (None, "") and unknown_phase_response is None:
            unknown_phase_response = text
    return unknown_phase_response


def _write_codex_task_sidecar(out_dir: str, review_id: str, thread_id: str) -> None:
    if not out_dir or not review_id or not thread_id:
        return
    payload = {
        "schema_version": "diagram-codex-task/v1",
        "review_id": review_id,
        "agent_thread_id": thread_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    path = Path(out_dir) / "human_reviews" / f"{review_id}.codex-task.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_bytes(encoded)
    try:
        try:
            os.link(temporary, path)
            return
        except FileExistsError:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing == payload:
                return
            raise RuntimeError(f"Codex task sidecar conflict for {review_id}")
    finally:
        temporary.unlink(missing_ok=True)


def _human_revision_context(request: Dict[str, object]) -> Dict[str, object]:
    revision = request.get("human_revision")
    if request.get("schema_version") != "diagram-job-request/v2" or not isinstance(revision, dict):
        return {}
    review_id = str(revision.get("review_id") or "")
    requested_round = revision.get("requested_round")
    base_round = revision.get("base_round")
    job_id = str(request.get("job_id") or request.get("diagram_job_id") or "")
    if (
        not review_id.startswith("review_")
        or not job_id
        or not isinstance(requested_round, int)
        or not isinstance(base_round, int)
    ):
        return {}
    return {
        "out_dir": str(request.get("_agent_out_dir") or ""),
        "job_id": job_id,
        "review_id": review_id,
        "base_round": base_round,
        "requested_round": requested_round,
    }


def _record_preview_inspection(
    *,
    out_dir: str,
    base_round: int,
    requested_round: int,
    inspection_count: int,
) -> None:
    """Record SDK-observed image views against the exact preview bytes.

    This sidecar is written by the host worker, not by the diagram agent. The
    finalizer compares both hashes again, so rerendering invalidates stale
    inspection evidence until the agent opens the new preview.
    """

    root = Path(out_dir)
    base_preview = root / "rounds" / f"round_{base_round}" / "rendered" / "prompt.preview.png"
    current_preview = (
        root / "rounds" / f"round_{requested_round}" / "rendered" / "prompt.preview.png"
    )
    if inspection_count < 2 or not base_preview.is_file() or not current_preview.is_file():
        return
    payload = {
        "schema_version": "diagram-visual-inspection/v1",
        "status": "pass",
        "base_round": base_round,
        "requested_round": requested_round,
        "inspection_count": inspection_count,
        "base_preview_sha256": hashlib.sha256(base_preview.read_bytes()).hexdigest(),
        "current_preview_sha256": hashlib.sha256(current_preview.read_bytes()).hexdigest(),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    path = root / "rounds" / f"round_{requested_round}" / "visual_inspection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _codex_agent_worker(
    queue: mp.Queue,
    *,
    prompt: str,
    output_schema: Dict[str, object],
    cwd: str,
    model: str,
    codex_bin: str,
    skill_inputs: List[Dict[str, str]],
    out_dir: str = "",
    job_id: str = "",
    review_id: str = "",
    base_round: int | None = None,
    requested_round: int | None = None,
) -> None:
    temp_codex_home = ""
    try:
        from openai_codex import (
            ApprovalMode,
            Codex,
            CodexConfig,
            Sandbox,
            SkillInput,
            TextInput,
        )
        from openai_codex.generated.v2_all import (
            ItemCompletedNotification,
            ThreadSource,
            ThreadTokenUsageUpdatedNotification,
            TurnCompletedNotification,
        )

        source_codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
        env = os.environ.copy()
        persistent_thread = bool(review_id and out_dir and requested_round is not None)
        if persistent_thread:
            env["CODEX_HOME"] = str(source_codex_home)
        else:
            temp_codex_home = tempfile.mkdtemp(prefix="diagram-agent-codex-home-")
            for name in ("auth.json", "config.toml"):
                source_path = source_codex_home / name
                if source_path.exists():
                    shutil.copy2(source_path, Path(temp_codex_home) / name)
            env["CODEX_HOME"] = temp_codex_home

        config = CodexConfig(
            codex_bin=codex_bin or None,
            cwd=cwd,
            env=env,
        )
        run_input: list[object] = [
            SkillInput(name=item["name"], path=item["path"])
            for item in skill_inputs
        ]
        run_input.append(TextInput(prompt))

        with Codex(config=config) as codex:
            thread_start_options = {
                "approval_mode": ApprovalMode.deny_all,
                "cwd": cwd,
                "ephemeral": not persistent_thread,
                "model": model or None,
                "sandbox": Sandbox.full_access,
            }
            if persistent_thread:
                thread_start_options["thread_source"] = ThreadSource.user
            thread = codex.thread_start(
                **thread_start_options,
            )
            if persistent_thread:
                _write_codex_task_sidecar(out_dir, review_id, str(thread.id))
            queue.put(
                {
                    "kind": "progress",
                    "event": "agent.thread.started",
                    "thread_id": thread.id,
                }
            )
            if persistent_thread:
                safe_job_id = job_id[:42]
                task_name = f"几何图修订 · {safe_job_id} · Round {requested_round}"[:80]
                thread.set_name(task_name)
            turn = thread.turn(
                run_input,
                approval_mode=ApprovalMode.deny_all,
                cwd=cwd,
                model=model or None,
                output_schema=output_schema,
                sandbox=Sandbox.full_access,
            )
            queue.put(
                {
                    "kind": "progress",
                    "event": "agent.turn.started",
                    "thread_id": thread.id,
                    "turn_id": turn.id,
                }
            )
            items: List[object] = []
            preview_inspection_count = 0
            completed = None
            usage = None
            stream = turn.stream()
            try:
                for notification in stream:
                    progress = _notification_progress_event(notification)
                    if progress is not None:
                        queue.put({"kind": "progress", **progress})
                    payload = notification.payload
                    if (
                        notification.method == "item/completed"
                        and _stage_for_item(_item_root(getattr(payload, "item", None)))
                        == "preview_inspection"
                    ):
                        preview_inspection_count += 1
                        if (
                            persistent_thread
                            and base_round is not None
                            and requested_round is not None
                        ):
                            _record_preview_inspection(
                                out_dir=out_dir,
                                base_round=base_round,
                                requested_round=requested_round,
                                inspection_count=preview_inspection_count,
                            )
                    if isinstance(payload, ItemCompletedNotification) and payload.turn_id == turn.id:
                        items.append(payload.item)
                    elif (
                        isinstance(payload, ThreadTokenUsageUpdatedNotification)
                        and payload.turn_id == turn.id
                    ):
                        usage = payload.token_usage
                    elif isinstance(payload, TurnCompletedNotification) and payload.turn.id == turn.id:
                        completed = payload.turn
            finally:
                stream.close()
            if completed is None:
                raise RuntimeError("turn completed event not received")
            status = str(_value(completed.status))
            queue.put(
                {
                    "kind": "progress",
                    "event": "agent.turn.completed",
                    "thread_id": thread.id,
                    "turn_id": turn.id,
                    "status": status,
                    "duration_ms": completed.duration_ms,
                }
            )
            if status == "failed":
                message = getattr(getattr(completed, "error", None), "message", "")
                raise RuntimeError(message or f"turn failed with status {status}")
            final_response = _final_agent_response(items)
        queue.put(
            {
                "kind": "result",
                "status": "ok",
                "thread_id": thread.id,
                "turn_id": turn.id,
                "duration_ms": completed.duration_ms,
                "final_response": final_response or "{}",
                "usage": usage.model_dump(mode="json", by_alias=True) if usage else None,
            }
        )
    except Exception as exc:
        queue.put(
            {
                "kind": "result",
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error": redact_secrets(exc),
            }
        )
    finally:
        if temp_codex_home:
            shutil.rmtree(temp_codex_home, ignore_errors=True)


def run_codex_diagram_agent(
    *,
    request: Dict[str, object],
    out_dir: Path,
    request_path: Path,
) -> Dict[str, object]:
    model_config = request.get("model_config", {})
    if not isinstance(model_config, dict):
        model_config = {}
    config = _resolved_codex_config(model_config)
    timeout_s = _float_config(model_config, "codex_timeout_s", 600)
    heartbeat_s = max(5.0, _float_config(model_config, "progress_heartbeat_s", 30))
    queue: mp.Queue = mp.Queue()
    is_human_revision = isinstance(request.get("human_revision"), dict)
    skill_inputs = _skill_inputs_for_request(request)
    prompt = diagram_agent_prompt(
        request,
        out_dir,
        request_path,
        skill_names=_all_skill_names(include_revision=is_human_revision),
    )
    revision_context = _human_revision_context({**request, "_agent_out_dir": str(out_dir)})
    process = mp.Process(
        target=_codex_agent_worker,
        kwargs={
            "queue": queue,
            "prompt": prompt,
            "output_schema": agent_result_schema(),
            "cwd": str(_agent_cwd()),
            "model": str(config.get("codex_model") or ""),
            "codex_bin": str(config.get("codex_bin") or ""),
            "skill_inputs": skill_inputs,
            **revision_context,
        },
    )
    process.start()
    started_at = time.monotonic()
    last_progress_at = started_at
    last_heartbeat_at = started_at
    current_stage = "agent_starting"
    result: Dict[str, object] | None = None
    while result is None:
        now = time.monotonic()
        remaining = timeout_s - (now - started_at)
        if remaining <= 0:
            process.terminate()
            process.join(5)
            _emit_event(
                out_dir,
                "agent.timeout",
                **_heartbeat_fields(
                    started_at=started_at,
                    last_progress_at=last_progress_at,
                    now=now,
                    process_pid=process.pid,
                    stage=current_stage,
                ),
                timeout_s=timeout_s,
            )
            raise TimeoutError(f"Codex diagram agent timed out after {timeout_s:g}s")
        try:
            message = queue.get(timeout=min(1.0, remaining))
        except Empty:
            message = None
        now = time.monotonic()
        if isinstance(message, dict):
            if message.get("kind") == "progress":
                event_name = str(message.get("event") or "agent.progress")
                fields = {
                    key: value
                    for key, value in message.items()
                    if key not in {"kind", "event"}
                }
                _emit_event(out_dir, event_name, **fields)
                current_stage = str(message.get("stage") or event_name)
                last_progress_at = now
            elif message.get("kind") == "result":
                result = message
        if result is None and now - last_heartbeat_at >= heartbeat_s:
            _emit_event(
                out_dir,
                "agent.heartbeat",
                **_heartbeat_fields(
                    started_at=started_at,
                    last_progress_at=last_progress_at,
                    now=now,
                    process_pid=process.pid,
                    stage=current_stage,
                ),
            )
            last_heartbeat_at = now
        if result is None and not process.is_alive():
            try:
                message = queue.get(timeout=0.2)
            except Empty:
                break
            if isinstance(message, dict) and message.get("kind") == "result":
                result = message
    process.join(5)
    if result is None:
        raise RuntimeError("Codex diagram agent produced no result")
    if result.get("status") != "ok":
        raise RuntimeError(
            "Codex diagram agent failed: "
            f"{result.get('error_type', 'error')}: {result.get('error', '')}"
        )
    content = str(result.get("final_response") or "{}")
    payload = _extract_json_object(content)
    payload["agent_thread_id"] = str(result.get("thread_id") or "")
    payload["agent_turn_id"] = str(result.get("turn_id") or "")
    payload["agent_duration_ms"] = result.get("duration_ms")
    payload["raw_response"] = content
    return payload
