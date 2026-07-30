#!/usr/bin/env python3
"""Regenerate every crop declared by staged exam source records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from question_bank_repo import find_repo_root


REPO_ROOT = find_repo_root()


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def recrop_item(item_dir: Path) -> None:
    source_path = item_dir / "source.yaml"
    source = read_yaml(source_path)
    for crops in source["crops"].values():
        for crop in crops:
            original = (REPO_ROOT / crop["source"]).resolve()
            output = (item_dir / crop["output"]).resolve()
            left, top, right, bottom = map(int, crop["box_px"])
            with Image.open(original) as image:
                width, height = image.size
                if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                    raise ValueError(
                        f"{source['item_id']}: crop exceeds {original.name} ({width}x{height})"
                    )
                output.parent.mkdir(parents=True, exist_ok=True)
                cropped = image.crop((left, top, right, bottom))
                for whiteout in crop.get("whiteout_px", []):
                    whiteout_box = tuple(map(int, whiteout))
                    whiteout_left, whiteout_top, whiteout_right, whiteout_bottom = whiteout_box
                    crop_width, crop_height = cropped.size
                    if not (
                        0 <= whiteout_left < whiteout_right <= crop_width
                        and 0 <= whiteout_top < whiteout_bottom <= crop_height
                    ):
                        raise ValueError(
                            f"{source['item_id']}: whiteout exceeds crop "
                            f"({crop_width}x{crop_height})"
                        )
                    cropped.paste("white", whiteout_box)
                cropped.save(output)
            crop["source_sha256"] = sha256(original)
            crop["output_sha256"] = sha256(output)

    teacher = read_yaml(item_dir / "teacher.resolved.assignment.yaml")
    student = read_yaml(item_dir / "student.resolved.assignment.yaml")
    source["content_hash"] = canonical_hash(
        {
            "teacher": teacher,
            "student": student,
            "crop_hashes": {
                role: [crop["output_sha256"] for crop in crops]
                for role, crops in source["crops"].items()
            },
        }
    )
    write_yaml(source_path, source)
    print(f"{source['item_id']}: crops regenerated")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    wanted = set(args.only)
    for item_dir in sorted((args.staging_dir / "items").glob("Q[0-9][0-9][0-9]")):
        if wanted and item_dir.name not in wanted:
            continue
        recrop_item(item_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
