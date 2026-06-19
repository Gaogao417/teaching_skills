#!/usr/bin/env python3
"""Validate model-rule registry, relations, and optional patch files."""

from __future__ import annotations

import argparse
from pathlib import Path

from model_rule_lib import (
    add_common_paths,
    exit_for_result,
    print_result,
    read_yaml,
    validate_patch,
    validate_registry,
    validate_relations_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_paths(parser)
    parser.add_argument("--patch", type=Path, help="Optional patch YAML to validate against registry/relations")
    args = parser.parse_args()

    registry = read_yaml(args.registry)
    relations = read_yaml(args.relations)

    result = validate_registry(registry)
    result.extend(validate_relations_file(relations, registry))
    if args.patch:
        result.extend(validate_patch(read_yaml(args.patch), registry, relations))

    if result.ok:
        print("model rule validation passed")
    exit_for_result(result)


if __name__ == "__main__":
    main()

