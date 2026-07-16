#!/usr/bin/env python3
"""Opt-in live assignment E2E for Codex SDK + GeometricScene diagrams.

This script writes a small regression assignment under the requested artifact
directory, runs the real assignment diagram pipeline, renders LaTeX, compiles a
PDF, and verifies that at least one job used the live Codex SDK +
Wolfram-backed GeometricScene route.

It is intentionally not imported by default pytest because it requires local
Codex SDK credentials and a working Wolfram kernel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "杨茗贺" / "2026-07-07-线段比再练-出图回归"


def _write_yaml(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _run(cmd: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stdout[-4000:])
        print(completed.stderr[-4000:], file=sys.stderr)
    return completed


def _segment_slot(
    slot_id: str,
    given_objects: list[str],
    constraints: list[str],
) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "diagram_ref": slot_id,
        "variant": "prompt",
        "disclosure_policy": "clean",
        "required": True,
        "on_failure": "fail_assignment",
        "placement": "diagram_col",
        "layout_role": "question_sidecar",
        "display_profile": "worksheet_geometry_sidecar",
        "caption": "观察点在线段上的顺序和份数。",
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "teaching_intent": "practice_prompt",
        "semantic_constraints": {
            "given_objects": given_objects,
            "given_constraints": constraints,
            "clean_forbidden": ["不要写答案", "不要标注推理结论"],
        },
    }


def _plan() -> dict[str, object]:
    return {
        "meta": {
            "title": "线段比再练-出图回归",
            "subtitle": "Codex SDK + GeometricScene live E2E",
            "grade": "八年级",
            "subject": "数学",
            "duration": "15分钟",
            "total_points": 16,
            "version": "student",
            "assignment_id": "2026-07-07-segment-ratio-live-diagram-e2e",
        },
        "render": {"template": "exam-zh-practice", "paper_size": "a4paper"},
        "sections": [
            {
                "id": "live-segment-ratio",
                "title": "一、线段比出图回归",
                "type": "practice",
                "visibility": "student",
                "blocks": [
                    {
                        "type": "problem",
                        "id": "q1",
                        "points": 8,
                        "label": "第 1 题",
                        "stem_latex": (
                            r"如图，点 $A,B,C$ 在同一直线上，顺序为 $A-B-C$。"
                            r"若 $AB:BC=3:5$，且 $AC=64$，求 $BC$。"
                        ),
                        "diagram_slot": _segment_slot(
                            "live.q1.prompt",
                            ["A", "B", "C"],
                            ["A, B, C are collinear in order A-B-C", "AB:BC=3:5", "AC=64"],
                        ),
                        "answer_space": {"type": "steps", "height": "28mm"},
                    },
                    {
                        "type": "problem",
                        "id": "q2",
                        "points": 8,
                        "label": "第 2 题",
                        "stem_latex": (
                            r"如图，点 $A,B,C,D$ 在同一直线上，顺序为 $A-B-C-D$。"
                            r"若 $AB:BC:CD=2:3:4$，且 $AD=72$，求 $BD$。"
                        ),
                        "diagram_slot": _segment_slot(
                            "live.q2.prompt",
                            ["A", "B", "C", "D"],
                            [
                                "A, B, C, D are collinear in order A-B-C-D",
                                "AB:BC:CD=2:3:4",
                                "AD=72",
                                "BD target",
                            ],
                        ),
                        "answer_space": {"type": "steps", "height": "30mm"},
                    },
                ],
            }
        ],
    }


def _event_ok(events: list[dict[str, Any]], event_name: str) -> bool:
    return any(event.get("event") == event_name and event.get("status") == "ok" for event in events)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_live_jobs(artifact_dir: Path) -> dict[str, object]:
    jobs_manifest = _read_json(artifact_dir / "build" / "diagram" / "diagram_jobs.json")
    jobs = jobs_manifest.get("jobs") or []
    _require(isinstance(jobs, list) and jobs, "diagram_jobs.json has no jobs")

    fragment_hashes: dict[str, str] = {}
    live_ok = False
    for job in jobs:
        _require(isinstance(job, dict), "job entry is not an object")
        job_id = str(job.get("job_id") or "")
        engine = str(job.get("engine") or "")
        kind = str(job.get("diagram_kind") or "")
        job_dir = artifact_dir / "build" / "diagram" / "jobs" / job_id
        _require(job_dir.exists(), f"job dir missing: {job_id}")

        workflow_result = _read_json(job_dir / "workflow_result.json")
        renderer_result = _read_json(job_dir / "renderer_result.json")
        _require(workflow_result.get("status") == "ok", f"{job_id}: workflow_result.status is not ok")
        _require(renderer_result.get("status") == "ok", f"{job_id}: renderer_result.status is not ok")

        fragment = job_dir / str(renderer_result.get("tikz_fragment_path") or "")
        _require(fragment.exists() and fragment.stat().st_size > 0, f"{job_id}: TikZ fragment missing")
        fragment_hashes[job_id] = _sha256(fragment)

        if engine == "geometric_scene" and kind == "synthetic_geometry":
            events = _read_events(job_dir / "workflow_events.jsonl")
            agent_result = _read_json(job_dir / "agent_result.json")
            _require(_event_ok(events, "agent.end"), f"{job_id}: agent.end status=ok missing")
            _require(_event_ok(events, "workflow.finalize"), f"{job_id}: workflow.finalize status=ok missing")
            _require(str(agent_result.get("agent_thread_id") or ""), f"{job_id}: agent_thread_id missing")
            wolfram = workflow_result.get("wolfram") or {}
            model = workflow_result.get("model") or {}
            _require(isinstance(wolfram, dict) and wolfram.get("success") is True, f"{job_id}: wolfram success missing")
            _require(float(wolfram.get("solve_time_s") or 0) > 0, f"{job_id}: wolfram solve_time_s missing")
            _require(isinstance(model, dict) and str(model.get("text_model_used") or ""), f"{job_id}: text_model_used missing")
            live_ok = True

    _require(live_ok, "no live geometric_scene + synthetic_geometry job was verified")
    _require(len(set(fragment_hashes.values())) == len(fragment_hashes), "prompt TikZ fragments are duplicated")
    return {"jobs": len(jobs), "fragment_hashes": fragment_hashes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live assignment diagram E2E")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-s", type=int, default=900)
    args = parser.parse_args()

    artifact_dir = args.artifact_dir.resolve()
    plan_path = artifact_dir / "03-adaptive-practice.student.plan.assignment.yaml"
    resolved_path = artifact_dir / "03-adaptive-practice.student.resolved.assignment.yaml"
    tex_path = artifact_dir / "03-adaptive-practice.student.tex"
    pdf_path = artifact_dir / "03-adaptive-practice.student.pdf"

    _write_yaml(plan_path, _plan())

    pipeline = _run(
        [
            args.python,
            str(REPO_ROOT / "scripts" / "diagram_workflow" / "run_assignment_diagrams.py"),
            str(plan_path),
            "--out",
            str(resolved_path),
            "--max-workers",
            "2",
        ],
        cwd=REPO_ROOT,
        timeout=args.timeout_s,
    )
    _require(pipeline.returncode == 0, "run_assignment_diagrams.py failed")
    live_summary = _verify_live_jobs(artifact_dir)

    validate = _run(
        [args.python, str(REPO_ROOT / "math-assignment-latex" / "scripts" / "validate_assignment.py"), str(resolved_path)],
        cwd=REPO_ROOT,
        timeout=120,
    )
    _require(validate.returncode == 0, "resolved YAML validation failed")

    render = _run(
        [
            args.python,
            str(REPO_ROOT / "math-assignment-latex" / "scripts" / "render_assignment.py"),
            str(resolved_path),
            "--out",
            str(tex_path),
        ],
        cwd=REPO_ROOT,
        timeout=120,
    )
    _require(render.returncode == 0, "LaTeX render failed")

    compile_pdf = _run(
        ["bash", str(REPO_ROOT / "math-assignment-latex" / "scripts" / "compile_latex.sh"), str(tex_path)],
        cwd=REPO_ROOT,
        timeout=240,
    )
    _require(compile_pdf.returncode == 0, "PDF compile failed")
    _require(pdf_path.exists() and pdf_path.stat().st_size > 0, "PDF was not generated")

    print(json.dumps(
        {
            "status": "ok",
            "artifact_dir": str(artifact_dir),
            "plan": str(plan_path),
            "resolved": str(resolved_path),
            "pdf": str(pdf_path),
            **live_summary,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
