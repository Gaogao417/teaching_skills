from __future__ import annotations

import math
import re

from diagram_contracts import DiagramLabelPlacement, DiagramVariant, GeometryRenderSpec, RenderLabel

from .angle_markers import normalize_angle_marker
from .contracts import TikzCommand, TikzCompilerAudit, TikzCoordinate, TikzDiagramSpec, TikzStyleRole
from .styles import PX_TO_CM, natural_width_cm_for_profile, profile_to_style
from .writer import (
    color_option,
    dash_option,
    fmt_cm,
    fmt_num,
    join_options,
    node_text_tex,
    point_label_tex,
    segment_value_tex,
    stroke_width_option,
)

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
        self.label_boxes: list[tuple[str, float, float, float, float]] = []
        self.annotation_boxes: list[tuple[str, float, float, float, float]] = []
        self.natural_width_cm = 1.0
        self.natural_height_cm = 1.0

    def compile(self) -> TikzDiagramSpec:
        self._compute_coordinates()
        self._draw_polygons()
        self._draw_segments()
        self._draw_markers()
        self._draw_annotations()
        self._draw_points()
        self._remember_default_label_placements()
        self._draw_labels()
        self._audit_label_positions()
        point_label_count = len(self.source_points)
        audit = TikzCompilerAudit(
            bbox_source=self._source_bbox(),
            natural_width_cm=round(self.natural_width_cm, 4),
            natural_height_cm=round(self.natural_height_cm, 4),
            coordinate_count=len(self.coordinates),
            command_count=len(self.commands),
            point_label_count=point_label_count,
            condition_label_count=len(self.spec.annotations),
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
                TikzStyleRole(
                    name="segment value label",
                    options=(
                        "anchor=center, inner sep=1pt, "
                        f"font=\\fontsize{{{fmt_num(self.style.condition_label_pt, 2)}}}"
                        f"{{{fmt_num(self.style.condition_label_pt * 1.1, 2)}}}"
                        "\\selectfont\\bfseries"
                    ),
                ),
            ],
            required_packages=["amsmath"],
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
                "radius_cm": self.style.angle_radius_cm,
            }
        )
        options = join_options(
            f"draw={color_option(getattr(marker, 'stroke', '') or '#059669')}",
            f"angle radius={fmt_cm(self.style.angle_radius_cm)}",
        )
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

    def _draw_annotations(self) -> None:
        # Reserve space from newest to oldest.  In a staged solution the later
        # annotations are the values the current step has just solved, so they
        # should keep the segment midpoint while inherited values yield to the
        # other normal side or a slightly larger offset.
        resolved_layouts: dict[
            int,
            tuple[str, tuple[Point, tuple[float, float, float, float]] | None],
        ] = {}
        for index, annotation in reversed(list(enumerate(self.spec.annotations))):
            targets = list(annotation.target)
            if (
                len(targets) != 2
                or any(name not in self.coord_names for name in targets)
                or annotation.dx
                or annotation.dy
            ):
                continue
            segment_position = str(
                getattr(annotation, "segment_position", "offset") or "offset"
            )
            if segment_position == "legend":
                resolved_layouts[index] = ("legend", None)
                continue
            placement = self._label_placement(annotation.placement) or "above"
            auto_layout = self._place_segment_value(
                annotation, targets[0], targets[1], placement
            )
            if segment_position == "auto" and self._segment_value_needs_legend(
                auto_layout[1], targets[0], targets[1]
            ):
                resolved_layouts[index] = ("legend", None)
                continue
            resolved_layouts[index] = ("offset", auto_layout)
            self.annotation_boxes.append(
                (annotation.id or f"annotation-{index}", *auto_layout[1])
            )

        legend_counts: dict[str, int] = {}
        for index, annotation in enumerate(self.spec.annotations):
            targets = list(annotation.target)
            if any(name not in self.coord_names for name in targets):
                continue
            if len(targets) == 1:
                target_tex = f"({self.coord_names[targets[0]]})"
            else:
                target_tex = self._segment_midpoint_tex(targets[0], targets[1])
            placement = self._label_placement(annotation.placement) or "above"
            is_segment_value = len(targets) == 2
            options = [placement, "segment value label" if is_segment_value else "condition label"]
            segment_position = str(getattr(annotation, "segment_position", "offset") or "offset")
            content_tex = segment_value_tex(annotation.text) if is_segment_value else node_text_tex(annotation.text)
            auto_layout: tuple[Point, tuple[float, float, float, float]] | None = None
            if is_segment_value and index in resolved_layouts:
                segment_position, auto_layout = resolved_layouts[index]
            if is_segment_value and segment_position == "legend":
                legend_placement = str(getattr(annotation, "legend_placement", "top_left") or "top_left")
                legend_index = legend_counts.get(legend_placement, 0)
                legend_counts[legend_placement] = legend_index + 1
                target_tex, legend_anchor = self._legend_target(legend_placement, legend_index)
                options[0] = f"anchor={legend_anchor}"
                content_tex = (
                    f"{point_label_tex(''.join(targets))}\\,=\\,"
                    f"{segment_value_tex(annotation.text)}"
                )
            elif is_segment_value and not annotation.dx and not annotation.dy:
                center, box = auto_layout or self._place_segment_value(
                    annotation, targets[0], targets[1], placement
                )
                target_tex = f"({fmt_num(center[0])},{fmt_num(center[1])})"
                options[0] = "anchor=center"
            if is_segment_value and segment_position != "legend":
                rotation = self._segment_value_rotation(targets[0], targets[1])
                if rotation:
                    options.append(f"rotate={fmt_num(rotation)}")
                    options.append("transform shape")
            if annotation.color:
                options.append(f"text={color_option(annotation.color)}")
            if annotation.dx:
                options.append(f"xshift={fmt_cm(float(annotation.dx) * PX_TO_CM)}")
            if annotation.dy:
                options.append(f"yshift={fmt_cm(-float(annotation.dy) * PX_TO_CM)}")
            self.commands.append(
                TikzCommand(
                    kind="text_annotation",
                    order=350 + index,
                    tex=(
                        f"\\node[{join_options(*options)}] at {target_tex} "
                        f"{{{content_tex}}};"
                    ),
                )
            )

    def _segment_value_needs_legend(
        self,
        box: tuple[float, float, float, float],
        first: str,
        second: str,
    ) -> bool:
        left, right, bottom, top = box
        area = max(1e-9, (right - left) * (top - bottom))

        def overlap_ratio(other: tuple[float, float, float, float]) -> float:
            other_left, other_right, other_bottom, other_top = other
            width = max(0.0, min(right, other_right) - max(left, other_left))
            height = max(0.0, min(top, other_top) - max(bottom, other_bottom))
            return width * height / area

        if any(
            overlap_ratio((other_left, other_right, other_bottom, other_top)) >= 0.12
            for _, other_left, other_right, other_bottom, other_top in self.annotation_boxes
        ):
            return True
        if any(overlap_ratio(other) >= 0.12 for other in self._point_label_obstacle_boxes()):
            return True
        margin = 0.04
        for name, point in self.points.items():
            if name in {first, second}:
                continue
            if (
                left - margin <= point[0] <= right + margin
                and bottom - margin <= point[1] <= top + margin
            ):
                return True
        return False

    def _legend_target(self, placement: str, index: int) -> tuple[str, str]:
        xs = [point[0] for point in self.points.values()]
        ys = [point[1] for point in self.points.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        row_gap = 0.46
        if placement == "top_right":
            return f"({fmt_num(max_x - 0.08)},{fmt_num(max_y - 0.08 - index * row_gap)})", "north east"
        if placement == "bottom_left":
            return f"({fmt_num(min_x + 0.08)},{fmt_num(min_y + 0.08 + index * row_gap)})", "south west"
        if placement == "bottom_right":
            return f"({fmt_num(max_x - 0.08)},{fmt_num(min_y + 0.08 + index * row_gap)})", "south east"
        return f"({fmt_num(min_x + 0.08)},{fmt_num(max_y - 0.08 - index * row_gap)})", "north west"

    def _segment_midpoint_tex(self, first: str, second: str) -> str:
        return f"($({self.coord_names[first]})!0.5!({self.coord_names[second]})$)"

    def _segment_value_rotation(self, first: str, second: str) -> float:
        """Return a readable segment-parallel text angle for moderate slopes."""

        start = self.points[first]
        end = self.points[second]
        angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
        readable_angle = (angle + 90.0) % 180.0 - 90.0
        acute_angle = abs(readable_angle)
        if 10.0 <= acute_angle <= 45.0:
            return readable_angle
        return 0.0

    def _place_segment_value(
        self,
        annotation: object,
        first: str,
        second: str,
        placement: str,
    ) -> tuple[Point, tuple[float, float, float, float]]:
        """Place a horizontal value like an engineering dimension label.

        The longitudinal coordinate stays at the exact segment midpoint. We
        only move along the segment normal, choosing the clearer side and, if
        needed, a larger normal offset.
        """

        start = self.points[first]
        end = self.points[second]
        midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        vx, vy = end[0] - start[0], end[1] - start[1]
        length = max(math.hypot(vx, vy), 1e-9)
        normal = (-vy / length, vx / length)
        preferred = self._placement_vector(placement)
        text = str(getattr(annotation, "text", ""))
        is_fraction = bool(re.search(r"\d\s*/\s*\d", text))
        width = 0.58 + max(0, len(text) - 2) * 0.055
        height = 0.56 if is_fraction else 0.38
        rotation_rad = math.radians(abs(self._segment_value_rotation(first, second)))
        box_width = width * math.cos(rotation_rad) + height * math.sin(rotation_rad)
        box_height = width * math.sin(rotation_rad) + height * math.cos(rotation_rad)
        base_offset = 0.30 if is_fraction else 0.22
        centroid = (
            sum(point[0] for point in self.points.values()) / max(1, len(self.points)),
            sum(point[1] for point in self.points.values()) / max(1, len(self.points)),
        )
        target_key = frozenset((first, second))
        candidates: list[tuple[float, Point, tuple[float, float, float, float]]] = []
        point_label_boxes = self._point_label_obstacle_boxes()
        normal_side = str(getattr(annotation, "normal_side", "auto") or "auto")
        if normal_side == "clockwise":
            signs = (-1.0, 1.0)
            preferred_sign = -1.0
            multipliers = (1.0, 1.25, 1.5, 1.7)
        elif normal_side == "counterclockwise":
            signs = (1.0, -1.0)
            preferred_sign = 1.0
            multipliers = (1.0, 1.25, 1.5, 1.7)
        else:
            signs = (1.0, -1.0)
            preferred_sign = None
            multipliers = (1.0, 1.35, 1.7)
        explicit_offset = getattr(annotation, "normal_offset_cm", None)
        for multiplier in multipliers:
            for sign in signs:
                offset = float(explicit_offset or base_offset) * multiplier
                center = (
                    midpoint[0] + normal[0] * offset * sign,
                    midpoint[1] + normal[1] * offset * sign,
                )
                box = (
                    center[0] - box_width / 2,
                    center[0] + box_width / 2,
                    center[1] - box_height / 2,
                    center[1] + box_height / 2,
                )
                score = 0.0
                score += 8.0 * sign * (normal[0] * preferred[0] + normal[1] * preferred[1])
                if preferred_sign is not None:
                    score += 18.0 if sign == preferred_sign else -18.0
                score += 0.7 * math.hypot(center[0] - centroid[0], center[1] - centroid[1])
                score -= multiplier * 0.9
                for point in self.points.values():
                    distance = math.hypot(center[0] - point[0], center[1] - point[1])
                    if distance < 0.34:
                        score -= 900.0
                    elif distance < 0.58:
                        score -= (0.58 - distance) * 70.0
                for _, left, right, bottom, top in self.annotation_boxes:
                    overlap_w = max(0.0, min(box[1], right) - max(box[0], left))
                    overlap_h = max(0.0, min(box[3], top) - max(box[2], bottom))
                    score -= overlap_w * overlap_h * 1800.0
                for left, right, bottom, top in point_label_boxes:
                    overlap_w = max(0.0, min(box[1], right) - max(box[0], left))
                    overlap_h = max(0.0, min(box[3], top) - max(box[2], bottom))
                    score -= overlap_w * overlap_h * 2200.0
                for segment in self.spec.segments:
                    if frozenset((segment.start, segment.end)) == target_key:
                        continue
                    if segment.start not in self.points or segment.end not in self.points:
                        continue
                    distance = self._point_to_segment_distance(
                        center,
                        self.points[segment.start],
                        self.points[segment.end],
                    )
                    if distance < 0.16:
                        score -= 65.0
                candidates.append((score, center, box))
        _, center, box = max(candidates, key=lambda item: item[0])
        return center, box

    def _point_label_obstacle_boxes(self) -> list[tuple[float, float, float, float]]:
        boxes: list[tuple[float, float, float, float]] = []
        for name, point in self.points.items():
            label = self.spec.labels.get(name)
            text = str(label.text if label and label.text else name)
            placement = self._label_placement(label.placement if label else None) or "above"
            dx = 0.0
            dy = 0.0
            if label and (label.dx or label.dy not in (None, 0, -24)):
                dx = float(label.dx or 0) * PX_TO_CM
                dy = -float(label.dy if label.dy is not None else 0) * PX_TO_CM
            else:
                if "left" in placement:
                    dx -= self.style.point_label_offset_cm
                elif "right" in placement:
                    dx += self.style.point_label_offset_cm
                if "below" in placement:
                    dy -= self.style.point_label_offset_cm
                elif "above" in placement:
                    dy += self.style.point_label_offset_cm
            char_width = max(0.13, self.style.point_label_pt * 0.0352778 * 0.52)
            width = max(0.28, min(1.4, len(text) * char_width)) + 0.22
            height = max(0.3, self.style.point_label_pt * 0.0352778 * 0.9) + 0.22
            center = (point[0] + dx, point[1] + dy)
            boxes.append(
                (
                    center[0] - width / 2,
                    center[0] + width / 2,
                    center[1] - height / 2,
                    center[1] + height / 2,
                )
            )
        return boxes

    def _placement_vector(self, placement: str) -> Point:
        parts = placement.split()
        x = -1.0 if "left" in parts else 1.0 if "right" in parts else 0.0
        y = -1.0 if "below" in parts else 1.0 if "above" in parts else 0.0
        length = math.hypot(x, y)
        return (x / length, y / length) if length else (0.0, 1.0)

    def _point_to_segment_distance(self, point: Point, start: Point, end: Point) -> float:
        vx, vy = end[0] - start[0], end[1] - start[1]
        denom = vx * vx + vy * vy
        if denom <= 1e-12:
            return math.hypot(point[0] - start[0], point[1] - start[1])
        t = max(
            0.0,
            min(
                1.0,
                ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / denom,
            ),
        )
        nearest = (start[0] + t * vx, start[1] + t * vy)
        return math.hypot(point[0] - nearest[0], point[1] - nearest[1])

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
            self._record_label_box(name, text, label)

    def _record_label_box(self, name: str, text: str, label: RenderLabel) -> None:
        point = self.points[name]
        placement = self._label_placement(label.placement) or self.label_placements.get(name) or "above"
        has_explicit_offset = bool(label.dx) or label.dy not in (None, 0, -24)
        if has_explicit_offset:
            dx = float(label.dx or 0) * PX_TO_CM
            dy = -float(label.dy if label.dy is not None else 0) * PX_TO_CM
        else:
            # `dy=-24` is the legacy default sentinel. TikZ ignores that
            # numeric value and applies only the placement shift, so the audit
            # box must do the same. Mixing both offsets made labels appear much
            # closer to their points in the audit than in the rendered image.
            dx = 0.0
            dy = 0.0
            offset = self.style.point_label_offset_cm
            if "left" in placement:
                dx -= offset
            elif "right" in placement:
                dx += offset
            if "below" in placement:
                dy -= offset
            elif "above" in placement:
                dy += offset
        char_width_cm = max(0.13, self.style.point_label_pt * 0.0352778 * 0.52)
        width = max(0.18, min(1.4, len(str(text)) * char_width_cm))
        height = max(0.24, self.style.point_label_pt * 0.0352778 * 0.9)
        center_x = point[0] + dx
        center_y = point[1] + dy
        self.label_boxes.append(
            (
                name,
                center_x - width / 2,
                center_x + width / 2,
                center_y - height / 2,
                center_y + height / 2,
            )
        )
        if math.hypot(dx, dy) > 1.25:
            self.warnings.append(
                f"blocking:label_far_from_point:{name}:{math.hypot(dx, dy):.3f}cm"
            )

    def _audit_label_positions(self) -> None:
        for index, first in enumerate(self.label_boxes):
            name_a, left_a, right_a, bottom_a, top_a = first
            area_a = max(0.0, right_a - left_a) * max(0.0, top_a - bottom_a)
            for second in self.label_boxes[index + 1 :]:
                name_b, left_b, right_b, bottom_b, top_b = second
                overlap_w = max(0.0, min(right_a, right_b) - max(left_a, left_b))
                overlap_h = max(0.0, min(top_a, top_b) - max(bottom_a, bottom_b))
                overlap = overlap_w * overlap_h
                area_b = max(0.0, right_b - left_b) * max(0.0, top_b - bottom_b)
                if overlap and overlap / max(1e-9, min(area_a, area_b)) >= 0.45:
                    self.warnings.append(f"blocking:label_overlap:{name_a}:{name_b}")
            for point_name, point in self.points.items():
                if point_name == name_a:
                    continue
                inset_x = (right_a - left_a) * 0.18
                inset_y = (top_a - bottom_a) * 0.18
                if (
                    left_a + inset_x <= point[0] <= right_a - inset_x
                    and bottom_a + inset_y <= point[1] <= top_a - inset_y
                ):
                    self.warnings.append(
                        f"blocking:label_occludes_point:{name_a}:{point_name}"
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
