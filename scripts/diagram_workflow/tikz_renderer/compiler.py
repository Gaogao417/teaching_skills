from __future__ import annotations

from diagram_contracts import DiagramKind, GeometryRenderSpec

from .contracts import TikzDiagramSpec
from .coordinate_to_tikz import compile_coordinate_geometry
from .geometry_to_tikz import compile_synthetic_geometry
from .spatial_to_tikz import compile_spatial_geometry


def compile_geometry_render_spec(spec: GeometryRenderSpec) -> TikzDiagramSpec:
    if spec.type in {DiagramKind.COORDINATE_GEOMETRY.value, DiagramKind.FUNCTION_GRAPH.value}:
        return compile_coordinate_geometry(spec)
    if spec.type == DiagramKind.SPATIAL_GEOMETRY.value:
        return compile_spatial_geometry(spec)
    return compile_synthetic_geometry(spec)
