from __future__ import annotations

import math
import re
from typing import Any

from diagram_contracts import DiagramVariant, GeometryRenderSpec

from .contracts import TikzCommand, TikzCompilerAudit, TikzDiagramSpec, TikzStyleRole
from .styles import LABEL_PX_TO_PT, natural_width_cm_for_profile, profile_to_style, value_only_condition_label
from .writer import (
    color_option,
    dash_option,
    escape_tex,
    fmt_cm,
    fmt_num,
    join_options,
    node_text_tex,
    point_label_tex,
    stroke_width_option,
)

Point = tuple[float, float]


def _object_dict(value: object) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        data = value.model_dump(mode="json", by_alias=True)
    elif isinstance(value, dict):
        data = dict(value)
    else:
        data = {}
    return data


def _style_dict(obj: dict[str, Any]) -> dict[str, Any]:
    style = obj.get("style")
    return style if isinstance(style, dict) else {}


def _model_or_dict(value: object) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return dict(value) if isinstance(value, dict) else {}


def _coordinate(value: object, point_objects: dict[str, Point]) -> Point | None:
    if isinstance(value, str) and value in point_objects:
        return point_objects[value]
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    if isinstance(value, dict) and "x" in value and "y" in value:
        return (float(value["x"]), float(value["y"]))
    return None


def _style_coordinate(value: object) -> Point | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    if isinstance(value, dict) and "x" in value and "y" in value:
        return (float(value["x"]), float(value["y"]))
    return None


def _coordinates_tex(points: list[Point]) -> str:
    return " ".join(f"({fmt_num(x)},{fmt_num(y)})" for x, y in points)


