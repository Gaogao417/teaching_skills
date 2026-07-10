from __future__ import annotations

from dataclasses import dataclass, field
import shutil
import subprocess
from time import perf_counter
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
    timings_ms: dict[str, float] = field(default_factory=dict)


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
    xelatex = shutil.which("xelatex")
    tectonic = shutil.which("tectonic")
    if xelatex:
        result.compile_engine = "xelatex"
        command = [
            xelatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={rendered_dir}",
            str(standalone_path),
        ]
    elif tectonic:
        result.compile_engine = "tectonic"
        command = [tectonic, "--keep-logs", "--outdir", str(rendered_dir), str(standalone_path)]
    else:
        result.warnings.append("xelatex_and_tectonic_missing; skipped TikZ preview PDF")
        return result

    try:
        started = perf_counter()
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout_s)
        result.timings_ms["latex_compile"] = round((perf_counter() - started) * 1000, 3)
    except subprocess.TimeoutExpired:
        result.warnings.append(
            f"{result.compile_engine} timed out after {timeout_s}s; skipped TikZ preview PDF"
        )
        return result
    log_path = rendered_dir / f"{standalone_path.stem}.log"
    if completed.returncode != 0:
        result.log_path = log_path if log_path.exists() else None
        message = (
            completed.stderr
            or completed.stdout
            or f"{result.compile_engine}_failed"
        ).strip()
        result.warnings.append(message[-500:])
        return result

    produced_pdf = rendered_dir / f"{standalone_path.stem}.pdf"
    if produced_pdf.exists() and produced_pdf.stat().st_size > 0:
        if preview_pdf.exists():
            preview_pdf.unlink()
        produced_pdf.replace(preview_pdf)
        result.pdf_path = preview_pdf
    else:
        result.warnings.append(
            f"{result.compile_engine} did not create a non-empty PDF"
        )
        return result
    result.log_path = log_path if log_path.exists() else None

    pdftocairo = shutil.which("pdftocairo")
    if not pdftocairo:
        result.warnings.append("pdftocairo_missing; skipped TikZ preview PNG/SVG")
        return result
    result.export_tool = "pdftocairo"

    png_base = preview_png.with_suffix("")
    try:
        started = perf_counter()
        png_completed = subprocess.run(
            [pdftocairo, "-png", "-singlefile", "-r", "200", str(preview_pdf), str(png_base)],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
        result.timings_ms["png_export"] = round((perf_counter() - started) * 1000, 3)
    except subprocess.TimeoutExpired:
        result.warnings.append(f"pdftocairo PNG export timed out after {timeout_s}s")
        png_completed = None
    if png_completed and png_completed.returncode == 0 and preview_png.exists() and preview_png.stat().st_size > 0:
        result.png_path = preview_png
    elif png_completed:
        result.warnings.append((png_completed.stderr or png_completed.stdout or "pdftocairo_png_failed").strip()[-500:])

    try:
        started = perf_counter()
        svg_completed = subprocess.run(
            [pdftocairo, "-svg", str(preview_pdf), str(preview_svg)],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
        result.timings_ms["svg_export"] = round((perf_counter() - started) * 1000, 3)
    except subprocess.TimeoutExpired:
        result.warnings.append(f"pdftocairo SVG export timed out after {timeout_s}s")
        svg_completed = None
    if svg_completed and svg_completed.returncode == 0 and preview_svg.exists() and preview_svg.stat().st_size > 0:
        result.svg_path = preview_svg
    elif svg_completed:
        result.warnings.append((svg_completed.stderr or svg_completed.stdout or "pdftocairo_svg_failed").strip()[-500:])
    return result
