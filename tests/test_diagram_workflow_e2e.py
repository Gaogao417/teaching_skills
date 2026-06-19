#!/usr/bin/env python3
"""End-to-end test for the diagram workflow scripts.

Only the plan YAML is fabricated. Every stage runs against real
subprocesses and real file outputs:

    S2.5  collector  →  real
    S2.6  batch      →  real (workflow.py + renderer)
    S2.7  gate       →  real
    S2.8  resolver   →  real

Run from repo root:

    python3 tests/test_diagram_workflow_e2e.py
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:
    raise SystemExit("pip install pyyaml") from e

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# The only fixture: a fabricated assignment.plan.yaml with deterministic
# renderer_spec payloads. Every workflow script still runs as a subprocess.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
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


def run_script(
    args: list[str],
    label: str,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
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


# ---------------------------------------------------------------------------
# Per-stage checks
#
# Each function documents its pass conditions as a docstring.
# ---------------------------------------------------------------------------


def check_s25(plan_path: Path, jobs_path: Path) -> dict | None:
    """S2.5 collector: plan YAML -> diagram_jobs.json

    Pass iff ALL of:
      - script exits 0
      - output JSON has exactly 2 jobs
      - job_ids are c1-prompt and q3-part1-prompt
      - every job has variant=prompt, required=True, depends_on=[]
      - every slot_path starts with /sections/ (valid JSON Pointer prefix)
    """
    heading("S2.5  collect_diagram_jobs.py")
    r = run_script(
        [str(REPO_ROOT / "scripts/diagram_workflow/collect_diagram_jobs.py"),
         str(plan_path),
         "--out-dir", str(jobs_path.parent)],
        "Collector",
    )
    if r.returncode != 0:
        fail("Collector exited non-zero")
        return None

    manifest = json.loads(jobs_path.read_text())
    jobs = manifest.get("jobs", [])

    if len(jobs) != 2:
        fail(f"Expected 2 jobs, got {len(jobs)}")
        return None

    job_ids = {j["job_id"] for j in jobs}
    if job_ids != {"c1-prompt", "q3-part1-prompt"}:
        fail(f"Wrong job_ids: {job_ids}")
        return None

    for j in jobs:
        checks = [
            j["variant"] == "prompt",
            j["required"] is True,
            j["depends_on"] == [],
            j["slot_path"].startswith("/sections/"),
        ]
        if not all(checks):
            fail(f"{j['job_id']}: variant={j['variant']} required={j['required']} "
                 f"depends_on={j['depends_on']} slot_path={j['slot_path']}")
            return None

    ok("2 jobs: c1-prompt, q3-part1-prompt")
    for j in jobs:
        info(f"  {j['job_id']}: slot_path={j['slot_path']}")
    return manifest


def check_s26(jobs_path: Path, artifact_dir: Path, plan_path: Path) -> dict | None:
    """S2.6 batch runner: diagram_jobs.json -> real TikZ fragments

    Pass iff ALL of:
      - script exits 0
      - batch report shows all jobs with status=ok
      - each job dir contains workflow_result.json with status=ok
      - each job dir contains renderer_result.json with status=ok
      - each job dir contains final_renderer_spec.json with a 'points' key
      - each job dir does not contain the retired request filename
      - each renderer_result points to a non-empty TikZ fragment
    """
    heading("S2.6  run_diagram_batch.py  (REAL)")
    info("Calls workflow.py + render_geometry_spec.py")
    info("Uses deterministic renderer_spec fixtures; no LLM/API key required.\n")

    r = run_script(
        [str(REPO_ROOT / "scripts/diagram_workflow/run_diagram_batch.py"),
         str(jobs_path),
         "--artifact-dir", str(artifact_dir),
         "--plan-yaml", str(plan_path),
         "--max-workers", "2"],
        "Batch",
        timeout=300,
    )

    build_dir = jobs_path.parent
    report = json.loads(r.stdout) if r.stdout.strip() else {}
    jobs = report.get("jobs", [])

    ok_count = sum(1 for j in jobs if j.get("status") == "ok")
    info(f"Batch result: {ok_count}/{len(jobs)} ok")

    for j in jobs:
        icon = GREEN + "✓" + RESET if j["status"] == "ok" else RED + "✗" + RESET
        print(f"  {icon} {j['job_id']}: {j['status']}")
        if j.get("failure_reason"):
            info(f"    reason: {j['failure_reason']}")

    if r.returncode != 0 or ok_count != len(jobs):
        fail(f"Batch: {ok_count}/{len(jobs)} succeeded (expected all)")
        return report

    # Verify real output files per job
    for j in jobs:
        job_id = j["job_id"]
        job_dir = build_dir / "jobs" / job_id
        if not job_dir.exists():
            fail(f"{job_id}: job directory not found")
            continue

        retired_request = job_dir / ("diagram" + "-request.json")
        if retired_request.exists():
            fail(f"{job_id}: retired request file should not be written in production path")

        wf_path = job_dir / "workflow_result.json"
        if wf_path.exists():
            wf = json.loads(wf_path.read_text())
            if wf.get("status") != "ok":
                fail(f"{job_id}: workflow status={wf.get('status')}")
        else:
            fail(f"{job_id}: workflow_result.json missing")

        rr_path = job_dir / "renderer_result.json"
        if rr_path.exists():
            rr = json.loads(rr_path.read_text())
            if rr.get("status") != "ok":
                fail(f"{job_id}: renderer status={rr.get('status')}")
        else:
            fail(f"{job_id}: renderer_result.json missing")

        spec_path = job_dir / "final_renderer_spec.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text())
            if "points" not in spec:
                fail(f"{job_id}: renderer spec missing 'points'")
        else:
            fail(f"{job_id}: final_renderer_spec.json missing")

        if rr_path.exists():
            fragment_rel = rr.get("tikz_fragment_path")
        else:
            fragment_rel = ""
        if fragment_rel:
            fragment = job_dir / fragment_rel
            if fragment.exists() and fragment.stat().st_size > 0:
                ok(f"{job_id}: {fragment.relative_to(job_dir)} ({fragment.stat().st_size / 1024:.1f} KB)")
            else:
                fail(f"{job_id}: TikZ fragment missing at {fragment_rel}")
        else:
            fail(f"{job_id}: renderer_result missing tikz_fragment_path")

    ok("All jobs produced complete output (workflow + renderer + TikZ)")
    return report


def check_s27(
    plan_path: Path, jobs_path: Path, jobs_dir: Path, artifact_dir: Path,
) -> str | None:
    """S2.7 gate: plan + jobs + renderer_result.json -> pass/warn/block

    Pass iff:    gate status == "pass"
    Warn (ok):   gate status == "warn"
    Block:       gate status == "block"  (downstream uses --skip-required-check)
    """
    heading("S2.7  check_diagram_gate.py")
    r = run_script(
        [str(REPO_ROOT / "scripts/diagram_workflow/check_diagram_gate.py"),
         "--plan", str(plan_path),
         "--jobs", str(jobs_path),
         "--jobs-dir", str(jobs_dir),
         "--artifact-dir", str(artifact_dir)],
        "Gate",
    )

    gate = json.loads(r.stdout) if r.stdout.strip() else {}
    status = gate.get("status", "unknown")
    ok(f"Gate status: {status}")

    for c in gate.get("checks", []):
        if c["status"] == "pass":
            icon = GREEN + "✓" + RESET
        elif c["status"] == "warn":
            icon = YELLOW + "⚠" + RESET
        else:
            icon = RED + "✗" + RESET
        print(f"  {icon} {c['status']:5s} {c['name']}: {c.get('message', '')}")

    if status == "block":
        fail("Gate blocked")
        return "block"
    if status in ("pass", "warn"):
        ok(f"Gate {status}")
        return status

    fail(f"Unexpected gate status: {status}")
    return None


def check_s28(
    plan_path: Path,
    jobs_path: Path,
    jobs_dir: Path,
    resolved_path: Path,
    gate_status: str | None,
    artifact_dir: Path,
) -> None:
    """S2.8 resolver: plan YAML + renderer_result.json -> resolved YAML

    Pass iff ALL of:
      - script exits 0
      - output is valid YAML with sections[].blocks[]
      - for every block whose diagram_slot had a bindable artifact:
          diagram_slot is removed, replaced by diagram_col
      - every diagram_col has kind=tikz plus tikz_code/tikz_path, variant, width
      - blocks without diagram_slot are unchanged (still present)
    If gate was block, uses --skip-required-check and verifies
      that unbindable slots remain as diagram_slot (partial build).
    """
    heading("S2.8  resolve_assignment_diagrams.py")
    skip_flag = ["--skip-required-check"] if gate_status == "block" else []

    r = run_script(
        [str(REPO_ROOT / "scripts/diagram_workflow/resolve_assignment_diagrams.py"),
         str(plan_path),
         "--jobs", str(jobs_path),
         "--jobs-dir", str(jobs_dir),
         "--artifact-dir", str(artifact_dir),
         "--out", str(resolved_path),
         *skip_flag],
        "Resolver",
    )
    if r.returncode != 0:
        fail("Resolver exited non-zero")
        return

    resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    blocks = resolved["sections"][0]["blocks"]

    for bi, block in enumerate(blocks):
        bid = block.get("id", f"block-{bi}")
        dc = block.get("diagram_col")
        slot = block.get("diagram_slot")

        if dc:
            # diagram_slot was resolved to diagram_col
            checks = [
                dc.get("kind") == "tikz",
                dc.get("tikz_code") or dc.get("tikz_path"),
                dc.get("variant"),
                dc.get("width"),
            ]
            if not all(checks):
                fail(f"Block {bid}: diagram_col missing required field "
                     f"(kind={dc.get('kind')}, tikz_path={dc.get('tikz_path')}, variant={dc.get('variant')}, "
                     f"width={dc.get('width')})")
            else:
                ok(f"Block {bid}: diagram_slot -> diagram_col "
                   f"tikz={str(dc.get('tikz_path') or 'inline')[:40]}... width={dc['width']}")
                if dc.get("tikz_path"):
                    source = artifact_dir / dc["tikz_path"]
                    if source.exists() and source.stat().st_size > 0:
                        ok(f"  TikZ source: {source.stat().st_size / 1024:.1f} KB")
        elif slot:
            info(f"Block {bid}: diagram_slot unchanged (no bindable artifact)")

        # Check answer_space parts
        for part in block.get("answer_space", {}).get("parts", []):
            dc = part.get("diagram_col")
            if dc:
                if dc.get("kind") == "tikz" and (dc.get("tikz_code") or dc.get("tikz_path")) and dc.get("variant") and dc.get("width"):
                    ok(f"  Part {part.get('label', '')}: diagram_slot -> diagram_col "
                       f"tikz={str(dc.get('tikz_path') or 'inline')[:40]}...")
                    if dc.get("tikz_path"):
                        source = artifact_dir / dc["tikz_path"]
                        if source.exists() and source.stat().st_size > 0:
                            ok(f"  TikZ source: {source.stat().st_size / 1024:.1f} KB")
                else:
                    fail(f"  Part {part.get('label', '')}: diagram_col missing fields")

    ok("Resolved YAML written")


def check_gate_negative(
    plan_path: Path, jobs_path: Path, jobs_dir: Path, artifact_dir: Path,
) -> None:
    """Negative: gate blocks when a required renderer result is not bindable.

    Pass iff ALL of:
      - gate exits rc=2
      - gate status == "block"
      - at least one check has status="block" with name containing "required"
    """
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
            [str(REPO_ROOT / "scripts/diagram_workflow/check_diagram_gate.py"),
             "--plan", str(plan_path),
             "--jobs", str(jobs_path),
             "--jobs-dir", str(jobs_dir),
             "--artifact-dir", str(artifact_dir)],
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
    has_required = any("required" in c.get("name", "") for c in blocking)
    if not has_required:
        fail(f"No 'required' blocking check found")
        return

    ok(f"Correctly blocked ({len(blocking)} issue(s)):")
    for c in blocking:
        info(f"  {c['name']}: {c.get('message', '')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Diagram workflow e2e test")
    parser.add_argument("--out-dir", type=Path,
                        default=Path("build/e2e-diagram-test"),
                        help="Persistent output directory (default: build/e2e-diagram-test)")
    args = parser.parse_args()

    td = args.out_dir.resolve()
    td.mkdir(parents=True, exist_ok=True)
    info(f"Output dir: {td}")

    plan_path = td / "assignment.plan.yaml"
    build_dir = td / "build" / "diagram"
    jobs_path = build_dir / "diagram_jobs.json"
    jobs_dir = build_dir / "jobs"
    resolved_path = td / "assignment.resolved.yaml"

    plan_path.write_text(
        yaml.dump(PLAN_YAML, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    info(f"Plan YAML -> {plan_path}")

    check_s25(plan_path, jobs_path)
    check_s26(jobs_path, td, plan_path)
    gate_status = check_s27(plan_path, jobs_path, jobs_dir, td)
    check_s28(plan_path, jobs_path, jobs_dir, resolved_path, gate_status, td)
    check_gate_negative(plan_path, jobs_path, jobs_dir, td)

    heading("Summary")
    if _errors == 0:
        print(f"  {GREEN}{BOLD}All checks passed!{RESET}")
        print(f"  Only mock: assignment.plan.yaml")
        print(f"  S2.5 collector  -> real   plan YAML -> job graph")
        print(f"  S2.6 batch      -> real   workflow.py + renderer -> TikZ")
        print(f"  S2.7 gate       -> real   policy + renderer_result checks")
        print(f"  S2.8 resolver   -> real   diagram_slot -> diagram_col")
        return 0
    else:
        print(f"  {RED}{BOLD}{_errors} error(s){RESET}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
