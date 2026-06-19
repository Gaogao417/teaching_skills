#!/usr/bin/env python3
"""Build a diagram artifacts manifest from per-job results.

Scans job output directories, reads renderer_result.json and
workflow_result.json per job, computes image hashes, and assembles
a DiagramArtifactsManifest.

Usage:
    python3 scripts/diagram_workflow/build_diagram_artifacts.py \
        --jobs <diagram_jobs.json> --jobs-dir <build/diagram/jobs> \
        --out <diagram_artifacts.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    DiagramArtifact,
    DiagramArtifactsManifest,
    DiagramJob,
    DiagramJobsManifest,
    DiagramRunStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, Any] | None:
    """Read JSON, returning None if the file doesn't exist or is invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def resolve_artifact_path(path_value: str, artifact_dir: Path) -> Path:
    """Resolve a potentially relative artifact path against the artifact dir."""
    p = Path(path_value)
    return p if p.is_absolute() else artifact_dir / p


# ---------------------------------------------------------------------------
# Artifact building
# ---------------------------------------------------------------------------

def build_artifact_for_job(
    job: DiagramJob,
    job_dir: Path,
    artifact_dir: Path,
) -> DiagramArtifact:
    """Build a DiagramArtifact from a single job's output directory."""
    rr_data = read_json(job_dir / "renderer_result.json")
    wf_data = read_json(job_dir / "workflow_result.json")

    # Determine status
    if rr_data and rr_data.get("status") == "ok":
        status = DiagramRunStatus.OK
    elif rr_data and rr_data.get("status") == "failed":
        status = DiagramRunStatus.FAILED
    elif wf_data and wf_data.get("status") == "ok":
        # Workflow succeeded but renderer didn't run or has no result
        status = DiagramRunStatus.FAILED
    elif wf_data and wf_data.get("status") == "failed":
        status = DiagramRunStatus.FAILED
    else:
        status = DiagramRunStatus.FAILED

    # Extract fields from renderer result. In the TikZ-only architecture the
    # bindable payload is TeX source; PNG/SVG files are previews for review.
    tikz_fragment = ""
    tikz_fragment_path = ""
    tikz_source_path = ""
    tikz_standalone_path = ""
    tikz_pdf_path = ""
    preview_png_path = ""
    preview_svg = ""
    renderer_audit = ""
    width_px = None
    height_px = None
    aspect_ratio = None
    warnings: list[str] = []

    if rr_data:
        tikz_fragment = rr_data.get("tikz_fragment", "")
        tikz_fragment_path = rr_data.get("tikz_fragment_path", "")
        tikz_source_path = rr_data.get("tikz_source_path", "")
        tikz_standalone_path = rr_data.get("tikz_standalone_path", "")
        tikz_pdf_path = rr_data.get("tikz_pdf_path", "")
        preview_png_path = rr_data.get("preview_png_path", "")
        preview_svg = rr_data.get("preview_svg", "")
        renderer_audit = rr_data.get("renderer_audit", "")
        width_px = rr_data.get("width_px")
        height_px = rr_data.get("height_px")
        aspect_ratio = rr_data.get("aspect_ratio")

    # Compute hash from the bindable TikZ payload. Prefer source files so the
    # manifest can avoid storing large inline fragments, but support inline
    # fragments for small diagrams.
    artifact_hash = ""
    resolved_tikz_for_hash: Path | None = None
    tikz_path_for_hash = tikz_fragment_path or tikz_source_path
    if tikz_path_for_hash:
        candidate = job_dir / tikz_path_for_hash
        if candidate.exists() and candidate.stat().st_size > 0:
            resolved_tikz_for_hash = candidate
            normalized = Path(os.path.relpath(candidate, artifact_dir)).as_posix()
            if tikz_fragment_path:
                tikz_fragment_path = normalized
            else:
                tikz_source_path = normalized
        else:
            candidate = resolve_artifact_path(tikz_path_for_hash, artifact_dir)
            if candidate.exists() and candidate.stat().st_size > 0:
                resolved_tikz_for_hash = candidate
            else:
                warnings.append(f"TikZ source file missing or empty: {tikz_path_for_hash}")

    if resolved_tikz_for_hash:
        artifact_hash = sha256_file(resolved_tikz_for_hash)
    elif tikz_fragment:
        artifact_hash = "sha256:" + hashlib.sha256(tikz_fragment.encode("utf-8")).hexdigest()

    # Compute aspect_ratio if not provided
    if aspect_ratio is None and width_px and height_px:
        aspect_ratio = round(width_px / height_px, 4)

    # Collect warnings
    if wf_data:
        wf_warnings = wf_data.get("policy_warnings") or []
        warnings.extend(wf_warnings)
    if rr_data and rr_data.get("status") != "ok":
        warnings.append(f"renderer status: {rr_data.get('status', 'unknown')}")

    # Determine bindable
    bindable = (
        status == DiagramRunStatus.OK
        and bool(tikz_fragment or tikz_fragment_path or tikz_source_path)
        and bool(artifact_hash)
    )

    # Relative paths for references
    rel_prefix = f"build/diagram/jobs/{job.job_id}"

    return DiagramArtifact(
        slot_id=job.slot_id,
        job_id=job.job_id,
        status=status,
        artifact_kind="tikz",
        variant=job.variant,
        disclosure_policy=job.disclosure_policy,
        tikz_fragment=tikz_fragment,
        tikz_fragment_path=tikz_fragment_path,
        tikz_source_path=tikz_source_path,
        tikz_standalone_path=tikz_standalone_path,
        tikz_pdf_path=tikz_pdf_path,
        preview_png_path=preview_png_path,
        preview_svg=preview_svg,
        renderer_audit=renderer_audit,
        width_px=width_px,
        height_px=height_px,
        aspect_ratio=aspect_ratio,
        hash=artifact_hash,
        renderer_result=f"{rel_prefix}/renderer_result.json" if (job_dir / "renderer_result.json").exists() else "",
        workflow_result=f"{rel_prefix}/workflow_result.json" if (job_dir / "workflow_result.json").exists() else "",
        final_renderer_spec=f"{rel_prefix}/final_renderer_spec.json" if (job_dir / "final_renderer_spec.json").exists() else "",
        bindable=bindable,
        warnings=warnings,
    )


