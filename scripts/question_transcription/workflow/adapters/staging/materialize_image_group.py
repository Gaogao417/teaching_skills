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
import re
from pathlib import Path
from typing import Any

import yaml

from .image_placement import PlacementDecision, Placement, _indexed_crop_ids


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
        # The renderer that produced this draft; carries the stashed composition
        # plan. The caller writes the composed PNGs via
        # ``renderer.compose_groups(staging_dir)`` after expand creates the tree.
        self.renderer: "ImageGroupRenderer | None" = None


class ImageGroupRenderer:
    """Compose ImageGroup placements into single PNGs and rewrite the draft.

    ``render(decisions, draft, repo_root)`` mutates ``draft`` in place: each
    multi-image role's crop list is replaced by a single crop whose ``source``
    points at the composed PNG and whose ``assignment_path`` is the group's path.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        # Stashed by render() so compose_groups() can write the PNGs after the
        # staging tree exists.
        self._last_composition_plan: dict[tuple[str, str, str], dict] = {}

    @classmethod
    def from_plan_file(cls, plan_path: Path, repo_root: Path) -> "ImageGroupRenderer":
        """Reconstruct a renderer from a placement-plan sidecar.

        The projector writes ``structured/placement-plan.yaml``; the materialize
        step (a separate node) reads it here to rebuild the composition plan and
        write the composed PNGs into the staging tree.
        """
        import yaml as _yaml

        renderer = cls(repo_root)
        payload = _yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
        for group in payload.get("groups", []) or []:
            qid = str(group.get("question_id"))
            role = str(group.get("role"))
            assignment_path = str(group.get("assignment_path") or "")
            renderer._last_composition_plan[(qid, role, assignment_path)] = {
                "members": list(group.get("members") or []),
                "composed_source": str(group.get("composed_source") or ""),
                "assignment_path": assignment_path,
            }
        return renderer

    def render(
        self,
        decisions: list[PlacementDecision],
        draft: dict,
        staging_dir: Path | None = None,
    ) -> ResolvedDraft:
        """Rewrite the draft so no role has unplaced multi-image crops.

        Two-phase: the draft is rewritten NOW (so the expander sees single-crop
        roles with a valid assignment_path), using a DETERMINISTIC composed path
        and dimensions derived from the member crops' box_px — no PNG is written
        here because the staging directory does not exist yet at projection time.
        The actual PNG composition happens later in :meth:`compose_groups`, once
        the staging tree exists (called from the materialize step).
        """
        # Index items by item_id for in-place rewrite.
        items_by_id: dict[str, dict] = {}
        for section in draft.get("sections", []) or []:
            for item in section.get("items", []) or []:
                items_by_id[str(item.get("item_id") or "")] = item

        audit_records: list[dict] = []
        # Stash the composition plan keyed by (item_id, role, assignment_path)
        # so separate solution steps never overwrite one another.
        composition_plan: dict[tuple[str, str, str], dict] = {}

        for decision in decisions:
            item = items_by_id.get(decision.question_id)
            if item is None:
                continue
            for placement in decision.placements:
                if placement.kind != "image_group":
                    _stamp_single(item, placement)
                    continue
                members = _collect_member_crops(item, placement)
                if not members:
                    continue
                # Deterministic composed path + dimensions derived from member
                # box_px (no file IO here). The path is staging-relative and
                # resolved by the materializer against repo_root.
                composed_rel = _composed_rel_path(
                    decision.question_id,
                    placement.role,
                    placement.assignment_path,
                )
                width, height = _vertical_dims_from_members(members)
                _replace_group_with_single_crop(
                    item, placement, members, composed_rel, width, height
                )
                composition_plan[
                    (
                        decision.question_id,
                        placement.role,
                        placement.assignment_path,
                    )
                ] = {
                    "members": [
                        {
                            "source": str(member.get("source") or ""),
                            "box_px": list(member.get("box_px") or []),
                        }
                        for member in members
                    ],
                    "composed_source": composed_rel,
                    "assignment_path": placement.assignment_path,
                }
                audit_records.append(_audit_record(decision, placement, members, composed_rel))

        decisions_path: str | None = None
        if audit_records:
            # Persist the composition plan so compose_groups (in the materialize
            # step) can write the PNGs without re-deriving the plan.
            payload = {"placements": audit_records, "_composition_plan": {
                f"{qid}:{role}:{assignment_path}": plan
                for (qid, role, assignment_path), plan in composition_plan.items()
            }}
            if staging_dir is not None:
                decisions_path = str((staging_dir / "placement-decisions.yaml"))
            else:
                # At projection time staging_dir is unknown; the projector stashes
                # the plan via the returned ResolvedDraft so the materialize step
                # can write both the audit YAML and the PNGs.
                decisions_path = None
            self._last_composition_plan = composition_plan
            if decisions_path is not None:
                Path(decisions_path).parent.mkdir(parents=True, exist_ok=True)
                Path(decisions_path).write_text(
                    yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
                    encoding="utf-8",
                )

        return ResolvedDraft(draft=draft, decisions_path=decisions_path)

    def compose_groups(self, staging_dir: Path) -> None:
        """Write the composed group PNGs into the staging tree.

        Called AFTER expand has created ``staging/items/<id>/``. Reads the
        composition plan stashed by :meth:`render` (or reconstructed via
        :meth:`from_plan_file`) and writes each group's vertical composite PNG
        to ``items/<id>/assets/<role>-group.png``. It then patches each item's
        ``source.yaml`` so the composed crop's ``source`` is the ABSOLUTE path of
        the written PNG (materialize_crop resolves an absolute source directly,
        without needing it under repo_root).
        """
        from PIL import Image
        import yaml as _yaml

        plan = getattr(self, "_last_composition_plan", None) or {}
        if not plan:
            return
        for (question_id, role, _assignment_path), entry in plan.items():
            member_specs = entry["members"]
            out_dir = staging_dir / "items" / question_id / "assets"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / Path(entry["composed_source"]).name
            images: list[Image.Image] = []
            for member in member_specs:
                if isinstance(member, dict):
                    src_rel = str(member.get("source") or "")
                    box_px = member.get("box_px") or []
                else:
                    # Backward compatibility for plans written before region
                    # crops were preserved in the composition sidecar.
                    src_rel = str(member)
                    box_px = []
                src = Path(src_rel)
                if not src.is_absolute():
                    src = self.repo_root / src
                with Image.open(src) as im:
                    member_image = im.convert("RGBA")
                    if isinstance(box_px, list) and len(box_px) == 4:
                        member_image = member_image.crop(tuple(map(int, box_px)))
                    images.append(member_image.copy())
            width = max(im.width for im in images)
            total_height = sum(im.height for im in images)
            canvas = Image.new("RGBA", (width, total_height), (255, 255, 255, 255))
            y = 0
            for im in images:
                canvas.paste(im, (0, y))
                y += im.height
            canvas.convert("RGB").save(out_path, format="PNG")

            # Patch the item's source.yaml so the composed crop points at the
            # absolute written PNG. expand copied the draft's placeholder source
            # into source.yaml; replace it with the real path.
            source_yaml = staging_dir / "items" / question_id / "source.yaml"
            if source_yaml.exists():
                doc = _yaml.safe_load(source_yaml.read_text(encoding="utf-8")) or {}
                crops = doc.get("crops", {}) if isinstance(doc.get("crops"), dict) else {}
                role_crops = crops.get(role, []) if isinstance(crops.get(role), list) else []
                for crop in role_crops:
                    if not isinstance(crop, dict):
                        continue
                    if crop.get("source") == entry["composed_source"]:
                        crop["source"] = str(out_path)
                source_yaml.write_text(
                    _yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000),
                    encoding="utf-8",
                )


# --------------------------------------------------------------------------- #
# Pure helpers (no IO)
# --------------------------------------------------------------------------- #


def _stamp_single(item: dict, placement: Placement) -> None:
    """Set assignment_path on the single crop of a role (no composition)."""

    members = _collect_member_crops(item, placement)
    if len(members) != 1:
        return
    members[0]["assignment_path"] = placement.assignment_path


def _collect_member_crops(item: dict, placement: Placement) -> list[dict]:
    """Return the crop dicts that belong to this group, in order."""

    crops = _role_crops(item, placement.role)
    ids = _indexed_crop_ids(crops)
    wanted = set(placement.image_ids)
    return [crop for crop, crop_id in zip(crops, ids, strict=True) if crop_id in wanted]


def _composed_rel_path(question_id: str, role: str, assignment_path: str) -> str:
    """The deterministic staging-relative path for a composed group PNG.

    ``items/<id>/assets/<role>-group.png``. The materializer resolves this
    against repo_root (materialize_crop does ``repo_root / source``).
    """
    if role == "prompt" and assignment_path == "/diagram_col":
        filename = "prompt-group.png"
    else:
        match = re.search(r"/solution_steps/(\d+)/diagram_col$", assignment_path)
        suffix = f"-step-{match.group(1)}" if match else ""
        filename = f"{role}{suffix}-group.png"
    return f"items/{question_id}/assets/{filename}"


def _vertical_dims_from_members(members: list[dict]) -> tuple[int, int]:
    """Compute the vertical-composite (width, height) from member box_px.

    Avoids opening the member images: the draft crops already carry full-image
    box_px (``[0, 0, w, h]`` for DOCX media), so the composite width is the max
    member width and the height is the sum. Falls back to opening the files if a
    member's box_px is missing/zero.
    """
    widths: list[int] = []
    heights: list[int] = []
    for m in members:
        box = m.get("box_px") or []
        if len(box) == 4:
            widths.append(int(box[2]) - int(box[0]))
            heights.append(int(box[3]) - int(box[1]))
    widths = [w for w in widths if w > 0]
    heights = [h for h in heights if h > 0]
    if widths and heights:
        return max(widths), sum(heights)
    # Fallback: open the files (used when box_px is unavailable).
    from PIL import Image
    w_max = 0
    h_sum = 0
    for m in members:
        src = Path(str(m.get("source") or ""))
        if not src.is_absolute():
            src = Path.cwd() / src
        with Image.open(src) as im:
            w_max = max(w_max, im.width)
            h_sum += im.height
    return w_max, h_sum


def _replace_group_with_single_crop(
    item: dict,
    placement: Placement,
    members: list[dict],
    composed_path: str,
    width: int,
    height: int,
) -> None:
    """Replace a role's multi-crop list with one crop on the composed PNG.

    The composed PNG's real dimensions populate ``box_px`` so the downstream
    expander/materializer see a positive-area full crop (a [0,0,0,0] box would
    be rejected by expand_staging_draft's positive-area check).

    If any member is ``needs_review``, the composed crop inherits an
    ``attribution_review`` block (state=needs_review, lowest member confidence)
    so the pending attribution is not silently swallowed by the composition.
    """

    new_crop = {
        "source": composed_path,
        "box_px": [0, 0, int(width), int(height)],
        "assignment_path": placement.assignment_path,
    }
    merged = _merge_member_attribution_reviews(members)
    if merged is not None:
        new_crop["attribution_review"] = merged
    crops = _role_crops(item, placement.role)
    member_ids = {id(member) for member in members}
    rewritten: list[dict] = []
    inserted = False
    for crop in crops:
        if id(crop) not in member_ids:
            rewritten.append(crop)
            continue
        if not inserted:
            rewritten.append(new_crop)
            inserted = True
    _set_role_crops(item, placement.role, rewritten)


# Confidence rank (higher = weaker); used to pick the lowest confidence among
# group members when composing an attribution_review for a merged crop.
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _merge_member_attribution_reviews(members: list[dict]) -> dict | None:
    """Merge the ``attribution_review`` blocks of group members.

    Returns ``None`` when no member is needs_review (nothing to surface).
    Otherwise returns a review block with ``state="needs_review"``, the
    lowest (weakest) member confidence, the joined attribution id, and the
    full list of member attribution ids for the audit trail.
    """
    pending = [
        m["attribution_review"] for m in members
        if isinstance(m.get("attribution_review"), dict)
        and m["attribution_review"].get("state") == "needs_review"
    ]
    if not pending:
        return None
    confidences = [p.get("confidence") for p in pending if p.get("confidence")]
    # Lowest = weakest confidence = highest rank value; fall back to "medium".
    confidence = (
        max(confidences, key=lambda c: _CONFIDENCE_RANK.get(c, 1))
        if confidences else "medium"
    )
    member_ids = [str(p.get("attribution_id") or "") for p in pending]
    member_ids = [mid for mid in member_ids if mid]
    return {
        "attribution_id": ",".join(member_ids) if member_ids else "group",
        "state": "needs_review",
        "confidence": confidence,
        "member_attribution_ids": member_ids,
    }


def _role_crops(item: dict, role: str) -> list[dict]:
    if role == "prompt":
        return item.get("prompt") or []
    return item.get("solution") or []


def _set_role_crops(item: dict, role: str, crops: list[dict]) -> None:
    if role == "prompt":
        item["prompt"] = crops
    else:
        item["solution"] = crops


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
    """Plan placements and rewrite the draft so it is expander-ready.

    This is the integration point between the projector (which emits a draft
    that may have multi-image roles without assignment_path) and the expander
    (which requires assignment_path for multi-crop roles). After this call, no
    role in ``draft`` has more than one crop, and every crop carries an
    ``assignment_path``.

    The composed PNGs are NOT written here (the staging tree does not exist at
    projection time). The composition plan is stashed on the returned renderer
    (``ResolvedDraft.renderer``); the caller writes the PNGs via
    ``renderer.compose_groups(staging_dir)`` once expand has created the staging
    tree. When ``staging_dir`` is provided here AND the staging tree already
    exists, the PNGs are written immediately as a convenience (used by tests
    that run the whole pipeline in one call against a pre-made staging dir).
    """

    from .image_placement import plan_placements

    decisions = plan_placements(draft)
    renderer = ImageGroupRenderer(repo_root)
    resolved = renderer.render(decisions, draft, staging_dir)
    resolved.renderer = renderer
    # Convenience: if a staging_dir was given and its items tree already exists,
    # write the PNGs now (the e2e test path). The projector path calls
    # compose_groups separately after expand.
    if staging_dir is not None and (staging_dir / "items").is_dir():
        renderer.compose_groups(staging_dir)
    return resolved
