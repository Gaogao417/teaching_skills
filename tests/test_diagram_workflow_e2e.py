#!/usr/bin/env python3
"""Offline one-shot e2e test for the default assignment diagram pipeline.

Only the plan YAML is fabricated. The test runs the default top-level entry
(`run_assignment_diagrams.py`) once, then verifies the real file outputs from
collect, batch, gate, render, and resolve. It uses deterministic renderer_spec
jobs, so it does not call the live GeometricScene LLM/Wolfram route.

Run from repo root:

    python3 tests/test_diagram_workflow_e2e.py
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
except ImportError as e:
    raise SystemExit("pip install pyyaml") from e


REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


PLAN_YAML = {
    "meta": {
        "title": "等腰三角形练习",
        "version": "student",
        "assignment_id": "2026-06-02-isosceles-triangle",
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
                    "stem_latex": r"如图，$AB=AC=5$，$BC=6$，点 $D$ 为 $BC$ 中点，则 $AD$ 的长为",
                    "choices": {
                        "A": "$3$",
                        "B": "$4$",
                        "C": r"$\sqrt{7}$",
                        "D": r"$2\sqrt{6}$",
                    },
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
                                "markers": [{"type": "equal_ticks", "segments": [["A", "B"], ["A", "C"]]}],
                            }
                        },
                        "semantic_constraints": {
                            "given_objects": ["A", "B", "C", "D"],
                            "given_constraints": ["AB=AC=5", "BC=6", "D is midpoint of BC"],
                            "clean_forbidden": ["不要画高 AD", "不要标注直角"],
                        },
                    },
                },
                {
                    "type": "problem",
                    "id": "q3",
                    "stem_latex": (
                        r"如图，在 $\triangle ABC$ 中，$AB=AC$，点 $D$ 在 $BC$ 上，"
                        r"$BD=DC$，连接 $AD$。证明：$AD\perp BC$。"
                    ),
                    "answer_space": {
                        "type": "steps",
                        "parts": [
                            {
                                "label": "(1)",
                                "height": "40mm",
                                "diagram_slot": {
                                    "slot_id": "q3.part1.prompt",
                                    "diagram_ref": "q3.part1.prompt",
                                    "variant": "prompt",
                                    "disclosure_policy": "clean",
                                    "required": True,
                                    "on_failure": "fail_assignment",
                                    "placement": "answer_space.parts[].diagram_col",
                                    "layout_role": "answer_area_sidecar",
                                    "display_profile": "worksheet_geometry_sidecar",
                                    "caption": "原题图",
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
                                            "markers": [{"type": "equal_ticks", "segments": [["B", "D"], ["D", "C"]]}],
                                        }
                                    },
                                    "semantic_constraints": {
                                        "given_objects": ["A", "B", "C", "D"],
                                        "given_constraints": ["AB=AC", "BD=DC"],
                                        "clean_forbidden": ["不要画辅助线", "不要标注垂直符号"],
                                    },
                                },
                            },
                        ],
                    },
                },
            ],
        }
    ],
}


GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

_errors = 0


def heading(msg: str) -> None:
    print(f"\n{BOLD}{'=' * 60}\n  {msg}\n{'=' * 60}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    global _errors
    _errors += 1
    print(f"  {RED}✗{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


def run_script(args: list[str], label: str, timeout: int = 300) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [PYTHON, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
    )
    if r.returncode != 0:
        print(f"\n  {RED}{label} failed (rc={r.returncode}){RESET}")
        if r.stderr.strip():
            for line in r.stderr.strip().split("\n")[:15]:
                print(f"    {RED}{line}{RESET}")
    return r


def check_main_pipeline(plan_path: Path, resolved_path: Path) -> None:
    """Run the default top-level CLI once and require a successful pipeline."""
    heading("Default pipeline  run_assignment_diagrams.py")
    r = run_script(
        [
            str(REPO_ROOT / "scripts/diagram_workflow/run_assignment_diagrams.py"),
            str(plan_path),
            "--out",
            str(resolved_path),
            "--max-workers",
            "2",
        ],
        "Default pipeline",
    )
    if r.returncode != 0:
        fail("Default pipeline exited non-zero")
        return
    ok("Default pipeline exited 0")


def check_manifest_and_batch(build_dir: Path) -> None:
    """Verify collect and batch artifacts emitted by the one-shot pipeline."""
    heading("Manifest and batch report")
    jobs_path = build_dir / "diagram_jobs.json"
    report_path = build_dir / "diagram_batch_report.json"
    if not jobs_path.exists():
        fail(f"Missing job manifest: {jobs_path}")
        return
    if not report_path.exists():
        fail(f"Missing batch report: {report_path}")
        return

    manifest = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs", [])
    job_ids = {j["job_id"] for j in jobs}
    if job_ids == {"c1-prompt", "q3-part1-prompt"}:
        ok("2 jobs collected: c1-prompt, q3-part1-prompt")
    else:
        fail(f"Wrong job_ids: {job_ids}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok_count") == 2 and report.get("failed_count") == 0:
        ok("Batch report: 2/2 ok")
    else:
        fail(
            f"Batch report unexpected: ok={report.get('ok_count')} "
            f"failed={report.get('failed_count')}"
        )


def check_job_outputs(build_dir: Path) -> None:
    """Verify real workflow/renderer/TikZ artifacts for every job."""
    heading("Per-job renderer artifacts")
    for job_id in ("c1-prompt", "q3-part1-prompt"):
        job_dir = build_dir / "jobs" / job_id
        for name in ("request.json", "workflow_result.json", "final_renderer_spec.json", "renderer_result.json"):
            if not (job_dir / name).exists():
                fail(f"{job_id}: missing {name}")
                continue
        wf = json.loads((job_dir / "workflow_result.json").read_text(encoding="utf-8"))
        rr = json.loads((job_dir / "renderer_result.json").read_text(encoding="utf-8"))
        spec = json.loads((job_dir / "final_renderer_spec.json").read_text(encoding="utf-8"))
        if wf.get("status") != "ok":
            fail(f"{job_id}: workflow status={wf.get('status')}")
        if rr.get("status") != "ok":
            fail(f"{job_id}: renderer status={rr.get('status')}")
        if "points" not in spec:
            fail(f"{job_id}: renderer spec missing points")
        fragment_rel = rr.get("tikz_fragment_path", "")
        fragment = job_dir / fragment_rel
        if fragment_rel and fragment.exists() and fragment.stat().st_size > 0:
            ok(f"{job_id}: {fragment.relative_to(job_dir)} ({fragment.stat().st_size / 1024:.1f} KB)")
        else:
            fail(f"{job_id}: TikZ fragment missing/empty at {fragment_rel}")


def check_resolved_yaml(resolved_path: Path, artifact_dir: Path) -> None:
    """Verify diagram_slot fields are replaced by bindable TikZ diagrams."""
    heading("Resolved YAML")
    if not resolved_path.exists():
        fail(f"Resolved YAML missing: {resolved_path}")
        return
    resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    blocks = resolved["sections"][0]["blocks"]

    block_diagram = blocks[0].get("diagram_col")
    if block_diagram and block_diagram.get("kind") == "tikz" and block_diagram.get("diagram_job_id") == "c1-prompt":
        ok("Block diagram_slot -> diagram_col")
    else:
        fail(f"Block diagram_col not bound: {block_diagram}")
    if "diagram_slot" in blocks[0]:
        fail("Block still carries diagram_slot")

    part = blocks[1]["answer_space"]["parts"][0]
    part_diagram = part.get("diagram_col")
    if part_diagram and part_diagram.get("kind") == "tikz" and part_diagram.get("diagram_job_id") == "q3-part1-prompt":
        ok("Answer-space part diagram_slot -> diagram_col")
    else:
        fail(f"Answer-space diagram_col not bound: {part_diagram}")
    if "diagram_slot" in part:
        fail("Answer-space part still carries diagram_slot")

    for diagram in (block_diagram, part_diagram):
        if isinstance(diagram, dict) and diagram.get("tikz_path"):
            source = artifact_dir / diagram["tikz_path"]
            if not source.exists() or source.stat().st_size == 0:
                fail(f"Resolved TikZ source missing/empty: {source}")


def check_gate_negative(plan_path: Path, jobs_path: Path, jobs_dir: Path, artifact_dir: Path) -> None:
    """The standalone gate CLI must still block an unbindable required result."""
    heading("Negative: gate blocks on missing TikZ binding")
    target_rr = jobs_dir / "c1-prompt" / "renderer_result.json"
    original = target_rr.read_text(encoding="utf-8")
    data = json.loads(original)
    data["tikz_fragment_path"] = ""
    data["tikz_source_path"] = ""
    data["tikz_fragment"] = ""
    target_rr.write_text(json.dumps(data, indent=2), encoding="utf-8")

    try:
        r = run_script(
            [
                str(REPO_ROOT / "scripts/diagram_workflow/check_diagram_gate.py"),
                "--plan",
                str(plan_path),
                "--jobs",
                str(jobs_path),
                "--jobs-dir",
                str(jobs_dir),
                "--artifact-dir",
                str(artifact_dir),
            ],
            "Gate (missing TikZ binding)",
        )
    finally:
        target_rr.write_text(original, encoding="utf-8")

    if r.returncode != 2:
        fail(f"Expected rc=2, got rc={r.returncode}")
        return
    gate = json.loads(r.stdout)
    if gate.get("status") != "block":
        fail(f"Expected status=block, got {gate.get('status')}")
        return
    blocking = [c for c in gate.get("checks", []) if c["status"] == "block"]
    if any("required" in c.get("name", "") for c in blocking):
        ok(f"Correctly blocked ({len(blocking)} issue(s))")
    else:
        fail("No required/bindable blocking check found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagram workflow e2e test")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build/e2e-diagram-test"),
        help="Output directory for this test run",
    )
    args = parser.parse_args()

    td = args.out_dir.resolve()
    td.mkdir(parents=True, exist_ok=True)
    info(f"Output dir: {td}")

    plan_path = td / "assignment.plan.yaml"
    build_dir = td / "build" / "diagram"
    jobs_path = build_dir / "diagram_jobs.json"
    jobs_dir = build_dir / "jobs"
    resolved_path = td / "assignment.resolved.yaml"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if resolved_path.exists():
        resolved_path.unlink()

    plan_path.write_text(
        yaml.dump(PLAN_YAML, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    info(f"Plan YAML -> {plan_path}")

    check_main_pipeline(plan_path, resolved_path)
    check_manifest_and_batch(build_dir)
    check_job_outputs(build_dir)
    check_resolved_yaml(resolved_path, td)
    check_gate_negative(plan_path, jobs_path, jobs_dir, td)

    heading("Summary")
    if _errors == 0:
        print(f"  {GREEN}{BOLD}All checks passed!{RESET}")
        print("  Only mock: assignment.plan.yaml")
        print("  Default entry -> real collect/batch/gate/resolve artifacts")
        print("  Standalone gate negative check remains covered")
        return 0
    print(f"  {RED}{BOLD}{_errors} error(s){RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
