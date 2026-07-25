#!/usr/bin/env python3
"""Validate archived exam source evidence and an optional user review."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops
import yaml
from pydantic import ValidationError

from exam_source_contracts import ExamItemReview, ExamItemSource


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def validate_source(
    source_path: Path, *, review_path: Path | None = None, repo_root: Path | None = None
) -> tuple[ExamItemSource | None, list[str]]:
    errors: list[str] = []
    try:
        source = ExamItemSource.model_validate(load_yaml(source_path))
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
        return None, [str(exc)]

    root = repo_root.resolve() if repo_root else Path.cwd().resolve()
    for role, crops in (
        ("question_evidence", source.crops.question_evidence),
        ("prompt", source.crops.prompt),
        ("solution", source.crops.solution),
        ("official_solution", source.crops.official_solution),
    ):
        for index, crop in enumerate(crops):
            prefix = f"{role}[{index}]"
            source_image = Path(crop.source)
            if not source_image.is_absolute():
                source_image = root / source_image
            output_image = Path(crop.output)
            if not output_image.is_absolute():
                output_image = source_path.parent / output_image
            if not source_image.is_file():
                errors.append(f"{prefix}: missing source image {crop.source}")
                continue
            if sha256(source_image) != crop.source_sha256:
                errors.append(f"{prefix}: source_sha256 mismatch")
            with Image.open(source_image) as image:
                width, height = image.size
            left, top, right, bottom = crop.box_px
            if right > width or bottom > height:
                errors.append(
                    f"{prefix}: box_px {list(crop.box_px)} exceeds source size {width}x{height}"
                )
            if not output_image.is_file():
                errors.append(f"{prefix}: missing crop output {crop.output}")
            else:
                if sha256(output_image) != crop.output_sha256:
                    errors.append(f"{prefix}: output_sha256 mismatch")
                if right <= width and bottom <= height:
                    with Image.open(source_image) as source_pixels:
                        expected = source_pixels.crop(crop.box_px).convert("RGB")
                    for whiteout in crop.whiteout_px:
                        expected.paste("white", whiteout)
                    with Image.open(output_image) as output_pixels:
                        actual = output_pixels.convert("RGB")
                    if actual.size != expected.size or ImageChops.difference(
                        expected, actual
                    ).getbbox() is not None:
                        errors.append(f"{prefix}: output pixels do not match box_px crop")

    manifest_cache: dict[Path, dict[str, Any]] = {}
    for role, spans in (
        ("question", source.word_evidence.question),
        ("official_solution", source.word_evidence.official_solution),
    ):
        for index, span in enumerate(spans):
            prefix = f"word_evidence.{role}[{index}]"
            manifest = Path(span.manifest)
            if not manifest.is_absolute():
                manifest = root / manifest
            manifest = manifest.resolve()
            try:
                manifest.relative_to(root)
            except ValueError:
                errors.append(f"{prefix}: manifest must stay inside repo root")
                continue
            if not manifest.is_file():
                errors.append(f"{prefix}: missing Word manifest {span.manifest}")
                continue
            if sha256(manifest) != span.manifest_sha256:
                errors.append(f"{prefix}: manifest_sha256 mismatch")
            try:
                payload = manifest_cache.setdefault(manifest, load_yaml(manifest))
            except (OSError, ValueError, yaml.YAMLError) as exc:
                errors.append(f"{prefix}: invalid Word manifest: {exc}")
                continue
            if payload.get("schema") != "math_word_source_extract/v1":
                errors.append(f"{prefix}: unsupported Word manifest schema")
                continue
            indexes = {
                int(record.get("index"))
                for record in payload.get("paragraphs") or []
                if isinstance(record, dict) and record.get("index") is not None
            }
            if not any(
                span.paragraph_start <= paragraph_index <= span.paragraph_end
                for paragraph_index in indexes
            ):
                errors.append(
                    f"{prefix}: paragraph range "
                    f"{span.paragraph_start}..{span.paragraph_end} is absent"
                )

    if review_path is not None:
        try:
            review = ExamItemReview.model_validate(load_yaml(review_path))
        except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
            errors.append(str(exc))
        else:
            if review.item_id != source.item_id:
                errors.append("review item_id does not match source")
            if review.source_key != source.source_key:
                errors.append("review source_key does not match source")
            if review.content_hash != source.content_hash:
                errors.append("review content_hash does not match source")
    return source, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()
    source, errors = validate_source(
        args.source.resolve(),
        review_path=args.review.resolve() if args.review else None,
        repo_root=args.repo_root,
    )
    if errors:
        print("EXAM SOURCE INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    assert source is not None
    print(f"EXAM SOURCE VALID: {source.source_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
