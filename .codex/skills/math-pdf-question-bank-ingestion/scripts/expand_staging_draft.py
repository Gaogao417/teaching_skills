#!/usr/bin/env python3
"""Expand one compact paper.draft.yaml into canonical exam staging files."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import yaml


ZERO_HASH = "sha256:" + "0" * 64
ROLES = ("question_evidence", "prompt", "solution", "official_solution")
QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must be a non-empty string")
    return text


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def normalize_crop(
    raw: Any, *, role: str, index: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, dict):
        raise ValueError(f"{role}[{index}] must be a mapping")
    source = require_text(raw.get("source"), f"{role}[{index}].source")
    box = raw.get("box_px", raw.get("box"))
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError(f"{role}[{index}].box_px must contain four integers")
    box_px = [int(value) for value in box]
    left, top, right, bottom = box_px
    if min(box_px) < 0 or left >= right or top >= bottom:
        raise ValueError(f"{role}[{index}].box_px must have positive area")
    whiteout = raw.get("whiteout_px") or []
    if not isinstance(whiteout, list):
        raise ValueError(f"{role}[{index}].whiteout_px must be a list")
    default_name = {
        "question_evidence": "source-question",
        "prompt": "prompt",
        "solution": "solution",
        "official_solution": "official-solution",
    }[role]
    output = str(raw.get("output") or f"assets/{default_name}-{index:02d}.png")
    if Path(output).is_absolute() or ".." in Path(output).parts:
        raise ValueError(f"{role}[{index}].output must stay inside the item directory")
    crop = {
        "source": source,
        "source_sha256": ZERO_HASH,
        "box_px": box_px,
        "whiteout_px": [[int(value) for value in entry] for entry in whiteout],
        "output": output,
        "output_sha256": ZERO_HASH,
    }
    presentation = {
        "assignment_path": raw.get("assignment_path"),
        "width": raw.get("width"),
        "label": raw.get("label"),
    }
    return crop, presentation


def normalize_word_evidence(raw: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a mapping")
    page_number = int(raw.get("page_number"))
    if page_number < 1:
        raise ValueError(f"{label}.page_number must be a positive integer")
    return {
        "page_image": require_text(raw.get("page_image"), f"{label}.page_image"),
        "page_image_sha256": ZERO_HASH,
        "page_number": page_number,
    }


def set_json_pointer(target: Any, pointer: str, value: Any) -> None:
    if not pointer.startswith("/"):
        raise ValueError(f"assignment_path must be a JSON pointer, got {pointer!r}")
    tokens = [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer.lstrip("/").split("/")
        if token != ""
    ]
    if not tokens:
        raise ValueError("assignment_path cannot target the block root")
    current = target
    for token in tokens[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"assignment_path does not exist: {pointer}") from exc
        elif isinstance(current, dict):
            if token not in current:
                current[token] = {}
            current = current[token]
        else:
            raise ValueError(f"assignment_path does not exist: {pointer}")
    final = tokens[-1]
    if isinstance(current, list):
        try:
            position = int(final)
        except ValueError as exc:
            raise ValueError(f"assignment_path list index is invalid: {pointer}") from exc
        if not 0 <= position < len(current):
            raise ValueError(f"assignment_path does not exist: {pointer}")
        if current[position] is not None:
            raise ValueError(f"assignment_path already contains a value: {pointer}")
        current[position] = value
    elif isinstance(current, dict):
        if final in current:
            raise ValueError(f"assignment_path already contains a value: {pointer}")
        current[final] = value
    else:
        raise ValueError(f"assignment_path does not exist: {pointer}")


def image_value(
    output: str, *, role: str, width: Any = None, label: Any = None
) -> dict[str, Any]:
    if role == "prompt":
        return {
            "image_path": output,
            "width": str(width or "58mm"),
            "variant": "prompt",
            "disclosure_policy": "clean",
        }
    if role == "solution":
        return {
            "image_path": output,
            "width": str(width or "58mm"),
            "variant": "solution",
            "disclosure_policy": "teacher_only",
        }
    if role == "official_solution":
        return {
            "image_path": output,
            "width": str(width or "0.96\\linewidth"),
            "variant": "source_solution",
            "disclosure_policy": "teacher_only",
            "label": str(label or "官方原解答"),
        }
    raise ValueError(f"{role} does not have assignment presentation metadata")


def build_item(
    raw: dict[str, Any],
    *,
    paper: dict[str, Any],
    section_title: str,
    staging_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    item_id = require_text(raw.get("item_id"), "item_id")
    if len(item_id) != 4 or not item_id.startswith("Q") or not item_id[1:].isdigit():
        raise ValueError(f"{item_id}: item_id must use Q001-style format")
    question_number = int(raw.get("question_number"))
    question_type = require_text(raw.get("question_type"), f"{item_id}.question_type")
    if question_type not in QUESTION_TYPES:
        raise ValueError(f"{item_id}: unsupported question_type {question_type}")
    points = int(raw.get("points", 0))
    if points < 0:
        raise ValueError(f"{item_id}: points cannot be negative")

    crops: dict[str, list[dict[str, Any]]] = {}
    presentations: dict[str, list[dict[str, Any]]] = {}
    for role in ROLES:
        if role == "official_solution":
            official = raw.get("official_solution") or {}
            raw_crops = official.get("crops") if isinstance(official, dict) else None
        else:
            raw_crops = raw.get(role)
        raw_crops = raw_crops or []
        if not isinstance(raw_crops, list):
            raise ValueError(f"{item_id}.{role} must be a list")
        pairs = [
            normalize_crop(value, role=role, index=index)
            for index, value in enumerate(raw_crops, start=1)
        ]
        crops[role] = [pair[0] for pair in pairs]
        presentations[role] = [pair[1] for pair in pairs]
    official_raw = raw.get("official_solution") or {}
    question_word_raw = raw.get("question_word_evidence") or []
    official_word_raw = (
        official_raw.get("word_evidence") if isinstance(official_raw, dict) else []
    ) or []
    if not isinstance(question_word_raw, list):
        raise ValueError(f"{item_id}.question_word_evidence must be a list")
    if not isinstance(official_word_raw, list):
        raise ValueError(f"{item_id}.official_solution.word_evidence must be a list")
    word_evidence = {
        "question": [
            normalize_word_evidence(
                value, label=f"{item_id}.question_word_evidence[{index}]"
            )
            for index, value in enumerate(question_word_raw, start=1)
        ],
        "official_solution": [
            normalize_word_evidence(
                value, label=f"{item_id}.official_solution.word_evidence[{index}]"
            )
            for index, value in enumerate(official_word_raw, start=1)
        ],
    }
    if not crops["question_evidence"] and not word_evidence["question"]:
        raise ValueError(f"{item_id}: question crop or Word evidence is required")
    if not crops["official_solution"] and not word_evidence["official_solution"]:
        raise ValueError(f"{item_id}: official solution crop or Word evidence is required")

    block_raw = raw.get("block")
    if not isinstance(block_raw, dict):
        raise ValueError(f"{item_id}.block must be a mapping")
    block = copy.deepcopy(block_raw)
    for reserved in ("id", "type", "points", "source_solution_images"):
        if reserved in block:
            raise ValueError(f"{item_id}.block must not define generated key {reserved}")
    block = {"type": question_type, "id": item_id, "points": points, **block}
    if not str(block.get("stem_latex") or block.get("stem") or "").strip():
        raise ValueError(f"{item_id}: block.stem_latex is required")
    if not block.get("answer"):
        raise ValueError(f"{item_id}: block.answer is required")
    if question_type == "choice":
        choices = block.get("choices")
        if not isinstance(choices, (list, dict)) or len(choices) != 4:
            raise ValueError(f"{item_id}: choice block requires exactly four choices")
    if question_type in {"problem", "short_answer"} and not block.get("solution_steps"):
        raise ValueError(f"{item_id}: problem block requires solution_steps")

    for role in ("prompt", "solution"):
        role_crops = crops[role]
        for index, crop in enumerate(role_crops):
            presentation = presentations[role][index]
            pointer = presentation.get("assignment_path")
            if pointer is None and len(role_crops) == 1:
                pointer = (
                    "/diagram_col"
                    if role == "prompt"
                    else "/solution_steps/0/diagram_col"
                )
            if pointer is None:
                raise ValueError(
                    f"{item_id}: every {role} crop needs assignment_path when there are multiple crops"
                )
            set_json_pointer(
                block,
                str(pointer),
                image_value(
                    crop["output"],
                    role=role,
                    width=presentation.get("width"),
                    label=presentation.get("label"),
                ),
            )
    block["source_solution_images"] = [
        image_value(
            crop["output"],
            role="official_solution",
            width=presentations["official_solution"][index].get("width"),
            label=presentations["official_solution"][index].get("label")
            or f"官方原解答第 {index + 1} 页",
        )
        for index, crop in enumerate(crops["official_solution"])
    ]

    source_key = str(
        raw.get("source_key")
        or f"{paper['id']}-Q{question_number:02d}"
    )
    transcription_raw = raw.get("transcription") or {}
    if not isinstance(transcription_raw, dict):
        raise ValueError(f"{item_id}.transcription must be a mapping")
    transcription = {
        "question_status": transcription_raw.get("question_status", "author_pass"),
        "official_solution_status": transcription_raw.get(
            "official_solution_status", "author_pass"
        ),
        "human_review": "pending",
        "prompt_status": transcription_raw.get("prompt_status", "author_pass"),
        "prompt_review_notes": transcription_raw.get("prompt_review_notes") or [],
    }
    if (
        transcription["prompt_status"] == "needs_human_crop"
        and not transcription["prompt_review_notes"]
    ):
        raise ValueError(
            f"{item_id}: prompt_review_notes is required for needs_human_crop"
        )
    source = {
        "schema": "math_exam_item_source/v1",
        "item_id": item_id,
        "source_key": source_key,
        "paper_id": paper["id"],
        "question_number": question_number,
        "question_type": question_type,
        "points": points,
        "section_title": section_title,
        "source_directory": paper["source_archive"],
        "crops": crops,
        "transcription": transcription,
        "content_hash": ZERO_HASH,
    }
    if word_evidence["question"] or word_evidence["official_solution"]:
        source["word_evidence"] = word_evidence
    teacher = {
        "meta": {
            "title": f"{paper['title']}第 {question_number} 题",
            "grade": paper["grade"],
            "subject": paper.get("subject", "数学"),
            "total_points": points,
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {"source_record": "source.yaml"},
        },
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "inline",
        },
        "sections": [
            {
                "id": "question",
                "title": section_title,
                "type": "practice",
                "visibility": "both",
                "blocks": [block],
            }
        ],
    }
    item_dir = staging_dir / "items" / item_id
    if (item_dir / "review.yaml").exists():
        raise ValueError(f"{item_id}: refuse to re-expand after review.yaml exists")
    write_yaml(item_dir / "source.yaml", source)
    write_yaml(item_dir / "teacher.resolved.assignment.yaml", teacher)
    map_item = {
        "item_id": item_id,
        "question_number": question_number,
        "question_pages": ordered_unique(
            [crop["source"] for crop in crops["question_evidence"]]
        ),
        "official_solution": {
            "pages": ordered_unique(
                [crop["source"] for crop in crops["official_solution"]]
            ),
            "start_anchor": require_text(
                (raw.get("official_solution") or {}).get("start_anchor"),
                f"{item_id}.official_solution.start_anchor",
            ),
            "end_anchor": require_text(
                (raw.get("official_solution") or {}).get("end_anchor"),
                f"{item_id}.official_solution.end_anchor",
            ),
        },
    }
    return {"item_id": item_id, "teacher": teacher}, map_item


def expand_draft(draft_path: Path) -> Path:
    draft_path = draft_path.resolve()
    payload = load_yaml(draft_path)
    if payload.get("schema") != "math_exam_staging_draft/v1":
        raise ValueError("draft schema must be math_exam_staging_draft/v1")
    paper_raw = payload.get("paper")
    if not isinstance(paper_raw, dict):
        raise ValueError("paper must be a mapping")
    paper = {
        "id": require_text(paper_raw.get("id"), "paper.id"),
        "title": require_text(paper_raw.get("title"), "paper.title"),
        "grade": require_text(paper_raw.get("grade"), "paper.grade"),
        "subject": require_text(paper_raw.get("subject", "数学"), "paper.subject"),
        "source_archive": require_text(
            paper_raw.get("source_archive"), "paper.source_archive"
        ),
    }
    if paper_raw.get("duration"):
        paper["duration"] = str(paper_raw["duration"])
    staging_dir = draft_path.parent
    sections_raw = payload.get("sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        raise ValueError("sections must be a non-empty list")

    paper_sections: list[dict[str, Any]] = []
    paper_map_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section_index, section in enumerate(sections_raw, start=1):
        if not isinstance(section, dict):
            raise ValueError(f"sections[{section_index}] must be a mapping")
        section_id = require_text(section.get("id"), f"sections[{section_index}].id")
        section_title = require_text(
            section.get("title"), f"sections[{section_index}].title"
        )
        items = section.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"sections[{section_index}].items must be non-empty")
        item_ids: list[str] = []
        for raw_item in items:
            if not isinstance(raw_item, dict):
                raise ValueError(f"{section_id}: item must be a mapping")
            built, map_item = build_item(
                raw_item,
                paper=paper,
                section_title=section_title,
                staging_dir=staging_dir,
            )
            item_id = built["item_id"]
            if item_id in seen:
                raise ValueError(f"duplicate item_id: {item_id}")
            seen.add(item_id)
            item_ids.append(item_id)
            paper_map_items.append(map_item)
        paper_sections.append(
            {"id": section_id, "title": section_title, "item_ids": item_ids}
        )

    write_yaml(
        staging_dir / "paper.yaml",
        {
            "schema": "math_exam_paper/v1",
            "paper": paper,
            "question_bank": require_text(
                payload.get("question_bank"), "question_bank"
            ),
            "sections": paper_sections,
        },
    )
    write_yaml(
        staging_dir / "paper-map.yaml",
        {
            "schema": "math_exam_paper_map/v1",
            "paper_id": paper["id"],
            "items": paper_map_items,
        },
    )
    return staging_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    args = parser.parse_args()
    try:
        staging_dir = expand_draft(args.draft)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(f"DRAFT EXPANSION FAILED: {exc}")
        return 1
    print(f"DRAFT EXPANDED: {staging_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
