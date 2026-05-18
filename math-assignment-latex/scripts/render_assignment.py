#!/usr/bin/env python3
"""render_assignment.py — Render assignment.yaml to LaTeX via Jinja2 templates.

Usage:
    python render_assignment.py <input.yaml> --out <output.tex>
"""

import argparse
import os
import sys

import yaml

# Add scripts dir to path for sanitize_latex import
sys.path.insert(0, os.path.dirname(__file__))
from sanitize_latex import sanitize_latex

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


def load_yaml(path):
    """Load YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def main():
    parser = argparse.ArgumentParser(description="Render assignment.yaml to LaTeX")
    parser.add_argument("input", help="Path to assignment.yaml")
    parser.add_argument("--out", "-o", help="Output .tex file path")
    parser.add_argument("--template", "-t", help="Override template name")
    args = parser.parse_args()

    # Load
    data = load_yaml(args.input)

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
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(latex)
        print(f"Rendered: {args.out}")
    else:
        print(latex)


if __name__ == "__main__":
    main()
