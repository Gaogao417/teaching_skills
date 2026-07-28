#!/usr/bin/env python3
"""Extract media, render pages, and build word-source.yaml from a DOCX file."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml
from docx import Document


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def extract_media(docx_path: Path, media_dir: Path) -> list[dict[str, Any]]:
    """Unzip docx and copy media files, returning metadata."""
    media_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    with zipfile.ZipFile(docx_path) as zf:
        media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
        for name in media_files:
            filename = Path(name).name
            dest = media_dir / filename
            with zf.open(name) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            entries.append({
                "filename": filename,
                "sha256": sha256(dest),
                "size": dest.stat().st_size,
            })
    return entries


def render_pages(docx_path: Path, pages_dir: Path) -> int:
    """Render DOCX to PNG page images via LibreOffice PDF intermediate."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Convert DOCX -> PDF
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                tmpdir,
                str(docx_path),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        pdfs = list(Path(tmpdir).glob("*.pdf"))
        if not pdfs:
            return 0
        pdf_path = pdfs[0]

        # Step 2: Convert PDF pages -> PNG using pdftoppm or Python
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", "200", str(pdf_path),
                 str(pages_dir / "page")],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except FileNotFoundError:
            # Fallback: use PyMuPDF or PIL-based pdf2image
            from pdf2image import convert_from_path
            images = convert_from_path(str(pdf_path), dpi=200)
            for i, img in enumerate(images, start=1):
                img.save(pages_dir / f"page-{i:02d}.png", "PNG")
            return len(images)

        rendered = sorted(pages_dir.glob("page-*.png"))
        # Rename to consistent format if needed
        for i, src in enumerate(rendered, start=1):
            dest = pages_dir / f"page-{i:02d}.png"
            if src != dest:
                src.rename(dest)
        return len(rendered)


def build_word_source(docx_path: Path) -> dict[str, Any]:
    """Parse docx paragraphs and build structured word-source data."""
    doc = Document(str(docx_path))
    paragraphs: list[dict[str, Any]] = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        entry: dict[str, Any] = {
            "index": i,
            "text": text,
            "style": para.style.name if para.style else None,
        }
        # Detect inline images in runs
        images: list[str] = []
        for run in para.runs:
            drawing_elements = run._element.findall(
                ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
            )
            for drawing in drawing_elements:
                blip_elements = drawing.findall(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
                )
                for blip in blip_elements:
                    rid = blip.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                    )
                    if rid:
                        images.append(rid)
        if images:
            entry["inline_images"] = images
        paragraphs.append(entry)
    return {
        "source_file": docx_path.name,
        "paragraph_count": len(paragraphs),
        "paragraphs": paragraphs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path, help="Path to .doc or .docx file")
    parser.add_argument("output_dir", type=Path, help="Output word/ directory")
    parser.add_argument("--skip-render", action="store_true",
                        help="Skip LibreOffice page rendering")
    args = parser.parse_args()

    docx_path = args.docx.resolve()
    if not docx_path.is_file():
        print(f"ERROR: {docx_path} not found", flush=True)
        return 1

    output_dir = args.output_dir.resolve()
    media_dir = output_dir / "media"
    pages_dir = output_dir / "pages"

    # Handle .doc by converting to .docx first via LibreOffice
    if docx_path.suffix.lower() == ".doc":
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "docx",
                 "--outdir", tmpdir, str(docx_path)],
                check=True, capture_output=True, timeout=120,
            )
            converted = list(Path(tmpdir).glob("*.docx"))
            if not converted:
                print("ERROR: .doc conversion failed", flush=True)
                return 1
            docx_path = converted[0]

    # Step 1: Extract media
    media_entries = extract_media(docx_path, media_dir)
    print(f"Extracted {len(media_entries)} media files to {media_dir}")

    # Step 2: Render pages
    page_count = 0
    if not args.skip_render:
        page_count = render_pages(docx_path, pages_dir)
        print(f"Rendered {page_count} page images to {pages_dir}")

    # Step 3: Build word-source.yaml
    word_source = build_word_source(docx_path)
    word_source["media_files"] = media_entries
    word_source["page_count"] = page_count

    source_yaml = output_dir / "word-source.yaml"
    source_yaml.parent.mkdir(parents=True, exist_ok=True)
    source_yaml.write_text(
        yaml.safe_dump(word_source, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(f"Written {source_yaml}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
