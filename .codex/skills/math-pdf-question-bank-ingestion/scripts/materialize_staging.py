#!/usr/bin/env python3
"""Crop source evidence, derive student assignments, and refresh item hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from PIL import Image
import yaml


TOPIC_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "math-topic-question-bank" / "scripts"
)
sys.path.insert(0, str(TOPIC_SCRIPTS))

from exam_image_utils import composite_transparency_on_white  # noqa: E402


ROLES = ("question_evidence", "prompt", "solution", "official_solution")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def materialize_crop(
    crop: dict[str, Any], *, item_dir: Path, repo_root: Path, label: str
) -> None:
    source = Path(str(crop.get("source", "")))
    if not source.is_absolute():
        source = repo_root / source
    source = source.resolve()
    if not inside(source, repo_root):
        raise ValueError(f"{label}: source escapes repo root")
    if not source.is_file():
        raise ValueError(f"{label}: source image not found: {source}")

    output = Path(str(crop.get("output", "")))
    if output.is_absolute():
        raise ValueError(f"{label}: output must be relative to item directory")
    output = (item_dir / output).resolve()
    if not inside(output, item_dir):
        raise ValueError(f"{label}: output escapes item directory")

    box = crop.get("box_px")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"{label}: box_px must contain four integers")
    left, top, right, bottom = map(int, box)
    with Image.open(source) as image:
        width, height = image.size
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(
                f"{label}: crop {box} exceeds source image {width}x{height}"
            )
        result = composite_transparency_on_white(
            image.crop((left, top, right, bottom))
        )

    for index, raw_whiteout in enumerate(crop.get("whiteout_px") or []):
        if not isinstance(raw_whiteout, list) or len(raw_whiteout) != 4:
            raise ValueError(f"{label}: whiteout_px[{index}] must contain four integers")
        whiteout = tuple(map(int, raw_whiteout))
        w_left, w_top, w_right, w_bottom = whiteout
        crop_width, crop_height = result.size
        if not (
            0 <= w_left < w_right <= crop_width
            and 0 <= w_top < w_bottom <= crop_height
        ):
            raise ValueError(
                f"{label}: whiteout_px[{index}] exceeds crop {crop_width}x{crop_height}"
            )
        result.paste("white", whiteout)

    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, format="PNG")
    crop["source_sha256"] = sha256(source)
    crop["output_sha256"] = sha256(output)


def materialize_word_evidence(
    span: dict[str, Any], *, repo_root: Path, label: str
) -> None:
    page_image = Path(str(span.get("page_image", "")))
    if not page_image.is_absolute():
        page_image = repo_root / page_image
    page_image = page_image.resolve()
    if not inside(page_image, repo_root):
        raise ValueError(f"{label}: page_image must stay inside repo root")
    if not page_image.is_file():
        raise ValueError(f"{label}: missing page image {page_image}")
    span["page_image_sha256"] = sha256(page_image)


def item_ids(staging_dir: Path, only: set[str]) -> list[str]:
    paper = load_yaml(staging_dir / "paper.yaml")
    ordered = [
        str(item_id)
        for section in paper.get("sections") or []
        for item_id in (section.get("item_ids") or [])
        if isinstance(section, dict)
    ]
    if len(ordered) != len(set(ordered)):
        raise ValueError("paper.yaml contains duplicate item IDs")
    if only:
        unknown = sorted(only.difference(ordered))
        if unknown:
            raise ValueError("--only item not present in paper.yaml: " + ", ".join(unknown))
        ordered = [item_id for item_id in ordered if item_id in only]
    return ordered


def materialize_item(item_dir: Path, repo_root: Path) -> tuple[str, bool]:
    source_path = item_dir / "source.yaml"
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    student_path = item_dir / "student.resolved.assignment.yaml"
    if not source_path.is_file() or not teacher_path.is_file():
        raise ValueError(f"{item_dir.name}: source.yaml and teacher assignment are required")

    source = load_yaml(source_path)
    crops = source.get("crops")
    if not isinstance(crops, dict):
        raise ValueError(f"{item_dir.name}: source crops must be a mapping")
    for role in ROLES:
        role_crops = crops.get(role, [])
        if not isinstance(role_crops, list):
            raise ValueError(f"{item_dir.name}: crops.{role} must be a list")
        for index, crop in enumerate(role_crops):
            if not isinstance(crop, dict):
                raise ValueError(f"{item_dir.name}: crops.{role}[{index}] must be a mapping")
            materialize_crop(
                crop,
                item_dir=item_dir,
                repo_root=repo_root,
                label=f"{item_dir.name} {role}[{index}]",
            )
    word_evidence = source.get("word_evidence") or {}
    if not isinstance(word_evidence, dict):
        raise ValueError(f"{item_dir.name}: word_evidence must be a mapping")
    for role in ("question", "official_solution"):
        spans = word_evidence.get(role, [])
        if not isinstance(spans, list):
            raise ValueError(f"{item_dir.name}: word_evidence.{role} must be a list")
        for index, span in enumerate(spans):
            if not isinstance(span, dict):
                raise ValueError(
                    f"{item_dir.name}: word_evidence.{role}[{index}] must be a mapping"
                )
            materialize_word_evidence(
                span,
                repo_root=repo_root,
                label=f"{item_dir.name} word_evidence.{role}[{index}]",
            )

    derive_script = (
        repo_root
        / ".codex/skills/math-topic-question-bank/scripts/derive_student_assignment.py"
    )
    subprocess.run(
        [
            sys.executable,
            str(derive_script),
            str(teacher_path),
            "--out",
            str(student_path),
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    teacher = load_yaml(teacher_path)
    student = load_yaml(student_path)
    previous_hash = source.get("content_hash")
    hash_payload = {
        "teacher": teacher,
        "student": student,
        "crop_hashes": {
            role: [crop["output_sha256"] for crop in crops.get(role, [])]
            for role in ROLES
        },
    }
    current_hash = canonical_hash(hash_payload)
    changed = previous_hash != current_hash
    source["content_hash"] = current_hash
    if changed:
        transcription = source.setdefault("transcription", {})
        transcription["human_review"] = "pending"
    write_yaml(source_path, source)
    return str(source.get("item_id") or item_dir.name), changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    staging_dir = args.staging_dir.resolve()
    repo_root = args.repo_root.resolve()
    try:
        ordered = item_ids(staging_dir, set(args.only))
        for item_id in ordered:
            actual_id, changed = materialize_item(staging_dir / "items" / item_id, repo_root)
            suffix = " (content hash changed; prior review is stale)" if changed else ""
            print(f"{actual_id}: materialized{suffix}")
    except (OSError, ValueError, yaml.YAMLError, subprocess.CalledProcessError) as exc:
        print(f"MATERIALIZATION FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"materialized {len(ordered)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
