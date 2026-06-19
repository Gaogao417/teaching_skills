from __future__ import annotations

from dataclasses import dataclass
import re

from diagram_contracts import DiagramConditionLabelStyle, DiagramRenderProfile


PX_TO_PT = 0.75
PX_TO_CM = 0.026458333


@dataclass(frozen=True)
class TikzRenderStyle:
    point_label_pt: float = 33.0
    condition_label_pt: float = 27.0
    axis_label_pt: float = 13.5
    tick_label_pt: float = 9.75
    point_radius_cm: float = 0.055
    point_label_offset_cm: float = 0.9
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
        point_label_pt=round(point_label_px * PX_TO_PT, 3),
        condition_label_pt=round(condition_label_px * PX_TO_PT, 3),
        axis_label_pt=round(axis_label_px * PX_TO_PT, 3),
        tick_label_pt=round(tick_label_px * PX_TO_PT, 3),
        point_radius_cm=round(point_radius_px * PX_TO_CM, 4),
        point_label_offset_cm=round(point_label_offset_px * PX_TO_CM, 4),
        point_label_font_style=profile.point_label_font_style or "italic",
        point_label_font_weight=profile.point_label_font_weight or "normal",
        condition_label_font_style=profile.condition_label_font_style or "normal",
        condition_label_font_weight=profile.condition_label_font_weight or "normal",
        condition_label_style=profile.condition_label_style,
    )


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
