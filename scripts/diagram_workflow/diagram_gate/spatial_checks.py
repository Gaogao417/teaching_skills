from __future__ import annotations

import json
from pathlib import Path

from diagram_contracts import (
    DiagramGateCheck,
    DiagramJobsManifest,
    DiagramKind,
    DiagramVariant,
    RendererBindingManifest,
)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _resolve(artifact_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else artifact_dir / path


def _check_spatial_renderer_specs(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    checks: list[DiagramGateCheck] = []
    for job in jobs.jobs:
        if job.diagram_kind != DiagramKind.SPATIAL_GEOMETRY:
            continue
        binding = artifacts.bindings.get(job.diagram_ref)
        if binding is None or not binding.final_renderer_spec:
            continue
        spec = _read_json(_resolve(artifact_dir, binding.final_renderer_spec))
        if spec is None:
            checks.append(DiagramGateCheck(
                name="spatial_renderer_spec",
                status="block" if job.required else "warn",
                message="Spatial renderer spec is missing or invalid JSON",
                refs=[job.slot_id],
            ))
            continue
        source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
        if spec.get("type") != DiagramKind.SPATIAL_GEOMETRY.value or not spec.get("points3d"):
            checks.append(DiagramGateCheck(
                name="spatial_3d_source",
                status="block" if job.required else "warn",
                message="Spatial diagram must preserve points3d through the final renderer spec",
                refs=[job.slot_id],
            ))
        if spec.get("points"):
            checks.append(DiagramGateCheck(
                name="spatial_no_flattened_points",
                status="block",
                message="Spatial diagram contains pre-projected 2D points; projection must remain in the TikZ compiler",
                refs=[job.slot_id],
            ))
        if source.get("projection_backend") not in {"tikz_coordinate_basis", "tikz-3dplot"}:
            checks.append(DiagramGateCheck(
                name="spatial_projection_backend",
                status="block" if job.required else "warn",
                message="Spatial diagram has no approved TikZ projection backend",
                refs=[job.slot_id],
            ))

        diagnostics = spec.get("diagnostics") if isinstance(spec.get("diagnostics"), dict) else {}
        projection = diagnostics.get("spatial_projection") if isinstance(diagnostics.get("spatial_projection"), dict) else {}
        for warning in projection.get("warnings") or []:
            checks.append(DiagramGateCheck(
                name="spatial_projection_readability",
                status="block" if job.required else "warn",
                message=str(warning),
                refs=[job.slot_id],
            ))

        if job.variant == DiagramVariant.PROMPT:
            auxiliary_ids = [
                str(segment.get("id") or "")
                for segment in spec.get("segments") or []
                if isinstance(segment, dict) and segment.get("role") == "auxiliary"
            ]
            if auxiliary_ids:
                checks.append(DiagramGateCheck(
                    name="spatial_prompt_no_auxiliary",
                    status="block",
                    message="Clean prompt spatial diagram contains auxiliary segments",
                    refs=[job.slot_id, *auxiliary_ids],
                ))
    return checks
