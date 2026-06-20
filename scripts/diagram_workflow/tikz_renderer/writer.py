from __future__ import annotations

import math
import re

from .contracts import TikzDiagramSpec
from .macros import DIAGRAM_TIKZ_MACROS


_SAFE_COLOR_NAMES = {
    "black",
    "white",
    "gray",
    "lightgray",
    "darkgray",
    "red",
    "green",
    "blue",
    "cyan",
    "magenta",
    "yellow",
    "orange",
    "purple",
    "brown",
    "teal",
}

_TEX_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def fmt_num(value: float, digits: int = 5) -> str:
    if not math.isfinite(value):
        raise ValueError(f"non-finite numeric value: {value!r}")
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text or "0"


def fmt_cm(value: float) -> str:
    return f"{fmt_num(value, 4)}cm"


def escape_tex(value: object) -> str:
    return "".join(_TEX_ESCAPE_MAP.get(ch, ch) for ch in str(value))


def point_label_tex(value: object) -> str:
    text = str(value)
    if re.match(r"^[A-Za-z][A-Za-z0-9']*$", text):
        return r"$\mathit{" + escape_tex(text) + "}$"
    subscript_match = re.match(r"^(?P<name>[A-Za-z])_\{?(?P<sub>[0-9]+)\}?$", text)
    if subscript_match:
        return (
            r"$\mathit{"
            + escape_tex(subscript_match.group("name"))
            + r"}_{"
            + escape_tex(subscript_match.group("sub"))
            + r"}$"
        )
    return escape_tex(text)


def _looks_like_math_label(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_{}=+\-*/^().,\\\s<>]+", text))


def _normalize_math_subscripts(text: str) -> str:
    return re.sub(r"([A-Za-z])_([A-Za-z0-9]+)", r"\1_{\2}", text)


def node_text_tex(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("$") and text.endswith("$"):
        return text
    if _looks_like_math_label(text) and any(ch in text for ch in "_=^+-*/"):
        return "$" + _normalize_math_subscripts(text) + "$"
    return escape_tex(text)


def color_option(value: object, *, default: str = "black") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    hex_match = re.match(r"^#(?P<r>[0-9a-fA-F]{2})(?P<g>[0-9a-fA-F]{2})(?P<b>[0-9a-fA-F]{2})$", text)
    if hex_match:
        r = int(hex_match.group("r"), 16)
        g = int(hex_match.group("g"), 16)
        b = int(hex_match.group("b"), 16)
        return f"{{rgb,255:red,{r};green,{g};blue,{b}}}"
    if text.lower() in _SAFE_COLOR_NAMES:
        return text.lower()
    return default


def opacity_option(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number >= 1:
        return ""
    if number < 0:
        number = 0
    return f"opacity={fmt_num(number, 3)}"


def stroke_width_option(value: object, *, default_px: float = 2.0) -> str:
    try:
        px = float(value)
    except (TypeError, ValueError):
        px = default_px
    return f"line width={fmt_num(px * 0.45, 3)}pt"


def dash_option(value: object) -> str:
    if value in (None, "", False):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text in {"dashed", "dash"}:
        return "dashed"
    if text in {"dotted", "dot"}:
        return "dotted"
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if len(numbers) >= 2:
        return f"dash pattern=on {numbers[0]}pt off {numbers[1]}pt"
    return "dashed"


def join_options(*items: str) -> str:
    return ", ".join(item for item in items if item)


def render_fragment(spec: TikzDiagramSpec) -> str:
    lines: list[str] = [
        r"\begin{tikzpicture}[x=1cm,y=1cm,baseline=(current bounding box.center)]"
    ]
    for style in spec.styles:
        lines.append(f"  \\tikzset{{{style.name}/.style={{{style.options}}}}}")
    for coordinate in spec.coordinates:
        lines.append(
            f"  \\coordinate ({coordinate.name}) at ({fmt_num(coordinate.x)},{fmt_num(coordinate.y)});"
        )
    for command in sorted(spec.commands, key=lambda item: item.order):
        for line in command.tex.splitlines():
            lines.append(f"  {line}" if line else "")
    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines) + "\n"


def render_standalone(fragment: str, libraries: list[str]) -> str:
    library_text = ",".join(dict.fromkeys(libraries))
    lines = [
        r"\documentclass[tikz,border=2pt]{standalone}",
        r"\usepackage{tikz}",
    ]
    if library_text:
        lines.append(r"\usetikzlibrary{" + library_text + "}")
    lines.extend(
        [
            r"\usepackage{pgfplots}",
            r"\pgfplotsset{compat=1.18}",
            DIAGRAM_TIKZ_MACROS,
            r"\begin{document}",
            fragment.rstrip(),
            r"\end{document}",
            "",
        ]
    )
    return "\n".join(lines)
