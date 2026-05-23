#!/usr/bin/env python3
"""render_assignment.py — Render assignment.yaml to LaTeX via Jinja2 templates.

Usage:
    python render_assignment.py <input.yaml> --out <output.tex>
"""

import argparse
import os
import re
import sys

import yaml

from sanitize_latex import sanitize_latex, sanitize_latex_data

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    print("Error: jinja2 not installed. Run: pip install jinja2", file=sys.stderr)
    sys.exit(1)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "templates")

TEMPLATE_MAP = {
    "exam-zh-practice": "exam-zh-practice.tex.j2",
    "exam-zh-explanation": "exam-zh-explanation.tex.j2",
    "exam-zh-homework": "exam-zh-homework.tex.j2",
    "exam-zh-solution": "exam-zh-solution.tex.j2",
}


def latex_escape(value):
    """Jinja2 filter: escape LaTeX special chars."""
    if value is None:
        return ""
    return sanitize_latex(str(value))


def _fix_yaml_escapes(raw: str) -> str:
    """Pre-process YAML to preserve LaTeX backslash commands in double-quoted strings.

    yaml.safe_load() interprets \\t as TAB, \\n as newline, \\r as CR inside
    double-quoted strings.  This corrupts LaTeX commands like \\times, \\neq, \\to.

    We double any single backslash (not already doubled, not before a quote)
    inside double-quoted regions so that safe_load preserves the literal
    backslash.  Single-quoted strings and block scalars are left untouched
    because YAML does not process escapes in those contexts.

    Exception: \\n \\t \\r are standard YAML escapes that the author may
    intend as actual whitespace (paragraph breaks, alignment).  We only
    double them when followed by a letter (e.g. \\neq → keep as LaTeX).
    """
    result: list[str] = []
    i = 0
    in_dq = False
    n = len(raw)
    while i < n:
        c = raw[i]
        if not in_dq:
            if c == '"':
                in_dq = True
            result.append(c)
            i += 1
        else:
            # Inside a double-quoted string
            if c == '\\' and i + 1 < n:
                nxt = raw[i + 1]
                if nxt == '"' or nxt == '\\':
                    # Legitimate YAML escapes — keep as-is
                    result.append(c)
                    result.append(nxt)
                    i += 2
                elif nxt in 'ntr' and (i + 2 >= n or not (raw[i + 2].isascii() and raw[i + 2].islower())):
                    # \n \t \r NOT followed by a lowercase ASCII letter → intentional YAML
                    # whitespace escape (paragraph break, etc.) — keep as-is.
                    # LaTeX commands start with lowercase ASCII (e.g. \neq, \theta).
                    result.append(c)
                    result.append(nxt)
                    i += 2
                else:
                    # Single backslash before a regular char — double it
                    # so safe_load produces a literal backslash
                    result.append('\\\\')
                    i += 1
            elif c == '"':
                in_dq = False
                result.append(c)
                i += 1
            else:
                result.append(c)
                i += 1
    return ''.join(result)


