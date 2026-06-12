#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RENDERER = ROOT / "scripts" / "diagram_workflow" / "render_geometry_spec.py"
PYTHON = ROOT / ".venv-diagram" / "bin" / "python"


WIDTHS_MM = [45, 55, 65]
LABEL_PX = [15, 32, 44, 52]


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


def make_spec(size: int) -> dict:
    value_size = max(12, round(size * 0.82))
    return {
        "schema_version": "geometry-render-spec/v1",
        "type": "coordinate_geometry",
        "diagram_variant": "prompt",
        "title": f"label-{size}px",
        "viewport": {
            "x_min": -1,
            "x_max": 20,
            "y_min": -1,
            "y_max": 5,
            "preserve_aspect": True,
        },
        "axes": {"x": False, "y": False, "grid": False, "show_ticks": False},
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
            label("la", "A", 2.55, 4.28, size),
            label("lb", "B", 10.45, 4.28, size),
            label("lc", "C", 19.45, -0.28, size),
            label("ld", "D", -0.45, -0.28, size),
            label("le", "E", 11.55, 2.23, size),
            label("lf", "F", 4.45, 2.23, size),
            label("ab", "AB=7", 6.5, 4.48, value_size, fill="#374151"),
            label("cd", "CD=19", 9.5, -0.58, value_size, fill="#374151"),
        ],
    }


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image_rel_by_size: dict[int, str] = {}

    for size in LABEL_PX:
        job_dir = OUT / "build" / f"label-{size}px"
        spec_path = job_dir / "final_renderer_spec.json"
        job_dir.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(make_spec(size), ensure_ascii=False, indent=2), encoding="utf-8")
        subprocess.run(
            [
                str(PYTHON),
                str(RENDERER),
                str(spec_path),
                "--out-dir",
                str(job_dir),
                "--width",
                "720",
                "--height",
                "520",
                "--png-size",
                "1024",
            ],
            cwd=str(ROOT),
            check=True,
        )
        image_rel_by_size[size] = str((job_dir / "rendered" / "prompt.png").relative_to(OUT))

    rows = []
    for size in LABEL_PX:
        cells = []
        for width in WIDTHS_MM:
            cells.append(
                "\\begin{minipage}[t]{%dmm}\\centering\n"
                "\\includegraphics[width=\\linewidth]{%s}\\\\[-0.5mm]\n"
                "{\\scriptsize %dpx / %dmm}\n"
                "\\end{minipage}" % (width, image_rel_by_size[size], size, width)
            )
        rows.append("\\noindent " + "\\hfill\n".join(cells) + "\\par\\vspace{3.5mm}")

    tex = r"""\documentclass[10pt]{article}
\usepackage[a4paper,margin=14mm]{geometry}
\usepackage{graphicx}
\usepackage{array}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\begin{document}
\small
\textbf{Diagram label readability experiment}

Canvas: 720px wide. Columns are final display widths. Rows are SVG text sizes.
\vspace{3mm}

""" + "\n\n".join(rows) + r"""

\vfill
\footnotesize Current coordinate point-label default is effectively 15px. The useful region should keep printed point labels close to normal worksheet text.
\end{document}
"""
    tex_path = OUT / "label-size-grid.tex"
    tex_path.write_text(tex, encoding="utf-8")
    subprocess.run(["tectonic", tex_path.name], cwd=str(OUT), check=True)
    subprocess.run(
        ["pdftoppm", "-png", "-r", "180", "label-size-grid.pdf", "label-size-grid"],
        cwd=str(OUT),
        check=True,
    )


if __name__ == "__main__":
    run()
