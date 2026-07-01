#!/usr/bin/env python3
"""Live Codex SDK + GeometricScene smoke test.

This script intentionally calls the real Codex SDK route and Wolfram-backed
synthetic geometry workflow. It is not imported by normal unit tests.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUEST = (
    REPO_ROOT
    / "artifacts/试卷摘录/2026-06-20-数学试卷20/build/diagram/jobs/q6-prompt/request.json"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def event_ok(events: list[dict[str, Any]], event_name: str) -> bool:
    return any(
        event.get("event") == event_name and event.get("status") == "ok"
        for event in events
    )


def latest_round_file(job_dir: Path, name: str) -> Path | None:
    rounds = sorted((job_dir / "rounds").glob("round_*"))
    for round_dir in reversed(rounds):
        candidate = round_dir / name
        if candidate.exists():
            return candidate
    return None


def run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def resolve_job_dir(out_root: Path, job_id: str) -> Path:
    nested = out_root / "jobs" / job_id
    if (nested / "workflow_result.json").exists():
        return nested
    if (out_root / "workflow_result.json").exists():
        return out_root
    raise FileNotFoundError(
        f"workflow_result.json not found under {nested} or {out_root}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live GeometricScene + Wolfram smoke test")
    parser.add_argument(
        "--request",
        type=Path,
        default=DEFAULT_REQUEST,
        help="DiagramJobRequest v2 JSON to run",
    )
    parser.add_argument("--job-id", default="live-geometric-scene-smoke")
    parser.add_argument("--out", type=Path, help="Output root; defaults to a temporary directory")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-s", type=int, default=420)
    args = parser.parse_args()

    request_path = args.request.resolve()
    require(request_path.exists(), f"request not found: {request_path}")

    with tempfile.TemporaryDirectory(prefix="diagram-live-smoke-") as tmp:
        out_root = args.out.resolve() if args.out else Path(tmp)
        out_root.mkdir(parents=True, exist_ok=True)
        request_copy = out_root / "request.json"
        shutil.copy2(request_path, request_copy)

        workflow_cmd = [
            args.python,
            str(REPO_ROOT / "scripts/diagram_workflow/run_diagram_workflow.py"),
            str(request_copy),
            "--job-id",
            args.job_id,
            "--out",
            str(out_root),
            "--python",
            args.python,
            "--strict",
        ]
        workflow = run(workflow_cmd, REPO_ROOT, args.timeout_s)
        if workflow.returncode != 0:
            print(workflow.stdout[-4000:])
            print(workflow.stderr[-4000:], file=sys.stderr)
            raise SystemExit(workflow.returncode)

        job_dir = resolve_job_dir(out_root, args.job_id)
        workflow_result = read_json(job_dir / "workflow_result.json")
        events = read_events(job_dir / "workflow_events.jsonl")
        render_result_path = latest_round_file(job_dir, "render_result.json")
        scene_payload_path = latest_round_file(job_dir, "scene_payload.json")
        require(workflow_result.get("status") == "ok", "workflow_result.status is not ok")
        require(event_ok(events, "agent.end"), "agent.end did not finish ok")
        require(event_ok(events, "workflow.finalize"), "workflow.finalize did not finish ok")
        require(scene_payload_path is not None, "scene_payload.json missing")
        require(render_result_path is not None, "render_result.json missing")

        render_result = read_json(render_result_path)
        require(render_result.get("success") is True, "Wolfram render_result.success is not true")
        wolfram_summary = workflow_result.get("wolfram") or {}
        require(isinstance(wolfram_summary, dict), "workflow_result.wolfram is invalid")
        require(wolfram_summary.get("success") is True, "workflow_result.wolfram.success is not true")
        require(float(wolfram_summary.get("solve_time_s") or 0) > 0, "Wolfram solve_time_s is not positive")
        model_summary = workflow_result.get("model") or {}
        require(isinstance(model_summary, dict), "workflow_result.model is invalid")
        require(str(model_summary.get("text_model_used") or ""), "text_model_used is empty")

        renderer_cmd = [
            args.python,
            str(REPO_ROOT / "scripts/diagram_workflow/render_geometry_spec.py"),
            str(job_dir / "final_renderer_spec.json"),
            "--out-dir",
            str(job_dir),
            "--variant",
            "prompt",
        ]
        renderer = run(renderer_cmd, REPO_ROOT, 180)
        if renderer.returncode != 0:
            print(renderer.stdout[-4000:])
            print(renderer.stderr[-4000:], file=sys.stderr)
            raise SystemExit(renderer.returncode)
        renderer_result = read_json(job_dir / "renderer_result.json")
        require(renderer_result.get("status") == "ok", "renderer_result.status is not ok")
        fragment = job_dir / str(renderer_result.get("tikz_fragment_path") or "")
        require(fragment.exists() and fragment.stat().st_size > 0, "TikZ fragment missing or empty")

        print(json.dumps(
            {
                "status": "ok",
                "job_dir": str(job_dir),
                "text_model_used": model_summary.get("text_model_used"),
                "wolfram_solve_time_s": wolfram_summary.get("solve_time_s"),
                "tikz_fragment_path": renderer_result.get("tikz_fragment_path"),
            },
            ensure_ascii=False,
            indent=2,
        ))


if __name__ == "__main__":
    main()
