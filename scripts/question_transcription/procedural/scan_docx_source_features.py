#!/usr/bin/env python3
"""Scan real DOCX files for SourceQuestion-v2 canary features.

This is a read-only selector, not an ingestion provider. It reuses the
production extractor's OOXML/OLE parsing so a canary set can be chosen from
evidence rather than filenames.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[3]
EXTRACTOR = (
    ROOT
    / ".codex/skills/math-docx-question-bank-ingestion/scripts"
    / "extract_docx_source.py"
)


def _load_extractor():
    spec = importlib.util.spec_from_file_location("extract_docx_source", EXTRACTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load extractor: {EXTRACTOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_docx(path: Path) -> dict[str, Any]:
    extractor = _load_extractor()
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
        rels_xml = archive.read("word/_rels/document.xml.rels")
        media = sorted(
            name.removeprefix("word/")
            for name in archive.namelist()
            if name.startswith("word/media/")
        )

    relationships = extractor.relationship_map(rels_xml)
    paragraphs = extractor.paragraph_records(document_xml, relationships)
    bindings = extractor.ole_formula_bindings(document_xml, relationships)
    vectors = [
        target for target in media if Path(target).suffix.lower() in {".emf", ".wmf"}
    ]
    unbound_vectors = [target for target in vectors if target not in bindings]

    attribution_error = None
    try:
        attributions = extractor.attribute_images(paragraphs, bindings)
    except ValueError as exc:
        attributions = []
        attribution_error = str(exc)

    choice_hits: list[dict[str, Any]] = []
    part_hits: list[dict[str, Any]] = []
    solution_hits: list[dict[str, Any]] = []
    mixed_suspects: list[dict[str, Any]] = []
    for record in paragraphs:
        content_media = [
            target
            for target in record["images"]
            if not bindings.get(target, {}).get("embedded")
        ]
        if not content_media:
            continue
        context = " ".join(
            [
                record.get("previous_text", ""),
                record.get("text", ""),
                record.get("next_text", ""),
            ]
        )
        hit = {
            "paragraph_index": record["index"],
            "media": content_media,
            "context": context[:240],
        }
        if re.search(r"(?:^|\s)[A-D][.．、]|A.*B.*C.*D", context):
            choice_hits.append(hit)
        if re.search(r"[（(][1-4][）)]|第[一二三四1234]问", context):
            part_hits.append(hit)
        if extractor.SOLUTION_MARKERS.search(context):
            solution_hits.append(hit)
        if any(target in unbound_vectors for target in content_media) and len(
            record.get("text", "")
        ) >= 12:
            mixed_suspects.append(hit)

    return {
        "path": str(path),
        "media_count": len(media),
        "ole_formula_preview_count": len(bindings),
        "vector_count": len(vectors),
        "unbound_vector_count": len(unbound_vectors),
        "unbound_vectors": unbound_vectors,
        "attribution_count": len(attributions),
        "attribution_error": attribution_error,
        "choice_image_hits": choice_hits,
        "part_image_hits": part_hits,
        "solution_image_hits": solution_hits,
        "mixed_content_suspects": mixed_suspects,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path, nargs="+")
    args = parser.parse_args()
    reports = [scan_docx(path) for path in args.docx]
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
