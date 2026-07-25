#!/usr/bin/env python3
"""Validate a math topic question bank and all ready single-item assignments."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

from question_bank_contracts import QuestionBank, QuestionBankItem


QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}
STUDENT_FORBIDDEN_KEYS = {
    "answer",
    "clue",
    "solution_steps",
    "solution_notes",
    "source_solution_images",
    "teaching",
}
STEM_NOISE_PATTERNS = {
    "完成三格填空": "remove answer-form scaffolding from the stem",
    "按照“提二次项系数": "move the prescribed solution method to solution_steps",
    "并明确写出第二步": "move intermediate-step requirements to solution_steps",
    "写出必要的推理过程": "ask only for the mathematical target",
    "再证明": "do not stack proof instructions onto a calculation target",
    "再写出对应关系": "move correspondence prompts to solution_steps",
    "最后验算": "move verification to the teacher solution",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return data


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
    blocks: list[dict[str, Any]] = []
    for section in assignment.get("sections", []):
        if not isinstance(section, dict) or section.get("type") != "practice":
            continue
        for block in section.get("blocks", []):
            if isinstance(block, dict) and block.get("type") in QUESTION_TYPES:
                blocks.append(block)
    return blocks


def stem_of(block: dict[str, Any]) -> str:
    return str(block.get("stem_latex") or block.get("stem") or "").strip()


def stem_quality_errors(stem: str) -> list[str]:
    errors = [
        f"stem contains noise phrase {pattern!r}: {guidance}"
        for pattern, guidance in STEM_NOISE_PATTERNS.items()
        if pattern in stem
    ]
    if "点序" in stem:
        errors.append("stem must not restate point order already shown by the prompt diagram")
    if r"\in" in stem or r"\cap" in stem:
        errors.append("middle-school stem must use textbook geometry language instead of set notation \\in/\\cap")
    return errors


def diagram_variants(assignment: dict[str, Any]) -> set[str]:
    variants: set[str] = set()
    for _, value in walk(assignment):
        if not isinstance(value, dict):
            continue
        if value.get("tikz_path") or value.get("image_path") or value.get("tikz_code"):
            variant = value.get("variant") or value.get("diagram_variant")
            if variant:
                variants.add(str(variant))
    return variants


def asset_errors(assignment: dict[str, Any], assignment_path: Path) -> list[str]:
    errors: list[str] = []
    for key, value in walk(assignment):
        if key not in {"tikz_path", "image_path"} or not isinstance(value, str):
            continue
        asset = Path(value)
        if not asset.is_absolute():
            asset = assignment_path.parent / asset
        if not asset.exists():
            errors.append(f"missing asset {value!r} referenced by {assignment_path}")
    return errors


def validate_pair(item: QuestionBankItem, bank_dir: Path, require_ready: bool) -> list[str]:
    errors: list[str] = []
    student_path = bank_dir / item.student_assignment
    teacher_path = bank_dir / item.teacher_assignment
    if not student_path.exists():
        errors.append(f"{item.id}: missing student assignment {item.student_assignment}")
    if not teacher_path.exists():
        errors.append(f"{item.id}: missing teacher assignment {item.teacher_assignment}")
    if errors:
        return errors

    try:
        student = load_yaml(student_path)
        teacher = load_yaml(teacher_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [f"{item.id}: {exc}"]

    student_blocks = question_blocks(student)
    teacher_blocks = question_blocks(teacher)
    if len(student_blocks) != 1:
        errors.append(f"{item.id}: student assignment must contain exactly one practice question")
    if len(teacher_blocks) != 1:
        errors.append(f"{item.id}: teacher assignment must contain exactly one practice question")
    if len(student_blocks) != 1 or len(teacher_blocks) != 1:
        return errors

    student_block = student_blocks[0]
    teacher_block = teacher_blocks[0]
    for label, block in (("student", student_block), ("teacher", teacher_block)):
        if block.get("id") != item.id:
            errors.append(f"{item.id}: {label} block id must equal manifest item id")
        if block.get("type") != item.question_type:
            errors.append(f"{item.id}: {label} question_type differs from manifest")
    if stem_of(student_block) != stem_of(teacher_block):
        errors.append(f"{item.id}: student and teacher stems differ")
    errors.extend(f"{item.id}: {message}" for message in stem_quality_errors(stem_of(student_block)))

    for key, _ in walk(student.get("sections", [])):
        if key in STUDENT_FORBIDDEN_KEYS:
            errors.append(f"{item.id}: student assignment contains forbidden key {key!r}")
        if key == "hints":
            errors.append(f"{item.id}: student question bank item must not contain hints")
    for _, value in walk(student.get("sections", [])):
        if isinstance(value, dict) and value.get("variant") == "prompt" and value.get("caption"):
            errors.append(f"{item.id}: single prompt diagram must not carry a student-facing caption")
    if not teacher_block.get("answer"):
        errors.append(f"{item.id}: teacher question requires answer")
    if item.question_type in {"problem", "short_answer"} and not teacher_block.get("solution_steps"):
        errors.append(f"{item.id}: teacher solution_steps required for {item.question_type}")
    source_solution_images = teacher_block.get("source_solution_images", [])
    if source_solution_images and not isinstance(source_solution_images, list):
        errors.append(f"{item.id}: teacher source_solution_images must be a list")
    elif isinstance(source_solution_images, list):
        for index, image in enumerate(source_solution_images):
            if not isinstance(image, dict) or not image.get("image_path"):
                errors.append(
                    f"{item.id}: source_solution_images[{index}] requires image_path"
                )
    solution_notes = teacher_block.get("solution_notes", [])
    if solution_notes and not isinstance(solution_notes, list):
        errors.append(f"{item.id}: teacher solution_notes must be a list")

    if require_ready:
        if any(key == "diagram_slot" for key, _ in walk(student)):
            errors.append(f"{item.id}: student assignment still contains diagram_slot")
        if any(key == "diagram_slot" for key, _ in walk(teacher)):
            errors.append(f"{item.id}: teacher assignment still contains diagram_slot")
        student_variants = diagram_variants(student)
        teacher_variants = diagram_variants(teacher)
        if item.diagram_requirement != "none":
            if "prompt" not in student_variants:
                errors.append(f"{item.id}: student prompt diagram is required")
            if "prompt" not in teacher_variants:
                errors.append(f"{item.id}: teacher prompt diagram is required")
        if item.diagram_requirement == "prompt_and_solution" and "solution" not in teacher_variants:
            errors.append(f"{item.id}: teacher solution diagram is required")
        errors.extend(f"{item.id}: {message}" for message in asset_errors(student, student_path))
        errors.extend(f"{item.id}: {message}" for message in asset_errors(teacher, teacher_path))
    return errors


def validate_manifest(path: Path) -> tuple[QuestionBank | None, list[str]]:
    try:
        raw = load_yaml(path)
        bank = QuestionBank.model_validate(raw)
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
        return None, [str(exc)]

    errors: list[str] = []
    require_ready = bank.bank.status == "ready"
    for item in bank.items:
        if item.source_ref:
            source_path = path.parent / item.source_ref
            if not source_path.is_file():
                errors.append(f"{item.id}: missing source_ref {item.source_ref}")
        errors.extend(validate_pair(item, path.parent, require_ready))
    return bank, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="Path to question-bank.yaml")
    args = parser.parse_args()

    bank, errors = validate_manifest(args.bank.resolve())
    if errors:
        print("QUESTION BANK INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    assert bank is not None
    print(
        f"QUESTION BANK VALID: {bank.bank.topic} | "
        f"status={bank.bank.status} | items={len(bank.items)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
