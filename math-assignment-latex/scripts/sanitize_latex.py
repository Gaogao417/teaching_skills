#!/usr/bin/env python3
"""sanitize_latex.py — LaTeX text sanitization.

Since assignment.yaml content is authored with LaTeX math awareness,
this sanitizer focuses on catching damage that slipped through YAML
loading (e.g. literal tab / CR characters) and common LLM generation
artefacts (Markdown syntax, AI self-doubt text).

Content in assignment.yaml is expected to already contain valid LaTeX
commands ($...$, \\textbf{}, \\begin{}, etc.).
"""

import re
import sys

_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*")

_AI_DOUBT_PATTERNS = [
    "不对", "让我重新", "等等，", "不是，", "重新计算",
    "让我确认", "让我检查", "让我再", "数据可能有误",
]


def sanitize_latex(text: str) -> str:
    """Sanitize a string that will be embedded in a LaTeX document.

    1. Replace residual tab / CR characters from YAML escape damage.
    2. Replace Markdown ``**bold**`` with ``\\textbf{bold}``.
    3. Warn (stderr) on AI self-doubt phrases.
    """
    if not text:
        return ""

    # 1. Residual control characters from YAML escape damage.
    #    _fix_yaml_escapes() in render_assignment.py handles the root cause,
    #    but this catches anything that slips through (e.g. block scalars,
    #    manual edits, etc.).
    if "\t" in text:
        text = text.replace("\t", "\\t")
    if "\r" in text:
        text = text.replace("\r", "\\r")

    # 2. Markdown **bold** → \textbf{bold}
    text = _MARKDOWN_BOLD.sub(r"\\textbf{\1}", text)

    # 3. Warn on AI self-doubt phrases (non-fatal, just a heads-up)
    for phrase in _AI_DOUBT_PATTERNS:
        if phrase in text:
            print(
                f"  ⚠ sanitize: AI self-doubt phrase \"{phrase}\" found in text",
                file=sys.stderr,
            )
            break  # one warning per field is enough

    return text


if __name__ == "__main__":
    text = sys.stdin.read()
    print(sanitize_latex(text))
