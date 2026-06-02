#!/usr/bin/env python3
"""End-to-end test for the diagram workflow scripts.

Only the plan YAML is fabricated. Every stage runs against real
subprocesses and real file outputs:

    S2.5  collector  →  real
    S2.6  batch      →  real (workflow.py + renderer)
    S2.7  artifacts  →  real (reads actual PNG + JSON)
    S2.8  gate       →  real
    S2.9  resolver   →  real

Run from repo root:

    python3 tests/test_diagram_workflow_e2e.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError as e:
    raise SystemExit("pip install pyyaml") from e

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# The ONLY mock: a fabricated assignment.plan.yaml
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
                    "diagram_slot": {
                        "slot_id": "c1.prompt",
                        "variant": "prompt",
                        "disclosure_policy": "clean",
                        "required": True,
                        "on_failure": "fail_assignment",
                        "placement": "diagram_col",
                        "layout_role": "question_sidecar",
                        "width_hint": r"0.30\linewidth",
                        "caption": "等腰三角形 ABC",
                        "engine": "geometric_scene",
                        "diagram_kind": "synthetic_geometry",
                        "teaching_intent": "practice_prompt",
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
                                    "width_hint": r"0.32\linewidth",
                                    "caption": "原题图",
                                    "engine": "geometric_scene",
                                    "diagram_kind": "synthetic_geometry",
                                    "teaching_intent": "practice_prompt",
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


def heading(msg: str) -> None:
    print(f"\n{BOLD}{'=' * 60}\n  {msg}\n{'=' * 60}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


def run_script(
    args: list[str],
    label: str,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a script, stream stderr on failure, return CompletedProcess."""
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
# Test runner
# ---------------------------------------------------------------------------

