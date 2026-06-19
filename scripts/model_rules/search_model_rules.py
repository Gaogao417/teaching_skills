#!/usr/bin/env python3
"""Search canonical model-rule relations by type, topic, signature, or id."""

from __future__ import annotations

import argparse

from model_rule_lib import add_common_paths, base_type, dump_yaml, read_yaml


def relation_types(relation: dict, side: str) -> set[str]:
    ports = relation.get("ports", {}).get(side, {}) or {}
    out: set[str] = set()
    for value in ports.values():
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, list):
            out.update(v for v in value if isinstance(v, str))
    return out


def type_matches(query: str, available: set[str]) -> bool:
    return query in available or query in {base_type(t) for t in available}


def relation_signature(relation: dict) -> str:
    inputs = sorted(relation_types(relation, "inputs"))
    outputs = sorted(relation_types(relation, "outputs"))
    return " + ".join(inputs) + " -> " + " + ".join(outputs)


def matches(relation: dict, args: argparse.Namespace) -> bool:
    if args.relation_id and relation.get("relation_id") != args.relation_id:
        return False
    if args.topic:
        topics = relation.get("topic_tags") or []
        if not any(args.topic in topic for topic in topics):
            return False
    if args.input_type and not type_matches(args.input_type, relation_types(relation, "inputs")):
        return False
    if args.output_type and not type_matches(args.output_type, relation_types(relation, "outputs")):
        return False
    if args.signature and args.signature != relation_signature(relation):
        return False
    return True


def summarize(relation: dict) -> dict:
    return {
        "relation_id": relation.get("relation_id"),
        "name": relation.get("name"),
        "model_family_id": relation.get("model_family_id"),
        "topic_tags": relation.get("topic_tags") or [],
        "input_types": sorted(relation_types(relation, "inputs")),
        "output_types": sorted(relation_types(relation, "outputs")),
        "signature": relation_signature(relation),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_paths(parser)
    parser.add_argument("--topic")
    parser.add_argument("--input-type")
    parser.add_argument("--output-type")
    parser.add_argument("--signature")
    parser.add_argument("--relation-id")
    parser.add_argument("--full", action="store_true", help="Print full relation records instead of summaries")
    args = parser.parse_args()

    data = read_yaml(args.relations)
    found = [r for r in data.get("relations") or [] if matches(r, args)]
    print(dump_yaml({"count": len(found), "relations": found if args.full else [summarize(r) for r in found]}))


if __name__ == "__main__":
    main()
