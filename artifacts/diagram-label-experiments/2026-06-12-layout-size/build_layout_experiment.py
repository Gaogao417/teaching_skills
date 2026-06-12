#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RENDERER = ROOT / "scripts" / "diagram_workflow" / "render_geometry_spec.py"
PYTHON = ROOT / ".venv-diagram" / "bin" / "python"

DISPLAY_WIDTHS_MM = [50, 60, 70]

VARIANTS = [
    {
        "id": "loose-720x520-44px",
        "label": "720x520 loose viewport, label 44px",
        "canvas": (720, 520),
        "viewport": {"x_min": -1.0, "x_max": 20.0, "y_min": -1.0, "y_max": 5.0},
        "label_px": 44,
    },
    {
        "id": "tight-720x520-44px",
        "label": "720x520 tight viewport, label 44px",
        "canvas": (720, 520),
        "viewport": {"x_min": -0.2, "x_max": 19.3, "y_min": -0.35, "y_max": 4.45},
        "label_px": 44,
    },
    {
        "id": "tight-720x360-44px",
        "label": "720x360 tight viewport, label 44px",
        "canvas": (720, 360),
        "viewport": {"x_min": -0.2, "x_max": 19.3, "y_min": -0.35, "y_max": 4.45},
        "label_px": 44,
    },
    {
        "id": "tight-720x360-52px",
        "label": "720x360 tight viewport, label 52px",
        "canvas": (720, 360),
        "viewport": {"x_min": -0.2, "x_max": 19.3, "y_min": -0.35, "y_max": 4.45},
        "label_px": 52,
    },
]


def point(pid: str, x: float, y: float) -> dict:
    return {
        "type": "point",
        "id": pid,
        "x": x,
        "y": y,
        "label": " ",
        "style": {"radius": 4.8},
    }


def label(tid: str, text: str, x: float, y: float, size: int, *, fill: str = "#111827") -> dict:
    return {
        "type": "text",
        "id": tid,
        "x": x,
        "y": y,
        "text": text,
        "style": {"font_size": size, "fill": fill},
    }


def make_spec(variant: dict) -> dict:
    size = int(variant["label_px"])
    value_size = max(12, round(size * 0.82))
    viewport = dict(variant["viewport"])
    viewport["preserve_aspect"] = True
    return {
        "schema_version": "geometry-render-spec/v1",
        "type": "coordinate_geometry",
        "diagram_variant": "prompt",
        "title": variant["id"],
        "viewport": viewport,
        "axes": {
            "x": False,
            "y": False,
            "grid": False,
            "show_ticks": False,
            "x_label": "",
            "y_label": "",
        },
        "objects": [
            {
                "type": "polygon",
                "id": "trap",
                "points": ["A", "B", "C", "D"],
                "style": {"fill": "#f8fafc", "stroke": "#111827", "stroke_width": 2.4},
            },
            {
                "type": "polyline",
                "id": "AC",
                "points": ["A", "C"],
                "style": {"stroke": "#2563eb", "stroke_width": 2.2},
            },
            {
                "type": "polyline",
                "id": "BD",
                "points": ["B", "D"],
                "style": {"stroke": "#2563eb", "stroke_width": 2.2},
            },
            {
                "type": "polyline",
                "id": "EF",
                "points": ["F", "E"],
                "style": {"stroke": "#dc2626", "stroke_width": 3.0},
            },
            point("A", 3, 4),
            point("B", 10, 4),
            point("C", 19, 0),
            point("D", 0, 0),
            point("E", 11, 2),
            point("F", 5, 2),
            label("la", "A", 2.5, 4.27, size),
            label("lb", "B", 10.5, 4.27, size),
            label("lc", "C", 19.35, -0.22, size),
            label("ld", "D", -0.35, -0.22, size),
            label("le", "E", 11.48, 2.23, size),
            label("lf", "F", 4.52, 2.23, size),
            label("ab", "AB=7", 6.5, 4.48, value_size, fill="#374151"),
            label("cd", "CD=19", 9.5, -0.47, value_size, fill="#374151"),
        ],
    }


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rel_images: dict[str, str] = {}

    for variant in VARIANTS:
        job_dir = OUT / "build" / variant["id"]
        spec_path = job_dir / "final_renderer_spec.json"
        job_dir.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(make_spec(variant), ensure_ascii=False, indent=2), encoding="utf-8")
        width, height = variant["canvas"]
        subprocess.run(
            [
                str(PYTHON),
                str(RENDERER),
                str(spec_path),
                "--out-dir",
                str(job_dir),
                "--width",
                str(width),
                "--height",
                str(height),
                "--png-size",
                "1024",
            ],
            cwd=str(ROOT),
            check=True,
        )
        rel_images[variant["id"]] = str((job_dir / "rendered" / "prompt.png").relative_to(OUT))

    rows = []
    for variant in VARIANTS:
        cells = []
        for width_mm in DISPLAY_WIDTHS_MM:
            cells.append(
                "\\begin{minipage}[t]{%dmm}\\centering\n"
                "\\includegraphics[width=\\linewidth]{%s}\\\\[-0.5mm]\n"
                "{\\scriptsize %dmm}\n"
                "\\end{minipage}" % (width_mm, rel_images[variant["id"]], width_mm)
            )
        rows.append(
            "{\\small\\bfseries %s}\\\\[1mm]\n%s\\par\\vspace{4mm}"
            % (variant["label"].replace("_", "\\_"), "\\hfill\n".join(cells))
        )

    tex = r"""\documentclass[10pt]{article}
\usepackage[a4paper,margin=10mm]{geometry}
\usepackage{graphicx}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\begin{document}
\small
\textbf{Diagram size / viewport experiment}

Columns are final display widths. Rows test canvas aspect, viewport tightness, and label size.
\vspace{2.5mm}

""" + "\n\n".join(rows) + r"""

\vfill
\footnotesize Tight viewport means the diagram's world bounds hug the actual geometry more closely; 720x360 reduces vertical whitespace for landscape geometry.
\end{document}
"""
    tex_path = OUT / "layout-size-grid.tex"
    tex_path.write_text(tex, encoding="utf-8")
    subprocess.run(["tectonic", tex_path.name], cwd=str(OUT), check=True)
    subprocess.run(["pdftoppm", "-png", "-r", "180", "layout-size-grid.pdf", "layout-size-grid"], cwd=str(OUT), check=True)


if __name__ == "__main__":
    run()
