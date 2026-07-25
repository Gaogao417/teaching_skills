#!/usr/bin/env python3
"""Crop deterministic prompt/solution assets declared in a YAML manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    repo_root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    for item in data.get("crops", []):
        source = Path(item["source"])
        if not source.is_absolute():
            source = repo_root / source
        output = Path(item["output"])
        if not output.is_absolute():
            output = manifest_path.parent / output

        with Image.open(source) as image:
            width, height = image.size
            box = item["box"]
            if item.get("units", "pixels") == "normalized":
                left, top, right, bottom = (
                    round(box[0] * width),
                    round(box[1] * height),
                    round(box[2] * width),
                    round(box[3] * height),
                )
            else:
                left, top, right, bottom = map(int, box)

            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError(
                    f"invalid crop {item.get('id', output.name)}: "
                    f"{(left, top, right, bottom)} for {source} ({width}, {height})"
                )

            cropped = image.crop((left, top, right, bottom))
            output.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(output)
            print(f"{item.get('id', output.stem)}: {source.name} -> {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
