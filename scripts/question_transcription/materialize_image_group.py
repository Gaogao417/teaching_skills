"""Image group materializer — compose multi-image placements into one PNG.

Receives the :class:`PlacementDecision` records from
:mod:`image_placement` and rewrites the v1 draft so that every role carries at
most ONE crop. An ``ImageGroup`` placement is replaced by a single crop pointing
at a vertically-composed PNG, with ``assignment_path`` set so the downstream
expander never raises "every prompt crop needs assignment_path".

This module owns the file-system side effect (PNG composition) and the
``placement-decisions.yaml`` audit record; the planner itself is pure.

Layout policy (v1 limitation): vertical stacking only. The original per-segment
inline position (e.g. a three-figure problem statement with figures between
text segments) cannot be expressed in v1's scalar ``stem_latex``, so the group
is shown adjacent and the downgrade is recorded as a non-blocking warning.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .image_placement import PlacementDecision, Placement


__all__ = [
    "ImageGroupRenderer",
    "ResolvedDraft",
    "resolve_placement_decisions",
]


class ResolvedDraft:
    """A draft rewritten so no role has unplaced multi-image crops."""

    def __init__(self, draft: dict, decisions_path: str | None) -> None:
        self.draft = draft
        self.decisions_path = decisions_path


class ImageGroupRenderer:
    """Compose ImageGroup placements into single PNGs and rewrite the draft.

    ``render(decisions, draft, repo_root)`` mutates ``draft`` in place: each
    multi-image role's crop list is replaced by a single crop whose ``source``
    points at the composed PNG and whose ``assignment_path`` is the group's path.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def render(
        self,
        decisions: list[PlacementDecision],
        draft: dict,
        staging_dir: Path | None = None,
    ) -> ResolvedDraft:
        from PIL import Image

        # Index items by item_id for in-place rewrite.
        items_by_id: dict[str, dict] = {}
        for section in draft.get("sections", []) or []:
            for item in section.get("items", []) or []:
                items_by_id[str(item.get("item_id") or "")] = item

        audit_records: list[dict] = []

        for decision in decisions:
            item = items_by_id.get(decision.question_id)
            if item is None:
                continue
            for placement in decision.placements:
                if placement.kind != "image_group":
                    # Single-image: just stamp the assignment_path on the crop so
                    # the expander does not need its default heuristic.
                    _stamp_single(item, placement)
                    continue
                # Compose the group members vertically.
                members = _collect_member_crops(item, placement)
                if not members:
                    continue
                composed_path = self._compose_vertical(
                    members, placement, decision.question_id, staging_dir
                )
                _replace_group_with_single_crop(
                    item, placement, members, composed_path
                )
                audit_records.append(_audit_record(decision, placement, members, composed_path))

        decisions_path: str | None = None
        if staging_dir is not None and audit_records:
            decisions_path = str((staging_dir / "placement-decisions.yaml"))
            Path(decisions_path).parent.mkdir(parents=True, exist_ok=True)
            Path(decisions_path).write_text(
                yaml.safe_dump(
                    {"placements": audit_records},
                    allow_unicode=True,
                    sort_keys=False,
                    width=1000,
                ),
                encoding="utf-8",
            )

        return ResolvedDraft(draft=draft, decisions_path=decisions_path)

    def _compose_vertical(
        self,
        members: list[dict],
        placement: Placement,
        question_id: str,
        staging_dir: Path | None,
    ) -> str:
        from PIL import Image

        images: list[Image.Image] = []
        for member in members:
            src = Path(str(member.get("source") or ""))
            if not src.is_absolute():
                src = self.repo_root / src
            with Image.open(src) as im:
                images.append(im.convert("RGBA").copy())

        width = max(im.width for im in images)
        total_height = sum(im.height for im in images)
        canvas = Image.new("RGBA", (width, total_height), (255, 255, 255, 255))
        y = 0
        for im in images:
            canvas.paste(im, (0, y))
            y += im.height

        if staging_dir is None:
            # In-memory only (tests); return a synthetic path.
            return f"assets/{question_id}-{placement.role}-group.png"
        out_dir = staging_dir / "items" / question_id / "assets"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{placement.role}-group.png"
        out_path = out_dir / out_name
        canvas.convert("RGB").save(out_path, format="PNG")
        # Return a repo-relative path if under repo root, else absolute.
        try:
            return str(out_path.relative_to(self.repo_root))
        except ValueError:
            return str(out_path)


# --------------------------------------------------------------------------- #
# Pure helpers (no IO)
# --------------------------------------------------------------------------- #


def _stamp_single(item: dict, placement: Placement) -> None:
    """Set assignment_path on the single crop of a role (no composition)."""

    crops = _role_crops(item, placement.role)
    if not crops:
        return
    crops[0]["assignment_path"] = placement.assignment_path


def _collect_member_crops(item: dict, placement: Placement) -> list[dict]:
    """Return the crop dicts that belong to this group, in order."""

    crops = _role_crops(item, placement.role)
    # The group covers all crops of this role (the planner grouped the whole list).
    return list(crops)


def _replace_group_with_single_crop(
    item: dict,
    placement: Placement,
    members: list[dict],
    composed_path: str,
) -> None:
    """Replace a role's multi-crop list with one crop on the composed PNG."""

    new_crop = {
        "source": composed_path,
        "box_px": [0, 0, 0, 0],  # filled from composed dims at materialize time
        "assignment_path": placement.assignment_path,
    }
    if placement.role == "prompt":
        item["prompt"] = [new_crop]
    else:
        official = item.setdefault("official_solution", {})
        official["crops"] = [new_crop]


def _role_crops(item: dict, role: str) -> list[dict]:
    if role == "prompt":
        return item.get("prompt") or []
    return ((item.get("official_solution") or {}).get("crops")) or []


def _audit_record(
    decision: PlacementDecision,
    placement: Placement,
    members: list[dict],
    composed_path: str,
) -> dict:
    return {
        "question_id": decision.question_id,
        "kind": "image_group",
        "role": placement.role,
        "image_ids": placement.image_ids,
        "members": [str(m.get("source") or "") for m in members],
        "assignment_path": placement.assignment_path,
        "layout": placement.layout,
        "composed_source": composed_path,
        "warnings": [
            {"code": w.code, "message": w.message} for w in decision.warnings
        ],
    }


# --------------------------------------------------------------------------- #
# Top-level convenience: plan + render in one call
# --------------------------------------------------------------------------- #


def resolve_placement_decisions(
    draft: dict, repo_root: Path, staging_dir: Path | None = None
) -> ResolvedDraft:
    """Plan placements and compose groups so the draft is expander-ready.

    This is the integration point between the projector (which emits a draft
    that may have multi-image roles without assignment_path) and the expander
    (which requires assignment_path for multi-crop roles). After this call, no
    role in ``draft`` has more than one crop, and every crop carries an
    ``assignment_path``.
    """

    from .image_placement import plan_placements

    decisions = plan_placements(draft)
    renderer = ImageGroupRenderer(repo_root)
    return renderer.render(decisions, draft, staging_dir)
