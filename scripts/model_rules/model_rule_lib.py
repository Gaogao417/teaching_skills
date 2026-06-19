#!/usr/bin/env python3
"""Utilities for the lightweight model-rule YAML library."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("PyYAML is required to use model rule scripts.") from exc


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "model_rules" / "type_registry.yaml"
DEFAULT_RELATIONS = ROOT / "model_rules" / "relations.yaml"


REQUIRED_PATCH_FIELDS = {
    "source_analysis_path",
    "model_family",
    "type_registry_patch",
    "relations",
    "review_status",
}

REQUIRED_RELATION_FIELDS = {
    "relation_id",
    "model_family_id",
    "topic_tags",
    "propositions",
    "constraints",
    "relation",
    "ports",
    "generation_notes",
    "non_examples",
}


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def extend(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def registry_types(registry: dict[str, Any]) -> dict[str, Any]:
    types = registry.get("types")
    return types if isinstance(types, dict) else {}


def known_type_ids(registry: dict[str, Any]) -> set[str]:
    return set(registry_types(registry).keys())


def aliases_by_type(registry: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for type_id, spec in registry_types(registry).items():
        aliases = set(spec.get("aliases") or [])
        aliases.add(type_id)
        out[type_id] = aliases
    return out


def alias_owner_map(registry: dict[str, Any]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for type_id, aliases in aliases_by_type(registry).items():
        for alias in aliases:
            owners.setdefault(alias, type_id)
    return owners


def collect_port_types(relation: dict[str, Any]) -> list[str]:
    ports = relation.get("ports") or {}
    found: list[str] = []
    for side in ("inputs", "outputs"):
        entries = ports.get(side) or {}
        if isinstance(entries, dict):
            for value in entries.values():
                if isinstance(value, str):
                    found.append(value)
                elif isinstance(value, list):
                    found.extend(v for v in value if isinstance(v, str))
    return found


def base_type(type_id: str) -> str:
    if type_id.endswith("[]"):
        return type_id[:-2]
    return type_id


def relation_constraint_text(relation: dict[str, Any]) -> str:
    values: list[str] = []
    constraints = relation.get("constraints") or {}
    if isinstance(constraints, dict):
        values.extend(str(v) for v in constraints.values())
    elif isinstance(constraints, list):
        values.extend(str(v) for v in constraints)
    rel = relation.get("relation") or {}
    if isinstance(rel.get("constraints"), list):
        values.extend(str(v) for v in rel.get("constraints") or [])
    return "\n".join(values)


def relation_outputs_candidate_set(relation: dict[str, Any]) -> bool:
    return any(t.startswith("CandidateSet<") for t in collect_port_types(relation))


def validate_registry(registry: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    types = registry_types(registry)
    if not types:
        result.error("type registry has no types")
        return result

    alias_to_type: dict[str, str] = {}
    for type_id, spec in types.items():
        if not isinstance(spec, dict):
            result.error(f"type {type_id} must be a mapping")
            continue
        aliases = spec.get("aliases") or []
        if not isinstance(aliases, list):
            result.error(f"type {type_id} aliases must be a list")
            aliases = []
        for alias in [type_id, *aliases]:
            existing = alias_to_type.get(alias)
            if existing and existing != type_id:
                result.error(f"alias {alias!r} belongs to both {existing} and {type_id}")
            alias_to_type[alias] = type_id
        for feed_type in spec.get("can_feed") or []:
            if feed_type not in types:
                result.error(f"type {type_id} can_feed unknown type {feed_type}")

    for item in registry.get("compatibility") or []:
        src = item.get("from")
        dst = item.get("to")
        if src not in types:
            result.error(f"compatibility source {src} is unknown")
        if dst not in types:
            result.error(f"compatibility target {dst} is unknown")

    for item in registry.get("construction_rules") or []:
        output = item.get("output")
        if output not in types:
            result.error(f"construction rule output {output} is unknown")
        for src in item.get("from") or []:
            if src not in types:
                result.error(f"construction rule input {src} is unknown")
    return result


def validate_relation(
    relation: dict[str, Any],
    registry: dict[str, Any],
    existing_ids: set[str] | None = None,
    *,
    allow_existing_id: bool = False,
) -> ValidationResult:
    result = ValidationResult()
    relation_id = relation.get("relation_id", "<missing>")
    missing = sorted(REQUIRED_RELATION_FIELDS - set(relation.keys()))
    if missing:
        result.error(f"relation {relation_id} missing required fields: {', '.join(missing)}")

    if existing_ids and relation_id in existing_ids and not allow_existing_id:
        result.error(f"relation_id {relation_id} already exists")

    rel = relation.get("relation")
    if not isinstance(rel, dict):
        result.error(f"relation {relation_id} relation must be a mapping")
    else:
        for key in ("given", "derive"):
            if not rel.get(key):
                result.error(f"relation {relation_id} relation.{key} must be nonempty")
            elif not isinstance(rel.get(key), list):
                result.error(f"relation {relation_id} relation.{key} must be a list")
        if not rel.get("constraints"):
            result.error(f"relation {relation_id} relation.constraints must be nonempty")

    constraints = relation.get("constraints")
    if not constraints:
        result.error(f"relation {relation_id} constraints must be nonempty")

    ports = relation.get("ports")
    if not isinstance(ports, dict):
        result.error(f"relation {relation_id} ports must be a mapping")
    else:
        for side in ("inputs", "outputs"):
            if not isinstance(ports.get(side), dict) or not ports.get(side):
                result.error(f"relation {relation_id} ports.{side} must be a nonempty mapping")

    known = known_type_ids(registry)
    for type_id in collect_port_types(relation):
        if base_type(type_id) not in known:
            result.error(f"relation {relation_id} references unknown type {type_id}")

    if relation_outputs_candidate_set(relation):
        ctext = relation_constraint_text(relation)
        if "selector_or_branching" not in ctext and "筛选" not in ctext and "分支" not in ctext:
            result.error(
                f"relation {relation_id} outputs CandidateSet but does not name selector/filter/branching constraints"
            )

    for list_field in ("topic_tags", "generation_notes", "non_examples"):
        if not isinstance(relation.get(list_field), list) or not relation.get(list_field):
            result.error(f"relation {relation_id} {list_field} must be a nonempty list")

    return result


def validate_relations_file(relations_data: dict[str, Any], registry: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    relations = relations_data.get("relations")
    if not isinstance(relations, list):
        result.error("relations.yaml must contain a relations list")
        return result
    seen: set[str] = set()
    for relation in relations:
        relation_id = relation.get("relation_id")
        sub = validate_relation(relation, registry, seen)
        result.extend(sub)
        if relation_id:
            seen.add(relation_id)
    return result


def validate_patch(patch: dict[str, Any], registry: dict[str, Any], relations_data: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    missing = sorted(REQUIRED_PATCH_FIELDS - set(patch.keys()))
    if missing:
        result.error(f"patch missing required fields: {', '.join(missing)}")

    status = patch.get("review_status")
    if status not in {"draft", "ready", "needs_review", "applied", "rejected"}:
        result.error("patch review_status must be one of draft/ready/needs_review/applied/rejected")

    if status == "rejected":
        if not patch.get("review_notes"):
            result.error("rejected patch must explain review_notes")
        return result

    type_patch = patch.get("type_registry_patch") or {}
    if not isinstance(type_patch, dict):
        result.error("type_registry_patch must be a mapping")
        type_patch = {}

    known = known_type_ids(registry)
    alias_owners = alias_owner_map(registry)
    for item in type_patch.get("aliases_to_add") or []:
        type_id = item.get("type_id")
        aliases = item.get("aliases")
        if type_id not in known:
            result.error(f"alias patch references unknown type {type_id}")
        if not isinstance(aliases, list) or not aliases:
            result.error(f"alias patch for {type_id} must have nonempty aliases")
            continue
        for alias in aliases:
            owner = alias_owners.get(alias)
            if owner and owner != type_id:
                result.error(f"alias {alias!r} already belongs to {owner}, cannot add to {type_id}")

    if type_patch.get("new_type_candidates"):
        result.error("patch contains new_type_candidates; review before applying")

    existing_ids = {r.get("relation_id") for r in relations_data.get("relations") or [] if r.get("relation_id")}
    rels = patch.get("relations")
    if not isinstance(rels, list) or not rels:
        result.error("patch relations must be a nonempty list")
    else:
        patch_seen: set[str] = set()
        for relation in rels:
            rid = relation.get("relation_id")
            if rid in patch_seen:
                result.error(f"patch contains duplicate relation_id {rid}")
            if rid:
                patch_seen.add(rid)
            result.extend(validate_relation(relation, registry, existing_ids, allow_existing_id=status == "applied"))

    return result


def apply_patch_data(
    registry: dict[str, Any],
    relations_data: dict[str, Any],
    patch: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    new_registry = deepcopy(registry)
    new_relations = deepcopy(relations_data)
    type_patch = patch.get("type_registry_patch") or {}

    types = registry_types(new_registry)
    for item in type_patch.get("aliases_to_add") or []:
        type_id = item["type_id"]
        aliases = item.get("aliases") or []
        spec = types[type_id]
        current = list(spec.get("aliases") or [])
        for alias in aliases:
            if alias not in current:
                current.append(alias)
        spec["aliases"] = current

    relations = new_relations.setdefault("relations", [])
    applied_ids: list[str] = []
    for relation in patch.get("relations") or []:
        relations.append(deepcopy(relation))
        applied_ids.append(relation.get("relation_id"))

    new_patch = deepcopy(patch)
    new_patch["review_status"] = "applied"
    new_patch["applied_relation_ids"] = applied_ids
    return new_registry, new_relations, new_patch


def add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS)


def print_result(result: ValidationResult) -> None:
    if result.errors:
        print("errors:")
        for err in result.errors:
            print(f"  - {err}")
    if result.warnings:
        print("warnings:")
        for warn in result.warnings:
            print(f"  - {warn}")


def exit_for_result(result: ValidationResult) -> None:
    print_result(result)
    raise SystemExit(0 if result.ok else 1)


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)
