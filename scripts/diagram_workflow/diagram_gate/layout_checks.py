from __future__ import annotations

import re

from diagram_contracts import (
    AssignmentPlanDiagramView,
    DiagramDisplayProfile,
    DiagramGateCheck,
)


_ABSOLUTE_DIMENSION_RE = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?|\.\d+)\s*(?P<unit>mm|cm|pt|in)\s*$"
)
_UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "pt": 25.4 / 72.27,
    "in": 25.4,
}


def _dimension_to_mm(value: str) -> float | None:
    match = _ABSOLUTE_DIMENSION_RE.match(value)
    if not match:
        return None
    return float(match.group("value")) * _UNIT_TO_MM[match.group("unit")]


def _iter_slots(plan_data: AssignmentPlanDiagramView | dict[str, object]):
    plan = (
        plan_data
        if isinstance(plan_data, AssignmentPlanDiagramView)
        else AssignmentPlanDiagramView.model_validate(plan_data)
    )
    for section in plan.sections:
        for block in section.blocks:
            if block.diagram_slot is not None:
                yield block.diagram_slot
            for step in block.steps:
                if step.diagram_slot is not None:
                    yield step.diagram_slot
            answer_space = block.answer_space
            if answer_space is None:
                continue
            if answer_space.diagram_slot is not None:
                yield answer_space.diagram_slot
            for part in answer_space.parts:
                if part.diagram_slot is not None:
                    yield part.diagram_slot


def _check_slot_layout_profiles(
    plan_data: AssignmentPlanDiagramView | dict[str, object],
) -> list[DiagramGateCheck]:
    """Enforce practical width floors for sidecar and centered diagrams."""
    checks: list[DiagramGateCheck] = []
    assumed_text_width_mm = 160.0
    min_left_width_mm = 80.0

    for slot in _iter_slots(plan_data):
        profile = slot.resolved_render_profile()
        width = slot.width_hint or profile.width
        width_mm = _dimension_to_mm(width)
        display_profile = profile.display_profile

        if display_profile == DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR and width_mm is not None:
            if width_mm < 55:
                checks.append(DiagramGateCheck(
                    name="diagram_sidecar_width",
                    status="block",
                    message=f"Sidecar diagram '{slot.slot_id}' is {width}; use at least 55mm or center placement",
                    refs=[slot.slot_id],
                ))
            left_width = assumed_text_width_mm - width_mm - 6
            if left_width < min_left_width_mm:
                checks.append(DiagramGateCheck(
                    name="diagram_sidecar_left_width",
                    status="warn",
                    message=f"Sidecar diagram '{slot.slot_id}' leaves about {left_width:.1f}mm for text",
                    refs=[slot.slot_id],
                ))

        if display_profile == DiagramDisplayProfile.WORKSHEET_GEOMETRY_CENTER and width_mm is not None and width_mm < 68:
            checks.append(DiagramGateCheck(
                name="diagram_center_width",
                status="block",
                message=f"Centered diagram '{slot.slot_id}' is {width}; use at least 68mm",
                refs=[slot.slot_id],
            ))
    return checks
