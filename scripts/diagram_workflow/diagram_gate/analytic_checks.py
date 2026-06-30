from __future__ import annotations

import json
from pathlib import Path

from diagram_contracts import (
    DiagramGateCheck,
    DiagramKind,
    DiagramJobsManifest,
    RendererBindingManifest,
)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _check_analytic_renderer_specs(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Coordinate/function jobs must produce a renderable GeometryRenderSpec."""
    checks: list[DiagramGateCheck] = []
    analytic_kinds = {DiagramKind.COORDINATE_GEOMETRY, DiagramKind.FUNCTION_GRAPH}
    for job in jobs.jobs:
        if job.diagram_kind not in analytic_kinds:
            continue
        art = artifacts.bindings.get(job.diagram_ref)
        if not art or not art.final_renderer_spec:
            checks.append(DiagramGateCheck(
                name="analytic_renderer_spec",
                status="block" if job.required else "warn",
                message=f"Analytic job '{job.job_id}' has no final_renderer_spec",
                refs=[job.slot_id],
            ))
            continue

        spec_path = Path(art.final_renderer_spec)
        if not spec_path.is_absolute():
            spec_path = artifact_dir / spec_path
        spec = _read_json(spec_path)
        if spec is None:
            checks.append(DiagramGateCheck(
                name="analytic_renderer_spec",
                status="block" if job.required else "warn",
                message=f"Analytic renderer spec is missing or invalid JSON: {art.final_renderer_spec}",
                refs=[job.slot_id],
            ))
            continue

        errors = _analytic_spec_errors(spec)
        if errors:
            checks.append(DiagramGateCheck(
                name="analytic_renderer_spec",
                status="block" if job.required else "warn",
                message="; ".join(errors),
                refs=[job.slot_id],
            ))
    return checks


def _analytic_spec_errors(spec: dict[str, object]) -> list[str]:
    errors: list[str] = []
    viewport = spec.get("viewport")
    if not isinstance(viewport, dict):
        errors.append("analytic spec requires viewport")
    else:
        for low, high in (("x_min", "x_max"), ("y_min", "y_max")):
            if low not in viewport or high not in viewport:
                errors.append(f"viewport requires {low} and {high}")
                continue
            try:
                if float(viewport[low]) >= float(viewport[high]):
                    errors.append(f"viewport {low} must be < {high}")
            except (TypeError, ValueError):
                errors.append(f"viewport {low}/{high} must be numeric")

    has_payload = bool(spec.get("points") or spec.get("objects") or spec.get("functions") or spec.get("curves") or spec.get("samples"))
    if not has_payload:
        errors.append("analytic spec requires points, objects, functions, curves, or samples")

    samples = spec.get("samples") if isinstance(spec.get("samples"), dict) else {}
    for func in spec.get("functions") or []:
        if not isinstance(func, dict):
            errors.append("function entry must be an object")
            continue
        fid = str(func.get("id", ""))
        if not fid:
            errors.append("function requires id")
        elif not samples.get(fid):
            errors.append(f"function '{fid}' has no samples")

    for index, obj in enumerate(spec.get("objects") or []):
        if not isinstance(obj, dict):
            errors.append(f"objects[{index}] must be an object")
            continue
        kind = obj.get("type")
        if kind == "point" and not {"x", "y"} <= set(obj):
            errors.append(f"objects[{index}] point requires x and y")
        elif kind == "line" and not (obj.get("equation") or {"slope", "intercept"} <= set(obj)):
            errors.append(f"objects[{index}] line requires equation or slope/intercept")
        elif kind == "circle":
            if "radius" not in obj:
                errors.append(f"objects[{index}] circle requires radius")
            else:
                try:
                    if float(obj["radius"]) <= 0:
                        errors.append(f"objects[{index}] circle radius must be positive")
                except (TypeError, ValueError):
                    errors.append(f"objects[{index}] circle radius must be numeric")
        elif kind == "polyline" and len(obj.get("points") or []) < 2:
            errors.append(f"objects[{index}] polyline requires at least two points")
        elif kind == "polygon" and len(obj.get("points") or []) < 3:
            errors.append(f"objects[{index}] polygon requires at least three points")
    return errors