def build_artifacts_manifest(
    jobs_manifest: DiagramJobsManifest,
    jobs_dir: Path,
    artifact_dir: Path,
) -> DiagramArtifactsManifest:
    """Build a complete DiagramArtifactsManifest from all job results."""
    artifacts: dict[str, DiagramArtifact] = {}

    for job in jobs_manifest.jobs:
        job_dir = jobs_dir / job.job_id
        if not job_dir.exists():
            # Job directory doesn't exist at all
            artifacts[job.diagram_ref] = DiagramArtifact(
                slot_id=job.slot_id,
                job_id=job.job_id,
                status=DiagramRunStatus.FAILED,
                variant=job.variant,
                disclosure_policy=job.disclosure_policy,
                bindable=False,
                warnings=["job directory not found"],
            )
            continue

        artifacts[job.diagram_ref] = build_artifact_for_job(
            job, job_dir, artifact_dir
        )

    return DiagramArtifactsManifest(
        assignment_id=jobs_manifest.assignment_id,
        source_jobs="build/diagram/diagram_jobs.json",
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build diagram artifacts manifest from per-job results"
    )
    parser.add_argument(
        "--jobs",
        type=Path,
        required=True,
        help="Path to diagram_jobs.json",
    )
    parser.add_argument(
        "--jobs-dir",
        type=Path,
        required=True,
        help="Path to build/diagram/jobs/ directory",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Artifact root directory (for resolving relative image paths)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for diagram_artifacts.json",
    )
    args = parser.parse_args()

    jobs_path = args.jobs.resolve()
    jobs_dir = args.jobs_dir.resolve()
    out_path = args.out.resolve()

    if not jobs_path.exists():
        raise SystemExit(f"Jobs manifest not found: {jobs_path}")
    if not jobs_dir.exists():
        raise SystemExit(f"Jobs directory not found: {jobs_dir}")

    # Determine artifact dir
    artifact_dir = args.artifact_dir.resolve() if args.artifact_dir else jobs_dir.parent.parent.parent

    # Load jobs manifest
    raw = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs_manifest = DiagramJobsManifest(**raw)

    # Build artifacts
    manifest = build_artifacts_manifest(jobs_manifest, jobs_dir, artifact_dir)

    # Write
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ok_count = sum(1 for a in manifest.artifacts.values() if a.status == DiagramRunStatus.OK)
    bindable_count = sum(1 for a in manifest.artifacts.values() if a.bindable)
    total = len(manifest.artifacts)

    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print(f"\nArtifacts: {total} total, {ok_count} ok, {bindable_count} bindable", file=sys.stderr)


if __name__ == "__main__":
    main()
