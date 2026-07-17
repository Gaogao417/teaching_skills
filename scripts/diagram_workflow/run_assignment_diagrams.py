#!/usr/bin/env python3
"""Run the assignment diagram collect/batch/job-gate/resolve/resolved-gate chain.

This is the deterministic wrapper used by the math-geometry-diagram-renderer
skill. It expects a plan YAML containing diagram_slot declarations and writes a
resolved assignment YAML after per-job and post-resolve gates pass.

By default the stages run in-process through
``assignment_pipeline.run_assignment_diagram_pipeline``: fewer Python
interpreors are spawned and the same library functions drive every stage. The
on-disk artifacts are identical to the legacy script-chained path.

``--process-isolation`` restores a subprocess-isolated chain
(collect_diagram_jobs.py → run_diagram_batch.py → resolve_assignment_diagrams.py
→ check_diagram_gate.py --resolved). It exists for debugging, localization, and
temporary rollback; the single-stage CLIs remain independently runnable for
the same reason.
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


def _run_process_isolation(args: argparse.Namespace) -> None:
    """Subprocess-isolated chain; kept for debugging and rollback."""
    plan_yaml = args.plan_yaml.resolve()
    if not plan_yaml.exists():
        raise SystemExit(f"Plan YAML not found: {plan_yaml}")

    artifact_dir = plan_yaml.parent
    build_dir = artifact_dir / "build" / "diagram"
    jobs_json = build_dir / "diagram_jobs.json"
    jobs_dir = build_dir / "jobs"
    out_yaml = (args.out.resolve() if args.out else default_resolved_path(plan_yaml).resolve())

    py = args.python

    def run(cmd: list[str]) -> None:
        print(f"+ {' '.join(cmd)}")
        if args.dry_run:
            return
        subprocess.run(cmd, cwd=ROOT, check=True)

    run([
        py,
        str(SCRIPT_DIR / "collect_diagram_jobs.py"),
        str(plan_yaml),
        "--out-dir",
        str(build_dir),
    ])
    run([
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
    ])
    run([
        py,
        str(SCRIPT_DIR / "resolve_assignment_diagrams.py"),
        str(plan_yaml),
        "--jobs",
        str(jobs_json),
        "--jobs-dir",
        str(jobs_dir),
        "--artifact-dir",
        str(artifact_dir),
        "--out",
        str(out_yaml),
    ])
    if not args.skip_gate:
        run([
            py,
            str(SCRIPT_DIR / "check_diagram_gate.py"),
            "--plan",
            str(plan_yaml),
            "--jobs",
            str(jobs_json),
            "--jobs-dir",
            str(jobs_dir),
            "--artifact-dir",
            str(artifact_dir),
            "--resolved",
            str(out_yaml),
        ])

    print(f"Resolved YAML: {out_yaml}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run diagram jobs for an assignment plan YAML and resolve diagram slots."
    )
    parser.add_argument("plan_yaml", type=Path, help="Path to *.plan.assignment.yaml")
    parser.add_argument("--out", type=Path, help="Resolved assignment YAML path")
    parser.add_argument("--max-workers", type=int, default=4, help="Parallel jobs per dependency wave")
    parser.add_argument("--python", default=sys.executable, help="Python executable for subprocesses")
    parser.add_argument("--dry-run", action="store_true", help="Print commands/phases without running them")
    parser.add_argument(
        "--skip-gate",
        action="store_true",
        help="Resolve without running check_diagram_gate.py; use only for debugging.",
    )
    parser.add_argument(
        "--process-isolation",
        action="store_true",
        help=(
            "Use the subprocess-isolated chain (collect/batch/resolve/gate "
            "each as a separate Python interpreter). Default runs in-process. "
            "Only use this for debugging, localizing, or temporary rollback."
        ),
    )
    args = parser.parse_args()

    if args.process_isolation:
        _run_process_isolation(args)
        return

    # Default: in-process orchestration. Imported lazily so that --help and the
    # process-isolation path do not pay the import cost or surface import errors
    # (e.g. missing PyYAML) unnecessarily.
    sys.path.insert(0, str(SCRIPT_DIR))
    from assignment_pipeline import run_assignment_diagram_pipeline

    run_assignment_diagram_pipeline(
        args.plan_yaml,
        out=args.out,
        max_workers=args.max_workers,
        python=args.python,
        skip_gate=args.skip_gate,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
