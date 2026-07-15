"""Compile spatial geometry without flattening its source coordinates."""

from __future__ import annotations

import math
import re

from diagram_contracts import (
    DiagramLabelPlacement,
    DiagramVariant,
    GeometryRenderSpec,
    RenderLabel,
    SpatialObjectRole,
    SpatialProjectionMode,
)
from spatial_geometry import project_point

from .angle_markers import normalize_angle_marker
from .contracts import TikzCommand, TikzCompilerAudit, TikzCoordinate, TikzDiagramSpec, TikzStyleRole
from .styles import natural_width_cm_for_profile, profile_to_style
from .writer import fmt_cm, fmt_num, join_options, node_text_tex, point_label_tex


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


class SpatialGeometryTikzCompiler:
    def __init__(self, spec: GeometryRenderSpec):
        self.spec = spec
        if spec.projection is None:
            raise ValueError("spatial diagram requires a projection")
        self.projection = spec.projection
        self.style = profile_to_style(spec.render_profile)
        used: set[str] = set()
        self.coord_names = {name: _coord_name(name, used) for name in spec.points3d}
        self.projected = {
            name: project_point(tuple(point), self.projection)
            for name, point in spec.points3d.items()
        }
        self.commands: list[TikzCommand] = []
        self.angle_marker_audit: list[dict[str, object]] = []
        self.scale = 1.0
        self.natural_width_cm = 1.0
        self.natural_height_cm = 1.0

    def compile(self) -> TikzDiagramSpec:
        self._compute_size()
        self._draw_polygons()
        self._draw_segments()
        self._draw_markers()
        self._draw_labelled_points()
        self._draw_labels()
        before_picture, picture_options, packages = self._projection_tex()
        warnings = list(
            ((self.spec.diagnostics or {}).get("spatial_projection") or {}).get("warnings") or []
        )
        return TikzDiagramSpec(
            job_id=self.spec.job_id,
            variant=self.spec.variant or DiagramVariant.PROMPT,
            diagram_type=self.spec.type,
            libraries=["calc", "angles", "quotes", "decorations.markings"],
            required_packages=packages,
            before_picture=before_picture,
            picture_options=picture_options,
            natural_width_cm=self.natural_width_cm,
            natural_height_cm=self.natural_height_cm,
            styles=[
                TikzStyleRole(name="spatial main", options="draw=black,line width=1.05pt,line cap=round"),
                TikzStyleRole(name="spatial secondary", options="draw=black!75,line width=0.9pt,line cap=round"),
                TikzStyleRole(name="spatial auxiliary", options="draw=black!60,line width=0.75pt,densely dashed"),
                TikzStyleRole(name="spatial hidden", options="draw=black!45,line width=0.65pt,dashed"),
                TikzStyleRole(name="spatial intersection", options="draw=black,line width=1.35pt,line cap=round"),
                TikzStyleRole(name="spatial projection", options="draw=black!55,line width=0.7pt,densely dashed"),
                TikzStyleRole(
                    name="point label",
                    options=(
                        "inner sep=1pt, font=\\fontsize{"
                        + fmt_num(self.style.point_label_pt, 2)
                        + "}{"
                        + fmt_num(self.style.point_label_pt * 1.1, 2)
                        + "}\\selectfont"
                    ),
                ),
            ],
            coordinates=[
                TikzCoordinate(
                    name=self.coord_names[name],
                    x=float(point[0]),
                    y=float(point[1]),
                    z=float(point[2]),
                    source_x=float(point[0]),
                    source_y=float(point[1]),
                    source_z=float(point[2]),
                )
                for name, point in self.spec.points3d.items()
            ],
            commands=self.commands,
            audit=TikzCompilerAudit(
                bbox_source=self._bbox(),
                natural_width_cm=self.natural_width_cm,
                natural_height_cm=self.natural_height_cm,
                coordinate_count=len(self.spec.points3d),
                command_count=len(self.commands),
                point_label_count=len(self.spec.labels),
                angle_markers=self.angle_marker_audit,
                warnings=warnings,
            ),
        )

    def _bbox(self) -> dict[str, float]:
        xs = [point[0] for point in self.projected.values()]
        ys = [point[1] for point in self.projected.values()]
        return {
            "x_min": min(xs, default=0),
            "x_max": max(xs, default=0),
            "y_min": min(ys, default=0),
            "y_max": max(ys, default=0),
        }

    def _compute_size(self) -> None:
        bbox = self._bbox()
        world_width = max(bbox["x_max"] - bbox["x_min"], 1e-6)
        world_height = max(bbox["y_max"] - bbox["y_min"], 1e-6)
        target_width = natural_width_cm_for_profile(self.spec.render_profile)
        target_height = max(3.8, min(5.5, target_width * 0.72))
        padding = 0.7
        self.scale = min(
            max(1.0, target_width - padding) / world_width,
            max(1.0, target_height - padding) / world_height,
        )
        self.natural_width_cm = round(world_width * self.scale + padding, 4)
        self.natural_height_cm = round(world_height * self.scale + padding, 4)

    def _projection_tex(self) -> tuple[list[str], str, list[str]]:
        baseline = "baseline=(current bounding box.center)"
        if self.projection.mode in {
            SpatialProjectionMode.TEXTBOOK_OBLIQUE,
            SpatialProjectionMode.AXIAL_SOLID,
        }:
            angle = math.radians(self.projection.depth_angle_deg)
            direction = -1 if self.projection.flip_depth else 1
            yx = direction * self.projection.depth_scale * math.cos(angle) * self.scale
            yy = self.projection.depth_scale * math.sin(angle) * self.scale
            return (
                [],
                join_options(
                    f"x={{({fmt_cm(self.scale)},0cm)}}",
                    f"y={{({fmt_cm(yx)},{fmt_cm(yy)})}}",
                    f"z={{(0cm,{fmt_cm(self.projection.vertical_scale * self.scale)})}}",
                    baseline,
                    "line join=round",
                ),
                [],
            )
        return (
            [
                "\\tdplotsetmaincoords{"
                + fmt_num(self.projection.theta, 3)
                + "}{"
                + fmt_num(self.projection.phi, 3)
                + "}"
            ],
            join_options(
                "tdplot_main_coords",
                f"scale={fmt_num(self.scale, 5)}",
                baseline,
                "line join=round",
            ),
            ["tikz-3dplot"],
        )

    @staticmethod
    def _role(value: object) -> str:
        return value.value if isinstance(value, SpatialObjectRole) else str(value or "main")

    def _draw_polygons(self) -> None:
        for index, polygon in enumerate(self.spec.polygons):
            names = [self.coord_names[name] for name in polygon.points]
            role = self._role(polygon.role)
            fill = "black!3" if role == "projection" else "black!5"
            opacity = 0.2 if role == "projection" else min(float(polygon.fill_opacity), 0.42)
            options = join_options(
                "spatial projection" if role == "projection" else "spatial secondary",
                f"fill={fill}",
                f"fill opacity={fmt_num(opacity, 3)}",
            )
            path = " -- ".join(f"({name})" for name in names)
            self.commands.append(
                TikzCommand(kind="spatial_polygon", order=100 + index, tex=f"\\path[{options}] {path} -- cycle;")
            )

    def _draw_segments(self) -> None:
        role_style = {
            "main": "spatial main",
            "secondary": "spatial secondary",
            "auxiliary": "spatial auxiliary",
            "hidden": "spatial hidden",
            "intersection": "spatial intersection",
            "projection": "spatial projection",
        }
        ordered = sorted(
            enumerate(self.spec.segments),
            key=lambda item: self._role(item[1].role) == "intersection",
        )
        for order_index, (source_index, segment) in enumerate(ordered):
            role = self._role(segment.role)
            options = role_style.get(role, "spatial main")
            if segment.dash:
                options = join_options(options, "dashed")
            self.commands.append(
                TikzCommand(
                    kind=f"spatial_segment:{role}",
                    order=200 + order_index,
                    tex=(
                        f"\\draw[{options}] ({self.coord_names[segment.start]}) -- "
                        f"({self.coord_names[segment.end]});"
                    ),
                )
            )

    def _draw_markers(self) -> None:
        for index, marker in enumerate(self.spec.markers):
            vertex = marker.vertex
            arms = list(marker.arms)[:2]
            tex = ""
            if marker.type in {"right_angle", "angle_arc"}:
                if vertex in self.coord_names and len(arms) == 2 and all(name in self.coord_names for name in arms):
                    macro = "RightAngleMark" if marker.type == "right_angle" else "AngleMark"
                    if marker.type == "angle_arc":
                        mode = marker.angle_mode or "minor"
                        normalized = normalize_angle_marker(
                            self.projected,
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
                        arms = list(normalized.arms)
                    tex = (
                        f"\\{macro}[draw=black!70]{{{self.coord_names[arms[0]]}}}"
                        f"{{{self.coord_names[vertex]}}}{{{self.coord_names[arms[1]]}}}"
                    )
            elif marker.type in {"equal_ticks", "parallel"}:
                macro = "EqualTick" if marker.type == "equal_ticks" else "ParallelMark"
                tex = "\n".join(
                    f"\\{macro}[draw=black!70]{{{self.coord_names[start]}}}{{{self.coord_names[end]}}}"
                    for start, end in marker.segments
                    if start in self.coord_names and end in self.coord_names
                )
            if tex:
                self.commands.append(TikzCommand(kind=f"marker:{marker.type}", order=300 + index, tex=tex))

    def _draw_labelled_points(self) -> None:
        self.commands.append(
            TikzCommand(
                kind="point_radius",
                order=390,
                tex=f"\\renewcommand{{\\DiagramPointRadius}}{{{fmt_cm(self.style.point_radius_cm)}}}",
            )
        )
        for index, name in enumerate(self.spec.labels):
            label = self.spec.labels[name]
            if name in self.coord_names and label.show_point:
                self.commands.append(
                    TikzCommand(
                        kind="point",
                        order=400 + index,
                        tex=f"\\PointDot[fill=black]{{{self.coord_names[name]}}}",
                    )
                )

    def _draw_labels(self) -> None:
        for index, (name, label) in enumerate(self.spec.labels.items()):
            if name not in self.coord_names:
                continue
            placement = self._label_placement(name, label)
            text = label.text or name
            rendered_text = (
                point_label_tex(text)
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9']*", text)
                else node_text_tex(text)
            )
            self.commands.append(
                TikzCommand(
                    kind="point_label",
                    order=500 + index,
                    tex=(
                        f"\\PointLabel[{placement}]{{{self.coord_names[name]}}}"
                        f"{{{rendered_text}}}"
                    ),
                )
            )

    def _label_placement(self, name: str, label: RenderLabel) -> str:
        if label.placement:
            return label.placement.value
        visible = [self.projected[item] for item in self.spec.labels if item in self.projected]
        center_x = sum(point[0] for point in visible) / max(1, len(visible))
        center_y = sum(point[1] for point in visible) / max(1, len(visible))
        point = self.projected[name]
        return self._vector_to_placement(point[0] - center_x, point[1] - center_y)

    @staticmethod
    def _vector_to_placement(x: float, y: float) -> str:
        if math.hypot(x, y) <= 1e-9:
            return DiagramLabelPlacement.ABOVE.value
        angle = math.degrees(math.atan2(y, x))
        index = int(((angle + 360 + 22.5) % 360) // 45)
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


def compile_spatial_geometry(spec: GeometryRenderSpec) -> TikzDiagramSpec:
    return SpatialGeometryTikzCompiler(spec).compile()
