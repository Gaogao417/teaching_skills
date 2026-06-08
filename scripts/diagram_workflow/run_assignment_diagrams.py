#!/usr/bin/env python3
"""Run the assignment diagram collect/batch/gate/resolve chain.

This is the deterministic wrapper used by the math-geometry-diagram-renderer
skill. It expects a plan YAML containing diagram_slot declarations and writes a
resolved assignment YAML after generated diagram artifacts pass the gate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]


def default_resolved_path(plan_yaml: Path) -> Path:
    name = plan_yaml.name
    if ".plan.assignment.yaml" in name:
        return plan_yaml.with_name(name.replace(".plan.assignment.yaml", ".resolved.assignment.yaml"))
    if name.endswith(".plan.yaml"):
        return plan_yaml.with_name(name[: -len(".plan.yaml")] + ".resolved.yaml")
    return plan_yaml.with_suffix(".resolved.yaml")


def run(cmd: list[str], cwd: Path, dry_run: bool) -> None:
    printable = " ".join(cmd)
    print(f"+ {printable}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run diagram jobs for an assignment plan YAML and resolve diagram slots."
    )
    parser.add_argument("plan_yaml", type=Path, help="Path to *.plan.assignment.yaml")
    parser.add_argument("--out", type=Path, help="Resolved assignment YAML path")
    parser.add_argument("--max-workers", type=int, default=4, help="Parallel jobs per dependency wave")
    parser.add_argument("--python", default=sys.executable, help="Python executable for subprocesses")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")
    parser.add_argument(
        "--skip-gate",
        action="store_true",
        help="Resolve without running check_diagram_gate.py; use only for debugging.",
    )
    args = parser.parse_args()

    plan_yaml = args.plan_yaml.resolve()
    if not plan_yaml.exists():
        raise SystemExit(f"Plan YAML not found: {plan_yaml}")

    artifact_dir = plan_yaml.parent
    build_dir = artifact_dir / "build" / "diagram"
    jobs_json = build_dir / "diagram_jobs.json"
    jobs_dir = build_dir / "jobs"
    artifacts_json = build_dir / "diagram_artifacts.json"
    out_yaml = (args.out.resolve() if args.out else default_resolved_path(plan_yaml).resolve())

    py = args.python
    common_cwd = ROOT

    run(
        [
            py,
            str(SCRIPT_DIR / "collect_diagram_jobs.py"),
            str(plan_yaml),
            "--out-dir",
            str(build_dir),
        ],
        cwd=common_cwd,
        dry_run=args.dry_run,
    )
    run(
        [
            py,
            str(SCRIPT_DIR / "run_diagram_batch.py"),
            str(jobs_json),
            "--artifact-dir",
            str(artifact_dir),
            "--plan-yaml",
            str(plan_yaml),
            "--max-workers",
            str(args.max_workers),
            "--python",
            py,
        ],
        cwd=common_cwd,
        dry_run=args.dry_run,
    )
    run(
        [
            py,
            str(SCRIPT_DIR / "build_diagram_artifacts.py"),
            "--jobs",
            str(jobs_json),
            "--jobs-dir",
            str(jobs_dir),
            "--artifact-dir",
            str(artifact_dir),
            "--out",
            str(artifacts_json),
        ],
        cwd=common_cwd,
        dry_run=args.dry_run,
    )
    if not args.skip_gate:
        run(
            [
                py,
                str(SCRIPT_DIR / "check_diagram_gate.py"),
                "--plan",
                str(plan_yaml),
                "--jobs",
                str(jobs_json),
                "--artifacts",
                str(artifacts_json),
                "--artifact-dir",
                str(artifact_dir),
            ],
            cwd=common_cwd,
            dry_run=args.dry_run,
        )
    run(
        [
            py,
            str(SCRIPT_DIR / "resolve_assignment_diagrams.py"),
            str(plan_yaml),
            "--artifacts",
            str(artifacts_json),
            "--out",
            str(out_yaml),
        ],
        cwd=common_cwd,
        dry_run=args.dry_run,
    )

    print(f"Resolved YAML: {out_yaml}")


if __name__ == "__main__":
    main()
