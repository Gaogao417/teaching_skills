from __future__ import annotations

import math
import re

from diagram_contracts import DiagramVariant, GeometryRenderSpec, RenderLabel

from .contracts import TikzCommand, TikzCompilerAudit, TikzCoordinate, TikzDiagramSpec, TikzStyleRole
from .styles import PX_TO_CM, profile_to_style
from .writer import color_option, dash_option, fmt_cm, fmt_num, join_options, node_text_tex, point_label_tex, stroke_width_option

Point = tuple[float, float]


def _coord_name(name: str, used: set[str]) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not candidate or not re.match(r"^[A-Za-z]", candidate):
        candidate = f"P_{candidate or 'point'}"
    original = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{original}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def _unit(a: Point) -> Point:
    length = math.hypot(a[0], a[1])
    if length <= 1e-12:
        return (0, 0)
    return (a[0] / length, a[1] / length)


def _perp(a: Point) -> Point:
    return (-a[1], a[0])


class SyntheticGeometryTikzCompiler:
    def __init__(self, spec: GeometryRenderSpec):
        self.spec = spec
        self.style = profile_to_style(spec.render_profile)
        self.used_names: set[str] = set()
        self.coord_names = {name: _coord_name(name, self.used_names) for name in spec.points}
        self.source_points = {name: (float(point[0]), float(point[1])) for name, point in spec.points.items()}
        self.points: dict[str, Point] = {}
        self.coordinates: list[TikzCoordinate] = []
        self.commands: list[TikzCommand] = []
        self.warnings: list[str] = []
        self.natural_width_cm = 1.0
        self.natural_height_cm = 1.0

    def compile(self) -> TikzDiagramSpec:
        self._compute_coordinates()
        self._draw_polygons()
        self._draw_segments()
        self._draw_markers()
        self._draw_points()
        self._draw_labels()
        point_label_count = len(self.source_points)
        audit = TikzCompilerAudit(
            bbox_source=self._source_bbox(),
            natural_width_cm=round(self.natural_width_cm, 4),
            natural_height_cm=round(self.natural_height_cm, 4),
            coordinate_count=len(self.coordinates),
            command_count=len(self.commands),
            point_label_count=point_label_count,
            condition_label_count=0,
            warnings=self.warnings,
        )
        return TikzDiagramSpec(
            job_id=self.spec.job_id,
            variant=self.spec.variant or DiagramVariant.PROMPT,
            diagram_type=self.spec.type,
            libraries=["calc", "angles", "quotes", "arrows.meta"],
            natural_width_cm=self.natural_width_cm,
            natural_height_cm=self.natural_height_cm,
            styles=[
                TikzStyleRole(
                    name="diagram point",
                    options=f"fill={color_option('#111827')}",
                ),
                TikzStyleRole(
                    name="point label",
                    options=f"inner sep=1pt, font=\\fontsize{{{fmt_num(self.style.point_label_pt, 2)}}}{{{fmt_num(self.style.point_label_pt * 1.1, 2)}}}\\selectfont",
                ),
                TikzStyleRole(
                    name="condition label",
                    options=f"inner sep=1pt, font=\\fontsize{{{fmt_num(self.style.condition_label_pt, 2)}}}{{{fmt_num(self.style.condition_label_pt * 1.1, 2)}}}\\selectfont",
                ),
            ],
            coordinates=self.coordinates,
            commands=self.commands,
            audit=audit,
        )

    def _source_bbox(self) -> dict[str, object]:
        xs = [point[0] for point in self.source_points.values()]
        ys = [point[1] for point in self.source_points.values()]
        return {
            "x_min": min(xs) if xs else 0,
            "x_max": max(xs) if xs else 0,
            "y_min": min(ys) if ys else 0,
            "y_max": max(ys) if ys else 0,
        }

    def _compute_coordinates(self) -> None:
        if not self.source_points:
            return
        bbox = self._source_bbox()
        min_x, max_x = float(bbox["x_min"]), float(bbox["x_max"])
        min_y, max_y = float(bbox["y_min"]), float(bbox["y_max"])
        world_w = max(max_x - min_x, 1e-6)
        world_h = max(max_y - min_y, 1e-6)
        target_w = 6.2
        target_h = 4.2
        scale = min(target_w / world_w, target_h / world_h)
        padding = 0.45
        self.natural_width_cm = round(world_w * scale + padding * 2, 4)
        self.natural_height_cm = round(world_h * scale + padding * 2, 4)
        for name, point in self.source_points.items():
            x = (point[0] - min_x) * scale + padding
            y = (point[1] - min_y) * scale + padding
            self.points[name] = (x, y)
            self.coordinates.append(
                TikzCoordinate(
                    name=self.coord_names[name],
                    x=round(x, 5),
                    y=round(y, 5),
                    source_x=point[0],
                    source_y=point[1],
                )
            )

    def _draw_polygons(self) -> None:
        for index, polygon in enumerate(self.spec.polygons):
            names = [self.coord_names[name] for name in polygon.points if name in self.coord_names]
            if len(names) < 3:
                continue
            fill = color_option(polygon.fill, default="")
            options = join_options(
                f"draw={color_option(polygon.stroke)}",
                f"fill={fill}" if fill and str(polygon.fill).lower() != "none" else "",
                stroke_width_option(polygon.stroke_width),
                "line join=round",
            )
            path = " -- ".join(f"({name})" for name in names) + " -- cycle"
            self.commands.append(TikzCommand(kind="polygon", order=100 + index, tex=f"\\path[{options}] {path};"))

    def _draw_segments(self) -> None:
        for index, segment in enumerate(self.spec.segments):
            if segment.start not in self.coord_names or segment.end not in self.coord_names:
                continue
            options = join_options(
                f"draw={color_option(segment.stroke)}",
                stroke_width_option(segment.stroke_width),
                dash_option(segment.dash),
                "line cap=round",
            )
            self.commands.append(
                TikzCommand(
                    kind="segment",
                    order=200 + index,
                    tex=f"\\draw[{options}] ({self.coord_names[segment.start]}) -- ({self.coord_names[segment.end]});",
                )
            )

    def _draw_markers(self) -> None:
        for index, marker in enumerate(self.spec.markers):
            if marker.type == "right_angle":
                tex = self._right_angle_tex(marker)
            elif marker.type == "equal_ticks":
                tex = self._equal_ticks_tex(marker)
            elif marker.type == "angle_arc":
                tex = self._angle_arc_tex(marker)
            else:
                self.warnings.append(f"unsupported synthetic marker: {marker.type}")
                continue
            if tex:
                self.commands.append(TikzCommand(kind=f"marker:{marker.type}", order=300 + index, tex=tex))

    def _right_angle_tex(self, marker: object) -> str:
        vertex = getattr(marker, "vertex", "")
        arms = list(getattr(marker, "arms", []) or [])[:2]
        if vertex not in self.points or len(arms) < 2 or any(arm not in self.points for arm in arms):
            return ""
        v = self.points[vertex]
        u1 = _unit(_sub(self.points[arms[0]], v))
        u2 = _unit(_sub(self.points[arms[1]], v))
        size = 0.28
        p1 = _add(v, _mul(u1, size))
        p2 = _add(p1, _mul(u2, size))
        p3 = _add(v, _mul(u2, size))
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#dc2626')}", "line width=1.2pt")
        return (
            f"\\draw[{options}] ({fmt_num(p1[0])},{fmt_num(p1[1])}) -- "
            f"({fmt_num(p2[0])},{fmt_num(p2[1])}) -- ({fmt_num(p3[0])},{fmt_num(p3[1])});"
        )

    def _equal_ticks_tex(self, marker: object) -> str:
        segments = list(getattr(marker, "segments", []) or [])
        count = max(1, int(getattr(marker, "count", 1) or 1))
        tick_size = 0.18
        spacing = 0.12
        lines: list[str] = []
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#dc2626')}", "line width=1.2pt")
        for start, end in segments:
            if start not in self.points or end not in self.points:
                continue
            p1, p2 = self.points[start], self.points[end]
            along = _unit(_sub(p2, p1))
            normal = _perp(along)
            mid = _mul(_add(p1, p2), 0.5)
            for i in range(count):
                center = _add(mid, _mul(along, (i - (count - 1) / 2) * spacing))
                a = _add(center, _mul(normal, -tick_size / 2))
                b = _add(center, _mul(normal, tick_size / 2))
                lines.append(
                    f"\\draw[{options}] ({fmt_num(a[0])},{fmt_num(a[1])}) -- ({fmt_num(b[0])},{fmt_num(b[1])});"
                )
        return "\n".join(lines)

    def _angle_arc_tex(self, marker: object) -> str:
        vertex = getattr(marker, "vertex", "")
        arms = list(getattr(marker, "arms", []) or [])[:2]
        if vertex not in self.points or len(arms) < 2 or any(arm not in self.points for arm in arms):
            return ""
        v = self.points[vertex]
        u1 = _unit(_sub(self.points[arms[0]], v))
        u2 = _unit(_sub(self.points[arms[1]], v))
        a1 = math.degrees(math.atan2(u1[1], u1[0]))
        a2 = math.degrees(math.atan2(u2[1], u2[0]))
        diff = (a2 - a1) % 360
        if diff > 180:
            a1, a2 = a2, a1
        radius = 0.48
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#059669')}", "line width=1.2pt")
        return (
            f"\\draw[{options}] ({self.coord_names[vertex]}) ++({fmt_num(a1, 3)}:{fmt_cm(radius)}) "
            f"arc[start angle={fmt_num(a1, 3)}, end angle={fmt_num(a2, 3)}, radius={fmt_cm(radius)}];"
        )

    def _draw_points(self) -> None:
        for index, name in enumerate(self.source_points):
            self.commands.append(
                TikzCommand(
                    kind="point",
                    order=400 + index,
                    tex=f"\\fill[diagram point] ({self.coord_names[name]}) circle[radius={fmt_cm(self.style.point_radius_cm)}];",
                )
            )

    def _draw_labels(self) -> None:
        for index, name in enumerate(self.source_points):
            label = self.spec.labels.get(name)
            if not label:
                label = RenderLabel(text=name, dy=-(self.spec.render_profile.point_label_offset_px or 34))
            text = label.text or name
            dx_cm = float(label.dx or 0) * PX_TO_CM
            dy_cm = -float(label.dy if label.dy is not None else -24) * PX_TO_CM
            self.commands.append(
                TikzCommand(
                    kind="point_label",
                    order=500 + index,
                    tex=(
                        f"\\node[point label, xshift={fmt_cm(dx_cm)}, yshift={fmt_cm(dy_cm)}] "
                        f"at ({self.coord_names[name]}) {{{point_label_tex(text)}}};"
                    ),
                )
            )


def compile_synthetic_geometry(spec: GeometryRenderSpec) -> TikzDiagramSpec:
    return SyntheticGeometryTikzCompiler(spec).compile()