def load_yaml(path):
    """Load YAML file, preserving LaTeX backslash commands."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    raw = _fix_yaml_escapes(raw)
    return yaml.safe_load(raw)


def flatten_problems(data):
    """Convert multi-problem format to flat sections format.

    If `problems` array exists (and `sections` doesn't), flatten each problem's
    sections into a single top-level sections list with page-break separators.

    Page-break strategy:
    - explanation template: each problem = one example, auto-break between examples
    - practice template: sections flow naturally, no auto-break
    - YAML can override via problem.layout.break_before
    """
    if "problems" not in data or "sections" in data:
        return data

    template = data.get("render", {}).get("template", "exam-zh-practice")
    is_explanation = template == "exam-zh-explanation"

    flat = []
    for i, prob in enumerate(data["problems"]):
        label = prob.get("label", f"第 {i + 1} 题")
        sections = prob.get("sections", [])
        if not sections:
            continue

        # Auto page-break: only for explanation (one example per page),
        # not for practice (sections should flow). YAML override wins.
        yaml_break = prob.get("layout", {}).get("break_before", None)
        if yaml_break is not None:
            should_break = yaml_break
        elif is_explanation:
            should_break = i > 0
        else:
            should_break = False

        flat.append({
            "id": f"problem-header-{i}",
            "title": label,
            "show_title": True,
            "layout": {"break_before": should_break},
            "blocks": [],
        })
        flat.extend(sections)

    data["sections"] = flat
    return data


def validate_assignment(data):
    """Basic validation of assignment data."""
    errors = []

    if "meta" not in data:
        errors.append("Missing top-level 'meta' key")
    else:
        meta = data["meta"]
        if "title" not in meta:
            errors.append("meta.title is required")
        if "version" not in meta:
            errors.append("meta.version is required")
        elif meta["version"] not in ("student", "teacher", "both"):
            errors.append(f"Invalid version: {meta['version']}")

    if "sections" not in data:
        errors.append("Missing top-level 'sections' key")
    else:
        seen_ids = set()
        for i, section in enumerate(data["sections"]):
            if "blocks" not in section:
                errors.append(f"Section {i} missing 'blocks'")
            for block in section.get("blocks", []):
                bid = block.get("id", f"<unnamed in section {i}>")
                if bid in seen_ids:
                    errors.append(f"Duplicate block id: {bid}")
                seen_ids.add(bid)
                if "type" not in block:
                    errors.append(f"Block {bid} missing 'type'")

    return errors


def render(data, template_name=None):
    """Render assignment data to LaTeX string."""
    # Determine template
    render_cfg = data.get("render", {})
    tpl_name = template_name or render_cfg.get("template", "exam-zh-practice")
    tpl_file = TEMPLATE_MAP.get(tpl_name)
    if not tpl_file:
        print(f"Error: Unknown template '{tpl_name}'. Available: {list(TEMPLATE_MAP.keys())}",
              file=sys.stderr)
        sys.exit(1)

    # Setup Jinja2 with custom delimiters to avoid LaTeX conflicts
    # <% %> for blocks, <%= %> for variables, <# #> for comments
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(default=False),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<%=",
        variable_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
    )
    env.filters["latex_escape"] = latex_escape

    template = env.get_template(tpl_file)

    # Render
    latex = template.render(
        meta=data.get("meta", {}),
        render=render_cfg,
        sections=data.get("sections", []),
    )

    return latex


def deliverable_name(yaml_stem: str) -> str:
    """Map yaml basename to canonical deliverable name per pipeline convention.

    Examples:
        02-student-explanation       → 02-explanation
        02a-student-explanation      → 02a-explanation
        02-explanation               → 02-explanation (unchanged)
        03-adaptive-practice.student → 03-practice-student
        03-adaptive-practice.teacher → 03-practice-teacher
        03a-practice.student         → 03a-practice-student
        03b-practice.teacher         → 03b-practice-teacher
    """
    name = yaml_stem
    # 02-student-explanation → 02-explanation
    name = re.sub(r'^(02\w*)-student-', r'\1-', name)
    # 03-adaptive-practice.student → 03-practice-student
    name = re.sub(r'^(0[3-9]\w*)-adaptive-practice\.(student|teacher)', r'\1-practice-\2', name)
    # 03a-practice.student → 03a-practice-student (dot → dash)
    name = re.sub(r'^(0[3-9]\w*-practice)\.(student|teacher)', r'\1-\2', name)
    return name


def default_output_path(yaml_path: str) -> str:
    """Derive default output .tex path from yaml path using deliverable naming."""
    yaml_dir = os.path.dirname(os.path.abspath(yaml_path))
    topic_dir = os.path.dirname(yaml_dir)  # build/ → topic/
    yaml_stem = os.path.splitext(os.path.basename(yaml_path))[0]
    # Strip .assignment suffix if present
    if yaml_stem.endswith(".assignment"):
        yaml_stem = yaml_stem[: -len(".assignment")]
    tex_name = deliverable_name(yaml_stem) + ".tex"
    return os.path.join(topic_dir, tex_name)


def main():
    parser = argparse.ArgumentParser(description="Render assignment.yaml to LaTeX")
    parser.add_argument("input", help="Path to assignment.yaml")
    parser.add_argument("--out", "-o", help="Output .tex file path (default: auto-derived from yaml name)")
    parser.add_argument("--template", "-t", help="Override template name")
    args = parser.parse_args()

    # Load
    data = load_yaml(args.input)
    data = sanitize_latex_data(data)

    # Flatten multi-problem format
    flatten_problems(data)

    # Validate
    errors = validate_assignment(data)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # Render
    latex = render(data, template_name=args.template)

    # Output
    out_path = args.out or default_output_path(args.input)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(latex)
    print(f"Rendered: {out_path}")


if __name__ == "__main__":
    main()
