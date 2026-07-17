from __future__ import annotations

from dataclasses import dataclass
import re

from diagram_contracts import DiagramConditionLabelStyle, DiagramDisplayProfile, DiagramRenderProfile


PX_TO_CM = 0.026458333
LABEL_PX_TO_PT = 0.24
AXIS_PX_TO_PT = 0.55
POINT_RADIUS_PX_TO_CM = 0.01
LABEL_OFFSET_PX_TO_CM = 0.007


@dataclass(frozen=True)
class TikzRenderStyle:
    point_label_pt: float = 10.56
    condition_label_pt: float = 8.64
    axis_label_pt: float = 9.9
    tick_label_pt: float = 7.15
    point_radius_cm: float = 0.073
    angle_radius_cm: float = 0.32
    point_label_offset_cm: float = 0.238
    point_label_font_style: str = "italic"
    point_label_font_weight: str = "normal"
    condition_label_font_style: str = "normal"
    condition_label_font_weight: str = "normal"
    condition_label_style: DiagramConditionLabelStyle | None = None


def profile_to_style(profile: DiagramRenderProfile) -> TikzRenderStyle:
    point_label_px = profile.point_label_px or 44
    condition_label_px = profile.condition_label_px or 36
    axis_label_px = profile.axis_label_px or 18
    tick_label_px = profile.tick_label_px or 13
    point_radius_px = profile.point_radius_px or 5.2
    point_label_offset_px = profile.point_label_offset_px or 34
    return TikzRenderStyle(
        point_label_pt=round(point_label_px * LABEL_PX_TO_PT, 3),
        condition_label_pt=round(condition_label_px * LABEL_PX_TO_PT, 3),
        axis_label_pt=round(axis_label_px * AXIS_PX_TO_PT, 3),
        tick_label_pt=round(tick_label_px * AXIS_PX_TO_PT, 3),
        point_radius_cm=round(point_radius_px * POINT_RADIUS_PX_TO_CM, 4),
        point_label_offset_cm=round(point_label_offset_px * LABEL_OFFSET_PX_TO_CM, 4),
        point_label_font_style=profile.point_label_font_style or "italic",
        point_label_font_weight=profile.point_label_font_weight or "normal",
        condition_label_font_style=profile.condition_label_font_style or "normal",
        condition_label_font_weight=profile.condition_label_font_weight or "normal",
        condition_label_style=profile.condition_label_style,
    )


def natural_width_cm_for_profile(profile: DiagramRenderProfile, *, fallback_cm: float = 6.0) -> float:
    """Return the target TikZ natural width for simple TeX dimensions."""
    width = (profile.width or "").strip()
    match = re.fullmatch(r"(?P<value>\d+(?:\.\d+)?|\.\d+)\s*(?P<unit>mm|cm|pt|in)", width)
    if match:
        value = float(match.group("value"))
        unit = match.group("unit")
        if unit == "mm":
            width_cm = value / 10
        elif unit == "cm":
            width_cm = value
        elif unit == "pt":
            width_cm = value / 28.4528
        else:
            width_cm = value * 2.54
        return max(3.0, min(12.0, width_cm - 0.45))
    if profile.display_profile == DiagramDisplayProfile.WORKSHEET_GEOMETRY_CENTER:
        return 7.0
    return fallback_cm


def value_only_condition_label(value: str, style: TikzRenderStyle) -> str:
    if style.condition_label_style != DiagramConditionLabelStyle.VALUE_ONLY:
        return value
    match = re.match(r"^\s*[A-Z]{1,3}\s*=\s*(?P<value>.+?)\s*$", value)
    return match.group("value") if match else value


def font_weight_option(weight: str) -> str:
    normalized = weight.lower()
    if normalized in {"bold", "semibold", "700", "800", "900"}:
        return "font=\\bfseries"
    return ""


def font_style_option(style: str) -> str:
    normalized = style.lower()
    if normalized == "italic":
        return "font=\\itshape"
    return ""
