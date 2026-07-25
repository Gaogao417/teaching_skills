#!/usr/bin/env python3
"""Typed contract and staging consistency checks for paper-map.yaml."""

from __future__ import annotations

from pathlib import Path
import sys
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
TOPIC_SCRIPTS = REPO_ROOT / ".codex/skills/math-topic-question-bank/scripts"
sys.path.insert(0, str(TOPIC_SCRIPTS))

from exam_source_contracts import ExamPaperMap  # noqa: E402


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def ordered_sources(source: dict, role: str) -> list[str]:
    values: list[str] = []
    for crop in (source.get("crops") or {}).get(role) or []:
        if not isinstance(crop, dict):
            continue
        page = str(crop.get("source") or "")
        if page and page not in values:
            values.append(page)
    return values


def validate_against_staging(
    paper_map: ExamPaperMap,
    *,
    paper_id: str,
    ordered_item_ids: list[str],
    staging_dir: Path,
) -> list[str]:
    errors: list[str] = []
    if paper_map.paper_id != paper_id:
        errors.append("paper-map paper_id differs from paper.yaml")
    mapped_ids = [item.item_id for item in paper_map.items]
    if mapped_ids != ordered_item_ids:
        errors.append("paper-map item order differs from paper.yaml")

    entries = {item.item_id: item for item in paper_map.items}
    for item_id in ordered_item_ids:
        entry = entries.get(item_id)
        if entry is None:
            continue
        source_path = staging_dir / "items" / item_id / "source.yaml"
        if not source_path.is_file():
            errors.append(f"{item_id}: source.yaml missing for paper-map check")
            continue
        source = load_yaml(source_path)
        if entry.question_number != source.get("question_number"):
            errors.append(f"{item_id}: paper-map question_number differs from source.yaml")
        question_pages = ordered_sources(source, "question_evidence")
        if entry.question_pages != question_pages:
            errors.append(
                f"{item_id}: paper-map question_pages differ from question_evidence sources"
            )
        solution_pages = ordered_sources(source, "official_solution")
        if entry.official_solution.pages != solution_pages:
            errors.append(
                f"{item_id}: paper-map official_solution pages differ from crop sources"
            )
    return errors
