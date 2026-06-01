#!/usr/bin/env python3
"""batch_yaml_review.py — Batch review assignment.yaml files against math-yaml-review checklist.

Checks:
1. LaTeX command integrity (compile-level) — tab chars, \\neq/\\times corruption, truncation
2. Markdown syntax residue (render-level) — **, ##, `code`, checkboxes
3. AI self-doubt text (content-level) — reasoning artifacts
4. Empty required fields (content-level)
5. Teacher info leak in student version (content-level)
6. Schema validation (via validate_assignment.py)

Usage:
    python batch_yaml_review.py <dir1> <dir2> ...   # review build/ dirs
    python batch_yaml_review.py --all-2026-05-19       # auto-find all today's yaml
"""

import argparse
import glob
import os
import re
import subprocess
import sys


def check_latex_integrity(content, lines):
    """Check 1: LaTeX command integrity — compile-level."""
    issues = []

    for i, line in enumerate(lines, 1):
        # Tab character in string values (should be \times, \to, \theta, etc.)
        if "\t" in line:
            issues.append(("compile", i, f"Tab character found: should be \\times/\\to/\\theta etc."))

        # Bare 'eq' after newline (should be \neq)
        if re.search(r'(?<!\\)eq\b', line) and "\\" not in line.split("eq")[0][-3:]:
            pass  # Too many false positives, skip

        # \times corruption: 'imes' preceded by tab or start
        if re.search(r'(?<!\\)imes\b', line):
            issues.append(("compile", i, f"'imes' found — likely corrupted \\times"))

        # \Leftrightarrow truncation
        if "eftrightarrow" in line and "\\L" not in line.split("eftrightarrow")[0][-5:]:
            issues.append(("compile", i, f"'eftrightarrow' found — likely truncated \\Leftrightarrow"))

        # \neq corruption: bare 'eq' after backslash context
        if re.search(r'\\ne\s*$', line):
            issues.append(("compile", i, f"Truncated \\neq detected"))

        # Check for unescaped % (comment char in LaTeX)
        if re.search(r'(?<!\\)%', line) and not line.strip().startswith("#"):
            # Only flag if it looks like it's in a YAML value (not a comment)
            if ":" in line and "%" not in line[:line.index(":")]:
                issues.append(("compile", i, f"Unescaped % in YAML value — will break LaTeX"))

    return issues


def check_markdown_residue(content, lines):
    """Check 2: Markdown syntax residue — render-level."""
    issues = []

    for i, line in enumerate(lines, 1):
        # Skip YAML structure lines (key: value) and comments
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("---") or ":" in stripped[:20]:
            # But still check values for markdown
            val_part = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
        else:
            val_part = stripped

        # **bold** markdown
        bold_matches = re.findall(r'\*\*[^*]+\*\*', val_part)
        if bold_matches:
            for m in bold_matches:
                issues.append(("render", i, f"Markdown bold: {m} — should be \\textbf{{...}}"))

        # ## heading (but not in YAML key position)
        if re.match(r'^##\s', stripped) and not stripped.startswith("## "):
            pass  # false positive
        heading_match = re.search(r':\s*##\s+\S', line)
        if heading_match:
            issues.append(("render", i, f"Markdown heading in YAML value"))

        # `code` backticks
        code_matches = re.findall(r'`[^`]+`', val_part)
        if code_matches:
            for m in code_matches:
                issues.append(("render", i, f"Markdown code: {m} — should be \\texttt{{...}} or removed"))

        # Checkboxes
        if re.search(r'-\s*\[[ x]\]', val_part):
            issues.append(("render", i, f"Markdown checkbox found — not valid in LaTeX"))

    return issues


