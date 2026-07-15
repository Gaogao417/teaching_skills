from __future__ import annotations

import math
import re

from diagram_contracts import DiagramLabelPlacement, DiagramVariant, GeometryRenderSpec, RenderLabel

from .angle_markers import normalize_angle_marker
from .contracts import TikzCommand, TikzCompilerAudit, TikzCoordinate, TikzDiagramSpec, TikzStyleRole
from .styles import PX_TO_CM, natural_width_cm_for_profile, profile_to_style
from .writer import color_option, dash_option, fmt_cm, fmt_num, join_options, point_label_tex, stroke_width_option

Point = tuple[float, float]
TIKZ_LABEL_PLACEMENTS = {placement.value for placement in DiagramLabelPlacement}


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
        self.label_placements: dict[str, str] = {}
        self.warnings: list[str] = []
        self.angle_marker_audit: list[dict[str, object]] = []
        self.natural_width_cm = 1.0
        self.natural_height_cm = 1.0

    def compile(self) -> TikzDiagramSpec:
        self._compute_coordinates()
        self._draw_polygons()
        self._draw_segments()
        self._draw_markers()
        self._draw_points()
        self._remember_default_label_placements()
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
            angle_markers=self.angle_marker_audit,
            warnings=self.warnings,
        )
        return TikzDiagramSpec(
            job_id=self.spec.job_id,
            variant=self.spec.variant or DiagramVariant.PROMPT,
            diagram_type=self.spec.type,
            libraries=["calc", "intersections", "angles", "quotes", "arrows.meta", "decorations.markings"],
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
        target_total_w = natural_width_cm_for_profile(self.spec.render_profile)
        target_total_h = max(3.6, min(5.2, target_total_w * 0.68))
        padding = 0.4
        target_w = max(1.0, target_total_w - padding * 2)
        target_h = max(1.0, target_total_h - padding * 2)
        scale = min(target_w / world_w, target_h / world_h)
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
            if len(names) == 3:
                tex = f"\\Triangle[{options}]{{{names[0]}}}{{{names[1]}}}{{{names[2]}}}"
            elif len(names) == 4:
                tex = f"\\Quadrilateral[{options}]{{{names[0]}}}{{{names[1]}}}{{{names[2]}}}{{{names[3]}}}"
            else:
                path = " -- ".join(f"({name})" for name in names)
                tex = f"\\PolygonPath[{options}]{{{path}}}"
            self.commands.append(TikzCommand(kind="polygon", order=100 + index, tex=tex))
            self._remember_polygon_label_placements(polygon.points)

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
                    tex=f"\\DrawSegment[{options}]{{{self.coord_names[segment.start]}}}{{{self.coord_names[segment.end]}}}",
                )
            )

    def _draw_markers(self) -> None:
        for index, marker in enumerate(self.spec.markers):
            if marker.type == "right_angle":
                tex = self._right_angle_tex(marker)
            elif marker.type == "equal_ticks":
                tex = self._equal_ticks_tex(marker)
            elif marker.type == "parallel":
                tex = self._parallel_mark_tex(marker)
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
        if vertex not in self.coord_names or len(arms) < 2 or any(arm not in self.coord_names for arm in arms):
            return ""
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#dc2626')}")
        return f"\\RightAngleMark[{options}]{{{self.coord_names[arms[0]]}}}{{{self.coord_names[vertex]}}}{{{self.coord_names[arms[1]]}}}"

    def _equal_ticks_tex(self, marker: object) -> str:
        segments = list(getattr(marker, "segments", []) or [])
        count = max(1, int(getattr(marker, "count", 1) or 1))
        lines: list[str] = []
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#dc2626')}")
        macro_name = "EqualTick" if count == 1 else "DoubleEqualTick" if count == 2 else "TripleEqualTick"
        for start, end in segments:
            if start not in self.coord_names or end not in self.coord_names:
                continue
            lines.append(f"\\{macro_name}[{options}]{{{self.coord_names[start]}}}{{{self.coord_names[end]}}}")
        return "\n".join(lines)

    def _parallel_mark_tex(self, marker: object) -> str:
        segments = list(getattr(marker, "segments", []) or [])
        lines: list[str] = []
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#2563eb')}")
        for start, end in segments:
            if start not in self.coord_names or end not in self.coord_names:
                continue
            lines.append(f"\\ParallelMark[{options}]{{{self.coord_names[start]}}}{{{self.coord_names[end]}}}")
        return "\n".join(lines)

    def _angle_arc_tex(self, marker: object) -> str:
        vertex = getattr(marker, "vertex", "")
        arms = list(getattr(marker, "arms", []) or [])[:2]
        if vertex not in self.coord_names or len(arms) < 2 or any(arm not in self.coord_names for arm in arms):
            return ""
        mode = getattr(marker, "angle_mode", "minor") or "minor"
        normalized = normalize_angle_marker(
            self.source_points,
            vertex=vertex,
            arms=(arms[0], arms[1]),
            mode=mode,
        )
        self.angle_marker_audit.append(
            {
                "vertex": vertex,
                "requested_arms": arms,
                "normalized_arms": list(normalized.arms),
                "angle_mode": mode,
                "sweep_deg": normalized.sweep_deg,
                "swapped": normalized.swapped,
            }
        )
        options = join_options(f"draw={color_option(getattr(marker, 'stroke', '') or '#059669')}")
        return f"\\AngleMark[{options}]{{{self.coord_names[normalized.arms[0]]}}}{{{self.coord_names[vertex]}}}{{{self.coord_names[normalized.arms[1]]}}}"

    def _draw_points(self) -> None:
        self.commands.append(
            TikzCommand(
                kind="point_radius",
                order=390,
                tex=f"\\renewcommand{{\\DiagramPointRadius}}{{{fmt_cm(self.style.point_radius_cm)}}}",
            )
        )
        for index, name in enumerate(self.source_points):
            self.commands.append(
                TikzCommand(
                    kind="point",
                    order=400 + index,
                    tex=f"\\PointDot[fill={color_option('#111827')}]{{{self.coord_names[name]}}}",
                )
            )

    def _draw_labels(self) -> None:
        for index, name in enumerate(self.source_points):
            label = self.spec.labels.get(name)
            if not label:
                label = RenderLabel(text=name, dx=0, dy=0)
            text = label.text or name
            options = self._label_options(name, label)
            self.commands.append(
                TikzCommand(
                    kind="point_label",
                    order=500 + index,
                    tex=f"\\PointLabel[{options}]{{{self.coord_names[name]}}}{{{point_label_tex(text)}}}",
                )
            )

    def _label_options(self, name: str, label: RenderLabel) -> str:
        placement = self._label_placement(label.placement) or self.label_placements.get(name) or "above"
        options = ["anchor=center" if placement == DiagramLabelPlacement.CENTER.value else placement]
        has_explicit_offset = bool(label.dx) or label.dy not in (None, 0, -24)
        if has_explicit_offset:
            dx_cm = float(label.dx or 0) * PX_TO_CM
            dy_cm = -float(label.dy if label.dy is not None else 0) * PX_TO_CM
            options.extend([f"xshift={fmt_cm(dx_cm)}", f"yshift={fmt_cm(dy_cm)}"])
        elif placement != DiagramLabelPlacement.CENTER.value:
            options.extend(self._placement_shift_options(placement))
        return join_options(*options)

    def _placement_shift_options(self, placement: str) -> list[str]:
        dx = 0.0
        dy = 0.0
        parts = placement.split()
        if "left" in parts:
            dx = -self.style.point_label_offset_cm
        elif "right" in parts:
            dx = self.style.point_label_offset_cm
        if "below" in parts:
            dy = -self.style.point_label_offset_cm
        elif "above" in parts:
            dy = self.style.point_label_offset_cm
        options: list[str] = []
        if dx:
            options.append(f"xshift={fmt_cm(dx)}")
        if dy:
            options.append(f"yshift={fmt_cm(dy)}")
        return options

    def _label_placement(self, placement: DiagramLabelPlacement | str | None) -> str:
        if not placement:
            return ""
        value = placement.value if isinstance(placement, DiagramLabelPlacement) else str(placement)
        value = re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))
        if value in TIKZ_LABEL_PLACEMENTS:
            return value
        self.warnings.append(f"unsupported point label placement: {value}")
        return ""

    def _remember_polygon_label_placements(self, point_names: list[str]) -> None:
        polygon_points = [self.points[name] for name in point_names if name in self.points]
        if len(polygon_points) < 3:
            return
        centroid_x = sum(point[0] for point in polygon_points) / len(polygon_points)
        centroid_y = sum(point[1] for point in polygon_points) / len(polygon_points)
        for name in point_names:
            if name in self.label_placements or name not in self.points:
                continue
            point = self.points[name]
            vx = point[0] - centroid_x
            vy = point[1] - centroid_y
            self.label_placements[name] = self._vector_to_label_placement(vx, vy)

    def _remember_default_label_placements(self) -> None:
        if len(self.points) < 2:
            return
        xs = [point[0] for point in self.points.values()]
        ys = [point[1] for point in self.points.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        tol_x = max((max_x - min_x) * 0.08, 1e-6)
        tol_y = max((max_y - min_y) * 0.08, 1e-6)
        centroid_x = sum(point[0] for point in self.points.values()) / len(self.points)
        centroid_y = sum(point[1] for point in self.points.values()) / len(self.points)
        for name, point in self.points.items():
            if name in self.label_placements:
                continue
            self.label_placements[name] = self._bbox_label_placement(
                point,
                min_x=min_x,
                max_x=max_x,
                min_y=min_y,
                max_y=max_y,
                tol_x=tol_x,
                tol_y=tol_y,
            ) or self._vector_to_label_placement(point[0] - centroid_x, point[1] - centroid_y)

    def _bbox_label_placement(
        self,
        point: Point,
        *,
        min_x: float,
        max_x: float,
        min_y: float,
        max_y: float,
        tol_x: float,
        tol_y: float,
    ) -> str:
        x, y = point
        on_left = x <= min_x + tol_x
        on_right = x >= max_x - tol_x
        on_bottom = y <= min_y + tol_y
        on_top = y >= max_y - tol_y
        if on_bottom:
            if on_left:
                return "below left"
            if on_right:
                return "below right"
            return "below"
        if on_top:
            if on_left:
                return "above left"
            if on_right:
                return "above right"
            return "above"
        if on_left:
            return "left"
        if on_right:
            return "right"
        return ""

    def _vector_to_label_placement(self, vx: float, vy: float) -> str:
        if math.hypot(vx, vy) <= 1e-9:
            return "above"
        angle = math.degrees(math.atan2(vy, vx))
        index = int(((angle + 360.0 + 22.5) % 360.0) // 45.0)
        return [
            "right",
            "above right",
            "above",
            "above left",
            "left",
            "below left",
            "below",
            "below right",
        ][index]


def compile_synthetic_geometry(spec: GeometryRenderSpec) -> TikzDiagramSpec:
    return SyntheticGeometryTikzCompiler(spec).compile()
