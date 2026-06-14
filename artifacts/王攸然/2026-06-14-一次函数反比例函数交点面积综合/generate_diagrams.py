from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


OUT_DIR = Path(__file__).parent / "diagrams"


@dataclass
class Diagram:
    name: str
    k: float
    b: float
    m: float
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    points: dict[str, tuple[float, float]]
    triangle: tuple[str, str, str] | None = None


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def polyline(commands: list[str], pts: list[tuple[float, float]]) -> None:
    if len(pts) < 2:
        return
    first = pts[0]
    commands.append(f"{first[0]:.2f} {first[1]:.2f} m")
    for x, y in pts[1:]:
        commands.append(f"{x:.2f} {y:.2f} l")
    commands.append("S")


def write_pdf(path: Path, content: str, width: int = 300, height: int = 220) -> None:
    stream = content.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>".encode("latin-1"),
        b"<< /Length " + str(len(stream)).encode("latin-1") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{idx} 0 obj\n".encode("latin-1"))
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n".encode("latin-1"))
    data.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        data.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    data.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1"))
    path.write_bytes(data)


def render(diagram: Diagram) -> None:
    width, height = 300, 220
    left, right, bottom, top = 34, 14, 26, 16
    plot_w = width - left - right
    plot_h = height - bottom - top
    xmin, xmax = diagram.xlim
    ymin, ymax = diagram.ylim

    def xy(x: float, y: float) -> tuple[float, float]:
        px = left + (x - xmin) / (xmax - xmin) * plot_w
        py = bottom + (y - ymin) / (ymax - ymin) * plot_h
        return px, py

    def inside_y(y: float) -> bool:
        return ymin <= y <= ymax

    cmds: list[str] = []
    cmds.append("1 1 1 rg 0 0 300 220 re f")

    # Grid.
    cmds.append("0.90 0.90 0.90 RG 0.35 w")
    for x in range(int(xmin), int(xmax) + 1):
        x0, y0 = xy(x, ymin)
        x1, y1 = xy(x, ymax)
        cmds.append(f"{x0:.2f} {y0:.2f} m {x1:.2f} {y1:.2f} l S")
    for y in range(int(ymin), int(ymax) + 1):
        x0, y0 = xy(xmin, y)
        x1, y1 = xy(xmax, y)
        cmds.append(f"{x0:.2f} {y0:.2f} m {x1:.2f} {y1:.2f} l S")

    # Axes.
    cmds.append("0 0 0 RG 0.9 w")
    if xmin < 0 < xmax:
        x0, y0 = xy(0, ymin)
        x1, y1 = xy(0, ymax)
        cmds.append(f"{x0:.2f} {y0:.2f} m {x1:.2f} {y1:.2f} l S")
    if ymin < 0 < ymax:
        x0, y0 = xy(xmin, 0)
        x1, y1 = xy(xmax, 0)
        cmds.append(f"{x0:.2f} {y0:.2f} m {x1:.2f} {y1:.2f} l S")

    # Optional triangle.
    if diagram.triangle:
        tri_pts = [xy(*diagram.points[name]) for name in diagram.triangle]
        cmds.append("0.86 0.86 0.86 rg 0.55 0.55 0.55 RG 0.7 w")
        cmds.append(f"{tri_pts[0][0]:.2f} {tri_pts[0][1]:.2f} m")
        for px, py in tri_pts[1:]:
            cmds.append(f"{px:.2f} {py:.2f} l")
        cmds.append("h B")

    # Line y = kx + b.
    pts: list[tuple[float, float]] = []
    for i in range(301):
        x = xmin + (xmax - xmin) * i / 300
        y = diagram.k * x + diagram.b
        if inside_y(y):
            pts.append(xy(x, y))
        else:
            polyline(cmds, pts)
            pts = []
    cmds.append("0.05 0.28 0.80 RG 1.4 w")
    polyline(cmds, pts)

    # Hyperbola y = m/x, split at x = 0.
    cmds.append("0.84 0.18 0.14 RG 1.4 w")
    for start, end in [(xmin, min(-0.12, xmax)), (max(0.12, xmin), xmax)]:
        pts = []
        if start >= end:
            continue
        for i in range(360):
            x = start + (end - start) * i / 359
            y = diagram.m / x
            if inside_y(y):
                pts.append(xy(x, y))
            else:
                polyline(cmds, pts)
                pts = []
        polyline(cmds, pts)

    # Points.
    cmds.append("0 0 0 rg 0 0 0 RG 0.8 w")
    for label, (x, y) in diagram.points.items():
        px, py = xy(x, y)
        cmds.append(f"{px-2.2:.2f} {py-2.2:.2f} 4.4 4.4 re f")
        dx = 5 if x <= (xmin + xmax) / 2 else -14
        dy = 6 if y <= (ymin + ymax) / 2 else -12
        cmds.append(f"BT /F1 10 Tf {px+dx:.2f} {py+dy:.2f} Td ({pdf_escape(label)}) Tj ET")

    # Labels.
    cmds.append("0.05 0.28 0.80 rg BT /F1 9 Tf 208 196 Td (y1) Tj ET")
    cmds.append("0.84 0.18 0.14 rg BT /F1 9 Tf 236 42 Td (y2) Tj ET")
    cmds.append("0 0 0 rg BT /F1 8 Tf 282 30 Td (x) Tj ET")
    cmds.append("0 0 0 rg BT /F1 8 Tf 39 205 Td (y) Tj ET")

    write_pdf(OUT_DIR / f"{diagram.name}.pdf", "\n".join(cmds), width, height)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    diagrams = [
        Diagram("original", 1, -1, 2, (-4, 5), (-5, 4), {"A": (2, 1), "B": (-1, -2), "O": (0, 0)}, ("O", "A", "B")),
        Diagram("p1", 1, -2, 3, (-4, 5), (-5, 4), {"A": (3, 1), "B": (-1, -3), "O": (0, 0)}, ("O", "A", "B")),
        Diagram("p2", -1, 5, 4, (-2, 6), (-3, 6), {"A": (1, 4), "B": (4, 1), "O": (0, 0)}, ("O", "A", "B")),
        Diagram("p3", 1, 1, 6, (-5, 5), (-5, 6), {"A": (2, 3), "B": (-3, -2), "P": (0, 4)}, ("P", "A", "B")),
        Diagram("p4", -1, -1, -2, (-4, 4), (-5, 4), {"A": (1, -2), "B": (-2, 1)}, None),
    ]
    for diagram in diagrams:
        render(diagram)


if __name__ == "__main__":
    main()
