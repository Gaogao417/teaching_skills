#!/usr/bin/env python3
"""validate_assignment.py — Validate assignment.yaml against schema.

Usage:
    python validate_assignment.py <input.yaml>
"""

import argparse
import sys

import yaml

VALID_TYPES = {"choice", "fillin", "problem", "short_answer", "key_idea",
               "mistake", "hint", "route", "step", "problemcard"}
VALID_VERSIONS = {"student", "teacher", "both"}
VALID_VISIBILITIES = {"student", "teacher", "both"}
VALID_FILLIN_TYPES = {"line", "paren", "circle", "blank", "rectangle"}
VALID_ANSWER_SPACE_TYPES = {"lines", "blank", "steps"}


def validate(data):
    """Validate assignment.yaml structure. Returns list of errors."""
    errors = []

    # Top-level
    if "meta" not in data:
        errors.append("Missing 'meta'")
    if "sections" not in data:
        errors.append("Missing 'sections'")

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
                if "stem" not in block:
                    errors.append(f"{bprefix} ({bid}): missing 'stem'")

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
