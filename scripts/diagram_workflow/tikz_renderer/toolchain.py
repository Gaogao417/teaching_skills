from __future__ import annotations

from dataclasses import dataclass, field
import shutil
import subprocess
from pathlib import Path


@dataclass
class PreviewResult:
    compile_engine: str = "none"
    export_tool: str = "none"
    pdf_path: Path | None = None
    png_path: Path | None = None
    svg_path: Path | None = None
    log_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


def build_previews(
    standalone_path: Path,
    preview_pdf: Path,
    preview_png: Path,
    preview_svg: Path,
    *,
    timeout_s: int = 15,
) -> PreviewResult:
    result = PreviewResult()
    rendered_dir = standalone_path.parent
    tectonic = shutil.which("tectonic")
    if not tectonic:
        result.warnings.append("tectonic_missing; skipped TikZ preview PDF")
        return result

    result.compile_engine = "tectonic"
    command = [tectonic, "--keep-logs", "--outdir", str(rendered_dir), str(standalone_path)]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        result.warnings.append(f"tectonic timed out after {timeout_s}s; skipped TikZ preview PDF")
        return result
    log_path = rendered_dir / f"{standalone_path.stem}.log"
    if completed.returncode != 0:
        result.log_path = log_path if log_path.exists() else None
        message = (completed.stderr or completed.stdout or "tectonic_failed").strip()
        result.warnings.append(message[-500:])
        return result

    produced_pdf = rendered_dir / f"{standalone_path.stem}.pdf"
    if produced_pdf.exists() and produced_pdf.stat().st_size > 0:
        if preview_pdf.exists():
            preview_pdf.unlink()
        produced_pdf.replace(preview_pdf)
        result.pdf_path = preview_pdf
    else:
        result.warnings.append("tectonic did not create a non-empty PDF")
        return result
    result.log_path = log_path if log_path.exists() else None

    pdftocairo = shutil.which("pdftocairo")
    if not pdftocairo:
        result.warnings.append("pdftocairo_missing; skipped TikZ preview PNG/SVG")
        return result
    result.export_tool = "pdftocairo"

    png_base = preview_png.with_suffix("")
    try:
        png_completed = subprocess.run(
            [pdftocairo, "-png", "-singlefile", "-r", "200", str(preview_pdf), str(png_base)],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        result.warnings.append(f"pdftocairo PNG export timed out after {timeout_s}s")
        png_completed = None
    if png_completed and png_completed.returncode == 0 and preview_png.exists() and preview_png.stat().st_size > 0:
        result.png_path = preview_png
    elif png_completed:
        result.warnings.append((png_completed.stderr or png_completed.stdout or "pdftocairo_png_failed").strip()[-500:])

    try:
        svg_completed = subprocess.run(
            [pdftocairo, "-svg", str(preview_pdf), str(preview_svg)],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        result.warnings.append(f"pdftocairo SVG export timed out after {timeout_s}s")
        svg_completed = None
    if svg_completed and svg_completed.returncode == 0 and preview_svg.exists() and preview_svg.stat().st_size > 0:
        result.svg_path = preview_svg
    elif svg_completed:
        result.warnings.append((svg_completed.stderr or svg_completed.stdout or "pdftocairo_svg_failed").strip()[-500:])
    return result
