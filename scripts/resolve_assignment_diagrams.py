#!/usr/bin/env python3
"""Resolve diagram slots in plan YAML by binding generated artifacts.

Reads assignment.plan.yaml + diagram_artifacts.json, replaces each
diagram_slot with a resolved diagram object (diagram_col / type: diagram)
consumable by LaTeX templates, and writes assignment.resolved.yaml.

Usage:
    python3 scripts/resolve_assignment_diagrams.py <plan.yaml> \
        --artifacts <diagram_artifacts.json> --out <resolved.yaml>
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: PyYAML is required") from exc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    DiagramArtifactsManifest,
    DiagramArtifact,
    DiagramRunStatus,
    ResolvedDiagramImage,
)


# ---------------------------------------------------------------------------
# JSON Pointer resolution
# ---------------------------------------------------------------------------

def _parse_pointer(pointer: str) -> list[str]:
    """Parse a JSON Pointer string into path segments.

    Handles escaped ~0 and ~1 per RFC 6901.
    """
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer (must start with /): {pointer}")
    raw = pointer[1:]  # strip leading /
    if not raw:
        return []
    return [
        segment.replace("~1", "/").replace("~0", "~")
        for segment in raw.split("/")
    ]


def _get_by_pointer(data: dict, pointer: str) -> Any:
    """Retrieve a value from a nested dict by JSON Pointer."""
    segments = _parse_pointer(pointer)
    current = data
    for seg in segments:
        if isinstance(current, dict):
            current = current[seg]
        elif isinstance(current, list):
            current = current[int(seg)]
        else:
            raise KeyError(f"Cannot traverse through {type(current).__name__} at segment '{seg}'")
    return current


def _set_by_pointer(data: dict, pointer: str, value: Any) -> None:
    """Set a value in a nested dict by JSON Pointer, replacing the parent key.

    Because diagram_slot needs to be replaced by diagram_col (a different key),
    this resolves the parent path and replaces the last segment's key.
    """
    segments = _parse_pointer(pointer)
    if len(segments) < 1:
        raise ValueError("Pointer must have at least one segment")
    parent_segments = segments[:-1]
    leaf_key = segments[-1]

    current: Any = data
    for seg in parent_segments:
        if isinstance(current, dict):
            current = current[seg]
        elif isinstance(current, list):
            current = current[int(seg)]
        else:
            raise KeyError(f"Cannot traverse through {type(current).__name__} at segment '{seg}'")

    if isinstance(current, dict):
        del current[leaf_key]
        # value is a dict that may carry a different key; merge it
        if isinstance(value, dict):
            current.update(value)
        else:
            current[leaf_key] = value
    elif isinstance(current, list):
        idx = int(leaf_key)
        current[idx] = value
    else:
        raise TypeError(f"Cannot set value in {type(current).__name__}")


# ---------------------------------------------------------------------------
# Placement → target field mapping
# ---------------------------------------------------------------------------

def _resolved_field_for_placement(placement: str) -> str:
    """Map a DiagramSlot.placement value to the resolved YAML key.

    Examples:
        "diagram_col" or "answer_space.parts[].diagram_col" → "diagram_col"
        "diagram_row.items[]" → "diagram_row_item" (special)
        "block_center" → "diagram" (standalone block)
    """
    if "diagram_col" in placement:
        return "diagram_col"
    if "diagram_row" in placement:
        return "diagram_row_item"
    return "diagram_col"  # default


# ---------------------------------------------------------------------------
# Slot resolution
# ---------------------------------------------------------------------------

def _resolve_slot(
    slot_data: dict[str, Any],
    artifact: DiagramArtifact,
) -> dict[str, dict[str, Any]]:
    """Build a resolved diagram object from a slot and its artifact.

    Returns a single-key dict like {"diagram_col": {...}} ready for
    _set_by_pointer to merge into the parent container.
    """
    resolved = ResolvedDiagramImage(
        image_path=artifact.image_path,
        diagram_ref=slot_data.get("diagram_ref", slot_data.get("slot_id", "")),
        diagram_job_id=artifact.job_id,
        width=slot_data.get("width_hint", ""),
        caption=slot_data.get("caption", ""),
        variant=artifact.variant,
        disclosure_policy=artifact.disclosure_policy,
        artifact_hash=artifact.artifact_hash,
    )

    field = _resolved_field_for_placement(slot_data.get("placement", "diagram_col"))
    return {field: resolved.model_dump(mode="json")}


def _handle_missing_slot(
    slot_data: dict[str, Any],
) -> dict[str, Any] | None:
    """Determine the fallback for a slot with no bindable artifact.

    Returns None for omit_diagram, a dict with fallback content for
    textual_fallback, or raises for fail_assignment.
    """
    on_failure = slot_data.get("on_failure", "fail_assignment")

    if on_failure == "omit_diagram":
        return None  # signal: remove the slot entirely

    if on_failure == "textual_fallback":
        field = _resolved_field_for_placement(slot_data.get("placement", "diagram_col"))
        return {
            field: {
                "fallback": True,
                "message": slot_data.get("caption", "图暂不可用"),
            }
        }

    # fail_assignment or unspecified
    slot_id = slot_data.get("slot_id", "<unknown>")
    raise ValueError(
        f"Required diagram slot '{slot_id}' has no bindable artifact "
        f"(on_failure={on_failure})"
    )


# ---------------------------------------------------------------------------
# Main resolution
# ---------------------------------------------------------------------------

def resolve_assignment(
    plan_data: dict[str, Any],
    artifacts_manifest: DiagramArtifactsManifest,
    *,
    skip_required_check: bool = False,
) -> dict[str, Any]:
    """Resolve all diagram slots in plan_data using artifacts.

    Returns a deep copy of plan_data with diagram_slots replaced by
    resolved diagram objects.

    If skip_required_check is True, missing required slots produce a
    warning dict instead of raising (used during partial builds).
    """
    result = copy.deepcopy(plan_data)
    artifacts = artifacts_manifest.artifacts

    # Collect all slots with their paths (same logic as collector)
    slots_to_resolve: list[tuple[str, dict[str, Any]]] = []
    for si, section in enumerate(result.get("sections") or []):
        if not isinstance(section, dict):
            continue
        for bi, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict):
                continue

            # diagram_slot under block
            if isinstance(block.get("diagram_slot"), dict):
                sp = f"/sections/{si}/blocks/{bi}/diagram_slot"
                slots_to_resolve.append((sp, block["diagram_slot"]))

            # diagram_slot under answer_space
            answer_space = block.get("answer_space")
            if isinstance(answer_space, dict):
                if isinstance(answer_space.get("diagram_slot"), dict):
                    sp = f"/sections/{si}/blocks/{bi}/answer_space/diagram_slot"
                    slots_to_resolve.append((sp, answer_space["diagram_slot"]))

                for pi, part in enumerate(answer_space.get("parts") or []):
                    if not isinstance(part, dict):
                        continue
                    if isinstance(part.get("diagram_slot"), dict):
                        sp = (
                            f"/sections/{si}/blocks/{bi}"
                            f"/answer_space/parts/{pi}/diagram_slot"
                        )
                        slots_to_resolve.append((sp, part["diagram_slot"]))

    # Resolve each slot
    for slot_path, slot_data in slots_to_resolve:
        diagram_ref = slot_data.get("diagram_ref") or slot_data.get("slot_id", "")
        artifact = artifacts.get(diagram_ref)

        if artifact and artifact.bindable and artifact.status == DiagramRunStatus.OK:
            replacement = _resolve_slot(slot_data, artifact)
        elif artifact and artifact.status == DiagramRunStatus.OK and not artifact.bindable:
            # Artifact exists but not fully bindable; try anyway with warnings
            replacement = _resolve_slot(slot_data, artifact)
        else:
            # No usable artifact
            try:
                replacement = _handle_missing_slot(slot_data)
            except ValueError:
                if skip_required_check:
                    # Leave the slot as-is for a partial build
                    continue
                raise

        if replacement is None:
            # omit_diagram: remove the slot entirely
            _set_by_pointer(result, slot_path, {})
        else:
            _set_by_pointer(result, slot_path, replacement)

    return result


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------

def read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve diagram slots in plan YAML using generated artifacts"
    )
    parser.add_argument(
        "plan_yaml",
        type=Path,
        help="Path to assignment.plan.yaml",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        required=True,
        help="Path to diagram_artifacts.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for assignment.resolved.yaml",
    )
    parser.add_argument(
        "--skip-required-check",
        action="store_true",
        help="Skip errors for missing required slots (partial build)",
    )
    args = parser.parse_args()

    plan_path = args.plan_yaml.resolve()
    artifacts_path = args.artifacts.resolve()
    out_path = args.out.resolve()

    if not plan_path.exists():
        raise SystemExit(f"Plan YAML not found: {plan_path}")
    if not artifacts_path.exists():
        raise SystemExit(f"Artifacts manifest not found: {artifacts_path}")

    plan_data = read_yaml(plan_path)
    artifacts_raw = json.loads(artifacts_path.read_text(encoding="utf-8"))
    artifacts_manifest = DiagramArtifactsManifest(**artifacts_raw)

    try:
        resolved = resolve_assignment(
            plan_data,
            artifacts_manifest,
            skip_required_check=args.skip_required_check,
        )
    except ValueError as exc:
        print(f"Resolution failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    write_yaml(out_path, resolved)
    print(f"Resolved YAML written to {out_path}")
    slot_count = sum(
        1 for sp, sd in _collect_slots_from_result(resolved)
        if not sd  # empty dict means slot was removed
    )
    print(f"Slots resolved: {slot_count}")


def _collect_slots_from_result(data: dict) -> list[tuple[str, dict]]:
    """Quick scan for remaining diagram_slot or resolved diagram_col fields."""
    found: list[tuple[str, dict]] = []
    for si, section in enumerate(data.get("sections") or []):
        if not isinstance(section, dict):
            continue
        for bi, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict):
                continue
            for key in ("diagram_col", "diagram_slot"):
                obj = block.get(key)
                if isinstance(obj, dict) and obj:
                    found.append((f"sections[{si}].blocks[{bi}].{key}", obj))
            answer_space = block.get("answer_space")
            if isinstance(answer_space, dict):
                for key in ("diagram_col", "diagram_slot"):
                    obj = answer_space.get(key)
                    if isinstance(obj, dict) and obj:
                        found.append(
                            (f"sections[{si}].blocks[{bi}].answer_space.{key}", obj)
                        )
                for pi, part in enumerate(answer_space.get("parts") or []):
                    if not isinstance(part, dict):
                        continue
                    for key in ("diagram_col", "diagram_slot"):
                        obj = part.get(key)
                        if isinstance(obj, dict) and obj:
                            found.append(
                                (
                                    f"sections[{si}].blocks[{bi}]"
                                    f".answer_space.parts[{pi}].{key}",
                                    obj,
                                )
                            )
    return found


if __name__ == "__main__":
    main()
