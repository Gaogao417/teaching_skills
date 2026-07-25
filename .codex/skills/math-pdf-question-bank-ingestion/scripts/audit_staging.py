#!/usr/bin/env python3
"""Audit a staged exam and build compact visual contact sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageOps
import yaml


ROLES = ("question_evidence", "prompt", "solution", "official_solution")
FORBIDDEN_STUDENT_KEYS = {
    "answer",
    "explanation",
    "solution_steps",
    "solution_notes",
    "source_solution_images",
    "teaching",
}
EMBEDDED_CHOICE_LABEL = re.compile(
    r"^\s*(?:(?:[A-Da-d]|[0-3])\s*[.、．]\s*|[（(]\s*(?:[A-Da-d]|[0-3])\s*[）)]\s*)"
)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from walk(child)


def question_blocks(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for section in assignment.get("sections") or []
        if isinstance(section, dict) and section.get("type") == "practice"
        for block in section.get("blocks") or []
        if isinstance(block, dict)
        and block.get("type") in {"choice", "fillin", "problem", "short_answer"}
    ]


def image_references(value: Any) -> list[tuple[str, dict[str, Any]]]:
    references: list[tuple[str, dict[str, Any]]] = []
    for _, child in walk(value):
        if isinstance(child, dict) and isinstance(child.get("image_path"), str):
            references.append((child["image_path"], child))
    return references


def crop_outputs(source: dict[str, Any], role: str) -> list[str]:
    crops = (source.get("crops") or {}).get(role) or []
    return [str(crop.get("output")) for crop in crops if isinstance(crop, dict)]


def relative_image_refs(value: Any) -> list[str]:
    return [path for path, _ in image_references(value)]


def count_path(references: list[str], path: str) -> int:
    return sum(reference == path for reference in references)


def choice_values(choices: Any) -> list[str]:
    if isinstance(choices, dict):
        return [str(value) for value in choices.values()]
    if isinstance(choices, list):
        return [str(value) for value in choices]
    return []


def box_area(box: Any) -> int:
    if not isinstance(box, list) or len(box) != 4:
        return 0
    try:
        left, top, right, bottom = (int(value) for value in box)
    except (TypeError, ValueError):
        return 0
    return max(0, right - left) * max(0, bottom - top)


def box_intersection_area(first: Any, second: Any) -> int:
    if (
        not isinstance(first, list)
        or len(first) != 4
        or not isinstance(second, list)
        or len(second) != 4
    ):
        return 0
    try:
        a_left, a_top, a_right, a_bottom = (int(value) for value in first)
        b_left, b_top, b_right, b_bottom = (int(value) for value in second)
    except (TypeError, ValueError):
        return 0
    width = max(0, min(a_right, b_right) - max(a_left, b_left))
    height = max(0, min(a_bottom, b_bottom) - max(a_top, b_top))
    return width * height


def audit_item(
    item_id: str,
    item_dir: Path,
    repo_root: Path,
    require_approved_review: bool,
    validate_source,
) -> tuple[list[str], list[str], dict[str, list[Path]]]:
    errors: list[str] = []
    warnings: list[str] = []
    assets: dict[str, list[Path]] = {role: [] for role in ROLES}
    source_path = item_dir / "source.yaml"
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    student_path = item_dir / "student.resolved.assignment.yaml"
    review_path = item_dir / "review.yaml"
    missing = [
        path.name
        for path in (source_path, teacher_path, student_path)
        if not path.is_file()
    ]
    if missing:
        return [f"{item_id}: missing {', '.join(missing)}"], warnings, assets

    source, source_errors = validate_source(
        source_path,
        review_path=review_path if review_path.is_file() else None,
        repo_root=repo_root,
    )
    errors.extend(f"{item_id}: {message}" for message in source_errors)
    try:
        raw_source = load_yaml(source_path)
        teacher = load_yaml(teacher_path)
        student = load_yaml(student_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return errors + [f"{item_id}: {exc}"], warnings, assets

    if raw_source.get("item_id") != item_id:
        errors.append(f"{item_id}: source item_id differs")
    hash_payload = {
        "teacher": teacher,
        "student": student,
        "crop_hashes": {
            role: [
                crop.get("output_sha256")
                for crop in (raw_source.get("crops") or {}).get(role, [])
                if isinstance(crop, dict)
            ]
            for role in ROLES
        },
    }
    calculated_content_hash = canonical_hash(hash_payload)
    if raw_source.get("content_hash") != calculated_content_hash:
        errors.append(f"{item_id}: content_hash does not match assignments and crops")
    teacher_blocks = question_blocks(teacher)
    student_blocks = question_blocks(student)
    if len(teacher_blocks) != 1:
        errors.append(f"{item_id}: teacher must contain exactly one question block")
    if len(student_blocks) != 1:
        errors.append(f"{item_id}: student must contain exactly one question block")
    if len(teacher_blocks) != 1 or len(student_blocks) != 1:
        return errors, warnings, assets
    teacher_block = teacher_blocks[0]
    student_block = student_blocks[0]

    for label, block in (("teacher", teacher_block), ("student", student_block)):
        if block.get("id") != item_id:
            errors.append(f"{item_id}: {label} block id differs")
        if block.get("type") != raw_source.get("question_type"):
            errors.append(f"{item_id}: {label} question type differs from source")
    teacher_stem = str(teacher_block.get("stem_latex") or teacher_block.get("stem") or "").strip()
    student_stem = str(student_block.get("stem_latex") or student_block.get("stem") or "").strip()
    if teacher_stem != student_stem:
        errors.append(f"{item_id}: student and teacher stems differ")
    if not teacher_block.get("answer"):
        errors.append(f"{item_id}: teacher answer is required")
    if raw_source.get("question_type") == "choice":
        teacher_choices = choice_values(teacher_block.get("choices"))
        student_choices = choice_values(student_block.get("choices"))
        if len(teacher_choices) != 4:
            errors.append(
                f"{item_id}: choice question must contain exactly four option bodies"
            )
        if teacher_choices != student_choices:
            errors.append(f"{item_id}: student and teacher choices differ")
        for choice_index, choice in enumerate(teacher_choices):
            if not choice.strip():
                errors.append(f"{item_id}: choice {choice_index + 1} is empty")
            if EMBEDDED_CHOICE_LABEL.match(choice):
                errors.append(
                    f"{item_id}: choice {choice_index + 1} contains an embedded label; "
                    "store only the option body and let the renderer add A/B/C/D"
                )
        answer = str(teacher_block.get("answer") or "").strip().upper()
        if answer not in {"A", "B", "C", "D"}:
            errors.append(f"{item_id}: choice answer must be one of A/B/C/D")
    if raw_source.get("question_type") in {"problem", "short_answer"} and not teacher_block.get(
        "solution_steps"
    ):
        errors.append(f"{item_id}: teacher solution_steps are required")

    for key, child in walk(student.get("sections") or []):
        if key in FORBIDDEN_STUDENT_KEYS:
            errors.append(f"{item_id}: student contains forbidden key {key}")
        if key == "diagram_slot":
            errors.append(f"{item_id}: student contains diagram_slot")
        if isinstance(child, dict) and (
            child.get("variant") in {"solution", "source_solution", "annotated"}
            or child.get("disclosure_policy") == "teacher_only"
        ):
            errors.append(f"{item_id}: student contains teacher-only image")
    if any(key == "diagram_slot" for key, _ in walk(teacher)):
        errors.append(f"{item_id}: teacher contains diagram_slot")

    teacher_refs = relative_image_refs(teacher_block)
    student_refs = relative_image_refs(student_block)
    solution_step_refs = relative_image_refs(teacher_block.get("solution_steps") or [])
    official_refs = [
        str(image.get("image_path"))
        for image in teacher_block.get("source_solution_images") or []
        if isinstance(image, dict)
    ]

    for role in ROLES:
        for output in crop_outputs(raw_source, role):
            path = (item_dir / output).resolve()
            assets[role].append(path)
            if not path.is_file():
                errors.append(f"{item_id}: missing {role} output {output}")

    for output in crop_outputs(raw_source, "question_evidence"):
        if count_path(student_refs, output):
            errors.append(f"{item_id}: question evidence leaks into student assignment: {output}")
    for output in crop_outputs(raw_source, "prompt"):
        if count_path(teacher_refs, output) != 1:
            errors.append(f"{item_id}: prompt must appear once in teacher assignment: {output}")
        if count_path(student_refs, output) != 1:
            errors.append(f"{item_id}: prompt must appear once in student assignment: {output}")
    evidence_crops = [
        crop
        for crop in (raw_source.get("crops") or {}).get("question_evidence", [])
        if isinstance(crop, dict)
    ]
    prompt_crops = [
        crop
        for crop in (raw_source.get("crops") or {}).get("prompt", [])
        if isinstance(crop, dict)
    ]
    for prompt_crop in prompt_crops:
        same_page_evidence = [
            crop
            for crop in evidence_crops
            if prompt_crop.get("source") == crop.get("source")
        ]
        full_question_candidates = [
            crop
            for crop in same_page_evidence
            if not any(
                marker in str(crop.get("output") or "").lower()
                for marker in ("diagram", "figure")
            )
        ]
        largest_evidence = max(
            full_question_candidates or same_page_evidence,
            key=lambda crop: box_area(crop.get("box_px")),
            default=None,
        )
        prompt_area = box_area(prompt_crop.get("box_px"))
        evidence_area = (
            box_area(largest_evidence.get("box_px")) if largest_evidence else 0
        )
        duplicates_full_evidence = bool(
            largest_evidence
            and prompt_crop.get("box_px") == largest_evidence.get("box_px")
            and (prompt_crop.get("whiteout_px") or [])
            == (largest_evidence.get("whiteout_px") or [])
        )
        near_full_evidence = bool(
            largest_evidence
            and prompt_area
            and evidence_area
            and prompt_area / evidence_area >= 0.8
            and box_intersection_area(
                prompt_crop.get("box_px"), largest_evidence.get("box_px")
            )
            / prompt_area
            >= 0.9
        )
        if duplicates_full_evidence or near_full_evidence:
            errors.append(
                f"{item_id}: prompt duplicates or nearly duplicates full question evidence; "
                "crop only the independent illustration or remove prompt"
            )
    for output in crop_outputs(raw_source, "solution"):
        if count_path(solution_step_refs, output) != 1:
            errors.append(f"{item_id}: solution image must appear once in solution_steps: {output}")
        if count_path(student_refs, output):
            errors.append(f"{item_id}: solution image leaks into student assignment: {output}")
        matching = [
            meta
            for path, meta in image_references(teacher_block.get("solution_steps") or [])
            if path == output
        ]
        if matching and (
            matching[0].get("variant") != "solution"
            or matching[0].get("disclosure_policy") != "teacher_only"
        ):
            errors.append(f"{item_id}: solution image metadata is not teacher-only: {output}")
    expected_official = crop_outputs(raw_source, "official_solution")
    if official_refs != expected_official:
        errors.append(f"{item_id}: source_solution_images order differs from official_solution crops")
    for output in expected_official:
        if count_path(student_refs, output):
            errors.append(f"{item_id}: official solution leaks into student assignment: {output}")

    transcription = raw_source.get("transcription") or {}
    prompt_status = transcription.get("prompt_status", "author_pass")
    prompt_notes = transcription.get("prompt_review_notes") or []
    if prompt_status == "needs_human_crop":
        warnings.append(
            f"{item_id}: prompt needs human crop review — {'; '.join(map(str, prompt_notes))}"
        )
    if review_path.is_file():
        review = load_yaml(review_path)
        if review.get("content_hash") != raw_source.get("content_hash"):
            errors.append(f"{item_id}: review is stale")
        if require_approved_review and review.get("status") != "approved":
            errors.append(f"{item_id}: review status is not approved")
    elif require_approved_review:
        errors.append(f"{item_id}: review.yaml is required")
    return errors, warnings, assets


def fit_cell(paths: list[Path], width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height), "white")
    valid = [path for path in paths if path.is_file()]
    if not valid:
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 12), "(none)", fill="gray")
        return canvas
    slot_height = max(1, height // len(valid))
    for index, path in enumerate(valid):
        with Image.open(path) as image:
            thumb = ImageOps.contain(
                image.convert("RGB"), (width - 12, slot_height - 12)
            )
        x = (width - thumb.width) // 2
        y = index * slot_height + (slot_height - thumb.height) // 2
        canvas.paste(thumb, (x, y))
    return canvas


def contact_sheets(
    staging_dir: Path,
    ordered: list[str],
    assets_by_item: dict[str, dict[str, list[Path]]],
    rows_per_sheet: int,
) -> list[Path]:
    qa_dir = staging_dir / "qa"
    qa_dir.mkdir(exist_ok=True)
    cell_width, cell_height, label_width, header_height = 330, 230, 72, 32
    outputs: list[Path] = []
    for sheet_index, start in enumerate(range(0, len(ordered), rows_per_sheet), start=1):
        item_ids = ordered[start : start + rows_per_sheet]
        canvas = Image.new(
            "RGB",
            (
                label_width + cell_width * len(ROLES),
                header_height + cell_height * len(item_ids),
            ),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        for column, role in enumerate(ROLES):
            draw.text(
                (label_width + column * cell_width + 8, 9),
                role,
                fill="black",
            )
        for row, item_id in enumerate(item_ids):
            top = header_height + row * cell_height
            draw.text((8, top + 10), item_id, fill="black")
            for column, role in enumerate(ROLES):
                cell = fit_cell(
                    assets_by_item[item_id][role], cell_width, cell_height
                )
                canvas.paste(cell, (label_width + column * cell_width, top))
            draw.line(
                (0, top + cell_height - 1, canvas.width, top + cell_height - 1),
                fill="#cccccc",
            )
        output = qa_dir / f"contact-sheet-{sheet_index:03d}.png"
        canvas.save(output)
        outputs.append(output)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--rows-per-sheet", type=int, default=8)
    parser.add_argument("--require-approved-review", action="store_true")
    args = parser.parse_args()

    staging_dir = args.staging_dir.resolve()
    repo_root = args.repo_root.resolve()
    topic_scripts = (
        repo_root / ".codex/skills/math-topic-question-bank/scripts"
    ).resolve()
    sys.path.insert(0, str(topic_scripts))
    try:
        from exam_source_contracts import ExamPaperManifest, ExamPaperMap
        from paper_map_contracts import validate_against_staging
        from validate_exam_source import validate_source

        paper = ExamPaperManifest.model_validate(load_yaml(staging_dir / "paper.yaml"))
        ordered = [
            item_id for section in paper.sections for item_id in section.item_ids
        ]
        paper_map_path = staging_dir / "paper-map.yaml"
        if not paper_map_path.is_file():
            raise ValueError("paper-map.yaml is required")
        paper_map = ExamPaperMap.model_validate(load_yaml(paper_map_path))
        map_errors = validate_against_staging(
            paper_map,
            paper_id=paper.paper.id,
            ordered_item_ids=ordered,
            staging_dir=staging_dir,
        )
        if args.only:
            wanted = set(args.only)
            unknown = sorted(wanted.difference(ordered))
            if unknown:
                raise ValueError("--only item not in paper.yaml: " + ", ".join(unknown))
            ordered = [item_id for item_id in ordered if item_id in wanted]
        if args.rows_per_sheet < 1:
            raise ValueError("--rows-per-sheet must be positive")

        all_errors: list[str] = list(map_errors)
        all_warnings: list[str] = []
        assets_by_item: dict[str, dict[str, list[Path]]] = {}
        for item_id in ordered:
            errors, warnings, assets = audit_item(
                item_id,
                staging_dir / "items" / item_id,
                repo_root,
                args.require_approved_review,
                validate_source,
            )
            all_errors.extend(errors)
            all_warnings.extend(warnings)
            assets_by_item[item_id] = assets
        sheets = contact_sheets(
            staging_dir, ordered, assets_by_item, args.rows_per_sheet
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"STAGING AUDIT FAILED: {exc}", file=sys.stderr)
        return 1

    for warning in all_warnings:
        print(f"WARNING: {warning}")
    for sheet in sheets:
        print(f"CONTACT SHEET: {sheet}")
    if all_errors:
        print("STAGING INVALID", file=sys.stderr)
        for error in all_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    review_label = "approved" if args.require_approved_review else "structural"
    print(
        f"STAGING VALID: {paper.paper.id} | items={len(ordered)} "
        f"| gate={review_label}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
