#!/usr/bin/env python3
r"""检查渲染后的 .tex 文件中的常见语法错误。

用法：python check_latex.py <file.tex>

检查项：
  1. 双重转义（\\frac, \\times 等应为单反斜杠）
  2. \begin/\end 环境数量不配对
  3. 数学模式未闭合（$ 不配对）
  4. 空环境
"""

import re
import sys
from collections import Counter

LATEX_CMDS = [
    "frac", "dfrac", "tfrac", "times", "div", "cdot", "cdots",
    "ldots", "vdots", "ddots", "quad", "qquad", "enspace",
    "textbf", "textit", "emph", "underline", "overline",
    "sqrt", "sum", "prod", "int", "lim", "log", "sin", "cos",
    "tan", "to", "rightarrow", "leftarrow", "Rightarrow",
    "Leftarrow", "neq", "leq", "geq", "approx", "equiv",
    "infty", "partial", "alpha", "beta", "gamma", "delta",
    "pi", "theta", "lambda", "mu", "sigma", "omega",
    "begin", "end", "text", "mathrm", "mathbf", "mathit",
    "left", "right", "bigl", "bigr", "Bigl", "Bigr",
    "dfrac", "tfrac", "binom", "boxed", "hat", "bar", "vec",
    "paren", "fillin", "solution", "question", "problem",
]


def strip_comments(line: str) -> str:
    i = 0
    result = []
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            result.append(line[i : i + 2])
            i += 2
            continue
        if line[i] == "%":
            break
        result.append(line[i])
        i += 1
    return "".join(result)


def get_body(text: str) -> str:
    idx = text.find("\\begin{document}")
    if idx < 0:
        return ""
    return text[idx:]


def check_double_escapes(body: str) -> list[str]:
    errors = []
    pattern = re.compile(
        r"\\\\(" + "|".join(LATEX_CMDS) + r")" + r"(?![a-zA-Z])"
    )
    for i, line in enumerate(body.splitlines(), 1):
        clean = strip_comments(line)
        for m in pattern.finditer(clean):
            errors.append(
                f"L{i}: 双重转义 \\\\{m.group(1)} → 应为 \\{m.group(1)}"
            )
    return errors


def check_env_counts(body: str) -> list[str]:
    errors = []
    begin_re = re.compile(r"\\begin\{(\w+)\}")
    end_re = re.compile(r"\\end\{(\w+)\}")

    lines = [strip_comments(l) for l in body.splitlines()]
    clean = "\n".join(lines)

    begins: Counter[str] = Counter()
    ends: Counter[str] = Counter()
    for m in begin_re.finditer(clean):
        begins[m.group(1)] += 1
    for m in end_re.finditer(clean):
        ends[m.group(1)] += 1

    all_envs = set(begins.keys()) | set(ends.keys())
    for env in sorted(all_envs):
        b = begins.get(env, 0)
        e = ends.get(env, 0)
        if b != e:
            errors.append(f"\\begin{{{env}}} 出现 {b} 次，\\end{{{env}}} 出现 {e} 次")

    return errors


def check_math_delimiters(body: str) -> list[str]:
    errors = []
    in_math = False
    for i, line in enumerate(body.splitlines(), 1):
        clean = strip_comments(line)
        j = 0
        while j < len(clean):
            if clean[j] == "\\" and j + 1 < len(clean) and clean[j + 1] == "$":
                j += 2
                continue
            if clean[j] == "$":
                if j + 1 < len(clean) and clean[j + 1] == "$":
                    j += 2
                    continue
                in_math = not in_math
            j += 1
    if in_math:
        errors.append("数学模式未闭合（$ 不配对）")
    return errors


def check_empty_environments(body: str) -> list[str]:
    errors = []
    pattern = re.compile(r"\\begin\{(\w+)\}\s*\\end\{\1\}")
    for i, line in enumerate(body.splitlines(), 1):
        clean = strip_comments(line)
        m = pattern.search(clean)
        if m:
            errors.append(f"L{i}: 空 \\begin{{{m.group(1)}}} 环境")
    return errors


def main():
    if len(sys.argv) < 2:
        print("用法: python check_latex.py <file.tex>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        text = f.read()

    body = get_body(text)
    if not body:
        print(f"✗ {path}: 未找到 \\begin{{document}}", file=sys.stderr)
        sys.exit(1)

    all_errors = []
    all_errors.extend(check_double_escapes(body))
    all_errors.extend(check_env_counts(body))
    all_errors.extend(check_math_delimiters(body))
    all_errors.extend(check_empty_environments(body))

    if all_errors:
        print(f"发现 {len(all_errors)} 个问题：\n")
        for e in all_errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"✓ {path}: 未发现常见语法问题")
        sys.exit(0)


if __name__ == "__main__":
    main()
