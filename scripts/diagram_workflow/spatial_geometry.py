"""Deterministic 3D geometry checks and print-projection audits."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from diagram_contracts import SpatialProjectionMode, SpatialProjectionSpec


EPS = 1e-7
Point3D = tuple[float, float, float]
Point2D = tuple[float, float]


def add(a: Point3D, b: Point3D) -> Point3D:
    return tuple(a[i] + b[i] for i in range(3))  # type: ignore[return-value]


def sub(a: Point3D, b: Point3D) -> Point3D:
    return tuple(a[i] - b[i] for i in range(3))  # type: ignore[return-value]


def scale(a: Point3D, value: float) -> Point3D:
    return tuple(value * a[i] for i in range(3))  # type: ignore[return-value]


def dot(a: Point3D, b: Point3D) -> float:
    return sum(a[i] * b[i] for i in range(3))


def cross(a: Point3D, b: Point3D) -> Point3D:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Point3D) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Point3D) -> Point3D:
    length = norm(a)
    if length <= EPS:
        raise ValueError("zero vector cannot be normalized")
    return scale(a, 1 / length)


def parallel(a: Point3D, b: Point3D) -> bool:
    return norm(cross(a, b)) <= EPS * max(1.0, norm(a) * norm(b))


def perpendicular(a: Point3D, b: Point3D) -> bool:
    return abs(dot(a, b)) <= EPS * max(1.0, norm(a) * norm(b))


def cross2(a: Point2D, b: Point2D) -> float:
    return a[0] * b[1] - a[1] * b[0]


def point3d(value: object, *, name: str) -> Point3D:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"points3d.{name} must be [x, y, z]")
    try:
        return float(value[0]), float(value[1]), float(value[2])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"points3d.{name} must contain numeric coordinates") from exc


def normalize_segments(raw: object) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index, item in enumerate(raw or []):
        if isinstance(item, dict):
            segment = dict(item)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            segment = {"from": str(item[0]), "to": str(item[1])}
        else:
            raise ValueError(f"invalid spatial segment: {item!r}")
        start = str(segment.get("from") or segment.get("start") or "")
        end = str(segment.get("to") or segment.get("end") or "")
        if not start or not end:
            raise ValueError(f"spatial segment {index} requires from/to")
        segment["from"] = start
        segment["to"] = end
        segment.setdefault("id", f"{start}{end}")
        segments.append(segment)
    return segments


def normalize_polygons(raw: object) -> list[dict[str, Any]]:
    polygons: list[dict[str, Any]] = []
    for index, item in enumerate(raw or []):
        if isinstance(item, dict):
            polygon = dict(item)
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            polygon = {"points": [str(name) for name in item]}
        else:
            raise ValueError(f"invalid spatial polygon: {item!r}")
        names = [str(name) for name in polygon.get("points") or []]
        if len(names) < 3:
            raise ValueError(f"spatial polygon {index} requires at least three points")
        polygon["points"] = names
        polygon.setdefault("id", f"plane{index + 1}")
        polygons.append(polygon)
    return polygons


@dataclass
class SpatialScene:
    points: dict[str, Point3D]
    segments: list[dict[str, Any]]
    polygons: list[dict[str, Any]]

    @property
    def segment_map(self) -> dict[str, dict[str, Any]]:
        return {str(item["id"]): item for item in self.segments}

    @property
    def polygon_map(self) -> dict[str, dict[str, Any]]:
        return {str(item["id"]): item for item in self.polygons}

    def segment_points(self, name: str) -> tuple[Point3D, Point3D]:
        segment = self.segment_map.get(name)
        if segment is None:
            raise ValueError(f"unknown segment {name}")
        return self.points[str(segment["from"])], self.points[str(segment["to"])]

    def segment_direction(self, name: str) -> Point3D:
        start, end = self.segment_points(name)
        return sub(end, start)

    def plane_points(self, name: str) -> list[Point3D]:
        polygon = self.polygon_map.get(name)
        if polygon is None:
            raise ValueError(f"unknown plane {name}")
        return [self.points[str(point)] for point in polygon["points"]]

    def plane_normal(self, name: str) -> Point3D:
        points = self.plane_points(name)
        base = points[0]
        for index in range(1, len(points) - 1):
            candidate = cross(sub(points[index], base), sub(points[index + 1], base))
            if norm(candidate) > EPS:
                return candidate
        raise ValueError(f"plane {name} is degenerate")

    def point_in_plane(self, point_name: str, plane_name: str) -> bool:
        point = self.points[point_name]
        base = self.plane_points(plane_name)[0]
        normal = self.plane_normal(plane_name)
        return abs(dot(sub(point, base), normal)) <= EPS * max(1.0, norm(normal))

    def point_on_line(self, point_name: str, segment_name: str) -> bool:
        point = self.points[point_name]
        start, end = self.segment_points(segment_name)
        return parallel(sub(point, start), sub(end, start))

    def segment_in_plane(self, segment_name: str, plane_name: str) -> bool:
        segment = self.segment_map[segment_name]
        return all(self.point_in_plane(str(segment[key]), plane_name) for key in ("from", "to"))


def _plane_equation(scene: SpatialScene, name: str) -> tuple[Point3D, float]:
    normal = scene.plane_normal(name)
    return normal, dot(normal, scene.plane_points(name)[0])


def solve_plane_intersection(scene: SpatialScene, plane_a: str, plane_b: str) -> tuple[Point3D, Point3D]:
    n1, c1 = _plane_equation(scene, plane_a)
    n2, c2 = _plane_equation(scene, plane_b)
    direction = cross(n1, n2)
    if norm(direction) <= EPS:
        raise ValueError(f"planes are parallel: {plane_a}, {plane_b}")
    for fixed_axis in sorted(range(3), key=lambda axis: abs(direction[axis]), reverse=True):
        i, j = [axis for axis in range(3) if axis != fixed_axis]
        determinant = n1[i] * n2[j] - n1[j] * n2[i]
        if abs(determinant) <= EPS:
            continue
        point = [0.0, 0.0, 0.0]
        point[i] = (c1 * n2[j] - c2 * n1[j]) / determinant
        point[j] = (n1[i] * c2 - n2[i] * c1) / determinant
        return (point[0], point[1], point[2]), unit(direction)
    raise ValueError(f"cannot solve plane intersection: {plane_a}, {plane_b}")


def _plane_basis(scene: SpatialScene, name: str) -> tuple[Point3D, Point3D, Point3D]:
    points = scene.plane_points(name)
    origin = points[0]
    edge = next((sub(point, origin) for point in points[1:] if norm(sub(point, origin)) > EPS), None)
    if edge is None:
        raise ValueError(f"plane {name} has no basis edge")
    u = unit(edge)
    v = unit(cross(unit(scene.plane_normal(name)), u))
    return origin, u, v


def _basis_point(point: Point3D, origin: Point3D, u: Point3D, v: Point3D) -> Point2D:
    relative = sub(point, origin)
    return dot(relative, u), dot(relative, v)


def _line_polygon_interval(
    scene: SpatialScene,
    plane_name: str,
    point: Point3D,
    direction: Point3D,
) -> tuple[float, float]:
    origin, u, v = _plane_basis(scene, plane_name)
    p2 = _basis_point(point, origin, u, v)
    d2 = dot(direction, u), dot(direction, v)
    polygon = [_basis_point(item, origin, u, v) for item in scene.plane_points(plane_name)]
    values: list[float] = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        edge = end[0] - start[0], end[1] - start[1]
        difference = start[0] - p2[0], start[1] - p2[1]
        denominator = cross2(d2, edge)
        if abs(denominator) <= EPS:
            if abs(cross2(difference, d2)) <= EPS:
                direction_length = d2[0] * d2[0] + d2[1] * d2[1]
                if direction_length > EPS:
                    for vertex in (start, end):
                        relative = vertex[0] - p2[0], vertex[1] - p2[1]
                        values.append(
                            (relative[0] * d2[0] + relative[1] * d2[1])
                            / direction_length
                        )
            continue
        t = cross2(difference, edge) / denominator
        side = cross2(difference, d2) / denominator
        if -EPS <= side <= 1 + EPS:
            values.append(t)
    values = sorted({round(value, 9) for value in values})
    if len(values) < 2:
        raise ValueError(f"cannot clip intersection line to plane {plane_name}")
    return values[0], values[-1]


def derive_plane_intersections(scene: SpatialScene, raw: object) -> None:
    for index, item in enumerate(raw or []):
        if not isinstance(item, dict) or item.get("relation") != "plane_intersection_line":
            raise ValueError(f"invalid derived_segments[{index}]")
        planes = [str(name) for name in item.get("planes") or []]
        if len(planes) != 2:
            raise ValueError("plane_intersection_line requires two planes")
        point, direction = solve_plane_intersection(scene, planes[0], planes[1])
        first = _line_polygon_interval(scene, planes[0], point, direction)
        second = _line_polygon_interval(scene, planes[1], point, direction)
        low, high = max(first[0], second[0]), min(first[1], second[1])
        if high - low <= EPS:
            raise ValueError(f"planes {planes[0]}, {planes[1]} have no visible common segment")
        segment_id = str(item.get("id") or f"intersection{index + 1}")
        start_name = str(item.get("from") or f"_{segment_id}_1")
        end_name = str(item.get("to") or f"_{segment_id}_2")
        scene.points[start_name] = add(point, scale(direction, low))
        scene.points[end_name] = add(point, scale(direction, high))
        segment = dict(item)
        segment.update({"id": segment_id, "from": start_name, "to": end_name})
        segment.pop("relation", None)
        segment.pop("planes", None)
        segment.setdefault("role", "intersection")
        scene.segments.append(segment)


def validate_relations(scene: SpatialScene, raw: object) -> None:
    for index, relation_spec in enumerate(raw or []):
        if not isinstance(relation_spec, dict):
            raise ValueError(f"relations[{index}] must be an object")
        relation = str(relation_spec.get("relation") or "")
        objects = [str(item) for item in relation_spec.get("objects") or []]
        passed = True
        if relation == "parallel":
            a, b = objects
            if a in scene.segment_map and b in scene.segment_map:
                passed = parallel(scene.segment_direction(a), scene.segment_direction(b))
            elif a in scene.polygon_map and b in scene.polygon_map:
                passed = parallel(scene.plane_normal(a), scene.plane_normal(b))
            else:
                raise ValueError(f"parallel requires two lines or two planes: {objects}")
        elif relation == "perpendicular":
            a, b = objects
            if a in scene.segment_map and b in scene.segment_map:
                passed = perpendicular(scene.segment_direction(a), scene.segment_direction(b))
            elif a in scene.segment_map and b in scene.polygon_map:
                passed = parallel(scene.segment_direction(a), scene.plane_normal(b))
            elif a in scene.polygon_map and b in scene.polygon_map:
                passed = perpendicular(scene.plane_normal(a), scene.plane_normal(b))
            else:
                raise ValueError(f"unsupported perpendicular objects: {objects}")
        elif relation == "point_on_line":
            passed = scene.point_on_line(objects[0], objects[1])
        elif relation == "point_in_plane":
            passed = scene.point_in_plane(objects[0], objects[1])
        elif relation in {"line_in_plane", "segment_in_plane"}:
            passed = scene.segment_in_plane(objects[0], objects[1])
        elif relation == "plane_intersection_line":
            plane_a, plane_b, line = objects
            passed = (
                not parallel(scene.plane_normal(plane_a), scene.plane_normal(plane_b))
                and scene.segment_in_plane(line, plane_a)
                and scene.segment_in_plane(line, plane_b)
            )
        elif relation == "non_collinear":
            a, b, c = (scene.points[name] for name in objects)
            passed = norm(cross(sub(b, a), sub(c, a))) > EPS
        elif relation in {"angle_between", "distance_between", "area_projection", "volume_height"}:
            known = set(scene.points) | set(scene.segment_map) | set(scene.polygon_map)
            passed = all(name in known for name in objects)
        else:
            raise ValueError(f"unsupported spatial relation: {relation}")
        if not passed:
            raise ValueError(f"spatial relation failed: {relation}({', '.join(objects)})")


def project_point(point: Point3D, projection: SpatialProjectionSpec) -> Point2D:
    x, y, z = point
    if projection.mode in {SpatialProjectionMode.TEXTBOOK_OBLIQUE, SpatialProjectionMode.AXIAL_SOLID}:
        angle = math.radians(projection.depth_angle_deg)
        direction = -1 if projection.flip_depth else 1
        return (
            x + direction * projection.depth_scale * math.cos(angle) * y,
            projection.vertical_scale * z + projection.depth_scale * math.sin(angle) * y,
        )
    theta = math.radians(projection.theta)
    phi = math.radians(projection.phi)
    return (
        math.cos(phi) * x + math.sin(phi) * y,
        -math.cos(theta) * math.sin(phi) * x
        + math.cos(theta) * math.cos(phi) * y
        + math.sin(theta) * z,
    )


def _polygon_opening(points: list[Point2D]) -> float:
    area = abs(sum(cross2(points[index], points[(index + 1) % len(points)]) for index in range(len(points)))) / 2
    longest = max(
        math.dist(points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )
    return area / max(longest * longest, EPS)


def _angle(vertex: Point2D, first: Point2D, second: Point2D) -> float:
    u = first[0] - vertex[0], first[1] - vertex[1]
    v = second[0] - vertex[0], second[1] - vertex[1]
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator <= EPS:
        return 0.0
    cosine = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / denominator))
    value = math.degrees(math.acos(cosine))
    return min(value, 180 - value)


def projection_diagnostics(
    scene: SpatialScene,
    projection: SpatialProjectionSpec,
    quality_focus: object = None,
) -> dict[str, Any]:
    projected = {name: project_point(point, projection) for name, point in scene.points.items()}
    focus = quality_focus if isinstance(quality_focus, dict) else {}
    requested_planes = [str(name) for name in focus.get("base_planes") or []]
    if not requested_planes and scene.polygons:
        requested_planes = [str(scene.polygons[0]["id"])]
    plane_openings = {
        name: round(_polygon_opening([projected[point] for point in scene.polygon_map[name]["points"]]), 5)
        for name in requested_planes
        if name in scene.polygon_map
    }
    angle_values: dict[str, float] = {}
    for index, item in enumerate(focus.get("angle_checks") or []):
        if not isinstance(item, dict):
            continue
        vertex = str(item.get("vertex") or "")
        arms = [str(name) for name in item.get("arms") or []]
        if vertex in projected and len(arms) == 2 and all(name in projected for name in arms):
            angle_values[str(item.get("id") or f"angle{index + 1}")] = round(
                _angle(projected[vertex], projected[arms[0]], projected[arms[1]]),
                3,
            )
    minimum_opening = min(plane_openings.values(), default=1.0)
    minimum_angle = min(angle_values.values(), default=90.0)
    warnings: list[str] = []
    if minimum_opening < projection.min_plane_opening:
        warnings.append(
            f"base plane opening {minimum_opening:.3f} is below {projection.min_plane_opening:.3f}"
        )
    if minimum_angle < projection.min_core_angle_deg:
        warnings.append(
            f"core projected angle {minimum_angle:.1f} is below {projection.min_core_angle_deg:.1f} degrees"
        )
    return {
        "projection_mode": projection.mode.value,
        "plane_openings": plane_openings,
        "min_plane_opening": round(minimum_opening, 5),
        "core_angles_deg": angle_values,
        "min_core_angle_deg": round(minimum_angle, 3),
        "warnings": warnings,
    }
