#!/usr/bin/env python3
"""Apply a model-rule patch when it passes registry and relation validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from model_rule_lib import (
    add_common_paths,
    apply_patch_data,
    print_result,
    read_yaml,
    validate_patch,
    validate_registry,
    validate_relations_file,
    write_yaml,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_paths(parser)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry = read_yaml(args.registry)
    relations = read_yaml(args.relations)
    patch = read_yaml(args.patch)

    if patch.get("review_status") == "rejected":
        print("rejected")
        for note in patch.get("review_notes") or []:
            print(f"  - {note}")
        raise SystemExit(3)

    if patch.get("review_status") == "applied":
        print("already_applied")
        for rid in patch.get("applied_relation_ids") or []:
            print(f"  - {rid}")
        return

    result = validate_registry(registry)
    result.extend(validate_relations_file(relations, registry))
    result.extend(validate_patch(patch, registry, relations))

    if not result.ok:
        patch["review_status"] = "needs_review"
        patch["review_notes"] = result.errors
        if not args.dry_run:
            write_yaml(args.patch, patch)
        print("needs_review")
        print_result(result)
        raise SystemExit(2)

    new_registry, new_relations, new_patch = apply_patch_data(registry, relations, patch)
    if args.dry_run:
        print("applied (dry-run)")
        for rid in new_patch.get("applied_relation_ids") or []:
            print(f"  - {rid}")
        return

    write_yaml(args.registry, new_registry)
    write_yaml(args.relations, new_relations)
    write_yaml(args.patch, new_patch)
    print("applied")
    for rid in new_patch.get("applied_relation_ids") or []:
        print(f"  - {rid}")


if __name__ == "__main__":
    main()
