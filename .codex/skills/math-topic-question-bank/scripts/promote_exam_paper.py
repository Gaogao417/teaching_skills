#!/usr/bin/env python3
"""Atomically promote one fully reviewed exam paper into a source question bank."""

from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from pydantic import ValidationError
import yaml

from exam_source_contracts import (
    ExamItemReview,
    ExamItemSource,
    ExamPaperManifest,
    ExamPaperMap,
)
from question_bank_contracts import QuestionBank, QuestionBankItem
from validate_exam_source import load_yaml, validate_source
from validate_question_bank import QUESTION_TYPES, question_blocks, validate_manifest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_export import (  # noqa: E402
    CanonicalExportError,
    build_candidate_export,
    promote_canonical,
)


DIFFICULTIES = {"foundation", "standard", "challenge"}
DIAGRAM_REQUIREMENTS = {"none", "prompt_only", "prompt_and_solution"}


def _ordered_item_ids(paper: ExamPaperManifest) -> list[str]:
    return [item_id for section in paper.sections for item_id in section.item_ids]


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _single_teacher_block(path: Path, item_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    assignment = load_yaml(path)
    blocks = question_blocks(assignment)
    if len(blocks) != 1:
        raise ValueError(
            f"{item_id}: teacher assignment must contain exactly one practice question"
        )
    block = blocks[0]
    if block.get("id") != item_id:
        raise ValueError(f"{item_id}: teacher block id differs")
    if block.get("type") not in QUESTION_TYPES:
        raise ValueError(f"{item_id}: unsupported teacher question type")
    teaching = block.get("teaching") or {}
    if not isinstance(teaching, dict):
        raise ValueError(f"{item_id}: teacher block teaching must be a mapping")
    return assignment, block


def _validate_student(path: Path, item_id: str, expected_type: str) -> None:
    assignment = load_yaml(path)
    blocks = question_blocks(assignment)
    if len(blocks) != 1:
        raise ValueError(
            f"{item_id}: student assignment must contain exactly one practice question"
        )
    block = blocks[0]
    if block.get("id") != item_id:
        raise ValueError(f"{item_id}: student block id differs")
    if block.get("type") != expected_type:
        raise ValueError(f"{item_id}: student and teacher question types differ")


def _diagram_requirement(
    source: ExamItemSource, block: dict[str, Any], teaching: dict[str, Any]
) -> str:
    explicit = teaching.get("diagram_requirement")
    if explicit is not None:
        if explicit not in DIAGRAM_REQUIREMENTS:
            raise ValueError(f"{source.item_id}: invalid teaching.diagram_requirement")
        return str(explicit)
    if not source.crops.prompt:
        return "none"
    has_solution_diagram = any(
        isinstance(value, dict)
        and value.get("variant") in {"solution", "annotated"}
        and (value.get("image_path") or value.get("tikz_path") or value.get("tikz_code"))
        for value in _walk(block)
    )
    return "prompt_and_solution" if has_solution_diagram else "prompt_only"


def _item_metadata(
    source: ExamItemSource, teacher_path: Path, student_path: Path
) -> dict[str, Any]:
    _, block = _single_teacher_block(teacher_path, source.item_id)
    _validate_student(student_path, source.item_id, str(block["type"]))
    if block["type"] != source.question_type:
        raise ValueError(f"{source.item_id}: teacher question type differs from source")
    teaching = block.get("teaching") or {}

    difficulty = teaching.get("difficulty")
    if difficulty not in DIFFICULTIES:
        raise ValueError(
            f"{source.item_id}: teaching.difficulty must be one of "
            + ", ".join(sorted(DIFFICULTIES))
        )
    skill_tags = teaching.get("skill_tags")
    if (
        not isinstance(skill_tags, list)
        or not skill_tags
        or any(not isinstance(tag, str) or not tag.strip() for tag in skill_tags)
    ):
        raise ValueError(f"{source.item_id}: teaching.skill_tags must be non-empty strings")

    title = (
        teaching.get("title")
        or block.get("title")
        or block.get("label")
        or f"第 {source.question_number} 题"
    )
    variation_dimension = teaching.get("variation_dimension", "source_exam")
    if not isinstance(variation_dimension, str) or not variation_dimension.strip():
        raise ValueError(
            f"{source.item_id}: teaching.variation_dimension must be a non-empty string"
        )
    weight = teaching.get("weight", 1.0)
    enabled = teaching.get("enabled", True)

    return {
        "id": source.item_id,
        "title": str(title),
        "question_type": source.question_type,
        "difficulty": difficulty,
        "skill_tags": skill_tags,
        "variation_dimension": variation_dimension,
        "diagram_requirement": _diagram_requirement(source, block, teaching),
        "student_assignment": f"items/{source.item_id}/student.resolved.assignment.yaml",
        "teacher_assignment": f"items/{source.item_id}/teacher.resolved.assignment.yaml",
        "source_ref": f"items/{source.item_id}/source.yaml",
        "weight": weight,
        "enabled": enabled,
    }


def _validated_item(
    item_dir: Path, item_id: str, paper_id: str, repo_root: Path
) -> tuple[ExamItemSource, dict[str, Any]]:
    source_path = item_dir / "source.yaml"
    review_path = item_dir / "review.yaml"
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    student_path = item_dir / "student.resolved.assignment.yaml"
    missing = [
        path.name
        for path in (source_path, review_path, teacher_path, student_path)
        if not path.is_file()
    ]
    if missing:
        raise ValueError(f"{item_id}: missing required files: {', '.join(missing)}")

    source, errors = validate_source(
        source_path, review_path=review_path, repo_root=repo_root
    )
    if errors:
        raise ValueError(f"{item_id}: " + "; ".join(errors))
    assert source is not None
    review = ExamItemReview.model_validate(load_yaml(review_path))
    if source.item_id != item_id:
        raise ValueError(f"{item_id}: source item_id differs")
    if source.paper_id != paper_id:
        raise ValueError(f"{item_id}: source paper_id differs")
    if review.status != "approved":
        raise ValueError(f"{item_id}: review status must be approved")
    if review.content_hash != source.content_hash:
        raise ValueError(f"{item_id}: review content_hash differs from source")
    metadata = _item_metadata(source, teacher_path, student_path)
    QuestionBankItem.model_validate(metadata)
    return source, metadata


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def _atomic_replace_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                payload, handle, allow_unicode=True, sort_keys=False, width=1000
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def promote_paper(
    paper_path: Path,
    bank_path: Path,
    *,
    repo_root: Path | None = None,
    canonical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promote all paper items and atomically register them in ``question-bank.yaml``.

    ``canonical`` (Phase 2): when given (``{"parser_provenance": …,
    "pack_map": …}``), immutable canonical QuestionTruth versions are written
    for every approved item AFTER the bank promotion succeeds. Publication
    validation runs BEFORE the bank is touched (fail closed: an un-publishable
    truth never enters the bank, mirroring the pubfail fixtures).
    """

    paper_path = paper_path.resolve()
    bank_path = bank_path.resolve()
    root = repo_root.resolve() if repo_root else Path.cwd().resolve()
    canonical_export = None
    if canonical is not None:
        canonical_export = build_candidate_export(
            paper_path.parent,
            parser_provenance=canonical["parser_provenance"],
            pack_map=canonical["pack_map"],
            ledger_path=canonical.get("ledger_path"),
        )
        # Dry-run publication validation before ANY bank mutation. The version is
        # a schema-legal placeholder ("v0" is never a real version — real ones
        # start at v1); version/artifact_uri are content-hash-excluded identity
        # fields, so the validated content is exactly what promote will write.
        from canonical_export import _build_truth_payload, _validate_publication

        for item in canonical_export["items"]:
            _validate_publication(_build_truth_payload(item, version="v0"))
    if (paper_path.parent / "review-issues.yaml").is_file():
        raise ValueError(
            "staging contains review-issues.yaml; resolve issues, apply resolutions, "
            "and rebuild a normal staging before promotion"
        )
    try:
        paper = ExamPaperManifest.model_validate(load_yaml(paper_path))
        bank_raw = load_yaml(bank_path)
        bank = QuestionBank.model_validate(bank_raw)
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(str(exc)) from exc

    declared_bank = (paper_path.parent / paper.question_bank).resolve()
    if declared_bank != bank_path:
        raise ValueError(
            f"paper question_bank resolves to {declared_bank}, not {bank_path}"
        )

    ordered_ids = _ordered_item_ids(paper)
    existing_ids = {item.id for item in bank.items}
    conflicts = sorted(existing_ids.intersection(ordered_ids))
    if conflicts:
        raise ValueError("question bank item ID conflict: " + ", ".join(conflicts))

    bank_dir = bank_path.parent
    formal_items_dir = bank_dir / "items"
    destination_paper_dir = bank_dir / "papers" / paper.paper.id
    path_conflicts = [
        item_id for item_id in ordered_ids if (formal_items_dir / item_id).exists()
    ]
    if path_conflicts:
        raise ValueError("formal item directory conflict: " + ", ".join(path_conflicts))
    if destination_paper_dir.exists():
        raise ValueError(f"paper destination already exists: {destination_paper_dir}")

    source_items_dir = paper_path.parent / "items"
    metadata_by_id: dict[str, dict[str, Any]] = {}
    for item_id in ordered_ids:
        _, metadata = _validated_item(
            source_items_dir / item_id, item_id, paper.paper.id, root
        )
        metadata_by_id[item_id] = metadata

    candidate = copy.deepcopy(bank_raw)
    candidate["items"] = list(candidate.get("items") or []) + [
        metadata_by_id[item_id] for item_id in ordered_ids
    ]
    final_count = len(candidate["items"])
    status = candidate["bank"].get("status", "plan")
    target_count = int(candidate["bank"].get("target_count", 30))
    if status == "ready" and final_count != target_count:
        raise ValueError(
            f"ready bank target_count is {target_count}, promotion would produce {final_count} items"
        )
    if status == "plan" and final_count == target_count:
        candidate["bank"]["status"] = "ready"
    QuestionBank.model_validate(candidate)

    formal_items_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=".promote-paper-", dir=bank_dir))
    placed_items: list[Path] = []
    paper_placed = False
    try:
        copied_root = work_dir / "items"
        for item_id in ordered_ids:
            shutil.copytree(source_items_dir / item_id, copied_root / item_id)
        for item_id in ordered_ids:
            copied_source_path = copied_root / item_id / "source.yaml"
            copied_source = load_yaml(copied_source_path)
            copied_source["transcription"]["human_review"] = "approved"
            _write_yaml(copied_source_path, copied_source)
            _, copied_metadata = _validated_item(
                copied_root / item_id, item_id, paper.paper.id, root
            )
            if copied_metadata != metadata_by_id[item_id]:
                raise ValueError(f"{item_id}: copied metadata changed during promotion")

        for item_id in ordered_ids:
            destination = formal_items_dir / item_id
            if destination.exists():
                raise ValueError(f"formal item directory conflict: {item_id}")
            os.replace(copied_root / item_id, destination)
            placed_items.append(destination)

        destination_paper_dir.parent.mkdir(parents=True, exist_ok=True)
        staged_paper_dir = work_dir / "paper"
        staged_paper_dir.mkdir()
        promoted_paper = load_yaml(paper_path)
        promoted_paper["question_bank"] = Path(
            os.path.relpath(bank_path, destination_paper_dir)
        ).as_posix()
        staged_paper = staged_paper_dir / "paper.yaml"
        _write_yaml(staged_paper, promoted_paper)
        source_paper_map = paper_path.parent / "paper-map.yaml"
        if source_paper_map.is_file():
            paper_map = ExamPaperMap.model_validate(load_yaml(source_paper_map))
            if paper_map.paper_id != paper.paper.id:
                raise ValueError("paper-map paper_id differs from paper.yaml")
            if [item.item_id for item in paper_map.items] != ordered_ids:
                raise ValueError("paper-map item order differs from paper.yaml")
            shutil.copy2(source_paper_map, staged_paper_dir / "paper-map.yaml")
        ExamPaperManifest.model_validate(load_yaml(staged_paper))
        if destination_paper_dir.exists():
            raise ValueError(f"paper destination already exists: {destination_paper_dir}")
        os.replace(staged_paper_dir, destination_paper_dir)
        paper_placed = True

        descriptor, candidate_name = tempfile.mkstemp(
            prefix=".question-bank.candidate.", suffix=".yaml", dir=bank_dir
        )
        os.close(descriptor)
        candidate_path = Path(candidate_name)
        try:
            _write_yaml(candidate_path, candidate)
            promoted_bank, errors = validate_manifest(candidate_path)
            if errors:
                raise ValueError(
                    "promoted question bank validation failed: " + "; ".join(errors)
                )
            assert promoted_bank is not None
        finally:
            candidate_path.unlink(missing_ok=True)

        _atomic_replace_yaml(bank_path, candidate)
        canonical_result = None
        if canonical_export is not None:
            canonical_result = promote_canonical(canonical_export)
    except BaseException:
        if paper_placed:
            shutil.rmtree(destination_paper_dir, ignore_errors=True)
        for destination in reversed(placed_items):
            shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    result = {
        "paper_id": paper.paper.id,
        "item_ids": ordered_ids,
        "question_bank": str(bank_path),
        "paper_manifest": str(destination_paper_dir / "paper.yaml"),
    }
    if canonical_export is not None:
        result["canonical"] = canonical_result
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper", type=Path, help="staging/<paper>/paper.yaml")
    parser.add_argument("question_bank", type=Path, help="formal question-bank.yaml")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument(
        "--canonical",
        action="store_true",
        help=(
            "also write immutable canonical QuestionTruth versions "
            "(Phase 2; publication validation is fail closed)"
        ),
    )
    parser.add_argument(
        "--pack-map",
        type=Path,
        help="YAML mapping source directory name -> pack id (required with --canonical)",
    )
    parser.add_argument(
        "--parser-id", default="math-topic-question-bank/ingestion"
    )
    parser.add_argument(
        "--parser-version", default="langgraph-question-ingestion/v0+whole-paper-v2"
    )
    parser.add_argument(
        "--harness",
        default="langgraph+claude-code-glm-5.2+qwen3.5-ocr",
    )
    args = parser.parse_args()
    canonical = None
    if args.canonical:
        if not args.pack_map:
            raise SystemExit("--canonical requires --pack-map")
        pack_map = yaml.safe_load(args.pack_map.read_text(encoding="utf-8"))
        if not isinstance(pack_map, dict):
            raise SystemExit("--pack-map must be a mapping")
        canonical = {
            "parser_provenance": {
                "parser_id": args.parser_id,
                "parser_version": args.parser_version,
                "harness": args.harness,
            },
            "pack_map": pack_map,
        }
    try:
        result = promote_paper(
            args.paper,
            args.question_bank,
            repo_root=args.repo_root,
            canonical=canonical,
        )
    except (OSError, ValueError, yaml.YAMLError, ValidationError, CanonicalExportError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"PROMOTED PAPER {result['paper_id']}: "
        + ", ".join(result["item_ids"])
    )
    print(result["paper_manifest"])
    if result.get("canonical"):
        canonical_result = result["canonical"]
        print(
            "CANONICAL: promoted="
            + ",".join(canonical_result["promoted"])
            + " skipped="
            + ",".join(canonical_result["skipped"])
            + " superseded="
            + ",".join(canonical_result["superseded"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
