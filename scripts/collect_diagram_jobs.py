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

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: PyYAML is required") from exc

# ---------------------------------------------------------------------------
# Import contracts from the sibling module
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    AssignmentPlanDiagramView,
    DiagramJob,
    DiagramJobsManifest,
    DiagramSlotRef,
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


def _content_hash(slot_data: dict[str, object]) -> str:
    """Deterministic SHA-256 of the slot content for staleness detection."""
    canonical = json.dumps(slot_data, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# YAML traversal
# ---------------------------------------------------------------------------

def read_plan_yaml(path: Path) -> AssignmentPlanDiagramView:
    """Read and basic-validate an assignment plan YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return AssignmentPlanDiagramView.model_validate(data)


def _extract_assignment_id(data: AssignmentPlanDiagramView, path: Path) -> str:
    """Get assignment_id from meta block, or fall back to directory name."""
    if data.assignment_id:
        return data.assignment_id
    return path.parent.name


def _find_diagram_slots(data: AssignmentPlanDiagramView) -> list[DiagramSlotRef]:
    """Walk the YAML tree and collect all diagram_slot declarations.

    Returns stable slot refs with JSON Pointer paths and validated slots.
    """
    found: list[DiagramSlotRef] = []

    for si, section in enumerate(data.sections):
        for bi, block in enumerate(section.blocks):

            if block.diagram_slot is not None:
                sp = _slot_path(si, bi, "diagram_slot")
                found.append(DiagramSlotRef(
                    slot_path=sp,
                    slot=block.diagram_slot,
                    section_index=si,
                    block_index=bi,
                ))

            answer_space = block.answer_space
            if answer_space is not None:
                if answer_space.diagram_slot is not None:
                    sp = _slot_path(si, bi, "answer_space", "diagram_slot")
                    found.append(DiagramSlotRef(
                        slot_path=sp,
                        slot=answer_space.diagram_slot,
                        section_index=si,
                        block_index=bi,
                    ))

                for pi, part in enumerate(answer_space.parts):
                    if part.diagram_slot is not None:
                        sp = _slot_path(si, bi, "answer_space", "parts", str(pi), "diagram_slot")
                        found.append(DiagramSlotRef(
                            slot_path=sp,
                            slot=part.diagram_slot,
                            section_index=si,
                            block_index=bi,
                            part_index=pi,
                        ))

    return found


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect_jobs(
    data: AssignmentPlanDiagramView | dict[str, object],
    source_path: Path,
    out_dir: Path,
) -> DiagramJobsManifest:
    """Collect all diagram slots and build a DiagramJobsManifest."""

    if not isinstance(data, AssignmentPlanDiagramView):
        data = AssignmentPlanDiagramView.model_validate(data)
    assignment_id = _extract_assignment_id(data, source_path)
    slot_refs = _find_diagram_slots(data)

    if not slot_refs:
        return DiagramJobsManifest(
            assignment_id=assignment_id,
            source_assignment=source_path.name,
            jobs=[],
        )

    jobs: list[DiagramJob] = []

    for slot_ref in slot_refs:
        slot = slot_ref.slot
        slot_path = slot_ref.slot_path
        job_id = _job_id_from_slot_id(slot.slot_id)
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
            problem_id=slot.source_problem_ref,
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
            content_hash=_content_hash(slot.model_dump(mode="json", by_alias=True)),
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
