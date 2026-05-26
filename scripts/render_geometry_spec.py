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
import shutil
import subprocess
from pathlib import Path
from typing import Any

Point = tuple[float, float]


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def svg_attrs(**kwargs: Any) -> str:
    parts: list[str] = []
    for key, value in kwargs.items():
        if value is None:
            continue
        parts.append(f'{key.replace("_", "-")}="{html.escape(str(value), quote=True)}"')
    return " ".join(parts)


class SvgGeometryRenderer:
    def __init__(self, spec: dict[str, Any], width: int, height: int, padding: int = 64):
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

    def draw_right_angle(self, marker: dict[str, Any]) -> None:
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

    def draw_equal_ticks(self, marker: dict[str, Any]) -> None:
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

    def draw_angle_arc(self, marker: dict[str, Any]) -> None:
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


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
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
) -> dict[str, Any]:
    spec = read_json(spec_path)
    diagram_variant = variant or spec.get("diagram_variant") or spec.get("variant") or "prompt"
    if diagram_variant not in {"prompt", "solution"}:
        diagram_variant = "prompt"
    result_path = out_dir / "renderer_result.json"
    svg_path = out_dir / "rendered" / f"{diagram_variant}.svg"
    png_path = out_dir / "rendered" / f"{diagram_variant}.png"

    errors = validate_spec(spec)
    if errors:
        result = {
            "schema_version": "geometry-renderer-result/v1",
            "status": "failed",
            "fail_type": "invalid_renderer_spec",
            "message": "; ".join(errors),
            "renderer_spec": relpath(spec_path, out_dir),
            "image_path": "",
            "preview_svg": "",
            "checks": {"references_valid": False, "image_exists": False},
        }
        write_json(result_path, result)
        return result

    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(SvgGeometryRenderer(spec, width=width, height=height).render(), encoding="utf-8")
    converted, message = convert_svg_to_png(svg_path, png_path, width=width, height=height, size=size)
    image_exists = png_path.exists() and png_path.stat().st_size > 0
    legacy_png_path = out_dir / "rendered" / "diagram.png"
    legacy_svg_path = out_dir / "rendered" / "diagram.svg"
    legacy_image_path = ""
    if image_exists and diagram_variant == "prompt":
        if png_path != legacy_png_path:
            shutil.copyfile(png_path, legacy_png_path)
        if svg_path != legacy_svg_path:
            shutil.copyfile(svg_path, legacy_svg_path)
        legacy_image_path = relpath(legacy_png_path, out_dir)
    status = "ok" if converted and image_exists else "failed"
    result = {
        "schema_version": "geometry-renderer-result/v1",
        "status": status,
        "fail_type": "" if status == "ok" else "png_export_failed",
        "message": message,
        "renderer": "teaching-svg-geometry-renderer",
        "diagram_variant": diagram_variant,
        "disclosure_policy": "clean" if diagram_variant == "prompt" else "annotated",
        "renderer_spec": relpath(spec_path, out_dir),
        "image_path": relpath(png_path, out_dir) if image_exists else "",
        "legacy_image_path": legacy_image_path,
        "preview_svg": relpath(svg_path, out_dir),
        "checks": {
            "references_valid": True,
            "svg_exists": svg_path.exists(),
            "image_exists": image_exists,
        },
    }
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
