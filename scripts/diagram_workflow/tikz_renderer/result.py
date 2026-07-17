from __future__ import annotations

import json
import os
from pathlib import Path

from diagram_contracts import (
    DiagramRunStatus,
    GeometryRendererResult,
    RendererChecks,
    TikzNaturalSize,
    TikzReadabilityAudit,
    TikzRendererAudit,
    TikzRendererPaths,
)

from .contracts import TikzDiagramSpec
from .toolchain import PreviewResult


CM_TO_PT = 28.3464567


def relpath(target: Path, base: Path) -> str:
    return Path(os.path.relpath(target.resolve(), base.resolve())).as_posix()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json", by_alias=True)
    else:
        payload = data
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_success_result(
    *,
    out_dir: Path,
    renderer_spec_path: Path,
    diagram_spec: TikzDiagramSpec,
    fragment_path: Path,
    standalone_path: Path,
    preview_pdf_path: Path,
    preview_png_path: Path,
    preview_svg_path: Path,
    preview: PreviewResult,
) -> dict[str, object]:
    audit_path = out_dir / "renderer_audit.json"
    natural = TikzNaturalSize(
        width_pt=round(diagram_spec.natural_width_cm * CM_TO_PT, 3),
        height_pt=round(diagram_spec.natural_height_cm * CM_TO_PT, 3),
    )
    checks = RendererChecks(
        references_valid=True,
        tikz_exists=fragment_path.exists() and fragment_path.stat().st_size > 0,
        pdf_exists=preview_pdf_path.exists() and preview_pdf_path.stat().st_size > 0,
        image_exists=preview_png_path.exists() and preview_png_path.stat().st_size > 0,
        svg_exists=preview_svg_path.exists() and preview_svg_path.stat().st_size > 0,
        audit_exists=True,
    )
    audit = TikzRendererAudit(
        job_id=diagram_spec.job_id,
        variant=diagram_spec.variant,
        paths=TikzRendererPaths(
            fragment_path=relpath(fragment_path, out_dir),
            standalone_tex_path=relpath(standalone_path, out_dir),
            pdf_path=relpath(preview_pdf_path, out_dir) if checks.pdf_exists else "",
            preview_png_path=relpath(preview_png_path, out_dir) if checks.image_exists else "",
            preview_svg_path=relpath(preview_svg_path, out_dir) if checks.svg_exists else "",
            log_path=relpath(preview.log_path, out_dir) if preview.log_path else "",
            audit_path=relpath(audit_path, out_dir),
        ),
        natural_size=natural,
        readability=TikzReadabilityAudit(
            display_width="",
            point_label_count=diagram_spec.audit.point_label_count,
            condition_label_count=diagram_spec.audit.condition_label_count,
            condition_label_style=None,
            warnings=diagram_spec.audit.warnings,
        ),
        checks=checks,
        warnings=preview.warnings + diagram_spec.audit.warnings,
    )
    write_json(audit_path, audit)

    result = GeometryRendererResult(
        job_id=diagram_spec.job_id,
        status=DiagramRunStatus.OK,
        message="",
        diagram_variant=diagram_spec.variant,
        disclosure_policy="clean" if diagram_spec.variant.value == "prompt" else "annotated",
        renderer_spec=relpath(renderer_spec_path, out_dir),
        tikz_fragment_path=relpath(fragment_path, out_dir),
        tikz_source_path=relpath(fragment_path, out_dir),
        tikz_standalone_path=relpath(standalone_path, out_dir),
        tikz_pdf_path=relpath(preview_pdf_path, out_dir) if checks.pdf_exists else "",
        preview_png_path=relpath(preview_png_path, out_dir) if checks.image_exists else "",
        preview_svg=relpath(preview_svg_path, out_dir) if checks.svg_exists else "",
        renderer_audit=relpath(audit_path, out_dir),
        natural_width_pt=natural.width_pt,
        natural_height_pt=natural.height_pt,
        checks=checks,
    ).model_dump(mode="json", by_alias=True)
    write_json(out_dir / "renderer_result.json", result)
    return result


def write_failure_result(
    *,
    out_dir: Path,
    renderer_spec_path: Path,
    fail_type: str,
    message: str,
    job_id: str = "",
    variant: str = "prompt",
) -> dict[str, object]:
    result = GeometryRendererResult(
        job_id=job_id,
        status=DiagramRunStatus.FAILED,
        fail_type=fail_type,
        message=message,
        diagram_variant=variant if variant in {"prompt", "solution"} else "prompt",
        disclosure_policy="clean" if variant == "prompt" else "annotated",
        renderer_spec=relpath(renderer_spec_path, out_dir),
        checks=RendererChecks(references_valid=False),
    ).model_dump(mode="json", by_alias=True)
    write_json(out_dir / "renderer_result.json", result)
    return result
