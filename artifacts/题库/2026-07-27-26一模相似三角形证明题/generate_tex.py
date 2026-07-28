#!/usr/bin/env python3
"""Generate student.tex and teacher.tex from staging items.

Key formatting rules:
- student.tex: single \section*{}, each item is \begin{problem} with stem + diagram, no answer/solution
- teacher.tex: single \section*{}, each item has stem + diagram + answer + solution in solutionblock, proper line breaks, each problem on its own page
"""

import yaml
from pathlib import Path

STAGING = Path("/Users/gaochong/develop/teaching_skills/artifacts/题库/2026-07-27-26一模相似三角形证明题/staging/2026-一模相似三角形证明题")
OUTPUT_DIR = Path("/Users/gaochong/develop/teaching_skills/artifacts/题库/2026-07-27-26一模相似三角形证明题")

# Label for each item
LABELS = {
    "Q001": "宝山23",
    "Q002": "崇明23",
    "Q003": "奉贤23",
    "Q004": "嘉定23",
    "Q005": "闵行22",
    "Q006": "普陀23",
    "Q007": "青浦23",
    "Q008": "松江23",
    "Q009": "徐汇23",
    "Q010": "杨浦23",
}

# Diagram widths for each item (adjust based on image aspect ratio)
DIAGRAM_WIDTHS = {
    "Q001": "58mm",
    "Q002": "52mm",
    "Q003": "52mm",
    "Q004": "52mm",
    "Q005": "58mm",
    "Q006": "52mm",
    "Q007": "52mm",
    "Q008": "52mm",
    "Q009": "52mm",
    "Q010": "52mm",
}


def load_items():
    """Load all 10 items from staging."""
    items = []
    items_dir = STAGING / "items"
    for item_id in sorted(items_dir.iterdir()):
        if not item_id.is_dir():
            continue
        teacher_path = item_id / "teacher.resolved.assignment.yaml"
        if not teacher_path.exists():
            continue
        teacher = yaml.safe_load(teacher_path.read_text())
        items.append((item_id.name, teacher))
    return items


def get_diagram_path(teacher):
    """Extract diagram_col image_path from teacher assignment."""
    for section in teacher.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "problem":
                diagram = block.get("diagram_col", {})
                return diagram.get("image_path", "")
    return ""


def get_stem_latex(teacher):
    """Extract stem_latex from teacher assignment."""
    for section in teacher.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "problem":
                return block.get("stem_latex", "")
    return ""


def get_answer(teacher):
    """Extract answer from teacher assignment."""
    for section in teacher.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "problem":
                return block.get("answer", "")
    return ""


def get_solution_steps(teacher):
    """Extract solution_steps from teacher assignment."""
    for section in teacher.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "problem":
                return block.get("solution_steps", [])
    return []


def format_stem(stem):
    """Format stem for LaTeX display."""
    stem_clean = stem.replace("\n", " ").strip()
    # Split on 。 but keep the period
    parts = stem_clean.split("。")
    lines = []
    for part in parts:
        part = part.strip()
        if part:
            lines.append(f"    {part}。")
    return "\n".join(lines)


def format_solution_steps(steps):
    """Format solution steps as LaTeX solstep commands with proper line breaks."""
    parts = []
    for step in steps:
        title = step.get("title", "")
        content = step.get("content", "")
        # Split content by newlines
        content_lines = content.split("\n")
        # Join with LaTeX line breaks
        formatted_content = " \\\\\n".join(line.strip() for line in content_lines if line.strip())
        parts.append(f"    \\solstep{{{title}}}{{\n{formatted_content}\n}}")
    return "\n".join(parts)


def generate_student_tex(items):
    """Generate student.tex content."""
    lines = [
        "\\documentclass{exam-zh}",
        "\\usepackage{edu-practice}",
        "",
        "\\examsetup{",
        "  question/show-answer = false,",
        "  fillin/show-answer = false,",
        "  solution/show-solution = hide,",
        "}",
        "",
        "\\begin{document}",
        "",
        "\\section*{26一模相似三角形证明题精选}",
        "",
    ]

    for i, (item_id, teacher) in enumerate(items, 1):
        stem = get_stem_latex(teacher)
        diagram_path = get_diagram_path(teacher)
        width = DIAGRAM_WIDTHS.get(item_id, "52mm")
        # Use item-specific asset path
        asset_path = f"assets/{item_id}/{Path(diagram_path).name}"

        lines.append(f"% ---------- 第 {i} 题 ({LABELS[item_id]}) ----------")
        lines.append("")
        lines.append("\\needspace{8\\baselineskip}")
        lines.append("")
        lines.append("\\begin{problem}[points=12]")
        lines.append("  \\noindent")
        lines.append(f"  \\begin{{minipage}}[t]{{\\dimexpr\\linewidth-{width}-6mm\\relax}}")
        lines.append("    \\vspace{0pt}")
        lines.append(format_stem(stem))
        lines.append("  \\end{minipage}\\hfill")
        lines.append(f"  \\begin{{diagramcoltikz}}{{{width}}}{{}}")
        lines.append(f"  \\includegraphics[width=\\linewidth]{{\\detokenize{{{asset_path}}}}}")
        lines.append("  \\end{diagramcoltikz}")
        lines.append("  \\par\\medskip")
        lines.append("  \\answerarea[72mm]")
        lines.append("\\end{problem}")
        lines.append("")

    lines.append("\\end{document}")
    return "\n".join(lines)


