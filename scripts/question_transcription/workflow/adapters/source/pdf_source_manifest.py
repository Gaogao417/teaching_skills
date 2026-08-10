#!/usr/bin/env python3
"""Build an immutable manifest for pre-rendered PDF page images."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import yaml
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.pdf_observation_contracts import PdfSourceManifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def build_manifest(
    *,
    paper_id: str,
    source_archive: str,
    page_paths: list[Path],
    pdf_path: Path | None = None,
    dpi: int = 180,
    engine: str = "pre_rendered",
) -> PdfSourceManifest:
    pages = []
    for number, page_path in enumerate(page_paths, start=1):
        with Image.open(page_path) as image:
            width, height = image.size
        try:
            source = page_path.relative_to(Path(source_archive)).as_posix()
        except ValueError:
            source = page_path.as_posix()
        pages.append(
            {
                "page_number": number,
                "source": source,
                "width_px": width,
                "height_px": height,
                "sha256": _sha256(page_path),
            }
        )
    source_path = pdf_path.as_posix() if pdf_path else "<pre-rendered-pages>"
    source_sha = _sha256(pdf_path) if pdf_path else None
    return PdfSourceManifest.model_validate(
        {
            "schema": "math_pdf_source/v1",
            "paper_id": paper_id,
            "source_archive": source_archive.rstrip("/"),
            "source": {"path": source_path, "sha256": source_sha},
            "render": {"engine": engine, "dpi": dpi},
            "pages": pages,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--source-archive", required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--glob", default="*.png")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument(
        "--engine", choices=["pdftoppm", "pre_rendered"], default="pre_rendered"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    page_paths = sorted(args.pages_dir.glob(args.glob))
    if not page_paths:
        raise ValueError(f"no page images matched {args.pages_dir / args.glob}")
    manifest = build_manifest(
        paper_id=args.paper_id,
        source_archive=args.source_archive,
        page_paths=page_paths,
        pdf_path=args.pdf,
        dpi=args.dpi,
        engine=args.engine,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(
            manifest.model_dump(by_alias=True, exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"PDF SOURCE MANIFEST: {args.output} | pages={len(manifest.pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
