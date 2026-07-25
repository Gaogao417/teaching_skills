#!/usr/bin/env python3
"""Render a PDF into immutable, zero-padded PNG source pages."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    if not match:
        raise ValueError(f"unexpected pdftoppm output: {path.name}")
    return int(match.group(1))


def render(pdf: Path, output_dir: Path, dpi: int) -> list[Path]:
    pdf = pdf.resolve()
    output_dir = output_dir.resolve()
    if not pdf.is_file():
        raise ValueError(f"PDF not found: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        raise ValueError(f"input must be a PDF: {pdf}")
    if output_dir.exists():
        raise ValueError(f"output directory already exists; refusing overwrite: {output_dir}")
    if dpi < 96 or dpi > 600:
        raise ValueError("--dpi must be between 96 and 600")
    executable = shutil.which("pdftoppm")
    if executable is None:
        raise ValueError("pdftoppm is required but was not found")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}-", dir=output_dir.parent
    ) as temporary_name:
        temporary = Path(temporary_name)
        subprocess.run(
            [
                executable,
                "-png",
                "-r",
                str(dpi),
                str(pdf),
                str(temporary / "page"),
            ],
            check=True,
        )
        rendered = sorted(temporary.glob("page-*.png"), key=page_number)
        if not rendered:
            raise ValueError("pdftoppm produced no pages")
        output_dir.mkdir()
        outputs: list[Path] = []
        try:
            for index, source in enumerate(rendered, start=1):
                target = output_dir / f"{index:03d}.png"
                source.replace(target)
                with Image.open(target) as image:
                    image.verify()
                outputs.append(target)
        except BaseException:
            shutil.rmtree(output_dir, ignore_errors=True)
            raise
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()

    try:
        outputs = render(args.pdf, args.output_dir, args.dpi)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    for path in outputs:
        with Image.open(path) as image:
            size = f"{image.width}x{image.height}"
        print(f"{path.name}\t{size}\tsha256:{sha256(path)}")
    print(f"rendered {len(outputs)} immutable source pages into {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