def check_ai_self_doubt(content, lines):
    """Check 3: AI self-doubt text — content-level."""
    issues = []
    patterns = [
        r"不对", r"不是", r"等等", r"让我重新", r"让我再",
        r"重新计算", r"数据可能有误", r"需要确认",
        r"让我试试", r"可能有问题", r"我重新",
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("---"):
            continue
        for pat in patterns:
            if re.search(pat, stripped):
                issues.append(("content", i, f"AI self-doubt pattern '{pat}' found: {stripped[:80]}"))
                break  # One match per line is enough

    return issues


def check_empty_required_fields(data):
    """Check 5: Empty required fields — content-level."""
    issues = []
    meta = data.get("meta", {})
    version = meta.get("version", "student")

    sections = data.get("sections", [])
    if not sections and "problems" in data:
        for prob in data["problems"]:
            sections.extend(prob.get("sections", []))

    route_steps = {}
    for section in sections:
        for block in section.get("blocks", []):
            if block.get("type") != "route":
                continue
            for step in block.get("steps") or []:
                if isinstance(step, dict) and step.get("id"):
                    route_steps[step["id"]] = step

    for si, section in enumerate(sections):
        for bi, block in enumerate(section.get("blocks", [])):
            bid = block.get("id", f"blocks[{bi}]")
            btype = block.get("type", "")

            if btype == "choice":
                if not block.get("choices"):
                    issues.append(("content", 0, f"{bid}: choice block has empty 'choices'"))
                if not block.get("answer"):
                    issues.append(("content", 0, f"{bid}: choice block missing 'answer'"))

            elif btype == "fillin":
                if not block.get("answer"):
                    issues.append(("content", 0, f"{bid}: fillin block missing 'answer'"))

            elif btype == "problem":
                if not block.get("stem") and not block.get("stem_latex"):
                    issues.append(("content", 0, f"{bid}: problem block missing 'stem'/'stem_latex'"))

            elif btype == "variation_training":
                if not block.get("stem") and not block.get("stem_latex"):
                    issues.append(("content", 0, f"{bid}: variation_training missing 'stem'/'stem_latex'"))
                aspace = block.get("answer_space")
                if not isinstance(aspace, dict) or not aspace.get("height"):
                    issues.append(("content", 0, f"{bid}: variation_training requires answer_space.height"))

            # Check solutionblock not empty in teacher version
            if version == "teacher" and btype in ("solutionblock", "solution"):
                if not block.get("content") and not block.get("content_latex") and not block.get("items"):
                    issues.append(("content", 0, f"{bid}: empty solution in teacher version"))

            # right_steps not empty
            if "right_steps" in block and not block["right_steps"]:
                issues.append(("content", 0, f"{bid}: empty 'right_steps' list"))

            # left_items not empty
            if "left_items" in block and not block["left_items"]:
                issues.append(("content", 0, f"{bid}: empty 'left_items' list"))

            if btype in ("dual_explanation", "explanation_dual"):
                for legacy_key in ("left_title", "left_items", "right_title", "right_steps"):
                    if legacy_key in block:
                        issues.append(("compile", 0, f"{bid}: legacy '{legacy_key}' field is not allowed"))

                side_items = block.get("side_items") or []
                if not any(isinstance(item, dict) and item.get("kind") in ("hint", "mistake") for item in side_items):
                    issues.append(("content", 0, f"{bid}: side_items should include at least one hint or mistake item"))

                for idx, item in enumerate(side_items):
                    if not isinstance(item, dict):
                        issues.append(("compile", 0, f"{bid}: side_items[{idx}] uses scalar/list format"))
                        continue
                    if not item.get("kind") or not item.get("title"):
                        issues.append(("content", 0, f"{bid}: side_items[{idx}] requires kind and title"))
                    if not (item.get("content_latex") or item.get("content") or item.get("latex")):
                        issues.append(("content", 0, f"{bid}: side_items[{idx}] requires content_latex/content/latex"))

                for idx, step_id in enumerate(block.get("solution_step_ids") or []):
                    if not isinstance(step_id, str):
                        issues.append(("compile", 0, f"{bid}: solution_step_ids[{idx}] must be a route step id string"))
                        continue
                    step = route_steps.get(step_id)
                    if not step:
                        issues.append(("compile", 0, f"{bid}: solution_step_ids[{idx}] references missing route step '{step_id}'"))
                    elif not (step.get("content_latex") or step.get("content")):
                        issues.append(("content", 0, f"{bid}: route step '{step_id}' requires content_latex/content for solution rendering"))

    return issues


def check_teacher_info_leak(data, filepath):
    """Check 6: Teacher info leak in student version — content-level."""
    issues = []
    meta = data.get("meta", {})
    version = meta.get("version", "")
    student_name = meta.get("student", {}).get("name", "") if isinstance(meta.get("student"), dict) else ""

    if version != "student" or not student_name:
        return issues

    # Check blocks with visibility != "teacher"
    sections = data.get("sections", [])
    if not sections and "problems" in data:
        for prob in data["problems"]:
            sections.extend(prob.get("sections", []))

    content_str = str(data)  # Simple brute-force check

    leak_patterns = [
        (student_name, f"Student name '{student_name}' in student version"),
        ("教学节奏", "Teaching strategy text in student version"),
        ("档位判断", "Teaching strategy text in student version"),
        ("eduTeacherNote", "Teacher note environment in student version"),
        ("teachernote", "Teacher note environment in student version"),
    ]

    for pattern, desc in leak_patterns:
        if pattern in content_str:
            issues.append(("content", 0, desc))

    return issues


def run_schema_validation(filepath):
    """Run validate_assignment.py for schema checks."""
    script = os.path.join(os.path.dirname(__file__), "validate_assignment.py")
    try:
        result = subprocess.run(
            [sys.executable, script, filepath],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return [("compile", 0, f"Schema validation failed: {result.stderr.strip()}")]
        return []
    except Exception as e:
        return [("compile", 0, f"Schema validation error: {e}")]


def review_file(filepath):
    """Review a single yaml file. Returns (pass, issues_list)."""
    issues = []

    # Read raw content
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")

    # Check 1: LaTeX integrity
    issues.extend(check_latex_integrity(content, lines))

    # Check 2: Markdown residue
    issues.extend(check_markdown_residue(content, lines))

    # Check 3: AI self-doubt
    issues.extend(check_ai_self_doubt(content, lines))

    # Parse YAML for structural checks
    try:
        import yaml
        data = yaml.safe_load(content)
    except Exception as e:
        issues.append(("compile", 0, f"YAML parse error: {e}"))
        return False, issues

    # Check 4 (answer consistency) — simplified: just verify answer field exists for choice/fillin
    sections = data.get("sections", [])
    if not sections and "problems" in data:
        for prob in data["problems"]:
            sections.extend(prob.get("sections", []))

    for si, section in enumerate(sections):
        for bi, block in enumerate(section.get("blocks", [])):
            btype = block.get("type", "")
            bid = block.get("id", "")
            if btype == "choice" and not block.get("answer"):
                issues.append(("content", 0, f"{bid}: choice missing answer field"))

    # Check 5: Empty required fields
    issues.extend(check_empty_required_fields(data))

    # Check 6: Teacher info leak
    issues.extend(check_teacher_info_leak(data, filepath))

    # Schema validation
    issues.extend(run_schema_validation(filepath))

    # Determine pass/fail
    compile_issues = [i for i in issues if i[0] == "compile"]
    render_issues = [i for i in issues if i[0] == "render"]
    content_issues = [i for i in issues if i[0] == "content"]

    if compile_issues:
        passed = False
    elif len(render_issues) >= 3:
        passed = False
    elif len(content_issues) >= 5:
        passed = False
    else:
        passed = True

    return passed, issues


def main():
    parser = argparse.ArgumentParser(description="Batch review assignment.yaml files")
    parser.add_argument("dirs", nargs="*", help="Directories containing *.assignment.yaml files")
    parser.add_argument("--all-today", action="store_true", help="Auto-find all 2026-05-19 yaml files")
    args = parser.parse_args()

    yaml_files = []

    if args.all_today:
        yaml_files = sorted(glob.glob("artifacts/**/*2026-05-19*/build/*.assignment.yaml", recursive=True))
    else:
        for d in args.dirs:
            yaml_files.extend(sorted(glob.glob(os.path.join(d, "*.assignment.yaml"))))

    if not yaml_files:
        print("No assignment.yaml files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(yaml_files)} yaml files to review.\n")

    results = {"pass": [], "fail": []}

    for fpath in yaml_files:
        rel = os.path.relpath(fpath)
        passed, issues = review_file(fpath)

        if passed:
            results["pass"].append(fpath)
            print(f"PASS  {rel}")
        else:
            results["fail"].append(fpath)
            print(f"FAIL  {rel}")
            for level, lineno, desc in issues:
                loc = f"L{lineno}" if lineno else "—"
                symbol = {"compile": "X", "render": "!", "content": "?"}[level]
                print(f"  [{symbol}] {loc}: {desc}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Results: {len(results['pass'])} passed, {len(results['fail'])} failed out of {len(yaml_files)}")

    if results["pass"]:
        print(f"\nPassed files:")
        for f in results["pass"]:
            print(f"  {os.path.relpath(f)}")

    if results["fail"]:
        print(f"\nFailed files (need manual fix):")
        for f in results["fail"]:
            print(f"  {os.path.relpath(f)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
