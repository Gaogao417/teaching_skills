#!/usr/bin/env python3
"""validate_assignment.py — Validate assignment.yaml against schema.

Usage:
    python validate_assignment.py <input.yaml>
"""

import argparse
from collections import defaultdict
import os
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
    "diagram",
    "diagram_row",
}
VALID_VERSIONS = {"student", "teacher", "both"}
VALID_VISIBILITIES = {"student", "teacher", "both"}
VALID_FILLIN_TYPES = {"line", "paren", "circle", "blank", "rectangle"}
VALID_ANSWER_SPACE_TYPES = {"lines", "blank", "steps"}
VALID_DIAGRAM_VARIANTS = {"prompt", "solution"}
VALID_DISCLOSURE_POLICIES = {"clean", "annotated"}


def has_any(block, keys):
    """Return True if block has a non-empty value for any key."""
    return any(block.get(key) for key in keys)


def validate_diagram_obj(obj, prefix, errors, base_dir=None):
    """Validate a diagram object used in diagram_col/prompt_diagram/answer_space."""
    if not isinstance(obj, dict):
        errors.append(f"{prefix}: diagram payload must be a dict")
        return
    image_path = obj.get("image_path")
    if not image_path:
        errors.append(f"{prefix}: diagram payload requires 'image_path'")
    elif base_dir:
        candidate = image_path if os.path.isabs(image_path) else os.path.join(base_dir, image_path)
        if not os.path.exists(candidate):
            errors.append(f"{prefix}: image_path does not exist: {image_path}")
    variant = obj.get("variant") or obj.get("diagram_variant")
    if variant and variant not in VALID_DIAGRAM_VARIANTS:
        errors.append(f"{prefix}: invalid diagram variant '{variant}'")
    disclosure = obj.get("disclosure_policy")
    if disclosure and disclosure not in VALID_DISCLOSURE_POLICIES:
        errors.append(f"{prefix}: invalid disclosure_policy '{disclosure}'")
    if obj.get("reuse_from") and not isinstance(obj.get("reuse_from"), str):
        errors.append(f"{prefix}: reuse_from must be a string diagram_job_id")
    if obj.get("diagram_job_id") and not isinstance(obj.get("diagram_job_id"), str):
        errors.append(f"{prefix}: diagram_job_id must be a string")


def collect_diagram_refs(block, owner):
    refs = []

    def add(obj, field):
        if isinstance(obj, dict) and obj.get("image_path"):
            refs.append(
                {
                    "owner": owner,
                    "field": field,
                    "image_path": obj.get("image_path"),
                    "diagram_job_id": obj.get("diagram_job_id"),
                    "reuse_from": obj.get("reuse_from"),
                }
            )

    for key in ("diagram_col", "prompt_diagram"):
        add(block.get(key), key)
    if block.get("type") == "diagram":
        add(block, "diagram")
    if block.get("type") == "diagram_row":
        for i, item in enumerate(block.get("items") or block.get("diagrams") or []):
            add(item, f"diagram_row[{i}]")
    aspace = block.get("answer_space") if isinstance(block.get("answer_space"), dict) else None
    if aspace:
        for key in ("diagram_col", "diagram"):
            add(aspace.get(key), f"answer_space.{key}")
        for pi, part in enumerate(aspace.get("parts") or []):
            if not isinstance(part, dict):
                continue
            for key in ("diagram_col", "prompt_diagram", "diagram"):
                add(part.get(key), f"answer_space.parts[{pi}].{key}")
    return refs


def validate(data, base_dir=None):
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
    diagram_refs = []
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

            if btype == "diagram":
                validate_diagram_obj(block, f"{bprefix} ({bid})", errors, base_dir)

            if btype == "diagram_row":
                items = block.get("items") or block.get("diagrams")
                if not isinstance(items, list) or not items:
                    errors.append(f"{bprefix} ({bid}): diagram_row requires non-empty 'items' list")
                else:
                    for ii, item in enumerate(items):
                        validate_diagram_obj(item, f"{bprefix} ({bid}).items[{ii}]", errors, base_dir)

            if btype in ("method_reminder", "reminder"):
                items = block.get("items")
                if not isinstance(items, list) or not items:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'items' list")

            # Prompt-side diagram columns for questions. Rendering templates use
            # these fields to avoid inferring geometry layout from prose.
            for key in ("diagram_col", "prompt_diagram"):
                if block.get(key):
                    validate_diagram_obj(block[key], f"{bprefix} ({bid}).{key}", errors, base_dir)

            # Answer space
            aspace = block.get("answer_space")
            if aspace:
                at = aspace.get("type")
                if at and at not in VALID_ANSWER_SPACE_TYPES:
                    errors.append(f"{bprefix} ({bid}): invalid answer_space type '{at}'")
                for key in ("diagram_col", "diagram"):
                    if aspace.get(key):
                        validate_diagram_obj(aspace[key], f"{bprefix} ({bid}).answer_space.{key}", errors, base_dir)
                parts = aspace.get("parts")
                if parts is not None:
                    if not isinstance(parts, list) or not parts:
                        errors.append(f"{bprefix} ({bid}).answer_space.parts: must be a non-empty list")
                    else:
                        for pi, part in enumerate(parts):
                            if not isinstance(part, dict):
                                errors.append(f"{bprefix} ({bid}).answer_space.parts[{pi}]: must be a dict")
                                continue
                            for key in ("diagram_col", "prompt_diagram", "diagram"):
                                if part.get(key):
                                    validate_diagram_obj(
                                        part[key],
                                        f"{bprefix} ({bid}).answer_space.parts[{pi}].{key}",
                                        errors,
                                        base_dir,
                                    )

            diagram_refs.extend(collect_diagram_refs(block, bid or f"{bprefix}"))

            if btype == "diagram_row":
                prior_question_seen = any(
                    prev.get("type") in ("fillin", "choice", "problem", "short_answer")
                    for prev in section.get("blocks", [])[:bi]
                )
                if not prior_question_seen:
                    errors.append(
                        f"{bprefix} ({bid}): diagram_row must appear after its related question blocks, not before them"
                    )

    by_path = defaultdict(list)
    for ref in diagram_refs:
        by_path[ref["image_path"]].append(ref)
    for image_path, refs in by_path.items():
        owners = {ref["owner"] for ref in refs}
        if len(owners) <= 1:
            continue
        missing_reuse = [
            f"{ref['owner']}.{ref['field']}"
            for ref in refs
            if not ref.get("reuse_from")
        ]
        if len(missing_reuse) > 1:
            errors.append(
                "diagram image reused by multiple blocks without explicit reuse_from: "
                f"{image_path} ({', '.join(missing_reuse)})"
            )

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

    errors = validate(data, base_dir=os.path.dirname(os.path.abspath(args.input)))

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
