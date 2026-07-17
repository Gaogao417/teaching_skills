#!/usr/bin/env python3
"""Serially benchmark Codex scene-writer model/effort pairs on one request."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


DEFAULT_MODELS = ("gpt-5.3-codex-spark", "gpt-5.4-mini", "gpt-5.5")
DEFAULT_EFFORTS = ("low", "medium", "high")


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value).strip("-")


def _scene_codes(job_dir: Path) -> list[dict[str, object]]:
    scenes: list[dict[str, object]] = []
    for path in sorted(job_dir.glob("rounds/round_*/scene_payload.json")):
        payload = _read_json(path)
        code = str(payload.get("scene_code") or "")
        scenes.append(
            {
                "round": path.parent.name,
                "path": str(path),
                "scene_code": code,
                "geometric_assertion_count": code.count("GeometricAssertion["),
                "distance_constraint_count": code.count("EuclideanDistance["),
                "planar_angle_count": code.count("PlanarAngle["),
                "vector_angle_count": code.count("VectorAngle["),
                "unequal_count": code.count("!="),
            }
        )
    return scenes


def _preview_path(job_dir: Path) -> str:
    renderer = _read_json(job_dir / "renderer_result.json") if (job_dir / "renderer_result.json").is_file() else {}
    raw = str(renderer.get("preview_png_path") or "")
    if not raw:
        matches = sorted(job_dir.glob("rendered/*.preview.png"))
        return str(matches[0]) if matches else ""
    path = Path(raw)
    return str(path if path.is_absolute() else job_dir / path)


def _build_request(
    source: dict[str, object],
    *,
    model: str,
    effort: str,
    codex_bin: Path,
    base_dir: Path,
    given_constraints: list[str],
    source_problem_text: str,
) -> dict[str, object]:
    request = copy.deepcopy(source)
    suffix = f"{_safe_name(model)}-{effort}"
    request["job_id"] = f"problem18-literal-{suffix}"
    request["slot_id"] = f"benchmark.problem18.literal.{suffix}"
    request["variant"] = "solution"
    request["disclosure_policy"] = "annotated"

    context = request.setdefault("problem_context", {})
    if not isinstance(context, dict):
        context = {}
        request["problem_context"] = context
    context["source_problem_text"] = source_problem_text

    semantic = request.setdefault("semantic_constraints", {})
    if not isinstance(semantic, dict):
        semantic = {}
        request["semantic_constraints"] = semantic
    semantic["given_objects"] = ["A", "B", "C", "D", "E", "F", "G"]
    semantic["given_constraints"] = given_constraints
    semantic["derived_objects"] = []
    semantic["derived_constraints"] = []
    semantic["clean_forbidden"] = [
        "do not label FG with its numeric answer",
        "do not add geometry conditions not listed in given_constraints",
    ]
    semantic["solution_allowed_annotations"] = [
        "mark DF and DG as equal",
    ]
    semantic["annotate"] = []

    request["reuse"] = {
        "reuse_geometry_from": "benchmark-base-prompt",
        "base_job_dir": str(base_dir),
    }
    engine_options = request.setdefault("engine_options", {})
    if not isinstance(engine_options, dict):
        engine_options = {}
        request["engine_options"] = engine_options
    engine_options["max_retries"] = 0
    engine_options["wolfram_timeout_s"] = 30
    engine_options["wolfram_hard_timeout_s"] = 60
    engine_options["engine_model_config"] = {
        "codex_model": model,
        "codex_bin": str(codex_bin),
        "model_reasoning_effort": effort,
        "service_tier": "default",
        "fast_mode": False,
        "codex_timeout_s": 180,
    }
    plan = request.setdefault("execution_plan", {})
    if not isinstance(plan, dict):
        plan = {}
        request["execution_plan"] = plan
    plan["job_id"] = request["job_id"]
    plan["slot_id"] = request["slot_id"]
    plan["max_candidate_rounds"] = 2
    plan["requires_visual_decision"] = False
    return request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-request", type=Path, required=True)
    parser.add_argument("--base-spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--effort", action="append", dest="efforts")
    parser.add_argument("--given-constraint", action="append", required=True)
    parser.add_argument("--source-problem-text", required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    source = _read_json(args.source_request.resolve())
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    codex_bin = args.codex_bin.expanduser().absolute()
    if not codex_bin.is_file():
        raise FileNotFoundError(f"configured Codex binary does not exist: {codex_bin}")

    results: list[dict[str, object]] = []
    started = time.perf_counter()
    for model in args.models or DEFAULT_MODELS:
        for effort in args.efforts or DEFAULT_EFFORTS:
            case_dir = output / f"{_safe_name(model)}-{effort}"
            base_dir = case_dir / "benchmark-base-prompt"
            base_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.base_spec.resolve(), base_dir / "final_renderer_spec.json")
            request = _build_request(
                source,
                model=model,
                effort=effort,
                codex_bin=codex_bin,
                base_dir=base_dir,
                given_constraints=args.given_constraint,
                source_problem_text=args.source_problem_text,
            )
            request_path = case_dir / "request.json"
            job_dir = case_dir / "job"
            _write_json(request_path, request)
            command = [
                sys.executable,
                str(
                    repo
                    / "scripts/diagram_workflow/geometry_diagram_workflow/core/workflow.py"
                ),
                "--action",
                "run",
                "--request",
                str(request_path),
                "--out",
                str(job_dir),
            ]
            env = dict(os.environ)
            env["CODEX_DIAGRAM_BIN"] = str(codex_bin)
            case_started = time.perf_counter()
            completed = subprocess.run(
                command,
                cwd=repo,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            elapsed = time.perf_counter() - case_started
            (case_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
            (case_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
            workflow = _read_json(job_dir / "workflow_result.json") if (job_dir / "workflow_result.json").is_file() else {}
            result = {
                "model": model,
                "reasoning_effort": effort,
                "configured_codex_bin": str(codex_bin),
                "returncode": completed.returncode,
                "wall_time_s": round(elapsed, 3),
                "status": str(workflow.get("status") or "missing"),
                "fail_type": str(workflow.get("fail_type") or ""),
                "message": str(workflow.get("message") or ""),
                "scene_attempts": _scene_codes(job_dir),
                "preview_path": _preview_path(job_dir),
                "job_dir": str(job_dir),
            }
            results.append(result)
            _write_json(output / "partial-report.json", {"results": results})
            print(json.dumps(result, ensure_ascii=False), flush=True)

    report = {
        "schema_version": "scene-writer-model-matrix/v1",
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "configured_codex_bin": str(codex_bin),
        "serial_execution": True,
        "wall_time_s": round(time.perf_counter() - started, 3),
        "source_request": str(args.source_request.resolve()),
        "base_spec": str(args.base_spec.resolve()),
        "given_constraints": args.given_constraint,
        "results": results,
    }
    _write_json(output / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
