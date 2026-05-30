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
VALID_DUAL_LEFT_KINDS = {"hint", "mistake", "note"}


def has_any(block, keys):
    """Return True if block has a non-empty value for any key."""
    return any(block.get(key) for key in keys)


def has_content(obj, keys=("content_latex", "content", "latex")):
    """Return True if a mapping has any non-empty content field."""
    return isinstance(obj, dict) and any(obj.get(key) for key in keys)


def step_text(step):
    """Return the route-step title text used by both route and solution."""
    if not isinstance(step, dict):
        return ""
    return step.get("latex") or step.get("text") or step.get("title") or ""


def collect_route_steps(sections):
    """Collect route steps by id."""
    route_steps = {}
    duplicate_ids = set()
    for section in sections:
        for block in section.get("blocks", []):
            if block.get("type") != "route":
                continue
            for step in block.get("steps", []):
                if not isinstance(step, dict):
                    continue
                sid = step.get("id")
                if not sid:
                    continue
                if sid in route_steps:
                    duplicate_ids.add(sid)
                route_steps[sid] = step
    return route_steps, duplicate_ids


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
    route_steps, duplicate_route_step_ids = collect_route_steps(data["sections"])
    for sid in sorted(duplicate_route_step_ids):
        errors.append(f"duplicate route step id '{sid}'")

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
                else:
                    for step_i, step in enumerate(steps):
                        if not isinstance(step, dict):
                            continue
                        if step.get("id") and not step_text(step):
                            errors.append(f"{bprefix} ({bid}).steps[{step_i}]: route step with id requires latex/text/title")

            if btype in ("dual_explanation", "explanation_dual"):
                for legacy_key in ("left_title", "left_items", "right_title", "right_steps"):
                    if legacy_key in block:
                        errors.append(
                            f"{bprefix} ({bid}): legacy '{legacy_key}' is not allowed; "
                            "use side_title/side_items/solution_title/solution_step_ids"
                        )
                if not block.get("label"):
                    errors.append(f"{bprefix} ({bid}): {btype} requires 'label' such as '(1)'")
                if not block.get("stem") and not block.get("stem_latex"):
                    errors.append(f"{bprefix} ({bid}): {btype} requires 'stem_latex' or 'stem'")

                side_items = block.get("side_items")
                solution_step_ids = block.get("solution_step_ids")
                if not isinstance(side_items, list) or not side_items:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'side_items' list")
                elif side_items:
                    for li, item in enumerate(side_items):
                        iprefix = f"{bprefix} ({bid}).side_items[{li}]"
                        if not isinstance(item, dict):
                            errors.append(f"{iprefix}: side_items entries must be objects with kind/title/content")
                            continue
                        kind = item.get("kind")
                        if kind not in VALID_DUAL_LEFT_KINDS:
                            errors.append(
                                f"{iprefix}: kind must be one of {sorted(VALID_DUAL_LEFT_KINDS)}, got '{kind}'"
                            )
                        if not item.get("title"):
                            errors.append(f"{iprefix}: requires non-empty 'title'")
                        if not has_content(item):
                            errors.append(f"{iprefix}: requires one of content_latex, content, or latex")
                if not isinstance(solution_step_ids, list) or not solution_step_ids:
                    errors.append(f"{bprefix} ({bid}): {btype} requires non-empty 'solution_step_ids' list")
                elif solution_step_ids:
                    for ri, sid in enumerate(solution_step_ids):
                        sprefix = f"{bprefix} ({bid}).solution_step_ids[{ri}]"
                        if not isinstance(sid, str):
                            errors.append(f"{sprefix}: must be a route step id string")
                            continue
                        step = route_steps.get(sid)
                        if not step:
                            errors.append(f"{sprefix}: references missing route step id '{sid}'")
                            continue
                        if not step_text(step):
                            errors.append(f"{sprefix}: route step '{sid}' requires latex/text/title")
                        if not has_content(step, keys=("content_latex", "content")):
                            errors.append(f"{sprefix}: route step '{sid}' requires 'content_latex' or 'content'")

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
