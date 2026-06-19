#!/usr/bin/env python3
"""Debug dump for renderer bindings.

The production TikZ path no longer uses diagram_artifacts.json as a contract.
Gate and resolver read per-job renderer_result.json directly through
renderer_bindings.py. This script remains as a convenience for inspecting the
same derived binding manifest.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from renderer_bindings import manifest_from_paths, write_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump renderer bindings from per-job renderer_result.json files")
    parser.add_argument("--jobs", type=Path, required=True, help="Path to diagram_jobs.json")
    parser.add_argument("--jobs-dir", type=Path, required=True, help="Path to build/diagram/jobs/ directory")
    parser.add_argument("--artifact-dir", type=Path, help="Artifact root directory for resolving relative TikZ paths")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for renderer_bindings.json",
    )
    args = parser.parse_args()

    jobs_path = args.jobs.resolve()
    jobs_dir = args.jobs_dir.resolve()
    artifact_dir = args.artifact_dir.resolve() if args.artifact_dir else jobs_path.parents[2]
    if not jobs_path.exists():
        raise SystemExit(f"Jobs manifest not found: {jobs_path}")
    if not jobs_dir.exists():
        raise SystemExit(f"Jobs directory not found: {jobs_dir}")

    manifest = manifest_from_paths(jobs_path, jobs_dir, artifact_dir)
    write_json(args.out.resolve(), manifest)
    print(f"Renderer bindings written to {args.out.resolve()}")


if __name__ == "__main__":
    main()
