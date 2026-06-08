#!/usr/bin/env python3
"""Render geometry-render-spec/v1 to a printable PNG.

This script is intentionally small and dependency-light. It renders the solved
geometry spec to SVG, then converts the SVG to PNG with a locally available
converter. The standard handoff artifact is renderer_result.json.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    GeometryRendererResult,
    GeometryRenderSpec,
    RendererChecks,
)

Point = tuple[float, float]


def read_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model_dump_json(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def model_dump_json(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


def relpath(target: Path, base: Path) -> str:
    return Path(os.path.relpath(target.resolve(), base.resolve())).as_posix()


def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def mul(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def unit(v: Point) -> Point:
    n = math.hypot(v[0], v[1])
    if n == 0:
        return (0.0, 0.0)
    return (v[0] / n, v[1] / n)


def perp(v: Point) -> Point:
    return (-v[1], v[0])


def svg_attrs(**kwargs: object) -> str:
    parts: list[str] = []
    for key, value in kwargs.items():
        if value is None:
            continue
        parts.append(f'{key.replace("_", "-")}="{html.escape(str(value), quote=True)}"')
    return " ".join(parts)


class SvgGeometryRenderer:
    def __init__(self, spec: dict[str, object], width: int, height: int, padding: int = 64):
        self.spec = spec
        self.width = width
        self.height = height
        self.padding = padding
        self.points: dict[str, Point] = {
            str(name): (float(value[0]), float(value[1]))
            for name, value in spec.get("points", {}).items()
        }
        self.elements: list[str] = []
        self.scale, self.offset_x, self.offset_y = self._fit_transform()

    def _fit_transform(self) -> tuple[float, float, float]:
        if not self.points:
            return (1.0, self.width / 2, self.height / 2)
        xs = [p[0] for p in self.points.values()]
        ys = [p[1] for p in self.points.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        world_w = max(max_x - min_x, 1e-6)
        world_h = max(max_y - min_y, 1e-6)
        scale = min(
            (self.width - 2 * self.padding) / world_w,
            (self.height - 2 * self.padding) / world_h,
        )
        drawn_w = world_w * scale
        drawn_h = world_h * scale
        offset_x = (self.width - drawn_w) / 2 - min_x * scale
        offset_y = (self.height - drawn_h) / 2 + max_y * scale
        return scale, offset_x, offset_y

    def screen(self, point_name: str) -> Point:
        x, y = self.points[point_name]
        return (x * self.scale + self.offset_x, -y * self.scale + self.offset_y)

    def line(self, p1: Point, p2: Point, stroke: str, width: float, dash: str | None = None) -> str:
        return f"<line {svg_attrs(x1=f'{p1[0]:.2f}', y1=f'{p1[1]:.2f}', x2=f'{p2[0]:.2f}', y2=f'{p2[1]:.2f}', stroke=stroke, stroke_width=width, stroke_linecap='round', stroke_dasharray=dash)} />"

    def polyline(self, points: list[Point], stroke: str, width: float, fill: str = "none", closed: bool = False) -> str:
        tag = "polygon" if closed else "polyline"
        value = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        return f"<{tag} {svg_attrs(points=value, fill=fill, stroke=stroke, stroke_width=width, stroke_linejoin='round', stroke_linecap='round')} />"

    def rect(self, x: float, y: float, width: float, height: float, fill: str, opacity: float) -> str:
        return f"<rect {svg_attrs(x=f'{x:.2f}', y=f'{y:.2f}', width=f'{width:.2f}', height=f'{height:.2f}', fill=fill, opacity=f'{opacity:.3g}')} />"

    def draw_polygons(self) -> None:
        for polygon in self.spec.get("polygons", []):
            names = polygon.get("points", [])
            if len(names) < 3:
                continue
            screen_points = [self.screen(str(name)) for name in names]
            self.elements.append(
                self.polyline(
                    screen_points,
                    stroke=polygon.get("stroke", "#374151"),
                    width=float(polygon.get("stroke_width", 2.0)),
                    fill=polygon.get("fill", "#eff6ff"),
                    closed=True,
                )
            )

    def draw_segments(self) -> None:
        for segment in self.spec.get("segments", []):
            start = str(segment.get("from") or segment.get("start"))
            end = str(segment.get("to") or segment.get("end"))
            self.elements.append(
                self.line(
                    self.screen(start),
                    self.screen(end),
                    stroke=segment.get("stroke", "#111827"),
                    width=float(segment.get("stroke_width", 2.6)),
                    dash=segment.get("dash"),
                )
            )

    def draw_right_angle(self, marker: dict[str, object]) -> None:
        vertex_name = marker.get("vertex") or marker.get("at")
        arms = [str(name) for name in marker.get("arms", [])[:2]]
        if not vertex_name or len(arms) < 2:
            return
        vertex = self.screen(str(vertex_name))
        arm1, arm2 = arms
        u = unit(sub(self.screen(arm1), vertex))
        v = unit(sub(self.screen(arm2), vertex))
        size = float(marker.get("size_px", 18))
        p1 = add(vertex, mul(u, size))
        p2 = add(p1, mul(v, size))
        p3 = add(vertex, mul(v, size))
        self.elements.append(self.polyline([p1, p2, p3], marker.get("stroke", "#dc2626"), 2.0))

    def draw_equal_ticks(self, marker: dict[str, object]) -> None:
        count = int(marker.get("count", 1))
        size = float(marker.get("size_px", 15))
        spacing = float(marker.get("spacing_px", 6))
        for start, end in marker.get("segments", []):
            p1 = self.screen(str(start))
            p2 = self.screen(str(end))
            along = unit(sub(p2, p1))
            normal = perp(along)
            mid = mul(add(p1, p2), 0.5)
            for i in range(count):
                center = add(mid, mul(along, (i - (count - 1) / 2) * spacing))
                self.elements.append(
                    self.line(
                        add(center, mul(normal, -size / 2)),
                        add(center, mul(normal, size / 2)),
                        marker.get("stroke", "#dc2626"),
                        2.0,
                    )
                )

    def draw_angle_arc(self, marker: dict[str, object]) -> None:
        vertex_name = marker.get("vertex") or marker.get("at")
        arms = [str(name) for name in marker.get("arms", [])[:2]]
        if not vertex_name or len(arms) < 2:
            return
        vertex = self.screen(str(vertex_name))
        arm1, arm2 = arms
        u1 = unit(sub(self.screen(arm1), vertex))
        u2 = unit(sub(self.screen(arm2), vertex))
        a1 = math.atan2(u1[1], u1[0])
        a2 = math.atan2(u2[1], u2[0])
        diff = (a2 - a1) % (2 * math.pi)
        if diff > math.pi:
            a1, a2 = a2, a1
            diff = (a2 - a1) % (2 * math.pi)
        radius = float(marker.get("radius_px", 38))
        start = add(vertex, (math.cos(a1) * radius, math.sin(a1) * radius))
        end = add(vertex, (math.cos(a2) * radius, math.sin(a2) * radius))
        self.elements.append(
            f"<path {svg_attrs(d=f'M {start[0]:.2f} {start[1]:.2f} A {radius:.2f} {radius:.2f} 0 {1 if diff > math.pi else 0} 1 {end[0]:.2f} {end[1]:.2f}', fill='none', stroke=marker.get('stroke', '#059669'), stroke_width=2.0, stroke_linecap='round')} />"
        )

    def draw_markers(self) -> None:
        for marker in self.spec.get("markers", []):
            marker_type = marker.get("type")
            if marker_type == "right_angle":
                self.draw_right_angle(marker)
            elif marker_type in {"equal_ticks", "equal_tick"}:
                self.draw_equal_ticks(marker)
            elif marker_type == "angle_arc":
                self.draw_angle_arc(marker)

    def draw_labels(self) -> None:
        labels = self.spec.get("labels", {})
        font_size = float(self.spec.get("label_font_size", 34))
        point_radius = float(self.spec.get("point_radius", 5.2))
        outline_width = float(self.spec.get("label_outline_width", 5.0))
        for name in self.points:
            x, y = self.screen(name)
            self.elements.append(f"<circle {svg_attrs(cx=f'{x:.2f}', cy=f'{y:.2f}', r=point_radius, fill='#111827')} />")
            label = labels.get(name, {})
            if not isinstance(label, dict):
                label = {"text": str(label)}
            dx = float(label.get("dx", 0))
            dy = float(label.get("dy", -24))
            text = html.escape(str(label.get("text", name)))
            self.elements.append(
                f"<text {svg_attrs(x=f'{x + dx:.2f}', y=f'{y + dy:.2f}', text_anchor='middle', dominant_baseline='central', font_family='Arial, Helvetica, sans-serif', font_size=font_size, font_weight=800, fill='none', stroke='#ffffff', stroke_width=outline_width)}>{text}</text>"
            )
            self.elements.append(
                f"<text {svg_attrs(x=f'{x + dx:.2f}', y=f'{y + dy:.2f}', text_anchor='middle', dominant_baseline='central', font_family='Arial, Helvetica, sans-serif', font_size=font_size, font_weight=800, fill='#111827')}>{text}</text>"
            )

    def render(self) -> str:
        self.draw_polygons()
        self.draw_segments()
        self.draw_markers()
        self.draw_labels()
        title = html.escape(str(self.spec.get("title", "geometry diagram")))
        body = "\n  ".join(self.elements)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-label="{title}">\n'
            f'  <rect x="0" y="0" width="{self.width}" height="{self.height}" fill="#ffffff" />\n'
            f"  {body}\n"
            "</svg>\n"
        )


class SvgCoordinateRenderer:
    def __init__(self, spec: dict[str, object], width: int, height: int, padding: int = 56):
        self.spec = spec
        self.width = width
        self.height = height
        self.padding = padding
        viewport = spec.get("viewport") or {}
        self.x_min = float(viewport.get("x_min", -5))
        self.x_max = float(viewport.get("x_max", 5))
        self.y_min = float(viewport.get("y_min", -5))
        self.y_max = float(viewport.get("y_max", 5))
        self.preserve_aspect = bool(viewport.get("preserve_aspect", True))
        self.view_x_min = self.x_min
        self.view_x_max = self.x_max
        self.view_y_min = self.y_min
        self.view_y_max = self.y_max
        self.scale_x, self.scale_y, self.plot_x, self.plot_y, self.plot_w, self.plot_h = self._plot_transform()
        self.elements: list[str] = []
        self.point_objects: dict[str, Point] = {}

    def _plot_transform(self) -> tuple[float, float, float, float, float, float]:
        span_x = self.x_max - self.x_min
        span_y = self.y_max - self.y_min
        available_w = self.width - 2 * self.padding
        available_h = self.height - 2 * self.padding
        if self.preserve_aspect:
            scale = min(available_w / span_x, available_h / span_y)
            view_span_x = available_w / scale
            view_span_y = available_h / scale
            center_x = (self.x_min + self.x_max) / 2
            center_y = (self.y_min + self.y_max) / 2
            self.view_x_min = center_x - view_span_x / 2
            self.view_x_max = center_x + view_span_x / 2
            self.view_y_min = center_y - view_span_y / 2
            self.view_y_max = center_y + view_span_y / 2
            return scale, scale, float(self.padding), float(self.padding), float(available_w), float(available_h)
        return (
            available_w / span_x,
            available_h / span_y,
            float(self.padding),
            float(self.padding),
            float(available_w),
            float(available_h),
        )

    def screen_xy(self, x: float, y: float) -> Point:
        sx = self.plot_x + (x - self.view_x_min) * self.scale_x
        sy = self.plot_y + self.plot_h - (y - self.view_y_min) * self.scale_y
        return (sx, sy)

    def line(self, p1: Point, p2: Point, stroke: str, width: float, dash: str | None = None) -> str:
        return f"<line {svg_attrs(x1=f'{p1[0]:.2f}', y1=f'{p1[1]:.2f}', x2=f'{p2[0]:.2f}', y2=f'{p2[1]:.2f}', stroke=stroke, stroke_width=width, stroke_linecap='round', stroke_dasharray=dash)} />"

    def polyline(self, points: list[Point], stroke: str, width: float, fill: str = "none", closed: bool = False) -> str:
        tag = "polygon" if closed else "polyline"
        value = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        return f"<{tag} {svg_attrs(points=value, fill=fill, stroke=stroke, stroke_width=width, stroke_linejoin='round', stroke_linecap='round')} />"

    def rect(self, x: float, y: float, width: float, height: float, fill: str, opacity: float) -> str:
        return f"<rect {svg_attrs(x=f'{x:.2f}', y=f'{y:.2f}', width=f'{width:.2f}', height=f'{height:.2f}', fill=fill, opacity=f'{opacity:.3g}')} />"

    def text(self, x: float, y: float, value: str, size: int = 18, anchor: str = "middle", fill: str = "#111827") -> str:
        attrs = svg_attrs(
            x=f"{x:.2f}",
            y=f"{y:.2f}",
            text_anchor=anchor,
            dominant_baseline="central",
            font_family="Arial, Helvetica, sans-serif",
            font_size=size,
            font_weight=700,
            fill=fill,
        )
        return f"<text {attrs}>{html.escape(value)}</text>"

    def draw_interval_bands(self) -> None:
        for obj in self.spec.get("objects") or []:
            if not isinstance(obj, dict) or obj.get("type") not in {"interval_band", "x_interval_band"}:
                continue
            try:
                x_min = max(float(obj.get("x_min", self.view_x_min)), self.view_x_min)
                x_max = min(float(obj.get("x_max", self.view_x_max)), self.view_x_max)
            except (TypeError, ValueError):
                continue
            if x_min >= x_max:
                continue
            style = obj.get("style") if isinstance(obj.get("style"), dict) else {}
            fill = str(style.get("fill") or obj.get("fill") or "#eef2ff")
            opacity = float(style.get("opacity", obj.get("opacity", 0.28)))
            top_left = self.screen_xy(x_min, self.view_y_max)
            bottom_right = self.screen_xy(x_max, self.view_y_min)
            self.elements.append(
                self.rect(
                    top_left[0],
                    top_left[1],
                    bottom_right[0] - top_left[0],
                    bottom_right[1] - top_left[1],
                    fill,
                    opacity,
                )
            )

    def tick_step(self, low: float, high: float, configured: object) -> float:
        if configured:
            return float(configured)
        span = abs(high - low)
        rough = span / 8
        power = 10 ** math.floor(math.log10(max(rough, 1e-9)))
        for factor in (1, 2, 5, 10):
            step = factor * power
            if span / step <= 10:
                return step
        return power

    def tick_values(self, low: float, high: float, step: float) -> list[float]:
        start = math.ceil(low / step) * step
        values: list[float] = []
        current = start
        guard = 0
        while current <= high + 1e-9 and guard < 200:
            values.append(0.0 if abs(current) < 1e-9 else current)
            current += step
            guard += 1
        return values

    def draw_axes(self) -> None:
        axes = self.spec.get("axes") or {}
        draw_x = axes.get("x", True)
        draw_y = axes.get("y", True)
        grid = axes.get("grid", True)
        show_ticks = axes.get("show_ticks", True)
        x_step = self.tick_step(self.view_x_min, self.view_x_max, axes.get("x_tick_step"))
        y_step = self.tick_step(self.view_y_min, self.view_y_max, axes.get("y_tick_step"))
        x_ticks = self.tick_values(self.view_x_min, self.view_x_max, x_step)
        y_ticks = self.tick_values(self.view_y_min, self.view_y_max, y_step)

        if grid:
            for x in x_ticks:
                p1 = self.screen_xy(x, self.view_y_min)
                p2 = self.screen_xy(x, self.view_y_max)
                self.elements.append(self.line(p1, p2, "#e5e7eb", 1.0))
            for y in y_ticks:
                p1 = self.screen_xy(self.view_x_min, y)
                p2 = self.screen_xy(self.view_x_max, y)
                self.elements.append(self.line(p1, p2, "#e5e7eb", 1.0))

        axis_stroke = "#111827"
        if draw_x:
            y_axis = 0 if self.view_y_min <= 0 <= self.view_y_max else self.view_y_min
            self.elements.append(self.line(self.screen_xy(self.view_x_min, y_axis), self.screen_xy(self.view_x_max, y_axis), axis_stroke, 2.0))
        if draw_y:
            x_axis = 0 if self.view_x_min <= 0 <= self.view_x_max else self.view_x_min
            self.elements.append(self.line(self.screen_xy(x_axis, self.view_y_min), self.screen_xy(x_axis, self.view_y_max), axis_stroke, 2.0))

        if show_ticks:
            for x in x_ticks:
                if abs(x) < 1e-9:
                    continue
                sx, sy = self.screen_xy(x, 0 if self.view_y_min <= 0 <= self.view_y_max else self.view_y_min)
                self.elements.append(self.text(sx, sy + 18, f"{x:g}", 13, fill="#4b5563"))
            for y in y_ticks:
                if abs(y) < 1e-9:
                    continue
                sx, sy = self.screen_xy(0 if self.view_x_min <= 0 <= self.view_x_max else self.view_x_min, y)
                self.elements.append(self.text(sx - 18, sy, f"{y:g}", 13, anchor="end", fill="#4b5563"))

        x_label = str(axes.get("x_label", "x"))
        y_label = str(axes.get("y_label", "y"))
        self.elements.append(self.text(*self.screen_xy(self.view_x_max, 0 if self.view_y_min <= 0 <= self.view_y_max else self.view_y_min), x_label, 16, fill="#111827"))
        self.elements.append(self.text(self.screen_xy(0 if self.view_x_min <= 0 <= self.view_x_max else self.view_x_min, self.view_y_max)[0] - 16, self.screen_xy(0 if self.view_x_min <= 0 <= self.view_x_max else self.view_x_min, self.view_y_max)[1], y_label, 16, anchor="end", fill="#111827"))

    def draw_functions(self) -> None:
        samples = self.spec.get("samples") or {}
        functions = self.spec.get("functions") or []
        palette = ["#2563eb", "#dc2626", "#059669", "#7c3aed"]
        for index, func in enumerate(functions):
            fid = str(func.get("id", f"f{index + 1}"))
            raw_points = samples.get(fid) or []
            points: list[Point] = []
            for item in raw_points:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    try:
                        points.append(self.screen_xy(float(item[0]), float(item[1])))
                    except (TypeError, ValueError):
                        continue
            if len(points) >= 2:
                style = func.get("style") if isinstance(func.get("style"), dict) else {}
                stroke = str(style.get("stroke") or palette[index % len(palette)])
                self.elements.append(self.polyline(points, stroke, float(style.get("stroke_width", 3.0))))
            label = func.get("label")
            if label and points:
                lx, ly = points[min(len(points) - 1, max(0, len(points) // 2))]
                self.elements.append(self.text(lx + 10, ly - 18, str(label), 15, anchor="start", fill=palette[index % len(palette)]))

    def object_point(self, value: object) -> Point | None:
        if isinstance(value, str) and value in self.point_objects:
            return self.point_objects[value]
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return (float(value[0]), float(value[1]))
        if isinstance(value, dict) and {"x", "y"} <= set(value):
            return (float(value["x"]), float(value["y"]))
        return None

    def line_endpoints(self, obj: dict[str, object]) -> tuple[Point, Point] | None:
        style_equation = str(obj.get("equation", "")).replace(" ", "")
        number = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
        if style_equation:
            vertical = re.match(rf"^x={{1,2}}(?P<c>{number})$", style_equation)
            if vertical:
                x = float(vertical.group("c"))
                return self.screen_xy(x, self.view_y_min), self.screen_xy(x, self.view_y_max)

            horizontal = re.match(rf"^y={{1,2}}(?P<c>{number})$", style_equation)
            if horizontal:
                y = float(horizontal.group("c"))
                return self.screen_xy(self.view_x_min, y), self.screen_xy(self.view_x_max, y)

            y_match = re.match(r"^y={1,2}(?P<rhs>.+)$", style_equation)
            if y_match:
                rhs = y_match.group("rhs")
                simple_x = re.match(rf"^(?P<sign>[+-]?)x(?P<b>[+-](?:\d+(?:\.\d+)?|\.\d+))?$", rhs)
                if simple_x:
                    m = -1.0 if simple_x.group("sign") == "-" else 1.0
                    b = float(simple_x.group("b") or 0)
                    return self.screen_xy(self.view_x_min, m * self.view_x_min + b), self.screen_xy(self.view_x_max, m * self.view_x_max + b)

                linear = re.match(rf"^(?P<m>{number})\*?x(?P<b>[+-](?:\d+(?:\.\d+)?|\.\d+))?$", rhs)
                if linear:
                    m = float(linear.group("m"))
                    b = float(linear.group("b") or 0)
                    return self.screen_xy(self.view_x_min, m * self.view_x_min + b), self.screen_xy(self.view_x_max, m * self.view_x_max + b)

        if "slope" in obj and "intercept" in obj:
            m = float(obj["slope"])
            b = float(obj["intercept"])
            return self.screen_xy(self.view_x_min, m * self.view_x_min + b), self.screen_xy(self.view_x_max, m * self.view_x_max + b)
        return None

    def draw_objects(self) -> None:
        objects = self.spec.get("objects") or []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "point" and "x" in obj and "y" in obj:
                self.point_objects[str(obj.get("id", ""))] = (float(obj["x"]), float(obj["y"]))

        for obj in objects:
            if not isinstance(obj, dict):
                continue
            kind = obj.get("type")
            style = obj.get("style") if isinstance(obj.get("style"), dict) else {}
            stroke = str(style.get("stroke", "#111827"))
            fill = str(style.get("fill", "none"))
            if kind == "point":
                if "x" not in obj or "y" not in obj:
                    continue
                x, y = float(obj["x"]), float(obj["y"])
                sx, sy = self.screen_xy(x, y)
                self.elements.append(f"<circle {svg_attrs(cx=f'{sx:.2f}', cy=f'{sy:.2f}', r=style.get('radius', 5.2), fill=stroke)} />")
                label = obj.get("label") or obj.get("id")
                if label:
                    self.elements.append(self.text(sx + float(style.get("label_dx", 14)), sy - float(style.get("label_dy", 14)), str(label), 15, anchor="start", fill=str(style.get("label_fill", "#111827"))))
            elif kind == "line":
                endpoints = self.line_endpoints(obj)
                if endpoints is None:
                    continue
                self.elements.append(self.line(endpoints[0], endpoints[1], stroke, float(style.get("stroke_width", 2.4)), style.get("dash")))
            elif kind == "text":
                if "x" not in obj or "y" not in obj:
                    continue
                sx, sy = self.screen_xy(float(obj["x"]), float(obj["y"]))
                self.elements.append(
                    self.text(
                        sx,
                        sy,
                        str(obj.get("text") or obj.get("label") or ""),
                        int(style.get("font_size", 13)),
                        anchor=str(style.get("anchor", "middle")),
                        fill=str(style.get("fill", "#374151")),
                    )
                )
            elif kind == "circle":
                center = obj.get("center")
                if isinstance(center, dict):
                    cx, cy = float(center.get("x", 0)), float(center.get("y", 0))
                elif isinstance(center, (list, tuple)) and len(center) == 2:
                    cx, cy = float(center[0]), float(center[1])
                else:
                    cx, cy = float(obj.get("cx", obj.get("x", 0))), float(obj.get("cy", obj.get("y", 0)))
                radius = float(obj.get("radius", 1))
                center_screen = self.screen_xy(cx, cy)
                edge_screen = self.screen_xy(cx + radius, cy)
                top_screen = self.screen_xy(cx, cy + radius)
                rx_screen = abs(edge_screen[0] - center_screen[0])
                ry_screen = abs(top_screen[1] - center_screen[1])
                if abs(rx_screen - ry_screen) < 1e-6:
                    self.elements.append(f"<circle {svg_attrs(cx=f'{center_screen[0]:.2f}', cy=f'{center_screen[1]:.2f}', r=f'{rx_screen:.2f}', fill=fill, stroke=stroke, stroke_width=style.get('stroke_width', 2.4))} />")
                else:
                    self.elements.append(f"<ellipse {svg_attrs(cx=f'{center_screen[0]:.2f}', cy=f'{center_screen[1]:.2f}', rx=f'{rx_screen:.2f}', ry=f'{ry_screen:.2f}', fill=fill, stroke=stroke, stroke_width=style.get('stroke_width', 2.4))} />")
            elif kind in {"polyline", "polygon"}:
                raw_points = obj.get("points") or []
                world_points = [self.object_point(item) for item in raw_points]
                points = [self.screen_xy(p[0], p[1]) for p in world_points if p is not None]
                if len(points) >= 2:
                    self.elements.append(self.polyline(points, stroke, float(style.get("stroke_width", 2.2)), fill if kind == "polygon" else "none", closed=kind == "polygon"))

    def render(self) -> str:
        self.draw_interval_bands()
        self.draw_axes()
        self.draw_functions()
        self.draw_objects()
        title = html.escape(str(self.spec.get("title", "coordinate diagram")))
        body = "\n  ".join(self.elements)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-label="{title}">\n'
            f'  <rect x="0" y="0" width="{self.width}" height="{self.height}" fill="#ffffff" />\n'
            f"  {body}\n"
            "</svg>\n"
        )


def validate_spec(spec: dict[str, object]) -> list[str]:
    errors: list[str] = []
    spec_type = spec.get("type", "synthetic_geometry")
    if spec_type in {"coordinate_geometry", "function_graph"}:
        viewport = spec.get("viewport")
        if not isinstance(viewport, dict):
            errors.append("analytic spec requires viewport")
            return errors
        for low, high in (("x_min", "x_max"), ("y_min", "y_max")):
            if low not in viewport or high not in viewport:
                errors.append(f"viewport requires {low} and {high}")
            elif float(viewport[low]) >= float(viewport[high]):
                errors.append(f"viewport {low} must be < {high}")
        has_payload = bool(spec.get("points") or spec.get("objects") or spec.get("functions") or spec.get("curves") or spec.get("samples"))
        if not has_payload:
            errors.append("analytic spec requires points, objects, functions, curves, or samples")
        for func in spec.get("functions") or []:
            fid = str(func.get("id", ""))
            if fid and fid not in (spec.get("samples") or {}):
                errors.append(f"function '{fid}' has no samples")
        for index, obj in enumerate(spec.get("objects") or []):
            kind = obj.get("type")
            if kind == "point" and not {"x", "y"} <= set(obj):
                errors.append(f"objects[{index}] point requires x and y")
            if kind == "circle" and "radius" not in obj:
                errors.append(f"objects[{index}] circle requires radius")
        return errors

    points = spec.get("points")
    if not isinstance(points, dict) or not points:
        errors.append("spec requires non-empty points")
        return errors
    point_names = set(str(name) for name in points)
    for section, keys in (("segments", ("from", "to")),):
        for index, item in enumerate(spec.get(section, [])):
            for key in keys:
                value = item.get(key)
                if value is None or str(value) not in point_names:
                    errors.append(f"{section}[{index}] references missing point: {value}")
    for index, polygon in enumerate(spec.get("polygons", [])):
        for name in polygon.get("points", []):
            if str(name) not in point_names:
                errors.append(f"polygons[{index}] references missing point: {name}")
    for index, marker in enumerate(spec.get("markers", [])):
        marker_vertex = marker.get("vertex") or marker.get("at")
        if marker_vertex is not None and str(marker_vertex) not in point_names:
            errors.append(f"markers[{index}] references missing point: {marker_vertex}")
        marker_points = list(marker.get("arms") or [])
        marker_points.extend(p for seg in (marker.get("segments") or []) for p in seg)
        for name in marker_points:
            if str(name) not in point_names:
                errors.append(f"markers[{index}] references missing point: {name}")
    return errors


def convert_svg_to_png(svg_path: Path, png_path: Path, width: int, height: int, size: int) -> tuple[bool, str]:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("rsvg-convert"):
        cmd = ["rsvg-convert", "-w", str(width), "-h", str(height), str(svg_path), "-o", str(png_path)]
    elif shutil.which("magick"):
        cmd = ["magick", str(svg_path), str(png_path)]
    elif shutil.which("convert"):
        cmd = ["convert", str(svg_path), str(png_path)]
    elif shutil.which("sips"):
        cmd = ["sips", "-s", "format", "png", str(svg_path), "--out", str(png_path)]
    elif shutil.which("qlmanage"):
        cmd = ["qlmanage", "-t", "-s", str(size), "-o", str(png_path.parent), str(svg_path)]
    else:
        return False, "png_converter_missing"

    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return False, (completed.stderr or completed.stdout or "png_converter_failed").strip()

    qlmanage_output = png_path.parent / f"{svg_path.name}.png"
    if qlmanage_output.exists() and qlmanage_output != png_path:
        if png_path.exists():
            png_path.unlink()
        qlmanage_output.replace(png_path)
    if not png_path.exists() or png_path.stat().st_size == 0:
        return False, "png_not_created"
    return True, ""


def render_geometry_spec(
    spec_path: Path,
    out_dir: Path,
    width: int,
    height: int,
    size: int,
    variant: str | None = None,
) -> dict[str, object]:
    result_path = out_dir / "renderer_result.json"
    raw_spec = read_json(spec_path)
    diagram_variant = variant or raw_spec.get("diagram_variant") or raw_spec.get("variant") or "prompt"
    if diagram_variant not in {"prompt", "solution"}:
        diagram_variant = "prompt"
    svg_path = out_dir / "rendered" / f"{diagram_variant}.svg"
    png_path = out_dir / "rendered" / f"{diagram_variant}.png"

    try:
        spec_model = GeometryRenderSpec.model_validate(raw_spec)
        spec = spec_model.model_dump(mode="json", by_alias=True)
    except Exception as exc:
        result = GeometryRendererResult(
            status="failed",
            fail_type="invalid_renderer_spec",
            message=str(exc),
            renderer_spec=relpath(spec_path, out_dir),
            image_path="",
            preview_svg="",
            checks=RendererChecks(references_valid=False, image_exists=False),
        ).model_dump(mode="json", by_alias=True)
        write_json(result_path, result)
        return result

    errors = validate_spec(spec)
    if errors:
        result = GeometryRendererResult(
            status="failed",
            fail_type="invalid_renderer_spec",
            message="; ".join(errors),
            renderer_spec=relpath(spec_path, out_dir),
            image_path="",
            preview_svg="",
            checks=RendererChecks(references_valid=False, image_exists=False),
        ).model_dump(mode="json", by_alias=True)
        write_json(result_path, result)
        return result

    svg_path.parent.mkdir(parents=True, exist_ok=True)
    if spec.get("type") in {"coordinate_geometry", "function_graph"}:
        svg_text = SvgCoordinateRenderer(spec, width=width, height=height).render()
    else:
        svg_text = SvgGeometryRenderer(spec, width=width, height=height).render()
    svg_path.write_text(svg_text, encoding="utf-8")
    converted, message = convert_svg_to_png(svg_path, png_path, width=width, height=height, size=size)
    image_exists = png_path.exists() and png_path.stat().st_size > 0
    status = "ok" if converted and image_exists else "failed"
    result = GeometryRendererResult(
        status=status,
        fail_type="" if status == "ok" else "png_export_failed",
        message=message,
        renderer="teaching-svg-geometry-renderer",
        diagram_variant=diagram_variant,
        disclosure_policy="clean" if diagram_variant == "prompt" else "annotated",
        renderer_spec=relpath(spec_path, out_dir),
        image_path=relpath(png_path, out_dir) if image_exists else "",
        preview_svg=relpath(svg_path, out_dir),
        checks=RendererChecks(
            references_valid=True,
            svg_exists=svg_path.exists(),
            image_exists=image_exists,
        ),
    ).model_dump(mode="json", by_alias=True)
    write_json(result_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Render final_renderer_spec.json to renderer_result.json + PNG")
    parser.add_argument("renderer_spec", type=Path, help="Path to final_renderer_spec.json")
    parser.add_argument("--out-dir", type=Path, help="Diagram output dir; defaults beside spec")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=520)
    parser.add_argument("--png-size", type=int, default=1024)
    parser.add_argument("--variant", choices=("prompt", "solution"), help="Output diagram variant")
    args = parser.parse_args()

    spec_path = args.renderer_spec.resolve()
    out_dir = (args.out_dir or spec_path.parent).resolve()
    result = render_geometry_spec(spec_path, out_dir, args.width, args.height, args.png_size, args.variant)
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