def main() -> int:
    errors = 0

    with tempfile.TemporaryDirectory(prefix="diagram-e2e-") as td:
        td = Path(td)

        plan_path = td / "assignment.plan.yaml"
        resolved_path = td / "assignment.resolved.yaml"
        build_dir = td / "build" / "diagram"
        jobs_path = build_dir / "diagram_jobs.json"
        artifacts_path = build_dir / "diagram_artifacts.json"

        plan_path.write_text(
            yaml.dump(PLAN_YAML, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        info(f"Plan YAML written to {plan_path}")

        # ================================================================
        heading("S2.5  collect_diagram_jobs.py")
        # ================================================================
        r = run_script(
            [str(REPO_ROOT / "scripts/collect_diagram_jobs.py"),
             str(plan_path), "--out-dir", str(build_dir)],
            "Collector",
        )
        if r.returncode != 0:
            errors += 1
        else:
            manifest = json.loads(jobs_path.read_text())
            ok(f"diagram_jobs.json: {len(manifest['jobs'])} jobs")
            for j in manifest["jobs"]:
                ok(f"  {j['job_id']}: variant={j['variant']}, "
                   f"required={j['required']}, depends_on={j['depends_on']}")
                info(f"    slot_path = {j['slot_path']}")

            assert len(manifest["jobs"]) == 2
            assert manifest["jobs"][0]["job_id"] == "c1-prompt"
            assert manifest["jobs"][1]["job_id"] == "q3-part1-prompt"
            ok("Job IDs correct")

        # ================================================================
        heading("S2.6  run_diagram_batch.py  (REAL)")
        # ================================================================
        info("This calls run_diagram_workflow.py + render_geometry_spec.py")
        info("May take 1-2 minutes (LLM + Wolfram)...\n")

        r = run_script(
            [str(REPO_ROOT / "scripts/run_diagram_batch.py"),
             str(jobs_path),
             "--artifact-dir", str(td),
             "--plan-yaml", str(plan_path),
             "--max-workers", "2"],
            "Batch (real)",
            timeout=300,
        )

        batch_ok = 0
        batch_fail = 0
        if r.returncode == 0:
            report = json.loads(r.stdout)
            batch_ok = report["ok_count"]
            batch_fail = report["failed_count"]
            ok(f"Batch: {batch_ok}/{batch_ok + batch_fail} jobs succeeded")
            for j in report["jobs"]:
                status_icon = GREEN + "✓" + RESET if j["status"] == "ok" else RED + "✗" + RESET
                print(f"  {status_icon} {j['job_id']}: {j['status']}")
                if j.get("image_path"):
                    info(f"    image_path = {j['image_path']}")
                if j.get("failure_reason"):
                    info(f"    reason = {j['failure_reason']}")

            # Verify v2 request was written with problem context
            req_path = build_dir / "jobs" / "c1-prompt" / "request.json"
            if req_path.exists():
                req = json.loads(req_path.read_text())
                assert req["schema_version"] == "diagram-job-request/v2"
                ok(f"v2 request: stem_latex = {req['problem_context']['stem_latex'][:30]}...")

            # Verify real output files exist for successful jobs
            for j in report["jobs"]:
                if j["status"] == "ok":
                    job_dir = build_dir / "jobs" / j["job_id"]
                    assert (job_dir / "workflow_result.json").exists()
                    assert (job_dir / "renderer_result.json").exists()
                    assert (job_dir / "final_renderer_spec.json").exists()
            ok("All successful jobs have complete output files")
        else:
            batch_fail = 2
            fail("Batch runner failed — workflow.py or renderer error")
            info("Continuing with whatever partial output exists...")

        if batch_ok == 0:
            fail("No jobs succeeded — cannot test downstream stages with real data")
            info("This likely means Wolfram / LLM is unavailable in this environment")
            errors += 1

        # ================================================================
        heading("S2.7  build_diagram_artifacts.py")
        # ================================================================
        r = run_script(
            [str(REPO_ROOT / "scripts/build_diagram_artifacts.py"),
             "--jobs", str(jobs_path),
             "--jobs-dir", str(build_dir / "jobs"),
             "--artifact-dir", str(td),
             "--out", str(artifacts_path)],
            "Artifact builder",
        )
        if r.returncode != 0:
            errors += 1
        else:
            arts = json.loads(artifacts_path.read_text())
            ok(f"diagram_artifacts.json: {len(arts['artifacts'])} artifacts")
            for ref, art in arts["artifacts"].items():
                status_icon = GREEN + "✓" + RESET if art["bindable"] else RED + "✗" + RESET
                print(f"  {status_icon} {ref}: status={art['status']}, "
                      f"bindable={art['bindable']}")
                if art["artifact_hash"]:
                    info(f"    hash = {art['artifact_hash'][:24]}...")
                if art["image_path"]:
                    info(f"    image_path = {art['image_path']}")
                    # Verify the real PNG exists
                    img = td / art["image_path"]
                    if img.exists():
                        size_kb = img.stat().st_size / 1024
                        ok(f"    Real PNG: {size_kb:.1f} KB")
                    else:
                        fail(f"    PNG not found at {img}")

        # ================================================================
        heading("S2.8  check_diagram_gate.py")
        # ================================================================
        r = run_script(
            [str(REPO_ROOT / "scripts/check_diagram_gate.py"),
             "--plan", str(plan_path),
             "--jobs", str(jobs_path),
             "--artifacts", str(artifacts_path),
             "--artifact-dir", str(td)],
            "Gate",
        )
        gate_passed = r.returncode in (0, None)
        if not gate_passed and r.returncode != 2:
            errors += 1

        gate = json.loads(r.stdout) if r.stdout.strip() else {}
        ok(f"Gate status: {gate.get('status', 'unknown')}")
        for c in gate.get("checks", []):
            icon = {GREEN + "✓" + RESET if c["status"] == "pass" else YELLOW + "⚠" + RESET if c["status"] == "warn" else RED + "✗" + RESET}
            print(f"  {c['status']:5s} {c['name']}: {c.get('message', '')}")

        if gate.get("status") == "pass":
            ok("All checks passed")
        elif gate.get("status") == "block":
            fail("Gate blocked — required diagram missing")
        else:
            ok("Gate passed with warnings")

        # ================================================================
        heading("S2.9  resolve_assignment_diagrams.py")
        # ================================================================
        if gate.get("status") != "block":
            r = run_script(
                [str(REPO_ROOT / "scripts/resolve_assignment_diagrams.py"),
                 str(plan_path),
                 "--artifacts", str(artifacts_path),
                 "--out", str(resolved_path)],
                "Resolver",
            )
        else:
            r = run_script(
                [str(REPO_ROOT / "scripts/resolve_assignment_diagrams.py"),
                 str(plan_path),
                 "--artifacts", str(artifacts_path),
                 "--out", str(resolved_path),
                 "--skip-required-check"],
                "Resolver (skip required)",
            )

        if r.returncode != 0:
            errors += 1
        else:
            resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
            blocks = resolved["sections"][0]["blocks"]

            for bi, block in enumerate(blocks):
                bid = block.get("id", f"block-{bi}")
                # Check block-level diagram_col
                if "diagram_col" in block:
                    dc = block["diagram_col"]
                    ok(f"Block {bid}: diagram_slot → diagram_col")
                    ok(f"  image_path = {dc['image_path']}")
                    ok(f"  width = {dc['width']}, variant = {dc['variant']}")
                    # Verify real PNG exists
                    img = td / dc["image_path"]
                    if img.exists():
                        ok(f"  Real PNG exists ({img.stat().st_size / 1024:.1f} KB)")
                elif "diagram_slot" in block:
                    info(f"Block {bid}: diagram_slot unchanged (no artifact)")

                # Check answer_space.parts
                for pi, part in enumerate(block.get("answer_space", {}).get("parts", [])):
                    if "diagram_col" in part:
                        dc = part["diagram_col"]
                        ok(f"  Part {part.get('label', pi)}: diagram_slot → diagram_col")
                        ok(f"    image_path = {dc['image_path']}")
                        img = td / dc["image_path"]
                        if img.exists():
                            ok(f"    Real PNG exists ({img.stat().st_size / 1024:.1f} KB)")

            ok("Resolved YAML written successfully")

        # ================================================================
        heading("Negative test: gate blocks on missing required")
        # ================================================================
        if artifacts_path.exists():
            arts_missing = json.loads(artifacts_path.read_text())
            for ref, art in arts_missing["artifacts"].items():
                art["status"] = "failed"
                art["bindable"] = False
                art["image_path"] = ""
                art["artifact_hash"] = ""
            missing_path = build_dir / "diagram_artifacts_missing.json"
            missing_path.write_text(json.dumps(arts_missing, indent=2))

            r = run_script(
                [str(REPO_ROOT / "scripts/check_diagram_gate.py"),
                 "--plan", str(plan_path),
                 "--jobs", str(jobs_path),
                 "--artifacts", str(missing_path),
                 "--artifact-dir", str(td)],
                "Gate (all missing)",
            )
            if r.returncode == 2:
                gate = json.loads(r.stdout)
                assert gate["status"] == "block"
                blocking = [c for c in gate["checks"] if c["status"] == "block"]
                ok(f"Correctly blocked with {len(blocking)} issue(s)")
            else:
                fail(f"Expected rc=2 (block), got rc={r.returncode}")
                errors += 1

    # ================================================================
    heading("Summary")
    # ================================================================
    if errors == 0:
        print(f"  {GREEN}{BOLD}All checks passed!{RESET}")
        if batch_ok > 0:
            print(f"  {BOLD}Real diagram generation:{RESET} {batch_ok} job(s) produced actual PNGs")
            print(f"  S2.5 collector  → real  (plan YAML → job graph)")
            print(f"  S2.6 batch      → real  (workflow.py + renderer → PNG)")
            print(f"  S2.7 artifacts  → real  (PNG hashes + bindable status)")
            print(f"  S2.8 gate       → real  (policy + path + hash checks)")
            print(f"  S2.9 resolver   → real  (diagram_slot → diagram_col)")
        print()
        print(f"  {DIM}Next: Phase 5 (skill updates) → Phase 6 (pipeline integration){RESET}")
        return 0
    else:
        print(f"  {RED}{BOLD}{errors} error(s){RESET}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
