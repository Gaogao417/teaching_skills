#!/usr/bin/env python3
"""Collect diagram slots from assignment.plan.yaml into an executable job manifest.

Reads plan YAML, scans all diagram_slot declarations, validates them as
DiagramSlot contracts, converts each to a DiagramJob, and writes a
DiagramJobsManifest to build/diagram/diagram_jobs.json.

Usage:
    python3 scripts/collect_diagram_jobs.py <plan.yaml> [--out-dir <dir>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: PyYAML is required") from exc

# ---------------------------------------------------------------------------
# Import contracts from the sibling module
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    DiagramJob,
    DiagramJobsManifest,
    DiagramSlot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_id_from_slot_id(slot_id: str) -> str:
    """Convert a dotted slot_id to a hyphenated job_id."""
    return slot_id.replace(".", "-")


def _slot_path(section_idx: int, block_idx: int, *parts: str) -> str:
    """Build a JSON Pointer string for a diagram_slot location."""
    segments = ["sections", str(section_idx), "blocks", str(block_idx)]
    for p in parts:
        segments.append(p)
    return "/" + "/".join(segments)


def _content_hash(slot_data: dict[str, Any]) -> str:
    """Deterministic SHA-256 of the slot content for staleness detection."""
    canonical = json.dumps(slot_data, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# YAML traversal
# ---------------------------------------------------------------------------

def read_plan_yaml(path: Path) -> dict[str, Any]:
    """Read and basic-validate an assignment plan YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _extract_assignment_id(data: dict[str, Any], path: Path) -> str:
    """Get assignment_id from meta block, or fall back to directory name."""
    meta = data.get("meta")
    if isinstance(meta, dict):
        aid = meta.get("assignment_id")
        if isinstance(aid, str) and aid.strip():
            return aid.strip()
    return path.parent.name


def _find_diagram_slots(
    data: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Walk the YAML tree and collect all diagram_slot declarations.

    Returns a list of (slot_path, slot_data) tuples.
    """
    found: list[tuple[str, dict[str, Any]]] = []

    for si, section in enumerate(data.get("sections") or []):
        if not isinstance(section, dict):
            continue
        for bi, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict):
                continue

            # diagram_slot directly under a block
            if isinstance(block.get("diagram_slot"), dict):
                sp = _slot_path(si, bi, "diagram_slot")
                found.append((sp, block["diagram_slot"]))

            # diagram_slot under answer_space
            answer_space = block.get("answer_space")
            if isinstance(answer_space, dict):
                if isinstance(answer_space.get("diagram_slot"), dict):
                    sp = _slot_path(si, bi, "answer_space", "diagram_slot")
                    found.append((sp, answer_space["diagram_slot"]))

                # diagram_slot under answer_space.parts[]
                for pi, part in enumerate(answer_space.get("parts") or []):
                    if not isinstance(part, dict):
                        continue
                    if isinstance(part.get("diagram_slot"), dict):
                        sp = _slot_path(
                            si, bi, "answer_space", f"parts/{pi}", "diagram_slot"
                        )
                        found.append((sp, part["diagram_slot"]))

    return found


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect_jobs(
    data: dict[str, Any],
    source_path: Path,
    out_dir: Path,
) -> DiagramJobsManifest:
    """Collect all diagram slots and build a DiagramJobsManifest."""

    assignment_id = _extract_assignment_id(data, source_path)
    slots = _find_diagram_slots(data)

    if not slots:
        return DiagramJobsManifest(
            assignment_id=assignment_id,
            source_assignment=source_path.name,
            jobs=[],
        )

    jobs: list[DiagramJob] = []

    for slot_path, slot_data in slots:
        # Validate as DiagramSlot contract
        try:
            slot = DiagramSlot(**slot_data)
        except Exception as exc:
            raise ValueError(
                f"Invalid diagram_slot at {slot_path}: {exc}"
            ) from exc

        job_id = _job_id_from_slot_id(slot.slot_id)
        job_dir = out_dir / "jobs" / job_id
        public_image_dir = f"diagram/jobs/{job_id}/rendered"

        # Compute depends_on from reuse_geometry_from (already a slot_id)
        depends_on: list[str] = []
        if slot.reuse_geometry_from:
            depends_on.append(_job_id_from_slot_id(slot.reuse_geometry_from))

        # Convert reuse_geometry_from to job_id form for DiagramJob
        reuse_job_id = ""
        if slot.reuse_geometry_from:
            reuse_job_id = _job_id_from_slot_id(slot.reuse_geometry_from)

        job = DiagramJob(
            job_id=job_id,
            slot_id=slot.slot_id,
            diagram_ref=slot.diagram_ref,
            slot_path=slot_path,
            problem_id=slot_data.get("source_problem_ref", ""),
            variant=slot.variant,
            disclosure_policy=slot.disclosure_policy,
            required=slot.required,
            on_failure=slot.on_failure,
            engine=slot.engine,
            diagram_kind=slot.diagram_kind,
            teaching_intent=slot.teaching_intent,
            request_path=f"build/diagram/jobs/{job_id}/request.json",
            out_dir=f"build/diagram/jobs/{job_id}",
            public_image_dir=public_image_dir,
            depends_on=depends_on,
            content_hash=_content_hash(slot_data),
            reuse_geometry_from=reuse_job_id,
        )
        jobs.append(job)

    manifest = DiagramJobsManifest(
        assignment_id=assignment_id,
        source_assignment=source_path.name,
        jobs=jobs,
    )
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect diagram slots from plan YAML into a job manifest"
    )
    parser.add_argument(
        "plan_yaml",
        type=Path,
        help="Path to assignment.plan.yaml",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Output directory for diagram build artifacts "
             "(defaults to <plan_yaml_dir>/build/diagram)",
    )
    args = parser.parse_args()

    plan_path = args.plan_yaml.resolve()
    if not plan_path.exists():
        raise SystemExit(f"Plan YAML not found: {plan_path}")

    out_dir = (args.out_dir or (plan_path.parent / "build" / "diagram")).resolve()

    data = read_plan_yaml(plan_path)
    manifest = collect_jobs(data, plan_path, out_dir)

    # Write manifest
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "diagram_jobs.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2))

    if not manifest.jobs:
        print(f"\nNo diagram_slot declarations found in {plan_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
