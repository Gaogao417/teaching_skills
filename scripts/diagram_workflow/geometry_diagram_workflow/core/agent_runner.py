from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List

from agent_prompt import agent_result_schema, diagram_agent_prompt
from runtime import redact_secrets
from tools import (
    _agent_cwd,
    _all_skill_inputs,
    _all_skill_names,
    _extract_json_object,
    _float_config,
    _resolved_codex_config,
)


def _codex_agent_worker(
    queue: mp.Queue,
    *,
    prompt: str,
    output_schema: Dict[str, object],
    cwd: str,
    model: str,
    codex_bin: str,
    skill_inputs: List[Dict[str, str]],
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

        temp_codex_home = tempfile.mkdtemp(prefix="diagram-agent-codex-home-")
        source_codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
        for name in ("auth.json", "config.toml"):
            source_path = source_codex_home / name
            if source_path.exists():
                shutil.copy2(source_path, Path(temp_codex_home) / name)
        env = os.environ.copy()
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
            thread = codex.thread_start(
                approval_mode=ApprovalMode.deny_all,
                cwd=cwd,
                ephemeral=True,
                model=model or None,
                sandbox=Sandbox.full_access,
            )
            result = thread.run(
                run_input,
                approval_mode=ApprovalMode.deny_all,
                cwd=cwd,
                model=model or None,
                output_schema=output_schema,
                sandbox=Sandbox.full_access,
            )
        queue.put(
            {
                "status": "ok",
                "thread_id": thread.id,
                "turn_id": result.id,
                "duration_ms": result.duration_ms,
                "final_response": result.final_response or "{}",
            }
        )
    except Exception as exc:
        queue.put(
            {
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
    queue: mp.Queue = mp.Queue()
    prompt = diagram_agent_prompt(
        request,
        out_dir,
        request_path,
        skill_names=_all_skill_names(),
    )
    process = mp.Process(
        target=_codex_agent_worker,
        kwargs={
            "queue": queue,
            "prompt": prompt,
            "output_schema": agent_result_schema(),
            "cwd": str(_agent_cwd()),
            "model": str(config.get("codex_model") or ""),
            "codex_bin": str(config.get("codex_bin") or ""),
            "skill_inputs": _all_skill_inputs(),
        },
    )
    process.start()
    process.join(timeout_s)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise TimeoutError(f"Codex diagram agent timed out after {timeout_s:g}s")
    if queue.empty():
        raise RuntimeError("Codex diagram agent produced no result")
    result = queue.get()
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
