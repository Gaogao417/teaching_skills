#!/usr/bin/env python3
"""Render fixed theorem diagrams from auditable 3D specs.

The fixed theorem-recall diagrams are intentionally not produced by the live
diagram workflow.  They are still generated from structured geometry data:

    theorem conditions -> 3D coordinates -> tikz-3dplot TikZ

This script validates the declared theorem conditions in 3D before writing the
TikZ fragments used by assignment YAML.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

import yaml


EPS = 1e-7


def v_add(a: list[float], b: list[float]) -> list[float]:
    return [a[i] + b[i] for i in range(3)]


def v_sub(a: list[float], b: list[float]) -> list[float]:
    return [a[i] - b[i] for i in range(3)]


def v_scale(a: list[float], scalar: float) -> list[float]:
    return [scalar * a[i] for i in range(3)]


def v_dot(a: list[float], b: list[float]) -> float:
    return sum(a[i] * b[i] for i in range(3))


def v_cross(a: list[float], b: list[float]) -> list[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def v_norm(a: list[float]) -> float:
    return math.sqrt(v_dot(a, a))


def v_mid(a: list[float], b: list[float]) -> list[float]:
    return [(a[i] + b[i]) / 2 for i in range(3)]


def unit(a: list[float]) -> list[float]:
    n = v_norm(a)
    if n <= EPS:
        raise ValueError("zero vector cannot be normalized")
    return [a[i] / n for i in range(3)]


def is_zero(a: list[float], eps: float = EPS) -> bool:
    return v_norm(a) <= eps


def is_parallel(a: list[float], b: list[float]) -> bool:
    return is_zero(v_cross(a, b))


def is_perpendicular(a: list[float], b: list[float]) -> bool:
    return abs(v_dot(a, b)) <= EPS


def cross2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def fmt(n: float) -> str:
    if abs(n) < 1e-9:
        n = 0.0
    return f"{n:.3f}".rstrip("0").rstrip(".")


def tex_label(name: str) -> str:
    greek = {
        "alpha": r"\alpha",
        "beta": r"\beta",
        "gamma": r"\gamma",
    }
    if name in greek:
        return f"${greek[name]}$"
    if name.endswith("_prime"):
        return f"${name[:-6]}'$"
    if name == "S_original":
        return "$S$"
    if name == "S_projection":
        return "$S'$"
    return f"${name}$"


def coord3(point: list[float]) -> str:
    return f"({fmt(point[0])},{fmt(point[1])},{fmt(point[2])})"


def tikz_coord_name(name: str, used: set[str]) -> str:
    base = "pt" + re.sub(r"[^A-Za-z0-9]+", "", name)
    if base == "pt":
        base = "pt0"
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}{index}"
        index += 1
    used.add(candidate)
    return candidate


class DiagramContext:
    def __init__(self, diagram: dict[str, Any]):
        self.diagram = diagram
        self.points: dict[str, list[float]] = {
            key: [float(x) for x in value]
            for key, value in diagram.get("points", {}).items()
        }
        self.lines: dict[str, dict[str, Any]] = diagram.get("lines", {})
        self.planes: dict[str, dict[str, Any]] = diagram.get("planes", {})
        self.polygons: dict[str, dict[str, Any]] = diagram.get("polygons", {})
        used: set[str] = set()
        self.coord_names: dict[str, str] = {
            name: tikz_coord_name(name, used) for name in self.points
        }
        self._coord_names_used = used

    def point(self, name: str) -> list[float]:
        if name not in self.points:
            raise ValueError(f"missing point {name}")
        return self.points[name]

    def set_point(self, name: str, point: list[float]) -> None:
        self.points[name] = point
        if name not in self.coord_names:
            self.coord_names[name] = tikz_coord_name(name, self._coord_names_used)

    def line_points(self, name: str) -> tuple[list[float], list[float]]:
        line = self.lines.get(name)
        if not line:
            raise ValueError(f"missing line {name}")
        through = line.get("through")
        if not through or len(through) != 2:
            raise ValueError(f"line {name} needs through: [P,Q]")
        return self.point(through[0]), self.point(through[1])

    def line_dir(self, name: str) -> list[float]:
        p, q = self.line_points(name)
        d = v_sub(q, p)
        if is_zero(d):
            raise ValueError(f"line {name} has zero length")
        return d

    def ref(self, name: str) -> str:
        if name not in self.coord_names:
            raise ValueError(f"missing coordinate name for point {name}")
        return f"({self.coord_names[name]})"

    def plane_points(self, name: str) -> list[list[float]]:
        plane = self.planes.get(name)
        if not plane:
            raise ValueError(f"missing plane {name}")
        polygon = plane.get("polygon")
        if not polygon or len(polygon) < 3:
            raise ValueError(f"plane {name} needs at least 3 polygon points")
        return [self.point(p) for p in polygon]

    def plane_normal(self, name: str) -> list[float]:
        pts = self.plane_points(name)
        base = pts[0]
        for i in range(1, len(pts) - 1):
            n = v_cross(v_sub(pts[i], base), v_sub(pts[i + 1], base))
            if not is_zero(n):
                return n
        raise ValueError(f"plane {name} polygon is collinear")

    def point_on_line(self, point_name: str, line_name: str) -> bool:
        p = self.point(point_name)
        a, b = self.line_points(line_name)
        return is_zero(v_cross(v_sub(p, a), v_sub(b, a)))

    def point_in_plane(self, point_name: str, plane_name: str) -> bool:
        p = self.point(point_name)
        base = self.plane_points(plane_name)[0]
        n = self.plane_normal(plane_name)
        return abs(v_dot(v_sub(p, base), n)) <= EPS

    def line_in_plane(self, line_name: str, plane_name: str) -> bool:
        through = self.lines[line_name]["through"]
        return all(self.point_in_plane(p, plane_name) for p in through)


def validate_condition(ctx: DiagramContext, cond: dict[str, Any]) -> None:
    relation = cond["relation"]
    objects = cond.get("objects", [])

    def fail() -> None:
        raise ValueError(
            f"{ctx.diagram['theorem_id']}: condition failed: "
            f"{relation}({', '.join(objects)})"
        )

    if relation == "parallel":
        a, b = objects
        if a in ctx.lines and b in ctx.lines:
            if not is_parallel(ctx.line_dir(a), ctx.line_dir(b)):
                fail()
        elif a in ctx.planes and b in ctx.planes:
            if not is_parallel(ctx.plane_normal(a), ctx.plane_normal(b)):
                fail()
        else:
            raise ValueError(f"unsupported parallel objects: {objects}")
    elif relation == "perpendicular":
        a, b = objects
        if a in ctx.lines and b in ctx.lines:
            if not is_perpendicular(ctx.line_dir(a), ctx.line_dir(b)):
                fail()
        elif a in ctx.lines and b in ctx.planes:
            if not is_parallel(ctx.line_dir(a), ctx.plane_normal(b)):
                fail()
        elif a in ctx.planes and b in ctx.planes:
            if not is_perpendicular(ctx.plane_normal(a), ctx.plane_normal(b)):
                fail()
        else:
            raise ValueError(f"unsupported perpendicular objects: {objects}")
    elif relation == "line_in_plane":
        line, plane = objects
        if not ctx.line_in_plane(line, plane):
            fail()
    elif relation == "line_not_in_plane":
        line, plane = objects
        if ctx.line_in_plane(line, plane):
            fail()
    elif relation == "point_in_plane":
        point, plane = objects
        if not ctx.point_in_plane(point, plane):
            fail()
    elif relation == "point_on_line":
        point, line = objects
        if not ctx.point_on_line(point, line):
            fail()
    elif relation == "point_not_on_line":
        point, line = objects
        if ctx.point_on_line(point, line):
            fail()
    elif relation == "intersect_at":
        a, b, point = objects
        if not ctx.point_on_line(point, a) or not ctx.point_on_line(point, b):
            fail()
    elif relation == "plane_intersection_line":
        alpha, beta, line = objects
        if (
            is_parallel(ctx.plane_normal(alpha), ctx.plane_normal(beta))
            or not ctx.line_in_plane(line, alpha)
            or not ctx.line_in_plane(line, beta)
        ):
            fail()
    elif relation in {
        "angle_between",
        "distance_between",
        "area_projection",
        "volume_height",
        "classification",
        "symbol_example",
        "non_collinear",
    }:
        # Semantic relation used for catalog/teaching; no numeric check needed.
        for obj in objects:
            if (
                obj not in ctx.points
                and obj not in ctx.lines
                and obj not in ctx.planes
                and obj not in ctx.polygons
            ):
                raise ValueError(f"{ctx.diagram['theorem_id']}: unknown object {obj}")
    else:
        raise ValueError(f"unsupported relation {relation}")


def plane_equation(ctx: DiagramContext, plane_name: str) -> tuple[list[float], float]:
    normal = ctx.plane_normal(plane_name)
    return normal, v_dot(normal, ctx.plane_points(plane_name)[0])


def solve_plane_intersection(
    ctx: DiagramContext, plane_a: str, plane_b: str
) -> tuple[list[float], list[float]]:
    n1, c1 = plane_equation(ctx, plane_a)
    n2, c2 = plane_equation(ctx, plane_b)
    direction = v_cross(n1, n2)
    if is_zero(direction):
        raise ValueError(f"{ctx.diagram['theorem_id']}: planes are parallel: {plane_a}, {plane_b}")

    axis_order = sorted(range(3), key=lambda index: abs(direction[index]), reverse=True)
    for fixed_axis in axis_order:
        i, j = [axis for axis in range(3) if axis != fixed_axis]
        det = n1[i] * n2[j] - n1[j] * n2[i]
        if abs(det) <= EPS:
            continue
        point = [0.0, 0.0, 0.0]
        point[fixed_axis] = 0.0
        point[i] = (c1 * n2[j] - c2 * n1[j]) / det
        point[j] = (n1[i] * c2 - n2[i] * c1) / det
        return point, unit(direction)
    raise ValueError(f"{ctx.diagram['theorem_id']}: cannot solve plane intersection")


def plane_basis(ctx: DiagramContext, plane_name: str) -> tuple[list[float], list[float], list[float]]:
    pts = ctx.plane_points(plane_name)
    origin = pts[0]
    u = None
    for candidate in pts[1:]:
        edge = v_sub(candidate, origin)
        if not is_zero(edge):
            u = unit(edge)
            break
    if u is None:
        raise ValueError(f"{ctx.diagram['theorem_id']}: plane {plane_name} has no basis edge")
    normal = unit(ctx.plane_normal(plane_name))
    v = unit(v_cross(normal, u))
    return origin, u, v


def project_plane_basis(
    point: list[float], origin: list[float], u: list[float], v: list[float]
) -> tuple[float, float]:
    rel = v_sub(point, origin)
    return v_dot(rel, u), v_dot(rel, v)


def line_polygon_interval(
    ctx: DiagramContext, plane_name: str, point: list[float], direction: list[float]
) -> tuple[float, float]:
    origin, u, v = plane_basis(ctx, plane_name)
    p2 = project_plane_basis(point, origin, u, v)
    d2 = (v_dot(direction, u), v_dot(direction, v))
    polygon = [project_plane_basis(p, origin, u, v) for p in ctx.plane_points(plane_name)]

    ts: list[float] = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        edge = (end[0] - start[0], end[1] - start[1])
        diff = (start[0] - p2[0], start[1] - p2[1])
        denom = cross2(d2, edge)
        if abs(denom) <= EPS:
            if abs(cross2(diff, d2)) <= EPS:
                for vertex in (start, end):
                    rel = (vertex[0] - p2[0], vertex[1] - p2[1])
                    denom_dir = d2[0] * d2[0] + d2[1] * d2[1]
                    if denom_dir > EPS:
                        ts.append((rel[0] * d2[0] + rel[1] * d2[1]) / denom_dir)
            continue
        t = cross2(diff, edge) / denom
        s = cross2(diff, d2) / denom
        if -EPS <= s <= 1 + EPS:
            ts.append(t)

    unique = sorted({round(t, 9) for t in ts})
    if len(unique) < 2:
        raise ValueError(
            f"{ctx.diagram['theorem_id']}: cannot clip intersection line to plane {plane_name}"
        )
    return unique[0], unique[-1]


def clipped_plane_intersection_segment(
    ctx: DiagramContext, plane_a: str, plane_b: str
) -> tuple[list[float], list[float]]:
    point, direction = solve_plane_intersection(ctx, plane_a, plane_b)
    a_min, a_max = line_polygon_interval(ctx, plane_a, point, direction)
    b_min, b_max = line_polygon_interval(ctx, plane_b, point, direction)
    t_min = max(a_min, b_min)
    t_max = min(a_max, b_max)
    if t_max - t_min <= EPS:
        center = v_mid(v_add(point, v_scale(direction, a_min)), v_add(point, v_scale(direction, a_max)))
        t_min, t_max = -0.8, 0.8
        point = center
    return v_add(point, v_scale(direction, t_min)), v_add(point, v_scale(direction, t_max))


def derive_plane_intersection_lines(ctx: DiagramContext) -> None:
    for cond in ctx.diagram.get("conditions", []):
        if cond.get("relation") != "plane_intersection_line":
            continue
        alpha, beta, line_name = cond.get("objects", [])
        start_point, end_point = clipped_plane_intersection_segment(ctx, alpha, beta)
        line = ctx.lines.get(line_name, {})
        through = line.get("through")
        if not through or len(through) != 2:
            through = [f"_{line_name}_intersection_1", f"_{line_name}_intersection_2"]
            line["through"] = through
            line.setdefault("style", "third")
            line.setdefault("label", {"at": through[1], "text": tex_label(line_name), "pos": "right"})
            ctx.lines[line_name] = line
        ctx.set_point(through[0], start_point)
        ctx.set_point(through[1], end_point)


def intersection_line_names(diagram: dict[str, Any]) -> set[str]:
    return {
        cond["objects"][2]
        for cond in diagram.get("conditions", [])
        if cond.get("relation") == "plane_intersection_line"
        and len(cond.get("objects", [])) == 3
    }


def render_node(ctx: DiagramContext, at: Any, text: str, pos: str = "") -> str:
    location = ctx.ref(at) if isinstance(at, str) else coord3([float(x) for x in at])
    suffix = f",{pos}" if pos else ""
    return f"  \\node[label{suffix}] at {location} {{{text}}};"


def oriented_line_unit(
    ctx: DiagramContext, line_name: str, origin: list[float], reverse: bool = False
) -> list[float]:
    p, q = ctx.line_points(line_name)
    candidates = [v_sub(p, origin), v_sub(q, origin)]
    direction = max(candidates, key=v_norm)
    if is_zero(direction):
        direction = ctx.line_dir(line_name)
    direction = unit(direction)
    if reverse:
        direction = v_scale(direction, -1)
    return direction


def render_right_angle(ctx: DiagramContext, mark: dict[str, Any]) -> list[str]:
    at = ctx.point(mark["at"])
    size = float(mark.get("size", 0.18))
    l1, l2 = mark["lines"]
    u1 = oriented_line_unit(ctx, l1, at, bool(mark.get("reverse1")))
    u2 = oriented_line_unit(ctx, l2, at, bool(mark.get("reverse2")))
    p0 = at
    p1 = v_add(p0, v_scale(u1, size))
    p2 = v_add(p1, v_scale(u2, size))
    p3 = v_add(p0, v_scale(u2, size))
    return [
        f"  \\draw[aux] {coord3(p1)} -- {coord3(p2)} -- {coord3(p3)};"
    ]


def render_arc(ctx: DiagramContext, mark: dict[str, Any]) -> list[str]:
    if "lines" not in mark:
        raise ValueError(f"{ctx.diagram['theorem_id']}: arc mark needs lines")
    center = ctx.point(mark["at"])
    radius = float(mark.get("radius", 0.34))
    steps = int(mark.get("steps", 10))
    l1, l2 = mark["lines"]
    u1 = oriented_line_unit(ctx, l1, center, bool(mark.get("reverse1")))
    u2 = oriented_line_unit(ctx, l2, center, bool(mark.get("reverse2")))
    pts: list[list[float]] = []
    for index in range(steps + 1):
        t = index / steps
        blended = v_add(v_scale(u1, 1 - t), v_scale(u2, t))
        if is_zero(blended):
            blended = u1
        pts.append(v_add(center, v_scale(unit(blended), radius)))
    return [
        "  \\draw[aux] " + " -- ".join(coord3(point) for point in pts) + ";"
    ]


def render_diagram(diagram: dict[str, Any]) -> str:
    ctx = DiagramContext(diagram)
    derive_plane_intersection_lines(ctx)
    for cond in diagram.get("conditions", []):
        validate_condition(ctx, cond)
    intersection_lines = intersection_line_names(diagram)

    view = diagram.get("view", {})
    theta = float(view.get("theta", 65))
    phi = float(view.get("phi", 115))
    out = [
        r"\input{fixed_theorem_diagrams/tikz/_fixed_diagram_styles.tex}",
        rf"\tdplotsetmaincoords{{{fmt(theta)}}}{{{fmt(phi)}}}",
        r"\begin{tikzpicture}[tdplot_main_coords,theorem diagram]",
    ]

    for name, point in ctx.points.items():
        out.append(f"  \\coordinate ({ctx.coord_names[name]}) at {coord3(point)};")

    plane_labels: list[str] = []
    for name, plane in ctx.planes.items():
        style = plane.get("style", "plane")
        path = " -- ".join(ctx.ref(p) for p in plane["polygon"])
        out.append(f"  \\draw[{style}] {path} -- cycle;")
        label = plane.get("label", {})
        if label is not False:
            plane_labels.append(render_node(ctx, label.get("at", plane["polygon"][-1]), label.get("text", tex_label(name)), label.get("pos", "")))
    out.extend(plane_labels)

    for name, polygon in ctx.polygons.items():
        style = polygon.get("style", "surface")
        path = " -- ".join(ctx.ref(p) for p in polygon["points"])
        out.append(f"  \\draw[{style}] {path} -- cycle;")
        label = polygon.get("label", {})
        if label is not False:
            out.append(render_node(ctx, label.get("at", polygon["points"][0]), label.get("text", tex_label(name)), label.get("pos", "")))

    line_items = sorted(ctx.lines.items(), key=lambda item: item[0] in intersection_lines)
    for name, line in line_items:
        if line.get("draw") is False:
            continue
        base_style = line.get("style", "main")
        style = f"{base_style},intersection line" if name in intersection_lines else base_style
        start, end = line["through"]
        out.append(f"  \\draw[{style}] {ctx.ref(start)} -- {ctx.ref(end)};")
        label = line.get("label", {})
        if label is not False:
            at = label.get("at", line["through"][1])
            out.append(render_node(ctx, at, label.get("text", tex_label(name)), label.get("pos", "")))

    for name, point in ctx.points.items():
        if name.startswith("_"):
            continue
        meta = diagram.get("point_labels", {}).get(name)
        if meta is False:
            continue
        if meta is None and name not in diagram.get("visible_points", []):
            continue
        meta = meta or {}
        out.append(f"  \\fill {ctx.ref(name)} circle (1.1pt);")
        out.append(render_node(ctx, name, meta.get("text", tex_label(name)), meta.get("pos", "above right")))

    for mark in diagram.get("marks", []):
        if mark["type"] == "right_angle":
            out.extend(render_right_angle(ctx, mark))
        elif mark["type"] == "arc":
            out.extend(render_arc(ctx, mark))
        elif mark["type"] == "label":
            out.append(render_node(ctx, mark["at"], mark["text"], mark.get("pos", "")))
        else:
            raise ValueError(f"unsupported mark type {mark['type']}")

    out.append(r"\end{tikzpicture}")
    return "\n".join(out) + "\n"


def build_catalog(data: dict[str, Any]) -> dict[str, Any]:
    diagrams = []
    for diagram in data["diagrams"]:
        labels = diagram.get("diagram_labels")
        if labels is None:
            labels = sorted(
                set(diagram.get("lines", {}))
                | set(diagram.get("planes", {}))
                | set(diagram.get("polygons", {}))
                | set(diagram.get("visible_points", []))
                | {
                    obj
                    for cond in diagram.get("conditions", [])
                    for obj in cond.get("objects", [])
                    if not obj.startswith("_")
                }
            )
        diagrams.append(
            {
                "theorem_id": diagram["theorem_id"],
                "title": diagram["title"],
                "tikz_path": diagram["tikz_path"],
                "spec_source": "fixed_theorem_diagrams/specs.yaml",
                "renderer": "tikz-3dplot",
                "condition_count": len(diagram.get("conditions", [])),
                "diagram_labels": labels,
            }
        )

    return {
        "version": "fixed-theorem-diagrams/v3",
        "scope": data.get("scope", "立体几何定理默写"),
        "source": "fixed_theorem_diagrams/specs.yaml",
        "usage": {
            "diagram_field": "diagram_col",
            "kind": "tikz",
            "width": "55mm",
            "variant": "prompt",
            "disclosure_policy": "clean",
            "path_base": "artifact_dir",
        },
        "rules": data.get("rules", []),
        "diagrams": diagrams,
    }


def write_preview(base: Path, data: dict[str, Any]) -> None:
    preview = base / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\documentclass[10pt]{article}",
        r"\usepackage[a4paper,margin=12mm]{geometry}",
        r"\usepackage{tikz}",
        r"\usepackage{tikz-3dplot}",
        r"\usepackage{multicol}",
        r"\pagestyle{empty}",
        r"\begin{document}",
        r"\begin{multicols}{3}",
    ]
    for diagram in data["diagrams"]:
        lines.extend(
            [
                r"\noindent\begin{minipage}{\linewidth}",
                rf"\noindent\texttt{{{diagram['theorem_id']}}}\\[1mm]",
                rf"\input{{{diagram['tikz_path']}}}",
                r"\par\vspace{5mm}",
                r"\end{minipage}\par",
            ]
        )
    lines.extend([r"\end{multicols}", r"\end{document}"])
    (preview / "fixed-diagram-index.tex").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args()

    base = args.base
    spec_path = args.spec or base / "specs.yaml"
    data = yaml.safe_load(spec_path.read_text())

    tikz_dir = base / "tikz"
    tikz_dir.mkdir(parents=True, exist_ok=True)
    (tikz_dir / "_fixed_diagram_styles.tex").write_text(
        "\\tikzset{\n"
        "  theorem diagram/.style={line cap=round,line join=round},\n"
        "  plane/.style={draw=black!60,fill=black!5,fill opacity=0.55,line width=0.65pt},\n"
        "  planeB/.style={draw=black!65,fill=black!9,fill opacity=0.45,line width=0.65pt},\n"
        "  planeC/.style={draw=black!55,fill=black!12,fill opacity=0.38,line width=0.65pt},\n"
        "  intersection line/.style={draw=black,line width=1.45pt},\n"
        "  main/.style={draw=black,line width=1.1pt},\n"
        "  second/.style={draw=black!78,line width=1.05pt},\n"
        "  third/.style={draw=black!70,line width=1.05pt},\n"
        "  aux/.style={draw=black!65,line width=0.85pt,densely dashed},\n"
        "  ghost/.style={draw=black!45,line width=0.65pt,dashed},\n"
        "  surface/.style={draw=black!82,fill=black!4,fill opacity=0.45,line width=0.95pt},\n"
        "  surfaceB/.style={draw=black!76,fill=black!7,fill opacity=0.4,line width=0.95pt},\n"
        "  projectionSurface/.style={draw=black!55,fill=black!3,fill opacity=0.22,line width=0.8pt,dashed},\n"
        "  point/.style={circle,fill=black,inner sep=1.15pt},\n"
        "  label/.style={font=\\scriptsize,inner sep=1pt},\n"
        "  tiny label/.style={font=\\tiny,inner sep=0.8pt}\n"
        "}\n"
    )

    for diagram in data["diagrams"]:
        rendered = render_diagram(diagram)
        target = base.parent / diagram["tikz_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered)

    catalog = build_catalog(data)
    (base / "catalog.yaml").write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False)
    )
    if not args.no_preview:
        write_preview(base, data)

    print(f"rendered={len(data['diagrams'])}")


if __name__ == "__main__":
    main()
