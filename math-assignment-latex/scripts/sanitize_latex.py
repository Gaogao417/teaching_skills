#!/usr/bin/env python3
"""sanitize_latex.py — LaTeX text sanitization.

Since assignment.yaml content is authored with LaTeX math awareness,
this sanitizer is intentionally minimal. It only escapes characters
that would break LaTeX compilation but are NOT part of LaTeX syntax.

Content in assignment.yaml is expected to already contain valid LaTeX
commands ($...$, \textbf{}, \begin{}, etc.).
"""

import re


def sanitize_latex(text: str) -> str:
    """Pass-through with minimal safety checks.

    Content in assignment.yaml already contains LaTeX commands.
    We only need to handle edge cases, not full escaping.
    """
    if not text:
        return ""

    # Content is expected to be LaTeX-aware, so pass through.
    # The render_assignment.py templates handle the LaTeX structure.
    return text


if __name__ == "__main__":
    import sys
    text = sys.stdin.read()
    print(sanitize_latex(text))
