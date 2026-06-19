#!/usr/bin/env python3
"""Compile geometry-render-spec/v1 to a bindable TikZ fragment.

The final assignment consumes the generated ``*.fragment.tex`` directly.
Standalone PDF/PNG/SVG previews are diagnostic only and never define whether a
diagram is bindable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_contracts import GeometryRenderSpec  # noqa: E402
from tikz_renderer import compile_geometry_render_spec  # noqa: E402
from tikz_renderer.result import write_failure_result, write_json, write_success_result  # noqa: E402
from tikz_renderer.toolchain import build_previews  # noqa: E402
from tikz_renderer.validate import validate_render_spec  # noqa: E402
from tikz_renderer.writer import render_fragment, render_standalone  # noqa: E402


def read_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def render_geometry_spec(
    spec_path: Path,
    out_dir: Path,
    width: int | None = None,
    height: int | None = None,
    size: int | None = None,
    variant: str | None = None,
) -> dict[str, object]:
    del width, height, size
    spec_path = spec_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        raw_spec = read_json(spec_path)
    except Exception as exc:
        return write_failure_result(
            out_dir=out_dir,
            renderer_spec_path=spec_path,
            fail_type="invalid_renderer_spec",
            message=str(exc),
        )

    diagram_variant = variant or str(raw_spec.get("variant") or raw_spec.get("diagram_variant") or "prompt")
    if diagram_variant not in {"prompt", "solution"}:
        diagram_variant = "prompt"
    raw_spec["variant"] = diagram_variant

    try:
        spec_model = GeometryRenderSpec.model_validate(raw_spec)
    except Exception as exc:
        return write_failure_result(
            out_dir=out_dir,
            renderer_spec_path=spec_path,
            fail_type="invalid_renderer_spec",
            message=str(exc),
            job_id=str(raw_spec.get("job_id") or ""),
            variant=diagram_variant,
        )

    validation_errors = validate_render_spec(spec_model)
    if validation_errors:
        return write_failure_result(
            out_dir=out_dir,
            renderer_spec_path=spec_path,
            fail_type="invalid_renderer_spec",
            message="; ".join(validation_errors),
            job_id=spec_model.job_id,
            variant=diagram_variant,
        )

    try:
        diagram_spec = compile_geometry_render_spec(spec_model)
        fragment = render_fragment(diagram_spec)
    except Exception as exc:
        return write_failure_result(
            out_dir=out_dir,
            renderer_spec_path=spec_path,
            fail_type="tikz_compile_failed",
            message=str(exc),
            job_id=spec_model.job_id,
            variant=diagram_variant,
        )

    rendered_dir = out_dir / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    fragment_path = rendered_dir / f"{diagram_variant}.fragment.tex"
    standalone_path = rendered_dir / f"{diagram_variant}.standalone.tex"
    preview_pdf_path = rendered_dir / f"{diagram_variant}.preview.pdf"
    preview_png_path = rendered_dir / f"{diagram_variant}.preview.png"
    preview_svg_path = rendered_dir / f"{diagram_variant}.preview.svg"
    tikz_spec_path = rendered_dir / f"{diagram_variant}.tikz_spec.json"

    for stale_path in (preview_pdf_path, preview_png_path, preview_svg_path):
        if stale_path.exists():
            stale_path.unlink()
    fragment_path.write_text(fragment, encoding="utf-8")
    standalone_path.write_text(render_standalone(fragment, diagram_spec.libraries), encoding="utf-8")
    write_json(tikz_spec_path, diagram_spec)

    preview = build_previews(standalone_path, preview_pdf_path, preview_png_path, preview_svg_path)
    return write_success_result(
        out_dir=out_dir,
        renderer_spec_path=spec_path,
        diagram_spec=diagram_spec,
        fragment_path=fragment_path,
        standalone_path=standalone_path,
        preview_pdf_path=preview_pdf_path,
        preview_png_path=preview_png_path,
        preview_svg_path=preview_svg_path,
        preview=preview,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile final_renderer_spec.json to renderer_result.json + TikZ")
    parser.add_argument("renderer_spec", type=Path, help="Path to final_renderer_spec.json")
    parser.add_argument("--out-dir", type=Path, help="Diagram output dir; defaults beside spec")
    parser.add_argument("--width", type=int, help="Accepted for batch CLI compatibility; ignored by TikZ compiler")
    parser.add_argument("--height", type=int, help="Accepted for batch CLI compatibility; ignored by TikZ compiler")
    parser.add_argument("--png-size", type=int, help="Accepted for batch CLI compatibility; preview uses pdftocairo defaults")
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
