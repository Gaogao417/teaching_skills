#!/usr/bin/env python3
"""validate_assignment.py — Validate assignment.yaml against schema.

Usage:
    python validate_assignment.py <input.yaml>
"""

import argparse
import sys

import yaml

VALID_TYPES = {
    "choice",
    "fillin",
    "problem",
    "short_answer",
    "key_idea",
    "reading_tip",
    "mistake",
    "hint",
    "route",
    "step",
    "problemcard",
    "dual_explanation",
    "explanation_dual",
    "summary_dual",
    "answer_reminder",
    "answer",
    "answers",
    "method_reminder",
    "reminder",
    "solution",
}
VALID_VERSIONS = {"student", "teacher", "both"}
VALID_VISIBILITIES = {"student", "teacher", "both"}
VALID_FILLIN_TYPES = {"line", "paren", "circle", "blank", "rectangle"}
VALID_ANSWER_SPACE_TYPES = {"lines", "blank", "steps"}


def has_any(block, keys):
    """Return True if block has a non-empty value for any key."""
    return any(block.get(key) for key in keys)


def validate(data):
    """Validate assignment.yaml structure. Returns list of errors."""
    errors = []

    # Top-level
    if "meta" not in data:
        errors.append("Missing 'meta'")
    if "sections" not in data and "problems" not in data:
        errors.append("Missing 'sections' or 'problems'")

    # Flatten problems into sections for unified validation
    if "sections" not in data and "problems" in data:
        flat = []
        for i, prob in enumerate(data["problems"]):
            flat.extend(prob.get("sections", []))
        data = {**data, "sections": flat}

    if errors:
        return errors  # Can't continue without these

    # Meta
    meta = data["meta"]
    if "title" not in meta:
        errors.append("meta.title is required")
    if "version" not in meta:
        errors.append("meta.version is required")
    elif meta["version"] not in VALID_VERSIONS:
        errors.append(f"meta.version must be one of {VALID_VERSIONS}, got '{meta['version']}'")

    # Sections
    seen_ids = set()
    for si, section in enumerate(data["sections"]):
        prefix = f"sections[{si}]"

        if "blocks" not in section:
            errors.append(f"{prefix}: missing 'blocks'")
            continue

        for bi, block in enumerate(section["blocks"]):
            bprefix = f"{prefix}.blocks[{bi}]"

            # ID uniqueness
            bid = block.get("id")
            if not bid:
                errors.append(f"{bprefix}: missing 'id'")
            elif bid in seen_ids:
                errors.append(f"{bprefix}: duplicate id '{bid}'")
            else:
                seen_ids.add(bid)

            # Type
            btype = block.get("type")
            if not btype:
                errors.append(f"{bprefix}: missing 'type'")
            elif btype not in VALID_TYPES:
                errors.append(f"{bprefix}: unknown type '{btype}'")

            # Stem required for question types
            if btype in ("choice", "fillin", "problem", "short_answer"):
                if "stem" not in block and "stem_latex" not in block:
                    errors.append(f"{bprefix} ({bid}): missing 'stem' or 'stem_latex'")

            # Choice-specific
            if btype == "choice":
                if "choices" not in block:
                    errors.append(f"{bprefix} ({bid}): choice type requires 'choices'")
                elif not isinstance(block["choices"], dict):
                    errors.append(f"{bprefix} ({bid}): choices must be a dict")
                if "answer" not in block:
                    errors.append(f"{bprefix} ({bid}): choice type requires 'answer'")

            # Fillin-specific
            if btype == "fillin":
                if "answer" not in block:
                    errors.append(f"{bprefix} ({bid}): fillin type requires 'answer'")
                ft = block.get("fillin_type")
                if ft and ft not in VALID_FILLIN_TYPES:
                    errors.append(f"{bprefix} ({bid}): invalid fillin_type '{ft}'")

            # Explanation-page semantic blocks
            if btype == "reading_tip":
                if not has_any(block, ("items", "tips", "content", "content_latex")):
                    errors.append(f"{bprefix} ({bid}): reading_tip requires items, tips, content, or content_latex")

            if btype == "route":
                steps = block.get("steps")
                if not isinstance(steps, list) or not steps:
                    errors.append(f"{bprefix} ({bid}): route requires non-empty 'steps' list")

            if btype in ("dual_explanation", "explanation_dual"):
                left_items = block.get("left_items")
                right_steps = block.get("right_steps")
                if not isinstance(left_items, list) or not left_items:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'left_items' list")
                if not isinstance(right_steps, list) or not right_steps:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'right_steps' list")

            if btype == "solution":
                items = block.get("items")
                if not isinstance(items, list) or not items:
                    errors.append(f"{bprefix} ({bid}): solution requires non-empty 'items' list")

            if btype in ("summary_dual", "answer_reminder"):
                left_items = block.get("left_items")
                right_items = block.get("right_items")
                if not isinstance(left_items, list) or not left_items:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'left_items' list")
                if not isinstance(right_items, list) or not right_items:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'right_items' list")

            if btype in ("answer", "answers"):
                if not has_any(block, ("items", "content", "content_latex")):
                    errors.append(f"{bprefix} ({bid}): {btype} requires items, content, or content_latex")

            if btype in ("method_reminder", "reminder"):
                items = block.get("items")
                if not isinstance(items, list) or not items:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'items' list")

            # Answer space
            aspace = block.get("answer_space")
            if aspace:
                at = aspace.get("type")
                if at and at not in VALID_ANSWER_SPACE_TYPES:
                    errors.append(f"{bprefix} ({bid}): invalid answer_space type '{at}'")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate assignment.yaml")
    parser.add_argument("input", help="Path to assignment.yaml")
    parser.add_argument("--strict", action="store_true", help="Warn on missing optional fields")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Flatten problems into sections for display counting
    if "sections" not in data and "problems" in data:
        flat = []
        for prob in data["problems"]:
            flat.extend(prob.get("sections", []))
        data["sections"] = flat

    errors = validate(data)

    if errors:
        print(f"Validation FAILED ({len(errors)} errors):", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Validation passed: {args.input}")
        meta = data.get("meta", {})
        sections = data.get("sections", [])
        block_count = sum(len(s.get("blocks", [])) for s in sections)
        print(f"  Title: {meta.get('title', 'N/A')}")
        print(f"  Version: {meta.get('version', 'N/A')}")
        print(f"  Sections: {len(sections)}")
        print(f"  Blocks: {block_count}")


if __name__ == "__main__":
    main()
