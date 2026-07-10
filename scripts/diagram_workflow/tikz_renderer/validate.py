from __future__ import annotations

from diagram_contracts import DiagramKind, GeometryRenderSpec


def validate_render_spec(spec: GeometryRenderSpec) -> list[str]:
    errors: list[str] = []
    if spec.type in {DiagramKind.COORDINATE_GEOMETRY.value, DiagramKind.FUNCTION_GRAPH.value}:
        if spec.viewport is None:
            errors.append("analytic spec requires viewport")
        for func in spec.functions:
            if func.id not in spec.samples:
                errors.append(f"function '{func.id}' has no samples")
            elif len(spec.samples.get(func.id) or []) < 2:
                errors.append(f"function '{func.id}' requires at least two samples")
        return errors
    if spec.type == DiagramKind.SPATIAL_GEOMETRY.value:
        if not spec.points3d:
            errors.append("spatial geometry spec requires points3d")
        if spec.projection is None:
            errors.append("spatial geometry spec requires projection")
        return errors
    if not spec.points:
        errors.append("synthetic geometry spec requires points")
    return errors
