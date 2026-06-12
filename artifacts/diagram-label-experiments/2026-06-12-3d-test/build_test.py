#!/usr/bin/env python3
from __future__ import annotations

import html
import subprocess
from pathlib import Path


OUT = Path(__file__).resolve().parent

RIGHT_COL_MM = [50, 60, 70]
LABEL_PX = [36, 44, 52]
BODY_SCALES = [
    ("normal", 0.78),
    ("large", 0.90),
]

CANVAS_W = 720
CANVAS_H = 360


POINTS = {
    "A": (3, 6),
    "B": (10, 6),
    "C": (19, 0),
    "D": (0, 0),
    "E": (11, 3),
    "F": (5, 3),
}


def svg_text(x: float, y: float, text: str, size: int, *, italic: bool = False, anchor: str = "middle") -> str:
    family = "'Times New Roman', 'STIX Two Text', 'Latin Modern Roman', serif"
    style = "italic" if italic else "normal"
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="central" '
        f'font-family="{family}" font-size="{size}" font-style="{style}" font-weight="400" fill="#111827">'
        f"{html.escape(text)}</text>"
    )


def line(p1: tuple[float, float], p2: tuple[float, float], width: float = 2.4) -> str:
    return (
        f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
        f'stroke="#111827" stroke-width="{width}" stroke-linecap="round" />'
    )


def poly(points: list[tuple[float, float]], *, fill: str = "none", width: float = 2.4) -> str:
    raw = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polygon points="{raw}" fill="{fill}" stroke="#111827" stroke-width="{width}" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
    )


def make_svg(body_scale: float, label_px: int, out_path: Path) -> None:
    body_w = CANVAS_W * body_scale
    scale = body_w / 19.0
    body_h = 6.0 * scale
    x0 = (CANVAS_W - body_w) / 2
    y0 = (CANVAS_H - body_h) / 2

    def xy(name: str) -> tuple[float, float]:
        x, y = POINTS[name]
        return (x0 + x * scale, y0 + (6 - y) * scale)

    value_px = round(label_px * 0.78)
    dot_r = max(2.6, label_px * 0.07)
    offset = label_px * 0.55
    elements: list[str] = []
    elements.append('<rect x="0" y="0" width="720" height="360" fill="white" />')
    elements.append(poly([xy("A"), xy("B"), xy("C"), xy("D")], fill="#ffffff", width=2.4))
    elements.append(line(xy("A"), xy("C"), 2.1))
    elements.append(line(xy("B"), xy("D"), 2.1))
    elements.append(line(xy("F"), xy("E"), 2.7))
    for name in ["A", "B", "C", "D", "E", "F"]:
        x, y = xy(name)
        elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dot_r:.1f}" fill="#111827" />')

    label_offsets = {
        "A": (-offset * 0.35, -offset * 0.75),
        "B": (offset * 0.45, -offset * 0.75),
        "C": (offset * 0.75, offset * 0.45),
        "D": (-offset * 0.75, offset * 0.45),
        "E": (offset * 0.65, -offset * 0.15),
        "F": (-offset * 0.65, -offset * 0.15),
    }
    for name, (dx, dy) in label_offsets.items():
        x, y = xy(name)
        elements.append(svg_text(x + dx, y + dy, name, label_px, italic=True))

    ax, ay = xy("A")
    bx, by = xy("B")
    cx, cy = xy("C")
    dx, dy = xy("D")
    elements.append(svg_text((ax + bx) / 2, ay - label_px * 0.58, "7", value_px))
    elements.append(svg_text((cx + dx) / 2, cy + label_px * 0.58, "19", value_px))

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="360" '
        'viewBox="0 0 720 360" role="img">\n'
        + "\n".join(elements)
        + "\n</svg>\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")


def convert_svg(svg_path: Path, png_path: Path) -> None:
    subprocess.run(["sips", "-s", "format", "png", str(svg_path), "--out", str(png_path)], check=True)


def build_tex(cases: list[dict[str, object]]) -> str:
    pages: list[str] = []
    for index, case in enumerate(cases, start=1):
        col = int(case["right_col_mm"])
        left_expr = rf"\dimexpr\linewidth-{col}mm-8mm\relax"
        pages.append(
            rf"""
\section*{{实验 {index}: 右栏 {col}mm，字号 {case['label_px']}px，图形 {case['body_name']}}}
\noindent\begin{{minipage}}[t]{{{left_expr}}}
\textbf{{题干模拟}}\par
如图，在梯形 $ABCD$ 中，$AB\parallel CD$，点 $E,F$ 分别是对角线 $AC,BD$ 的中点。已知 $AB=7$，$CD=19$，求 $EF$ 的长，并说明所用的中位线结构。\par
\vspace{{4mm}}
\noindent\fbox{{%
  \begin{{minipage}}[t][112mm][t]{{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}}
  \vspace{{2mm}}
  {{\small 解题 / 讲解占位：}}\par\vspace{{10mm}}
  \dotfill\par\vspace{{10mm}}
  \dotfill\par\vspace{{10mm}}
  \dotfill\par\vspace{{10mm}}
  \dotfill
  \end{{minipage}}%
}}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{{col}mm}}
\vspace{{0pt}}\centering
\includegraphics[width=\linewidth]{{{case['image_path']}}}
\par\vspace{{1mm}}{{{{\small 图：右栏 {col}mm}}}}
\end{{minipage}}
\clearpage
"""
        )

    return (
        r"""\documentclass[10pt]{ctexart}
\usepackage[a4paper,margin=14mm]{geometry}
\usepackage{graphicx}
\usepackage{xcolor}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\fboxsep}{3mm}
\setlength{\fboxrule}{0.35pt}
\begin{document}
"""
        + "\n".join(pages)
        + "\n\\end{document}\n"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, object]] = []
    for body_name, body_scale in BODY_SCALES:
        for label_px in LABEL_PX:
            svg_path = OUT / "images" / f"{body_name}-{label_px}px.svg"
            png_path = OUT / "images" / f"{body_name}-{label_px}px.png"
            make_svg(body_scale, label_px, svg_path)
            convert_svg(svg_path, png_path)
            for right_col_mm in RIGHT_COL_MM:
                cases.append(
                    {
                        "body_name": body_name,
                        "label_px": label_px,
                        "right_col_mm": right_col_mm,
                        "image_path": str(png_path.relative_to(OUT)),
                    }
                )

    tex_path = OUT / "test.tex"
    tex_path.write_text(build_tex(cases), encoding="utf-8")
    subprocess.run(["tectonic", "test.tex"], cwd=str(OUT), check=True)
    subprocess.run(["pdftoppm", "-png", "-r", "160", "test.pdf", "test"], cwd=str(OUT), check=True)


if __name__ == "__main__":
    main()
