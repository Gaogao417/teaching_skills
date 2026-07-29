#!/usr/bin/env python3
"""Build a ``math_question_span_index/v1`` from a PDF prescan (§5.3).

Reads the ``prescan-manifest.yaml`` produced by :mod:`prescan_pdf_pages` and
feeds the per-page text files into the anchoring algorithm in
:mod:`question_span_index`. Page numbers are read explicitly from the prescan
manifest's ``pages[].page_number`` (never inferred from file-name string sort),
and non-contiguous or misaligned page numbers are rejected.

The fingerprint carries the per-page SHAs (from the prescan) and the offset, so
the observer can refuse a stale index.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
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

PRESCAN_SCHEMA = "math_pdf_prescan/v1"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _load_prescan(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a mapping")
    if data.get("schema") != PRESCAN_SCHEMA:
        raise ValueError(
            f"{path} schema must be {PRESCAN_SCHEMA!r}, got {data.get('schema')!r}"
        )
    return data


def _validate_page_numbers(entries: list[dict[str, Any]]) -> list[int]:
    """Return the explicit page numbers, rejecting gaps / non-ascending / dupes."""
    page_numbers = [int(entry["page_number"]) for entry in entries]
    if page_numbers != sorted(set(page_numbers)):
        raise ValueError(
            f"prescan page numbers must be strictly ascending and unique, "
            f"got {page_numbers}"
        )
    if len(page_numbers) >= 2:
        for prev, curr in zip(page_numbers, page_numbers[1:]):
            if curr != prev + 1:
                raise ValueError(
                    f"prescan page numbers must be contiguous: gap between "
                    f"{prev} and {curr}"
                )
    return page_numbers


# --------------------------------------------------------------------------- #
# Build entry point
# --------------------------------------------------------------------------- #


def build_pdf_span_index(
    prescan_path: Path,
    *,
    output: Path,
) -> QuestionSpanIndex:
    """Build and persist the PDF span index from a prescan manifest."""
    prescan = _load_prescan(prescan_path)
    entries = prescan.get("pages") or []
    if not entries:
        raise ValueError(f"{prescan_path} contains no prescan page entries")

    page_numbers = _validate_page_numbers(entries)
    prescan_dir = prescan_path.parent

    pages: list[PageText] = []
    page_sha: list[str] = []
    for entry in entries:
        text_path = prescan_dir / entry["text_file"]
        if not text_path.exists():
            raise RuntimeError(
                f"prescan page text not found: {text_path} (referenced by "
                f"{prescan_path})"
            )
        pages.append(
            PageText(
                page_number=int(entry["page_number"]),
                text=text_path.read_text(encoding="utf-8"),
                sha256=entry.get("page_sha256"),
            )
        )
        page_sha.append(entry["page_sha256"])

    fingerprint = SourceFingerprint(
        source_sha256=None,
        page_sha256=page_sha,
        page_number_offset=int(prescan.get("page_number_offset") or 0),
    )
    index = build_index_from_pages(
        pages, source_kind="pdf", fingerprint=fingerprint
    )
    dump_index(index, output)
    return index


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prescan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        index = build_pdf_span_index(args.prescan, output=args.output)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"PDF SPAN INDEX: {args.output} | status={index.status} "
        f"questions={len(index.questions)} issues={len(index.issues)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