def generate_teacher_tex(items):
    """Generate teacher.tex content with solutionblock and proper formatting."""
    lines = [
        "\\documentclass{exam-zh}",
        "\\usepackage{edu-practice}",
        "",
        "\\examsetup{",
        "  question/show-answer = true,",
        "  fillin/show-answer = true,",
        "  solution/show-solution = show-stay,",
        "}",
        "",
        "% ---------- 教师版解答样式 ----------",
        "\\newtcolorbox{solutionblock}{",
        "  enhanced, breakable,",
        "  colback=edu-blue-bg,",
        "  colframe=edu-blue!25,",
        "  boxrule=0pt,",
        "  borderline west={2pt}{0pt}{edu-blue!50},",
        "  arc=0pt,",
        "  left=3mm, right=3mm, top=2mm, bottom=2mm,",
        "  before skip=2mm,",
        "  after skip=3mm,",
        "  fontupper=\\small,",
        "}",
        "",
        "% 解答步骤编号",
        "\\newcounter{solstep}",
        "\\newcommand{\\solstep}[2]{%",
        "  \\stepcounter{solstep}%",
        "  \\par\\medskip",
        "  \\noindent\\hangindent=6mm",
        "  {\\color{edu-blue}\\bfseries\\textcircled{\\scriptsize\\thesolstep}\\enspace #1}\\enspace #2\\par",
        "}",
        "",
        "\\begin{document}",
        "",
        "\\section*{26一模相似三角形证明题精选}",
        "",
    ]

    for i, (item_id, teacher) in enumerate(items, 1):
        stem = get_stem_latex(teacher)
        diagram_path = get_diagram_path(teacher)
        answer = get_answer(teacher)
        solution_steps = get_solution_steps(teacher)
        width = DIAGRAM_WIDTHS.get(item_id, "52mm")
        # Use item-specific asset path
        asset_path = f"assets/{item_id}/{Path(diagram_path).name}"

        # Add \newpage before each problem (except the first) to put each on its own page
        if i > 1:
            lines.append("\\newpage")
            lines.append("")

        lines.append(f"% ---------- 第 {i} 题 ({LABELS[item_id]}) ----------")
        lines.append("")
        lines.append("\\needspace{8\\baselineskip}")
        lines.append("")
        lines.append("\\begin{problem}[points=12]")
        lines.append("  \\noindent")
        lines.append(f"  \\begin{{minipage}}[t]{{\\dimexpr\\linewidth-{width}-6mm\\relax}}")
        lines.append("    \\vspace{0pt}")
        lines.append(format_stem(stem))
        lines.append("  \\end{minipage}\\hfill")
        lines.append(f"  \\begin{{diagramcoltikz}}{{{width}}}{{}}")
        lines.append(f"  \\includegraphics[width=\\linewidth]{{\\detokenize{{{asset_path}}}}}")
        lines.append("  \\end{diagramcoltikz}")
        lines.append("  \\par\\medskip")
        lines.append("  \\answerarea[72mm]")
        lines.append("  \\setcounter{solstep}{0}")
        lines.append("  \\begin{solutionblock}")
        lines.append(f"    \\textbf{{答案：}}{answer}\\par\\medskip")
        lines.append(format_solution_steps(solution_steps))
        lines.append("  \\end{solutionblock}")
        lines.append("\\end{problem}")
        lines.append("")

    lines.append("\\end{document}")
    return "\n".join(lines)


def main():
    items = load_items()
    print(f"Loaded {len(items)} items")

    # Generate student.tex
    student_tex = generate_student_tex(items)
    student_path = OUTPUT_DIR / "student.tex"
    student_path.write_text(student_tex, encoding="utf-8")
    print(f"Generated {student_path}")

    # Generate teacher.tex
    teacher_tex = generate_teacher_tex(items)
    teacher_path = OUTPUT_DIR / "teacher.tex"
    teacher_path.write_text(teacher_tex, encoding="utf-8")
    print(f"Generated {teacher_path}")


if __name__ == "__main__":
    main()
