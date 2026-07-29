#!/usr/bin/env python3
"""Build a ``math_question_span_index/v1`` from a DOCX-rendered PDF (§5.2).

Locates ``rendered.pdf`` relative to the ``word-source.yaml`` manifest directory
(never assumes CWD), runs ``pdftotext -layout`` and splits on form-feed to get
per-page text, cross-checks the text page count against ``rendered_pages`` and
the on-disk ``pages/*.png``, and feeds the per-page text to the anchoring
algorithm in :mod:`question_span_index`.

The manifest ``paragraphs`` are used only for section/role cross-validation and
are never re-injected into the formal vision prompt (that was the OOXML 全文
串线 source this redesign removes). The fingerprint carries the rendered-PDF SHA,
the per-page PNG SHAs and the offset, so the observer can refuse a stale index.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.question_span_index import (
    PageText,
    QuestionSpanIndex,
    SourceFingerprint,
    build_index_from_pages,
    dump_index,
)

WORD_SOURCE_SCHEMA = "math_word_source_extract/v1"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _require_pdftotext() -> str:
    """Return the pdftotext executable path or raise a clear error."""
    executable = shutil.which("pdftotext")
    if executable is None:
        raise RuntimeError(
            "pdftotext (Poppler) is required to build a DOCX span index but was "
            "not found on PATH. Install Poppler, e.g. `brew install poppler`."
        )
    return executable


def _run_pdftotext(pdftotext: str, pdf_path: Path) -> list[str]:
    """Run ``pdftotext -layout`` and return one text block per page."""
    result = subprocess.run(
        [pdftotext, "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pdftotext exited with code {result.returncode}: "
            f"{result.stderr.strip()[:500]}"
        )
    pages = result.stdout.split("\f")
    # pdftotext emits a trailing empty page after the final form-feed; drop it.
    if pages and pages[-1].strip() == "":
        pages = pages[:-1]
    return pages


def _load_word_source(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a mapping")
    if data.get("schema") != WORD_SOURCE_SCHEMA:
        raise ValueError(
            f"{path} schema must be {WORD_SOURCE_SCHEMA!r}, got {data.get('schema')!r}"
        )
    return data


# --------------------------------------------------------------------------- #
# Build entry point
# --------------------------------------------------------------------------- #


def build_docx_span_index(
    word_source_path: Path,
    *,
    output: Path,
    page_number_offset: int = 0,
) -> QuestionSpanIndex:
    """Build and persist the DOCX span index.

    Raises :class:`RuntimeError` when pdftotext is missing, exits non-zero, or
    the text page count disagrees with the rendered pages / PNG count.
    """
    if page_number_offset < 0:
        raise ValueError("page_number_offset must be non-negative")
    manifest_dir = word_source_path.parent
    word_source = _load_word_source(word_source_path)

    rendered_pdf_field = word_source.get("rendered_pdf")
    rendered_pages_field = word_source.get("rendered_pages")
    if not rendered_pdf_field or not rendered_pages_field:
        raise RuntimeError(
            f"{word_source_path} has no rendered_pdf/rendered_pages; rerun the "
            "DOCX extractor without --no-pdf so a rendered PDF is available."
        )

    pdf_path = manifest_dir / rendered_pdf_field["path"]
    if not pdf_path.exists():
        raise RuntimeError(
            f"rendered PDF not found at {pdf_path} (resolved relative to the "
            "word-source.yaml directory, not CWD)"
        )

    pdftotext = _require_pdftotext()
    text_pages = _run_pdftotext(pdftotext, pdf_path)
    rendered_pdf_sha = rendered_pdf_field.get("sha256") or _sha256(pdf_path)

    # Page PNGs: re-hash the on-disk files (same files discover_pages() hashes),
    # in page-number order.
    pages_dir = manifest_dir / "pages"
    png_paths = sorted(pages_dir.glob("*.png"), key=lambda p: int(p.stem))
    if not png_paths:
        raise RuntimeError(f"no page PNGs found in {pages_dir}")
    if len(text_pages) != len(rendered_pages_field):
        raise RuntimeError(
            f"page count mismatch: pdftotext produced {len(text_pages)} text "
            f"pages but word-source.yaml rendered_pages has "
            f"{len(rendered_pages_field)}"
        )
    if len(text_pages) != len(png_paths):
        raise RuntimeError(
            f"page count mismatch: pdftotext produced {len(text_pages)} text "
            f"pages but {pages_dir} has {len(png_paths)} PNGs"
        )

    page_sha: list[str] = []
    for index, png_path in enumerate(png_paths):
        on_disk_sha = _sha256(png_path)
        recorded_sha = rendered_pages_field[index].get("sha256")
        if recorded_sha and recorded_sha != on_disk_sha:
            raise RuntimeError(
                f"page PNG sha mismatch for {png_path.name}: word-source.yaml "
                f"records {recorded_sha} but the file hashes to {on_disk_sha}"
            )
        page_sha.append(on_disk_sha)

    pages = [
        PageText(page_number=index + 1 + page_number_offset, text=text)
        for index, text in enumerate(text_pages)
    ]

    fingerprint = SourceFingerprint(
        source_sha256=rendered_pdf_sha,
        page_sha256=page_sha,
        page_number_offset=page_number_offset,
    )
    index = build_index_from_pages(
        pages, source_kind="docx", fingerprint=fingerprint
    )
    dump_index(index, output)
    return index


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--word-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page-number-offset", type=int, default=0)
    args = parser.parse_args()

    try:
        index = build_docx_span_index(
            args.word_source,
            output=args.output,
            page_number_offset=args.page_number_offset,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"DOCX SPAN INDEX: {args.output} | status={index.status} "
        f"questions={len(index.questions)} issues={len(index.issues)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
