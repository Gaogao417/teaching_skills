#!/usr/bin/env python3
"""One-shot main-entry e2e test for the in-process assignment pipeline.

Drives the real top-level CLI ``run_assignment_diagrams.py <plan.yaml>`` and
asserts the final resolved YAML plus all intermediate artifacts are produced in
one go. The deterministic ``renderer_spec`` fixture needs no LLM/Wolfram, so
the whole chain runs in-process by default.

Run from repo root:

    python3 tests/test_assignment_pipeline_e2e.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:  # pragma: no cover
    raise SystemExit("pip install pyyaml") from e

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# Deterministic renderer_spec fixture: synthetic geometry, no LLM/Wolfram.
PLAN_YAML = {
    "meta": {
        "title": "管线主入口测试",
        "version": "student",
        "assignment_id": "pipeline-one-shot",
    },
    "render": {"template": "exam-zh-practice"},
    "sections": [
        {
            "id": "s1",
            "type": "practice",
            "blocks": [
                {
                    "type": "choice",
                    "id": "c1",
                    "stem_latex": r"如图，$AB=AC=5$，$BC=6$，则 $AD$ 的长为",
                    "choices": {"A": "$3$", "B": "$4$", "C": r"$\sqrt{7}$", "D": r"$2\sqrt{6}$"},
                    "answer": "B",
                    "diagram_slot": {
                        "slot_id": "c1.prompt",
                        "variant": "prompt",
                        "disclosure_policy": "clean",
                        "required": True,
                        "on_failure": "fail_assignment",
                        "placement": "diagram_col",
                        "layout_role": "question_sidecar",
                        "display_profile": "worksheet_geometry_sidecar",
                        "caption": "等腰三角形 ABC",
                        "engine": "renderer_spec",
                        "diagram_kind": "synthetic_geometry",
                        "teaching_intent": "practice_prompt",
                        "engine_options": {
                            "renderer_spec": {
                                "points": {"A": [0, 2.4], "B": [-3, 0], "C": [3, 0], "D": [0, 0]},
                                "segments": [
                                    {"from": "A", "to": "B"},
                                    {"from": "A", "to": "C"},
                                    {"from": "B", "to": "C"},
                                    {"from": "A", "to": "D"},
                                ],
                                "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
                            }
                        },
                        "semantic_constraints": {
                            "given_objects": ["A", "B", "C", "D"],
                            "given_constraints": ["AB=AC=5", "BC=6"],
                        },
                    },
                }
            ],
        }
    ],
}

_errors = 0


def _ok(msg: str) -> None:
    print(f"  \033[92m✓\033[0m {msg}")


def _fail(msg: str) -> None:
    global _errors
    _errors += 1
    print(f"  \033[91m✗\033[0m {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assignment pipeline one-shot e2e test")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build/e2e-assignment-pipeline-test"),
    )
    args = parser.parse_args()

    td = args.out_dir.resolve()
    if td.exists():
        shutil.rmtree(td)
    td.mkdir(parents=True)

    plan_path = td / "assignment.plan.assignment.yaml"
    resolved_path = td / "assignment.resolved.assignment.yaml"
    plan_path.write_text(
        yaml.dump(PLAN_YAML, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    r = subprocess.run(
        [PYTHON, str(REPO_ROOT / "scripts/diagram_workflow/run_assignment_diagrams.py"),
         str(plan_path), "--out", str(resolved_path)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
    )
    if r.returncode != 0:
        _fail(f"main entry exited {r.returncode}")
        print(r.stderr[-1500:])
        return 1
    _ok("main entry exited 0")

    build_dir = td / "build" / "diagram"
    jobs_json = build_dir / "diagram_jobs.json"
    batch_report = build_dir / "diagram_batch_report.json"
    job_dir = build_dir / "jobs" / "c1-prompt"

    # Intermediate artifacts all present
    for label, path in [
        ("diagram_jobs.json", jobs_json),
        ("diagram_batch_report.json", batch_report),
        ("request.json", job_dir / "request.json"),
        ("workflow_result.json", job_dir / "workflow_result.json"),
        ("final_renderer_spec.json", job_dir / "final_renderer_spec.json"),
        ("renderer_result.json", job_dir / "renderer_result.json"),
    ]:
        if path.exists():
            _ok(f"{label} written")
        else:
            _fail(f"missing {label}: {path}")

    # Batch report: one ok job
    if batch_report.exists():
        report = json.loads(batch_report.read_text(encoding="utf-8"))
        if report.get("ok_count") == 1 and report.get("total_jobs") == 1:
            _ok("batch report: 1/1 ok")
        else:
            _fail(f"batch report: ok={report.get('ok_count')} total={report.get('total_jobs')}")

    # Workflow + renderer statuses
    if (job_dir / "workflow_result.json").exists():
        wf = json.loads((job_dir / "workflow_result.json").read_text(encoding="utf-8"))
        if wf.get("status") == "ok":
            _ok("workflow_result status=ok")
        else:
            _fail(f"workflow_result status={wf.get('status')}")
    if (job_dir / "renderer_result.json").exists():
        rr = json.loads((job_dir / "renderer_result.json").read_text(encoding="utf-8"))
        if rr.get("status") == "ok":
            _ok("renderer_result status=ok")
        else:
            _fail(f"renderer_result status={rr.get('status')}")

    # TikZ fragment exists and is non-empty
    if (job_dir / "renderer_result.json").exists():
        rr = json.loads((job_dir / "renderer_result.json").read_text(encoding="utf-8"))
        fragment_rel = rr.get("tikz_fragment_path", "")
        if fragment_rel:
            fragment = job_dir / fragment_rel
            if fragment.exists() and fragment.stat().st_size > 0:
                _ok(f"TikZ fragment ({fragment.stat().st_size} bytes)")
            else:
                _fail(f"TikZ fragment missing/empty at {fragment_rel}")
        else:
            _fail("renderer_result missing tikz_fragment_path")

    # Final resolved YAML: diagram_slot replaced by bindable diagram_col
    if resolved_path.exists():
        resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
        dc = resolved["sections"][0]["blocks"][0].get("diagram_col")
        if dc and dc.get("kind") == "tikz" and dc.get("diagram_job_id") == "c1-prompt":
            _ok("resolved YAML: diagram_slot -> diagram_col (tikz)")
        else:
            _fail(f"resolved YAML diagram_col not bound: {dc}")
        if "diagram_slot" in resolved["sections"][0]["blocks"][0]:
            _fail("resolved YAML still carries diagram_slot")
    else:
        _fail(f"resolved YAML not written: {resolved_path}")

    print()
    if _errors == 0:
        print(f"  \033[92m\033[1mAll checks passed!\033[0m")
        return 0
    print(f"  \033[91m\033[1m{_errors} error(s)\033[0m")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
