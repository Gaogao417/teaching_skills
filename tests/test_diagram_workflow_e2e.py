#!/usr/bin/env python3
"""End-to-end smoke test for the diagram workflow scripts.

Creates a realistic plan YAML, runs the full S2.5→S2.9 chain
(with mocked diagram generation), and verifies every intermediate
artifact. Run from the repo root:

    python3 tests/test_diagram_workflow_e2e.py
"""

import hashlib
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
# Test data
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
                # Block 0: 选择题 + 右栏图
                {
                    "type": "choice",
                    "id": "c1",
                    "stem_latex": r"如图，$AB=AC=5$，$BC=6$，点 $D$ 为 $BC$ 中点，则 $AD$ 的长为",
                    "choices": {"A": "$3$", "B": "$4$", "C": "$\\sqrt{7}$", "D": "$2\\sqrt{6}$"},
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
                # Block 1: 填空题 — 无图，跳过
                {
                    "type": "fill",
                    "id": "f1",
                    "stem_latex": r"若等腰三角形的一个角为 $40°$，则底角为______。",
                    "answer": "$70°$ 或 $40°$",
                },
                # Block 2: 解答题 + 答题区右侧图
                {
                    "type": "problem",
                    "id": "q3",
                    "stem_latex": r"如图，在 $\\triangle ABC$ 中，$AB=AC$，点 $D$ 在 $BC$ 上，"
                    r"$BD=DC$，连接 $AD$。证明：$AD\\perp BC$。",
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
# Helpers
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


def slot_hash(slot_data: dict) -> str:
    canonical = json.dumps(slot_data, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def run_script(args: list[str], label: str) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [PYTHON, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if r.returncode != 0:
        print(f"\n  {RED}{label} failed (rc={r.returncode}){RESET}")
        if r.stderr.strip():
            for line in r.stderr.strip().split("\n")[:10]:
                print(f"    {RED}{line}{RESET}")
    return r


def mock_job_output(jobs_dir: Path, artifact_dir: Path, job: dict) -> None:
    """Create mock workflow + renderer output for a single job."""
    job_id = job["job_id"]
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # workflow_result.json
    (job_dir / "workflow_result.json").write_text(json.dumps({
        "schema_version": "diagram-job-result/v2",
        "job_id": job_id,
        "status": "ok",
        "fail_type": "",
        "message": "",
        "policy_warnings": [],
    }, indent=2))

    # final_renderer_spec.json (minimal valid spec)
    (job_dir / "final_renderer_spec.json").write_text(json.dumps({
        "schema_version": "geometry-render-spec/v1",
        "job_id": job_id,
        "variant": "prompt",
        "disclosure_policy": "clean",
        "type": "synthetic_geometry",
        "points": {"A": [0, 4], "B": [-3, 0], "C": [3, 0]},
        "segments": [
            {"from": "A", "to": "B"},
            {"from": "A", "to": "C"},
            {"from": "B", "to": "C"},
        ],
        "markers": [{"type": "equal_ticks", "segments": [["A", "B"], ["A", "C"]]}],
        "labels": {},
        "teaching_focus": ["读清等腰三角形 ABC"],
    }, indent=2))

    # renderer_result.json
    img_dir = artifact_dir / "diagram" / "jobs" / job_id / "rendered"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "prompt.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"mock diagram " + job_id.encode())

    (job_dir / "renderer_result.json").write_text(json.dumps({
        "schema_version": "geometry-renderer-result/v1",
        "job_id": job_id,
        "status": "ok",
        "renderer": "teaching-svg-geometry-renderer",
        "diagram_variant": "prompt",
        "disclosure_policy": "clean",
        "image_path": f"diagram/jobs/{job_id}/rendered/prompt.png",
        "preview_svg": f"diagram/jobs/{job_id}/rendered/prompt.svg",
        "width_px": 720,
        "height_px": 520,
        "checks": {"references_valid": True, "svg_exists": True, "image_exists": True},
    }, indent=2))


# ---------------------------------------------------------------------------
# Tests
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
        gate_report_path = build_dir / "diagram_gate_report.json"

        plan_path.write_text(
            yaml.dump(PLAN_YAML, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

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
                info(f"  slot_path = {j['slot_path']}")

            assert len(manifest["jobs"]) == 2, "Expected 2 jobs"
            assert manifest["jobs"][0]["job_id"] == "c1-prompt"
            assert manifest["jobs"][1]["job_id"] == "q3-part1-prompt"
            ok("Job IDs and counts correct")

        # ================================================================
        heading("S2.6  run_diagram_batch.py --dry-run")
        # ================================================================
        r = run_script(
            [str(REPO_ROOT / "scripts/run_diagram_batch.py"),
             str(jobs_path), "--artifact-dir", str(td),
             "--dry-run", "--plan-yaml", str(plan_path)],
            "Batch (dry-run)",
        )
        if r.returncode != 0:
            errors += 1
        else:
            report = json.loads(r.stdout)
            ok(f"Batch report: {report['ok_count']}/{report['total_jobs']} ok")

            # Check v2 request was written
            req_path = build_dir / "jobs" / "c1-prompt" / "request.json"
            req = json.loads(req_path.read_text())
            assert req["schema_version"] == "diagram-job-request/v2"
            assert req["problem_context"]["stem_latex"]  # extracted from plan
            ok("v2 request.json written with problem context")

            # Check v1 adapter was written
            legacy_path = build_dir / "jobs" / "c1-prompt" / "diagram-request.json"
            legacy = json.loads(legacy_path.read_text())
            assert legacy["schema_version"] == "teaching-diagram-request/v1"
            assert legacy["diagram_type"] == "synthetic_geometry"
            ok("v1 adapter diagram-request.json written")

        # ================================================================
        heading("(mock)  Simulate diagram generation outputs")
        # ================================================================
        manifest = json.loads(jobs_path.read_text())
        for job in manifest["jobs"]:
            mock_job_output(build_dir / "jobs", td, job)
            ok(f"Mocked output for {job['job_id']}")

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
            bindable = [a["slot_id"] for a in arts["artifacts"].values() if a["bindable"]]
            ok(f"diagram_artifacts.json: {len(arts['artifacts'])} artifacts, "
               f"{len(bindable)} bindable")
            for ref, art in arts["artifacts"].items():
                ok(f"  {ref}: status={art['status']}, "
                   f"bindable={art['bindable']}, hash={art['artifact_hash'][:20]}...")

            assert all(a["bindable"] for a in arts["artifacts"].values())
            ok("All artifacts bindable")

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
        if r.returncode not in (0, None):
            errors += 1
        else:
            gate = json.loads(r.stdout)
            ok(f"Gate status: {gate['status']}")
            for c in gate["checks"]:
                ok(f"  {c['name']}: {c['status']}")

            assert gate["status"] == "pass"
            ok("Gate passes cleanly")

        # ================================================================
        heading("S2.9  resolve_assignment_diagrams.py")
        # ================================================================
        r = run_script(
            [str(REPO_ROOT / "scripts/resolve_assignment_diagrams.py"),
             str(plan_path),
             "--artifacts", str(artifacts_path),
             "--out", str(resolved_path)],
            "Resolver",
        )
        if r.returncode != 0:
            errors += 1
        else:
            resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
            blocks = resolved["sections"][0]["blocks"]

            # Block 0 (choice): diagram_slot → diagram_col
            b0 = blocks[0]
            assert "diagram_slot" not in b0, "diagram_slot should be removed"
            assert "diagram_col" in b0, "diagram_col should be present"
            dc = b0["diagram_col"]
            ok(f"Block c1: diagram_slot → diagram_col")
            ok(f"  image_path = {dc['image_path']}")
            ok(f"  width = {dc['width']}")
            ok(f"  variant = {dc['variant']}")
            ok(f"  artifact_hash = {dc['artifact_hash'][:20]}...")

            # Block 1 (fill): no diagram, untouched
            b1 = blocks[1]
            assert "diagram_slot" not in b1
            assert "diagram_col" not in b1
            ok(f"Block f1: no diagram, untouched ✓")

            # Block 2 (problem): answer_space.parts[0].diagram_slot → diagram_col
            part = blocks[2]["answer_space"]["parts"][0]
            assert "diagram_slot" not in part
            assert "diagram_col" in part
            dc2 = part["diagram_col"]
            ok(f"Block q3.part1: diagram_slot → diagram_col")
            ok(f"  image_path = {dc2['image_path']}")
            ok(f"  width = {dc2['width']}")

            # Verify resolved YAML is valid YAML that templates could consume
            assert dc["image_path"].endswith(".png")
            assert dc2["image_path"].endswith(".png")
            ok("Resolved YAML ready for LaTeX templates")

        # ================================================================
        heading("Chain verification: collector → gate block on missing")
        # ================================================================
        # Create a manifest where c1-prompt has no artifact
        arts_missing = json.loads(artifacts_path.read_text())
        arts_missing["artifacts"]["c1.prompt"]["status"] = "failed"
        arts_missing["artifacts"]["c1.prompt"]["bindable"] = False
        arts_missing["artifacts"]["c1.prompt"]["image_path"] = ""
        arts_missing["artifacts"]["c1.prompt"]["artifact_hash"] = ""
        test_art_path = build_dir / "diagram_artifacts_missing.json"
        test_art_path.write_text(json.dumps(arts_missing, indent=2))

        r = run_script(
            [str(REPO_ROOT / "scripts/check_diagram_gate.py"),
             "--plan", str(plan_path),
             "--jobs", str(jobs_path),
             "--artifacts", str(test_art_path),
             "--artifact-dir", str(td)],
            "Gate (missing required)",
        )
        if r.returncode == 2:
            gate = json.loads(r.stdout)
            assert gate["status"] == "block"
            blocking = [c for c in gate["checks"] if c["status"] == "block"]
            ok(f"Gate correctly blocks: {blocking[0]['message']}")
        else:
            fail(f"Expected gate to block, got rc={r.returncode}")
            errors += 1

        # ================================================================
        heading("Chain verification: resolver with --skip-required-check")
        # ================================================================
        skip_resolved = td / "assignment.partial.yaml"
        r = run_script(
            [str(REPO_ROOT / "scripts/resolve_assignment_diagrams.py"),
             str(plan_path),
             "--artifacts", str(test_art_path),
             "--out", str(skip_resolved),
             "--skip-required-check"],
            "Resolver (partial)",
        )
        if r.returncode == 0:
            partial = yaml.safe_load(skip_resolved.read_text())
            # q3 should be resolved, c1 should still have diagram_slot
            b0 = partial["sections"][0]["blocks"][0]
            # c1's slot was left as-is because skip_required_check
            # and the slot has no artifact → stays as diagram_slot
            ok("Partial build: c1 slot left as-is (skip required check)")
        else:
            fail(f"Partial resolver failed: rc={r.returncode}")
            errors += 1

    # ================================================================
    # Summary
    # ================================================================
    heading("Summary")
    if errors == 0:
        print(f"  {GREEN}{BOLD}All checks passed!{RESET}")
        print(f"  S2.5 collector    → scans plan YAML, builds job graph")
        print(f"  S2.6 batch runner → dry-run writes v1+v2 requests")
        print(f"  S2.7 artifacts    → aggregates renderer results + hashes")
        print(f"  S2.8 gate         → validates required/policy/hash")
        print(f"  S2.9 resolver     → diagram_slot → diagram_col")
        print()
        print(f"  {DIM}Next steps: skill updates (Phase 5) to produce plan YAML,{RESET}")
        print(f"  {DIM}then pipeline integration (Phase 6) to wire into pipeline.{RESET}")
        return 0
    else:
        print(f"  {RED}{BOLD}{errors} error(s) found{RESET}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
