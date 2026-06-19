from __future__ import annotations

import math
import re
from typing import Any

from diagram_contracts import DiagramVariant, GeometryRenderSpec

from .contracts import TikzCommand, TikzCompilerAudit, TikzDiagramSpec, TikzStyleRole
from .styles import profile_to_style, value_only_condition_label
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


def _coordinate(value: object, point_objects: dict[str, Point]) -> Point | None:
    if isinstance(value, str) and value in point_objects:
        return point_objects[value]
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    if isinstance(value, dict) and "x" in value and "y" in value:
        return (float(value["x"]), float(value["y"]))
    return None


def _coordinates_tex(points: list[Point]) -> str:
    return " ".join(f"({fmt_num(x)},{fmt_num(y)})" for x, y in points)


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
        self.natural_width_cm = 7.0
        self.natural_height_cm = max(3.2, min(6.5, self.natural_width_cm * height_px / width_px))

    def compile(self) -> TikzDiagramSpec:
        self._index_points()
        self._begin_axis()
        self._draw_interval_bands()
        self._draw_functions()
        self._draw_objects()
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
            "clip=true",
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
        if axes and axes.x_tick_step:
            axis_options.append(f"xtick distance={fmt_num(axes.x_tick_step)}")
        if axes and axes.y_tick_step:
            axis_options.append(f"ytick distance={fmt_num(axes.y_tick_step)}")
        x_label = axes.x_label if axes else "x"
        y_label = axes.y_label if axes else "y"
        if draw_x and x_label:
            axis_options.append(f"xlabel={{{escape_tex(x_label)}}}")
        if draw_y and y_label:
            axis_options.append(f"ylabel={{{escape_tex(y_label)}}}")
        body = ",\n    ".join(axis_options)
        self.commands.append(TikzCommand(kind="axis:begin", order=0, tex="\\begin{axis}[\n    " + body + "\n  ]"))

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
                mid = points[min(len(points) - 1, max(0, len(points) // 2))]
                tex += f"\n\\node[anchor=south west, text={color}] at (axis cs:{fmt_num(mid[0])},{fmt_num(mid[1])}) {{{node_text_tex(func.label)}}};"
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
            elif kind in {"polyline", "polygon"}:
                self._draw_poly_object(index, obj, style, closed=kind == "polygon")

    def _draw_point_object(self, index: int, obj: dict[str, Any], style: dict[str, Any]) -> None:
        if "x" not in obj or "y" not in obj:
            return
        x, y = float(obj["x"]), float(obj["y"])
        color = color_option(style.get("stroke") or "#111827")
        radius = float(style.get("radius", 2.2))
        tex = (
            f"\\addplot+[only marks, mark=*, mark size={fmt_num(radius, 3)}pt, draw={color}, fill={color}, forget plot] "
            f"coordinates {{({fmt_num(x)},{fmt_num(y)})}};"
        )
        label = obj.get("label") or obj.get("id")
        if label:
            tex += f"\n\\node[axis point label, anchor=south west] at (axis cs:{fmt_num(x)},{fmt_num(y)}) {{{point_label_tex(label)}}};"
        self.commands.append(TikzCommand(kind="object:point", order=500 + index, tex=tex))

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
            TikzCommand(kind="object:line", order=550 + index, tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex(list(endpoints))}}};")
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
        self.commands.append(TikzCommand(kind="object:text", order=600 + index, tex=tex))

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
        self.commands.append(TikzCommand(kind="object:circle", order=650 + index, tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex(points)}}};"))

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
        self.commands.append(TikzCommand(kind="object:polygon" if closed else "object:polyline", order=700 + index, tex=f"\\addplot+[{options}] coordinates {{{_coordinates_tex(clean_points)}}};"))


def opacity_option(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"opacity={fmt_num(max(0, min(number, 1)), 3)}"


def compile_coordinate_geometry(spec: GeometryRenderSpec) -> TikzDiagramSpec:
    return CoordinateTikzCompiler(spec).compile()
