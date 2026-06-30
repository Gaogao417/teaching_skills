from __future__ import annotations

import re
from pathlib import Path

from diagram_contracts import DiagramGateCheck, DiagramJobsManifest, RendererBindingManifest


def _artifact_path(artifact_dir: Path, job_id: str, path_value: str) -> Path | None:
    if not path_value:
        return None
    raw = Path(path_value)
    candidates = [raw] if raw.is_absolute() else [
        artifact_dir / raw,
        artifact_dir / "build" / "diagram" / "jobs" / job_id / raw,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1] if candidates else None


def _svg_text_tags(svg_text: str, label_kind: str) -> list[str]:
    tags = re.findall(r"<text\b[^>]*>", svg_text)
    return [tag for tag in tags if f'data-label-kind="{label_kind}"' in tag]


def _font_size_from_tag(tag: str) -> float | None:
    match = re.search(r'font-size="(?P<size>\d+(?:\.\d+)?)"', tag)
    return float(match.group("size")) if match else None


def _check_svg_readability(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Check preview SVGs for the label readability issues seen in worksheets."""
    checks: list[DiagramGateCheck] = []
    job_by_ref = {job.diagram_ref: job for job in jobs.jobs}
    for diagram_ref, art in artifacts.bindings.items():
        if not art.preview_svg:
            continue
        svg_path = _artifact_path(artifact_dir, art.job_id, art.preview_svg)
        if svg_path is None or not svg_path.exists():
            continue
        try:
            svg_text = svg_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        font_weights = re.findall(r'font-weight="([^"]+)"', svg_text)
        bad_weights = [w for w in font_weights if w.lower() not in {"normal", "400"}]
        if bad_weights:
            checks.append(DiagramGateCheck(
                name="diagram_svg_font_weight",
                status="block",
                message=f"SVG for '{diagram_ref}' uses bold/heavy font-weight values: {sorted(set(bad_weights))}",
                refs=[diagram_ref],
            ))

        if "Arial" in svg_text and bad_weights:
            checks.append(DiagramGateCheck(
                name="diagram_svg_arial_bold",
                status="block",
                message=f"SVG for '{diagram_ref}' still uses Arial with bold/heavy point labels",
                refs=[diagram_ref],
            ))

        point_tags = _svg_text_tags(svg_text, "point")
        point_sizes = [size for tag in point_tags if (size := _font_size_from_tag(tag)) is not None]
        if point_sizes and min(point_sizes) < 44:
            checks.append(DiagramGateCheck(
                name="diagram_svg_point_label_size",
                status="block",
                message=f"Point labels for '{diagram_ref}' are too small: min {min(point_sizes):g}px, expected at least 44px",
                refs=[diagram_ref],
            ))

        job = job_by_ref.get(diagram_ref)
        if job and re.search(r">\s*[A-Z]{1,3}\s*=\s*[^<]*\d[^<]*<", svg_text):
            checks.append(DiagramGateCheck(
                name="diagram_svg_condition_label_style",
                status="block",
                message=f"Length condition labels for '{diagram_ref}' should be value-only, e.g. 7 instead of AB=7",
                refs=[job.slot_id],
            ))
    return checks
