"""Image placement planner — pure logic deciding where each image goes.

Sits between the v1-compatible draft projection and the staging expander. The v1
draft contract uses scalar JSON-pointer paths (``/diagram_col``,
``/solution_steps/0/diagram_col``) for image placement, and the expander requires
an explicit ``assignment_path`` whenever a role (prompt/solution) carries MORE
than one crop. The planner resolves that ambiguity deterministically:

- a role with a SINGLE image  -> ``SingleImage(path)``
- a role with MULTIPLE images  -> ``ImageGroup([...], path, "vertical")`` plus a
  non-blocking warning (the original reading order is preserved, but the
  per-segment inline position the source paper had cannot be expressed in v1's
  scalar ``stem_latex``).

The planner is pure: it consumes a v2 ``SourcePaper`` plus the projected v1 draft
and emits :class:`PlacementDecision` records. The actual PNG composition is an
explicit side effect handled separately by :class:`ImageGroupRenderer` (in
``materialize_image_group.py``), so the planner stays auditable and testable.

``needsReview`` is raised only when placement is genuinely ambiguous (e.g. two
accepted attributions target conflicting part/step ids that v1 cannot represent);
a same-target multi-image group is NOT a review — it is a layout downgrade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


__all__ = [
    "PlacementReview",
    "PlacementWarning",
    "Placement",
    "PlacementDecision",
    "PlacementPlanner",
    "plan_placements",
]


@dataclass(frozen=True)
class PlacementReview:
    """A blocking placement ambiguity that requires human resolution.

    Carries the image ids at issue and a traceable reason; the workflow must
    pause (``waiting_for_placement_review``) until resolved.
    """

    reason: str
    image_ids: list[str]
    message: str


@dataclass(frozen=True)
class PlacementWarning:
    """A non-blocking layout downgrade (recorded, does not pause the workflow)."""

    code: str
    message: str


@dataclass(frozen=True)
class Placement:
    """One image or one vertical image group bound to a JSON-pointer path."""

    kind: Literal["single_image", "image_group"]
    image_ids: list[str]
    assignment_path: str
    layout: str = "single"
    role: str = "prompt"


@dataclass
class PlacementDecision:
    """The planner's verdict for one question's prompt/solution images."""

    question_id: str
    placements: list[Placement] = field(default_factory=list)
    needs_review: PlacementReview | None = None
    warnings: list[PlacementWarning] = field(default_factory=list)


class PlacementPlanner:
    """Plan image placement for a v1-compatible draft.

    ``plan`` consumes the draft items (each with a ``prompt`` and/or
    ``official_solution.crops`` list of crops) and returns one
    :class:`PlacementDecision` per question that has images.
    """

    def plan(self, draft: dict) -> list[PlacementDecision]:
        return plan_placements(draft)


# --------------------------------------------------------------------------- #
# Pure planning function
# --------------------------------------------------------------------------- #


def plan_placements(draft: dict) -> list[PlacementDecision]:
    """Plan placements for every question in a v1 draft.

    For each item, the prompt list and the official_solution.crops list are each
    examined. A single image maps to ``SingleImage``; multiple images map to one
    ``ImageGroup`` (vertical) with a non-blocking warning.
    """

    decisions: list[PlacementDecision] = []
    for section in draft.get("sections", []) or []:
        for item in section.get("items", []) or []:
            item_id = str(item.get("item_id") or "")
            decision = _plan_item(item_id, item)
            if decision.placements or decision.needs_review:
                decisions.append(decision)
    return decisions


def _plan_item(item_id: str, item: dict) -> PlacementDecision:
    decision = PlacementDecision(question_id=item_id)

    prompt_crops = item.get("prompt") or []
    if prompt_crops:
        _plan_role(item_id, "prompt", prompt_crops, "/diagram_col", decision)

    sol_crops = ((item.get("official_solution") or {}).get("crops")) or []
    if sol_crops:
        # Solution images default to the first solution step's diagram column,
        # matching the single-image default in expand_staging_draft.
        _plan_role(
            item_id, "solution", sol_crops, "/solution_steps/0/diagram_col", decision
        )

    return decision


def _plan_role(
    item_id: str,
    role: str,
    crops: list[dict],
    default_path: str,
    decision: PlacementDecision,
) -> None:
    # Identify each crop by a stable id derived from its source leaf. The
    # renderer composes them in this order.
    image_ids = [_crop_id(c, idx) for idx, c in enumerate(crops)]

    if len(crops) == 1:
        decision.placements.append(
            Placement(
                kind="single_image",
                image_ids=image_ids,
                assignment_path=default_path,
                layout="single",
                role=role,
            )
        )
        return

    # Multiple images for one role: group them vertically at the default path.
    # This is a layout downgrade, not a review (order + ownership are clear).
    decision.placements.append(
        Placement(
            kind="image_group",
            image_ids=image_ids,
            assignment_path=default_path,
            layout="vertical",
            role=role,
        )
    )
    decision.warnings.append(
        PlacementWarning(
            code="grouped_adjacent_to_scalar_stem",
            message=(
                f"{item_id} {role}: {len(crops)} images share the scalar path "
                f"{default_path}; composed vertically as an adjacent group "
                f"(original per-segment inline position not expressible in v1)"
            ),
        )
    )


def _crop_id(crop: dict, idx: int) -> str:
    """A stable id for a crop, preferring its source leaf, falling back to index."""

    source = str(crop.get("source") or "")
    leaf = source.rsplit("/", 1)[-1] if source else ""
    return leaf or f"crop-{idx}"
