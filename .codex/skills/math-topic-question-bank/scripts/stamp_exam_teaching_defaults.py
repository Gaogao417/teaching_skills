#!/usr/bin/env python3
"""Stamp deterministic ``teaching`` defaults onto staged exam items.

Why: the LangGraph ingestion pipeline produces question content but no legacy
bank metadata (``teaching.difficulty`` / ``skill_tags``), while the formal
question-bank contract requires them (fail closed at promote). This utility is
the workflow-level bridge for exam stagings: it stamps a *deterministic*,
position-based default block so 教研 can review/approve it like any other edit.

Semantics (content change, not a silent patch):
- only stamps items whose teacher block has no ``teaching`` (idempotent);
- recomputes ``content_hash`` with the same formula as materialize/audit
  (teacher + student + crop hashes + attribution reviews), so the previous
  review is deliberately invalidated — re-approve via Review UI afterwards;
- sets ``transcription.human_review`` back to ``pending``;
- appends a ``text-edits.yaml`` trail entry (same schema as UI text edits).

Default derivation (Shanghai 一模卷式, documented for review):
- difficulty: Q1–6 foundation；Q7–17 standard；Q18(填空压轴) challenge；
  Q19–22 standard；Q23–25(解答压轴) challenge.
- skill_tags: [题型标签(choice→选择题/fillin→填空题/其余→解答题), "一模"].
- variation_dimension: "source_exam"; title: "第 N 题".
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SKILL_DIR = Path(__file__).resolve().parent
PDF_SKILL_SCRIPTS = (
    SKILL_DIR.parent.parent
    / "math-pdf-question-bank-ingestion"
    / "scripts"
).resolve()
sys.path.insert(0, str(PDF_SKILL_SCRIPTS))

from audit_staging import canonical_hash, load_yaml  # noqa: E402

QUESTION_TYPES = ("choice", "fillin", "problem", "short_answer")


def derive_difficulty(question_number: int) -> str:
    if question_number <= 6:
        return "foundation"
    if question_number <= 17:
        return "standard"
    if question_number == 18:
        return "challenge"
    if question_number <= 22:
        return "standard"
    return "challenge"


def section_label(question_type: str) -> str:
    if question_type == "choice":
        return "选择题"
    if question_type == "fillin":
        return "填空题"
    return "解答题"


def _single_practice_block(teacher: dict[str, Any]) -> dict[str, Any] | None:
    for section in teacher.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") in QUESTION_TYPES:
                return block
    return None


def stamp_item(item_dir: Path) -> str:
    """Stamp teaching defaults on one item; returns 'stamped' | 'already' | error."""
    source = load_yaml(item_dir / "source.yaml")
    teacher = load_yaml(item_dir / "teacher.resolved.assignment.yaml")
    student = load_yaml(item_dir / "student.resolved.assignment.yaml")
    block = _single_practice_block(teacher)
    if block is None:
        raise ValueError(f"{item_dir.name}: no practice block in teacher assignment")
    if block.get("teaching"):
        return "already"
    number = source.get("question_number")
    if not isinstance(number, int) or number < 1:
        raise ValueError(f"{item_dir.name}: invalid question_number")
    block["teaching"] = {
        "title": f"第 {number} 题",
        "difficulty": derive_difficulty(number),
        "skill_tags": [section_label(source.get("question_type", "")), "一模"],
        "variation_dimension": "source_exam",
    }

    # content_hash mirrors audit_staging / materialize_staging exactly.
    roles = ("question_evidence", "prompt", "solution", "official_solution")
    crops = source.get("crops") or {}
    hash_payload = {
        "teacher": teacher,
        "student": student,
        "crop_hashes": {
            role: [
                crop.get("output_sha256")
                for crop in crops.get(role, [])
                if isinstance(crop, dict)
            ]
            for role in roles
        },
        "attribution_reviews": {
            role: [
                crop.get("attribution_review") if isinstance(crop, dict) else None
                for crop in crops.get(role, [])
            ]
            for role in roles
        },
    }
    source["content_hash"] = canonical_hash(hash_payload)
    transcription = source.setdefault("transcription", {})
    transcription["human_review"] = "pending"

    (item_dir / "teacher.resolved.assignment.yaml").write_text(
        yaml.safe_dump(teacher, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (item_dir / "source.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    edits_path = item_dir / "text-edits.yaml"
    edits = (
        load_yaml(edits_path)
        if edits_path.is_file()
        else {"schema": "math_item_text_edits/v1", "item_id": item_dir.name, "edits": []}
    )
    edits.setdefault("edits", []).append(
        {
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "editor": "stamp-exam-teaching-defaults",
            "fields": ["teaching"],
        }
    )
    edits_path.write_text(
        yaml.safe_dump(edits, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return "stamped"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    staging = args.staging_dir.resolve()
    items_dir = staging / "items"
    stamped = already = 0
    for item_dir in sorted(p for p in items_dir.iterdir() if p.is_dir()):
        try:
            result = stamp_item(item_dir) if not args.dry_run else (
                "already"
                if _single_practice_block(load_yaml(item_dir / "teacher.resolved.assignment.yaml")).get("teaching")
                else "stamped"
            )
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"STAMP FAILED: {item_dir.name}: {exc}", file=sys.stderr)
            return 1
        if result == "stamped":
            stamped += 1
        else:
            already += 1
    print(
        f"TEACHING DEFAULTS: stamped={stamped} already-had-teaching={already} "
        f"(reviews invalidated — re-approve in Review UI)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