def _axis_label_tex(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("$") and text.endswith("$"):
        return text
    if re.fullmatch(r"[A-Za-z]", text):
        return f"${escape_tex(text)}$"
    return node_text_tex(text)


def _axis_tick_label_tex(value: object, label: object | None = None) -> str:
    text = str(label if label not in (None, "") else fmt_num(float(value))).strip()
    if not text:
        return ""
    if text.startswith("$") and text.endswith("$"):
        return text
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", text):
        return f"${escape_tex(text)}$"
    return node_text_tex(text)


def _label_style_text(value: object, default_value: float) -> str:
    style = _model_or_dict(value)
    return _axis_tick_label_tex(default_value, style.get("label"))


def _tick_values_tex(values: list[float]) -> str:
    return ",".join(fmt_num(float(value)) for value in values)


def _line_endpoints(obj: dict[str, Any], x_min: float, x_max: float, y_min: float, y_max: float) -> tuple[Point, Point] | None:
    equation = str(obj.get("equation", "")).replace(" ", "")
    number = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
    if equation:
        vertical = re.match(rf"^x={{1,2}}(?P<c>{number})$", equation)
        if vertical:
            x = float(vertical.group("c"))
            return (x, y_min), (x, y_max)

        horizontal = re.match(rf"^y={{1,2}}(?P<c>{number})$", equation)
        if horizontal:
            y = float(horizontal.group("c"))
            return (x_min, y), (x_max, y)

        y_match = re.match(r"^y={1,2}(?P<rhs>.+)$", equation)
        if y_match:
            rhs = y_match.group("rhs")
            simple_x = re.match(rf"^(?P<sign>[+-]?)x(?P<b>[+-](?:\d+(?:\.\d+)?|\.\d+))?$", rhs)
            if simple_x:
                slope = -1.0 if simple_x.group("sign") == "-" else 1.0
                intercept = float(simple_x.group("b") or 0)
                return (x_min, slope * x_min + intercept), (x_max, slope * x_max + intercept)

            linear = re.match(rf"^(?P<m>{number})\*?x(?P<b>[+-](?:\d+(?:\.\d+)?|\.\d+))?$", rhs)
            if linear:
                slope = float(linear.group("m"))
                intercept = float(linear.group("b") or 0)
                return (x_min, slope * x_min + intercept), (x_max, slope * x_max + intercept)

    if "slope" in obj and "intercept" in obj:
        slope = float(obj["slope"])
        intercept = float(obj["intercept"])
        return (x_min, slope * x_min + intercept), (x_max, slope * x_max + intercept)
    return None


class CoordinateTikzCompiler:
    def __init__(self, spec: GeometryRenderSpec):
        self.spec = spec
        self.style = profile_to_style(spec.render_profile)
        self.commands: list[TikzCommand] = []
        self.warnings: list[str] = []
        self.point_objects: dict[str, Point] = {}
        viewport = spec.viewport
        self.x_min = float(viewport.x_min if viewport and viewport.x_min is not None else -5)
        self.x_max = float(viewport.x_max if viewport and viewport.x_max is not None else 5)
        self.y_min = float(viewport.y_min if viewport and viewport.y_min is not None else -5)
        self.y_max = float(viewport.y_max if viewport and viewport.y_max is not None else 5)
        self.preserve_aspect = bool(viewport.preserve_aspect if viewport else True)
        canvas = spec.canvas
        width_px = canvas.width_px or spec.render_profile.canvas_width_px or 720
        height_px = canvas.height_px or spec.render_profile.canvas_height_px or 520
        self.natural_width_cm = natural_width_cm_for_profile(spec.render_profile)
        if self.preserve_aspect and self.x_max > self.x_min and self.y_max > self.y_min:
            viewport_ratio = (self.y_max - self.y_min) / (self.x_max - self.x_min)
            self.natural_height_cm = max(3.2, min(7.5, self.natural_width_cm * viewport_ratio))
        else:
            self.natural_height_cm = max(3.2, min(6.5, self.natural_width_cm * height_px / width_px))

    def compile(self) -> TikzDiagramSpec:
        self._index_points()
        self._begin_axis()
        self._draw_interval_bands()
        self._draw_functions()
        self._draw_objects()
        self._draw_tick_labels()
        self._draw_axis_labels()
        self.commands.append(TikzCommand(kind="axis:end", order=9000, tex=r"\end{axis}"))
        audit = TikzCompilerAudit(
            bbox_source={"x_min": self.x_min, "x_max": self.x_max, "y_min": self.y_min, "y_max": self.y_max},
            natural_width_cm=round(self.natural_width_cm, 4),
            natural_height_cm=round(self.natural_height_cm, 4),
            coordinate_count=len(self.point_objects),
            command_count=len(self.commands),
            point_label_count=len(self.point_objects),
            condition_label_count=sum(1 for obj in self._objects() if obj.get("type") == "text"),
            warnings=self.warnings,
        )
        return TikzDiagramSpec(
            job_id=self.spec.job_id,
            variant=self.spec.variant or DiagramVariant.PROMPT,
            diagram_type=self.spec.type,
            libraries=["calc", "arrows.meta", "intersections"],
            natural_width_cm=self.natural_width_cm,
            natural_height_cm=self.natural_height_cm,
            styles=[
                TikzStyleRole(
                    name="axis point label",
                    options=f"inner sep=1pt, font=\\fontsize{{{fmt_num(self.style.point_label_pt, 2)}}}{{{fmt_num(self.style.point_label_pt * 1.1, 2)}}}\\selectfont",
                )
            ],
            commands=self.commands,
            audit=audit,
        )

    def _objects(self) -> list[dict[str, Any]]:
        return [_object_dict(obj) for obj in self.spec.objects]

    def _index_points(self) -> None:
        for name, point in self.spec.points.items():
            self.point_objects[name] = (float(point[0]), float(point[1]))
        for obj in self._objects():
            if obj.get("type") == "point" and "x" in obj and "y" in obj:
                self.point_objects[str(obj.get("id") or obj.get("label") or "")] = (float(obj["x"]), float(obj["y"]))

    def _begin_axis(self) -> None:
        axes = self.spec.axes
        draw_x = axes.x if axes else True
        draw_y = axes.y if axes else True
        grid = axes.grid if axes else True
        show_ticks = axes.show_ticks if axes else True
        axis_options = [
            f"width={fmt_cm(self.natural_width_cm)}",
            f"height={fmt_cm(self.natural_height_cm)}",
            f"xmin={fmt_num(self.x_min)}",
            f"xmax={fmt_num(self.x_max)}",
            f"ymin={fmt_num(self.y_min)}",
            f"ymax={fmt_num(self.y_max)}",
            "enlargelimits=false",
            "clip=false",
            "scale only axis",
            "grid=both" if grid else "grid=none",
            "ticks=both" if show_ticks else "ticks=none",
            f"tick label style={{font=\\fontsize{{{fmt_num(self.style.tick_label_pt, 2)}}}{{{fmt_num(self.style.tick_label_pt * 1.1, 2)}}}\\selectfont}}",
            f"label style={{font=\\fontsize{{{fmt_num(self.style.axis_label_pt, 2)}}}{{{fmt_num(self.style.axis_label_pt * 1.1, 2)}}}\\selectfont}}",
        ]
        if self.preserve_aspect:
            axis_options.append("axis equal image")
        if draw_x and draw_y:
            axis_options.append("axis lines=middle")
        elif draw_x:
            axis_options.extend(["axis x line=middle", "axis y line=none"])
        elif draw_y:
            axis_options.extend(["axis x line=none", "axis y line=middle"])
        else:
            axis_options.append("axis lines=none")
        x_ticks = list(axes.x_ticks or []) if axes else []
        y_ticks = list(axes.y_ticks or []) if axes else []
        if axes and not x_ticks and axes.x_tick_labels:
            x_ticks = [label.value for label in axes.x_tick_labels if label.show]
        if axes and not y_ticks and axes.y_tick_labels:
            y_ticks = [label.value for label in axes.y_tick_labels if label.show]
        if show_ticks and x_ticks:
            axis_options.append(f"xtick={{{_tick_values_tex(x_ticks)}}}")
        elif axes and axes.x_tick_step:
            axis_options.append(f"xtick distance={fmt_num(axes.x_tick_step)}")
        if show_ticks and y_ticks:
            axis_options.append(f"ytick={{{_tick_values_tex(y_ticks)}}}")
        elif axes and axes.y_tick_step:
            axis_options.append(f"ytick distance={fmt_num(axes.y_tick_step)}")
        if show_ticks and axes and axes.x_tick_labels:
            axis_options.append(r"xticklabel=\empty")
        if show_ticks and axes and axes.y_tick_labels:
            axis_options.append(r"yticklabel=\empty")
        body = ",\n    ".join(axis_options)
        self.commands.append(TikzCommand(kind="axis:begin", order=0, tex="\\begin{axis}[\n    " + body + "\n  ]"))

    def _draw_axis_labels(self) -> None:
        axes = self.spec.axes
        draw_x = axes.x if axes else True
        draw_y = axes.y if axes else True
        x_label = axes.x_label if axes else "x"
        y_label = axes.y_label if axes else "y"
        if draw_x and x_label:
            self._draw_axis_label("x", x_label)
        if draw_y and y_label:
            self._draw_axis_label("y", y_label)

    def _draw_axis_label(self, axis: str, label: str) -> None:
        label_tex = _axis_label_tex(label)
        if not label_tex:
            return
        if axis == "x":
            if self.y_min <= 0 <= self.y_max:
                at = f"axis cs:{fmt_num(self.x_max)},0"
                default_anchor = "west"
                default_dx = 2.0
                default_dy = -3.0
            else:
                at = "axis description cs:1.02,0.03"
                default_anchor = "west"
                default_dx = 0.0
                default_dy = 0.0
        else:
            if self.x_min <= 0 <= self.x_max:
                at = f"axis cs:0,{fmt_num(self.y_max)}"
                default_anchor = "south west"
                default_dx = 2.0
                default_dy = 1.0
            else:
                at = "axis description cs:0.03,1.02"
                default_anchor = "south"
                default_dx = 0.0
                default_dy = 0.0

        anchor = default_anchor
        dx = default_dx
        dy = default_dy
        label_font = f"font=\\fontsize{{{fmt_num(self.style.axis_label_pt, 2)}}}{{{fmt_num(self.style.axis_label_pt * 1.1, 2)}}}\\selectfont"
        options = join_options(
            f"anchor={anchor}",
            "inner sep=1pt",
            label_font,
            f"xshift={fmt_num(dx, 3)}pt" if dx else "",
            f"yshift={fmt_num(dy, 3)}pt" if dy else "",
        )
        self.commands.append(
            TikzCommand(
                kind=f"axis:label:{axis}",
                order=8600 if axis == "x" else 8610,
                tex=f"\\node[{options}] at ({at}) {{{label_tex}}};",
            )
        )

    def _draw_tick_labels(self) -> None:
        axes = self.spec.axes
        if not axes or not axes.show_ticks:
            return
        if axes.x and axes.x_tick_labels:
            for index, label in enumerate(axes.x_tick_labels):
                self._draw_tick_label("x", index, label)
        if axes.y and axes.y_tick_labels:
            for index, label in enumerate(axes.y_tick_labels):
                self._draw_tick_label("y", index, label)

    def _draw_tick_label(self, axis: str, index: int, raw_label: object) -> None:
        label = _model_or_dict(raw_label)
        if label.get("show") is False:
            return
        value = float(label["value"])
        custom_at = _style_coordinate(label.get("at") or label.get("label_at"))
        if custom_at is not None:
            at = f"axis cs:{fmt_num(custom_at[0])},{fmt_num(custom_at[1])}"
            default_anchor = "north" if axis == "x" else "east"
            default_dx = 0.0
            default_dy = 0.0
        elif axis == "x":
            at = f"axis cs:{fmt_num(value)},0"
            default_anchor = "north"
            default_dx = 0.0
            default_dy = -4.0
        else:
            at = f"axis cs:0,{fmt_num(value)}"
            default_anchor = "east"
            default_dx = -4.0
            default_dy = 0.0
        text = _axis_tick_label_tex(value, label.get("label"))
        if not text:
            return
        anchor = str(label.get("anchor") or default_anchor)
        dx = float(label.get("dx_pt", label.get("dx", default_dx)))
        dy = float(label.get("dy_pt", label.get("dy", default_dy)))
        tick_font = f"font=\\fontsize{{{fmt_num(self.style.tick_label_pt, 2)}}}{{{fmt_num(self.style.tick_label_pt * 1.1, 2)}}}\\selectfont"
        options = join_options(
            f"anchor={anchor}",
            "inner sep=1pt",
            tick_font,
            f"xshift={fmt_num(dx, 3)}pt" if dx else "",
            f"yshift={fmt_num(dy, 3)}pt" if dy else "",
        )
        self.commands.append(
            TikzCommand(
                kind=f"axis:tick_label:{axis}",
                order=(8400 if axis == "x" else 8450) + index,
                tex=f"\\node[{options}] at ({at}) {{{text}}};",
            )
        )

    def _draw_interval_bands(self) -> None:
        for index, obj in enumerate(self._objects()):
            if obj.get("type") not in {"interval_band", "x_interval_band"}:
                continue
            x_min = max(float(obj.get("x_min", self.x_min)), self.x_min)
            x_max = min(float(obj.get("x_max", self.x_max)), self.x_max)
            if x_min >= x_max:
                continue
            style = _style_dict(obj)
            fill = color_option(style.get("fill") or obj.get("fill") or "#eef2ff", default="gray")
            options = join_options(f"fill={fill}", opacity_option(style.get("opacity", obj.get("opacity", 0.28))), "draw=none")
            tex = (
                f"\\path[{options}] (axis cs:{fmt_num(x_min)},{fmt_num(self.y_min)}) "
                f"rectangle (axis cs:{fmt_num(x_max)},{fmt_num(self.y_max)});"
            )
            self.commands.append(TikzCommand(kind="interval_band", order=100 + index, tex=tex))

    def _draw_functions(self) -> None:
        samples = self.spec.samples
        for index, func in enumerate(self.spec.functions):
            fid = str(func.id)
            raw_points = samples.get(fid) or []
            points = [(float(point[0]), float(point[1])) for point in raw_points]
            if len(points) < 2:
                self.warnings.append(f"function has fewer than two sample points: {fid}")
                continue
            style = func.style if isinstance(func.style, dict) else {}
            color = color_option(style.get("stroke") or ["#2563eb", "#dc2626", "#059669", "#7c3aed"][index % 4])
            options = join_options(
                "no markers",
                f"draw={color}",
                stroke_width_option(style.get("stroke_width", 3.0)),
                "forget plot",
            )
            tex = f"\\addplot+[{options}] coordinates {{{_coordinates_tex(points)}}};"
            if func.label:
                label_point = _style_coordinate(style.get("label_at"))
                if label_point is None:
                    label_point = points[min(len(points) - 1, max(0, len(points) // 2))]
                label_anchor = str(style.get("label_anchor") or "south west")
                dx = float(style.get("label_dx", 4))
                dy = float(style.get("label_dy", 4))
                label_options = join_options(
                    f"anchor={label_anchor}",
                    f"text={color}",
                    f"xshift={fmt_num(dx, 3)}pt" if dx else "",
                    f"yshift={fmt_num(dy, 3)}pt" if dy else "",
                )
                tex += f"\n\\node[{label_options}] at (axis cs:{fmt_num(label_point[0])},{fmt_num(label_point[1])}) {{{node_text_tex(func.label)}}};"
            self.commands.append(TikzCommand(kind="function", order=300 + index, tex=tex))

    def _draw_objects(self) -> None:
        for index, obj in enumerate(self._objects()):
            kind = obj.get("type")
            style = _style_dict(obj)
            if kind == "point":
                self._draw_point_object(index, obj, style)
            elif kind == "line":
                self._draw_line_object(index, obj, style)
            elif kind == "text":
                self._draw_text_object(index, obj, style)
            elif kind == "circle":
                self._draw_circle_object(index, obj, style)
            elif kind == "projection_guide":
                self._draw_projection_guide_object(index, obj, style)
            elif kind in {"polyline", "polygon"}:
                self._draw_poly_object(index, obj, style, closed=kind == "polygon")

    def _draw_point_object(self, index: int, obj: dict[str, Any], style: dict[str, Any]) -> None:
        if "x" not in obj or "y" not in obj:
            return
        x, y = float(obj["x"]), float(obj["y"])
        color = color_option(style.get("stroke") or "#111827")
        radius = float(style.get("radius", 1.5))
        mark_tex = (
            f"\\addplot+[only marks, mark=*, mark size={fmt_num(radius, 3)}pt, draw={color}, fill={color}, forget plot] "
            f"coordinates {{({fmt_num(x)},{fmt_num(y)})}};"
        )
        self.commands.append(TikzCommand(kind="object:point", order=700 + index, tex=mark_tex))

        label = obj.get("label") or obj.get("id")
        if label:
            options = self._point_label_options(style)
            label_tex = (
                f"\\node[axis point label, {options}] "
                f"at (axis cs:{fmt_num(x)},{fmt_num(y)}) {{{point_label_tex(label)}}};"
            )
            self.commands.append(TikzCommand(kind="object:point_label", order=900 + index, tex=label_tex))

    def _point_label_options(self, style: dict[str, Any]) -> str:
        dx_value = style.get("label_dx")
        dy_value = style.get("label_dy")
        if dx_value is not None or dy_value is not None:
            dx = float(dx_value or 0)
            dy = float(dy_value or 0)
            return join_options(
                f"anchor={self._anchor_from_shift(dx, dy)}",
                f"xshift={fmt_num(dx * LABEL_PX_TO_PT, 3)}pt" if dx else "",
                f"yshift={fmt_num(dy * LABEL_PX_TO_PT, 3)}pt" if dy else "",
            )
        offset_pt = self.style.point_label_offset_cm * 28.4528
        return join_options(
            "anchor=south west",
            f"xshift={fmt_num(offset_pt, 3)}pt",
            f"yshift={fmt_num(offset_pt, 3)}pt",
        )

    @staticmethod
    def _anchor_from_shift(dx: float, dy: float) -> str:
        if dx < 0 and dy > 0:
            return "south east"
        if dx > 0 and dy > 0:
            return "south west"
        if dx < 0 and dy < 0:
            return "north east"
        if dx > 0 and dy < 0:
            return "north west"
        if dx < 0:
            return "east"
        if dx > 0:
            return "west"
        if dy > 0:
            return "south"
        if dy < 0:
            return "north"
        return "south west"

    def _draw_line_object(self, index: int, obj: dict[str, Any], style: dict[str, Any]) -> None:
        endpoints = _line_endpoints(obj, self.x_min, self.x_max, self.y_min, self.y_max)
        if endpoints is None:
            self.warnings.append(f"unsupported line object: {obj.get('id') or index}")
            return
        color = color_option(style.get("stroke") or "#111827")
        options = join_options(
            "no markers",
            f"draw={color}",
            stroke_width_option(style.get("stroke_width", 2.4)),
            dash_option(style.get("dash")),
            "forget plot",
        )
        self.commands.append(
            TikzCommand(kind="object:line", order=300 + index, tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex(list(endpoints))}}};")
        )

    def _draw_text_object(self, index: int, obj: dict[str, Any], style: dict[str, Any]) -> None:
        if "x" not in obj or "y" not in obj:
            return
        text = value_only_condition_label(str(obj.get("text") or obj.get("label") or ""), self.style)
        anchor = str(style.get("anchor", "center"))
        fill = color_option(style.get("fill") or "#374151")
        tex = (
            f"\\node[anchor={anchor}, text={fill}, font=\\fontsize{{{fmt_num(self.style.condition_label_pt, 2)}}}{{{fmt_num(self.style.condition_label_pt * 1.1, 2)}}}\\selectfont] "
            f"at (axis cs:{fmt_num(float(obj['x']))},{fmt_num(float(obj['y']))}) {{{node_text_tex(text)}}};"
        )
        self.commands.append(TikzCommand(kind="object:text", order=950 + index, tex=tex))

    def _draw_projection_guide_object(self, index: int, obj: dict[str, Any], style: dict[str, Any]) -> None:
        source = _coordinate(obj.get("point") or obj.get("from") or obj.get("source"), self.point_objects)
        if source is None:
            self.warnings.append(f"projection_guide references missing point: {obj.get('id') or index}")
            return
        to_axis = str(obj.get("to_axis") or "x")
        if to_axis == "x":
            foot = (source[0], 0.0)
            value = source[0]
        elif to_axis == "y":
            foot = (0.0, source[1])
            value = source[1]
        else:
            self.warnings.append(f"projection_guide has unsupported axis: {obj.get('id') or index}")
            return

        color = color_option(style.get("stroke") or "#6b7280")
        options = join_options(
            "no markers",
            f"draw={color}",
            stroke_width_option(style.get("stroke_width", 1.8)),
            dash_option(style.get("dash", "5 4")),
            "forget plot",
        )
        self.commands.append(
            TikzCommand(
                kind="object:projection_guide",
                order=520 + index,
                tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex([source, foot])}}};",
            )
        )
        if obj.get("show_axis_tick", True):
            if to_axis == "x":
                tick_tex = (
                    f"\\draw[draw={color}, line width=0.35pt] "
                    f"(axis cs:{fmt_num(foot[0])},{fmt_num(foot[1])}) ++(0pt,-2.4pt) -- ++(0pt,4.8pt);"
                )
            else:
                tick_tex = (
                    f"\\draw[draw={color}, line width=0.35pt] "
                    f"(axis cs:{fmt_num(foot[0])},{fmt_num(foot[1])}) ++(-2.4pt,0pt) -- ++(4.8pt,0pt);"
                )
            self.commands.append(TikzCommand(kind="object:projection_tick", order=8300 + index, tex=tick_tex))
        self._draw_projection_coordinate_label(index, obj, to_axis, value, foot)

    def _draw_projection_coordinate_label(self, index: int, obj: dict[str, Any], axis: str, value: float, foot: Point) -> None:
        label_style = _model_or_dict(obj.get("label_style"))
        if label_style.get("show") is False:
            return
        text = _label_style_text(label_style, value)
        if not text:
            return
        custom_at = _style_coordinate(label_style.get("at") or label_style.get("label_at"))
        at_point = custom_at if custom_at is not None else foot
        if axis == "x":
            default_anchor = "north"
            default_dx = 0.0
            default_dy = -4.0
        else:
            default_anchor = "east"
            default_dx = -4.0
            default_dy = 0.0
        anchor = str(label_style.get("anchor") or default_anchor)
        dx = float(label_style.get("dx_pt", label_style.get("dx", default_dx)))
        dy = float(label_style.get("dy_pt", label_style.get("dy", default_dy)))
        tick_font = f"font=\\fontsize{{{fmt_num(self.style.tick_label_pt, 2)}}}{{{fmt_num(self.style.tick_label_pt * 1.1, 2)}}}\\selectfont"
        options = join_options(
            f"anchor={anchor}",
            "inner sep=1pt",
            tick_font,
            f"xshift={fmt_num(dx, 3)}pt" if dx else "",
            f"yshift={fmt_num(dy, 3)}pt" if dy else "",
        )
        self.commands.append(
            TikzCommand(
                kind=f"object:projection_label:{axis}",
                order=8350 + index,
                tex=f"\\node[{options}] at (axis cs:{fmt_num(at_point[0])},{fmt_num(at_point[1])}) {{{text}}};",
            )
        )

    def _draw_circle_object(self, index: int, obj: dict[str, Any], style: dict[str, Any]) -> None:
        center = _coordinate(obj.get("center"), self.point_objects)
        if center is None:
            center = (float(obj.get("cx", obj.get("x", 0))), float(obj.get("cy", obj.get("y", 0))))
        radius = float(obj.get("radius", 1))
        points = [
            (center[0] + radius * math.cos(2 * math.pi * step / 72), center[1] + radius * math.sin(2 * math.pi * step / 72))
            for step in range(73)
        ]
        color = color_option(style.get("stroke") or "#111827")
        fill = color_option(style.get("fill"), default="")
        options = join_options(
            "no markers",
            f"draw={color}",
            f"fill={fill}" if fill and str(style.get("fill")).lower() != "none" else "",
            stroke_width_option(style.get("stroke_width", 2.4)),
            "forget plot",
        )
        self.commands.append(TikzCommand(kind="object:circle", order=350 + index, tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex(points)}}};"))

    def _draw_poly_object(self, index: int, obj: dict[str, Any], style: dict[str, Any], *, closed: bool) -> None:
        raw_points = obj.get("points") or []
        points = [_coordinate(item, self.point_objects) for item in raw_points]
        clean_points = [point for point in points if point is not None]
        if len(clean_points) < 2:
            return
        if closed and clean_points[0] != clean_points[-1]:
            clean_points.append(clean_points[0])
        color = color_option(style.get("stroke") or "#111827")
        fill = color_option(style.get("fill"), default="")
        options = join_options(
            "no markers",
            f"draw={color}",
            f"fill={fill}" if closed and fill and str(style.get("fill")).lower() != "none" else "",
            stroke_width_option(style.get("stroke_width", 2.2)),
            dash_option(style.get("dash")),
            "forget plot",
        )
        order = 200 + index if closed else 300 + index
        self.commands.append(TikzCommand(kind="object:polygon" if closed else "object:polyline", order=order, tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex(clean_points)}}};"))


def opacity_option(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"opacity={fmt_num(max(0, min(number, 1)), 3)}"


def compile_coordinate_geometry(spec: GeometryRenderSpec) -> TikzDiagramSpec:
    return CoordinateTikzCompiler(spec).compile()
