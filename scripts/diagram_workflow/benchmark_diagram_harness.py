#!/usr/bin/env python3
"""Run cold assignment-diagram fixtures and write a comparable timing report."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path


def _launcher_path(path: Path) -> Path:
    """Return an absolute launcher path without dereferencing venv symlinks."""

    return path.expanduser().absolute()


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _event_counts(plan: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    jobs_dir = plan.parent / "build" / "diagram" / "jobs"
    for path in jobs_dir.glob("*/workflow_events.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = str(event.get("event") or "")
            stage = str(event.get("stage") or "")
            key = f"{name}:{stage}" if stage else name
            counts[key] = counts.get(key, 0) + 1
    return counts


def run_fixture(
    *,
    repo: Path,
    python: Path,
    plan: Path,
    max_workers: int,
    log_dir: Path,
) -> dict[str, object]:
    command = [
        str(python),
        str(repo / "scripts/diagram_workflow/run_assignment_diagrams.py"),
        str(plan),
        "--max-workers",
        str(max_workers),
        "--python",
        str(python),
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    safe_name = plan.parent.name.replace("/", "_")
    (log_dir / f"{safe_name}.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (log_dir / f"{safe_name}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    build = plan.parent / "build" / "diagram"
    batch = _read_json(build / "diagram_batch_report.json")
    profile = _read_json(build / "pipeline_performance.json")
    jobs = batch.get("jobs") if isinstance(batch.get("jobs"), list) else []
    return {
        "plan": str(plan),
        "returncode": completed.returncode,
        "wall_time_s": round(elapsed, 3),
        "total_jobs": batch.get("total_jobs", 0),
        "ok_count": batch.get("ok_count", 0),
        "failed_count": batch.get("failed_count", 0),
        "cache_hits": sum(1 for job in jobs if isinstance(job, dict) and job.get("cache_hit")),
        "event_counts": _event_counts(plan),
        "pipeline_profile": profile.get("assignment_pipeline", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plans", nargs="+", type=Path)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args()

    repo = args.repo.resolve()
    # Keep the virtualenv launcher path intact. ``Path.resolve()`` follows the
    # ``.venv/bin/python`` symlink to the base interpreter and therefore drops
    # the virtualenv's import path when that resolved executable is launched.
    python = _launcher_path(args.python)
    output = args.out.resolve()
    log_dir = output.with_suffix("")
    log_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.perf_counter()
    fixtures = [
        run_fixture(
            repo=repo,
            python=python,
            plan=plan.resolve(),
            max_workers=max(1, args.max_workers),
            log_dir=log_dir,
        )
        for plan in args.plans
    ]
    report = {
        "schema_version": "diagram-harness-benchmark/v1",
        "label": args.label,
        "repo": str(repo),
        "started_at": started_at,
        "wall_time_s": round(time.perf_counter() - started, 3),
        "fixture_count": len(fixtures),
        "total_jobs": sum(int(item["total_jobs"]) for item in fixtures),
        "ok_count": sum(int(item["ok_count"]) for item in fixtures),
        "failed_count": sum(int(item["failed_count"]) for item in fixtures),
        "fixtures": fixtures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(int(item["returncode"]) != 0 for item in fixtures):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
