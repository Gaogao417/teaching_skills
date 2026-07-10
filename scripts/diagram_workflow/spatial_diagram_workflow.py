#!/usr/bin/env python3
"""Build auditable 3D renderer specs for high-school solid geometry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import (  # noqa: E402
    DiagramJobRequest,
    DiagramJobResult,
    GeometryRenderSpec,
    SpatialProjectionSpec,
)
from spatial_geometry import (  # noqa: E402
    SpatialScene,
    derive_plane_intersections,
    normalize_polygons,
    normalize_segments,
    point3d,
    projection_diagnostics,
    validate_relations,
)
from workflow_timing import StageTimer, write_profile_section  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _base_spatial_spec(out_dir: Path, reuse_job_id: str) -> dict[str, Any]:
    if not reuse_job_id:
        return {}
    base_spec_path = out_dir.parent / reuse_job_id / "final_renderer_spec.json"
    if not base_spec_path.exists():
        return {}
    base_spec = read_json(base_spec_path)
    source = base_spec.get("source")
    if not isinstance(source, dict):
        return {}
    spatial_spec = source.get("spatial_spec")
    return dict(spatial_spec) if isinstance(spatial_spec, dict) else {}


def _merge_spatial_spec(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(override)
    merged = dict(base)
    points = dict(base.get("points3d") or {})
    points.update(override.get("points3d") or {})
    merged["points3d"] = points
    for key in (
        "segments",
        "polygons",
        "markers",
        "relations",
        "derived_segments",
        "teaching_focus",
        "constraints",
    ):
        if key in override:
            merged[key] = list(base.get(key) or []) + list(override.get(key) or [])
    labels = dict(base.get("labels") or {})
    labels.update(override.get("labels") or {})
    if labels:
        merged["labels"] = labels
    for key, value in override.items():
        if key not in {
            "points3d",
            "segments",
            "polygons",
            "markers",
            "labels",
            "relations",
            "derived_segments",
            "teaching_focus",
            "constraints",
        }:
            merged[key] = value
    return merged


def _labels(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _projection(raw: object) -> SpatialProjectionSpec:
    if isinstance(raw, str):
        raw = {"mode": raw}
    return SpatialProjectionSpec.model_validate(raw or {})


def build_spatial_render_spec(
    request: DiagramJobRequest,
    out_dir: Path,
    timer: StageTimer | None = None,
) -> GeometryRenderSpec:
    timer = timer or StageTimer()
    with timer.measure("load_and_merge_spatial_spec"):
        raw_spec = dict(request.engine_options.spatial_spec or {})
        base_spec = _base_spatial_spec(out_dir, request.reuse.reuse_geometry_from)
        spatial_spec = _merge_spatial_spec(base_spec, raw_spec)

    with timer.measure("normalize_spatial_objects"):
        raw_points = spatial_spec.get("points3d")
        if not isinstance(raw_points, dict) or not raw_points:
            raise ValueError("spatial_spec.points3d must be a non-empty mapping")
        points = {str(name): point3d(value, name=str(name)) for name, value in raw_points.items()}
        segments = normalize_segments(spatial_spec.get("segments"))
        polygons = normalize_polygons(spatial_spec.get("polygons"))
    scene = SpatialScene(points=points, segments=segments, polygons=polygons)
    with timer.measure("derive_plane_intersections"):
        derive_plane_intersections(scene, spatial_spec.get("derived_segments"))
    with timer.measure("validate_spatial_relations"):
        validate_relations(scene, spatial_spec.get("relations"))

    with timer.measure("projection_readability_diagnostics"):
        projection = _projection(spatial_spec.get("projection"))
        diagnostics = projection_diagnostics(scene, projection, spatial_spec.get("quality_focus"))
    with timer.measure("normalize_spatial_payload"):
        labels = _labels(spatial_spec.get("labels"))

    normalized_spatial_spec = dict(spatial_spec)
    normalized_spatial_spec.update(
        {
            "points3d": {name: list(point) for name, point in scene.points.items()},
            "segments": scene.segments,
            "polygons": scene.polygons,
            "projection": projection.model_dump(mode="json"),
        }
    )
    payload = {
        "schema_version": "geometry-render-spec/v1",
        "job_id": request.job_id,
        "variant": request.variant.value,
        "disclosure_policy": request.disclosure_policy.value,
        "type": request.diagram_kind.value,
        "render_profile": request.render_profile.model_dump(mode="json"),
        "points3d": {name: list(point) for name, point in scene.points.items()},
        "projection": projection.model_dump(mode="json"),
        "segments": scene.segments,
        "polygons": scene.polygons,
        "markers": list(spatial_spec.get("markers") or []),
        "labels": labels,
        "teaching_focus": list(spatial_spec.get("teaching_focus") or []),
        "constraints": list(spatial_spec.get("constraints") or []),
        "source": {
            "coordinates": "3d",
            "projection_backend": (
                "tikz_coordinate_basis"
                if projection.mode.value in {"textbook_oblique", "axial_solid"}
                else "tikz-3dplot"
            ),
            "spatial_spec": normalized_spatial_spec,
        },
        "diagnostics": {"spatial_projection": diagnostics},
    }
    with timer.measure("validate_final_renderer_spec"):
        return GeometryRenderSpec.model_validate(payload)


def run_spatial_workflow(request_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timer = StageTimer()
    with timer.measure("read_request"):
        request_data = read_json(request_path)
    with timer.measure("validate_request"):
        request_model = DiagramJobRequest.model_validate(request_data)
    with timer.measure("write_normalized_request"):
        write_json(out_dir / "request.json", request_model.model_dump(mode="json", by_alias=True))
    try:
        spec = build_spatial_render_spec(request_model, out_dir, timer)
        with timer.measure("write_final_renderer_spec"):
            write_json(out_dir / "final_renderer_spec.json", spec.model_dump(mode="json", by_alias=True))
        result = DiagramJobResult.model_validate(
            {
                "schema_version": "diagram-job-result/v2",
                "job_id": request_model.job_id,
                "status": "ok",
                "fail_type": "",
                "message": "",
                "request": "request.json",
                "workflow_events": "",
                "scene_payload": "",
                "final_renderer_spec": "final_renderer_spec.json",
                "wolfram": {"success": False},
                "model": {"text_model_used": "", "attempts": []},
                "policy_warnings": [],
            }
        ).model_dump(mode="json", by_alias=True)
    except Exception as exc:
        result = DiagramJobResult.model_validate(
            {
                "schema_version": "diagram-job-result/v2",
                "job_id": request_model.job_id,
                "status": "failed",
                "fail_type": "spatial_renderer_failed",
                "message": str(exc),
                "request": "request.json",
                "workflow_events": "",
                "scene_payload": "",
                "final_renderer_spec": "final_renderer_spec.json",
                "wolfram": {"success": False},
                "model": {"text_model_used": "", "attempts": []},
                "policy_warnings": [],
            }
        ).model_dump(mode="json", by_alias=True)
    with timer.measure("write_workflow_result"):
        write_json(out_dir / "workflow_result.json", result)
    write_profile_section(
        out_dir,
        "workflow",
        timer,
        job_id=request_model.job_id,
        route="spatial_renderer",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 3D spatial geometry renderer specs")
    parser.add_argument("request", type=Path, help="Path to DiagramJobRequest v2 JSON")
    parser.add_argument("--out", type=Path, required=True, help="Output job directory")
    args = parser.parse_args()
    result = run_spatial_workflow(args.request.resolve(), args.out.resolve())
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
