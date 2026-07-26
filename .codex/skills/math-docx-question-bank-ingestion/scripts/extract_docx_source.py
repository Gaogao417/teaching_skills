#!/usr/bin/env python3
"""Normalize a DOC/DOCX source, extract Word media, and render PDF pages.

Text and formulas are transcribed from the PDF rendered pages; Word media
images are extracted only for diagram prompts (几何图/统计图/照片等) that would
lose resolution or transparency if re-rasterized from the PDF.

Paragraph stream (段落流) is the authoritative source for image attribution:
each embedded media is bound to its containing paragraph by OOXML structure,
then classified into prompt/solution buckets per question via a paragraph
state machine. Confidence flags mark cases needing human review.

Output directory layout:
  <output_dir>/
    source.docx|source.doc       # original file copy
    normalized.docx               # OOXML version (DOC→DOCX conversion if needed)
    word-source.yaml              # paragraph stream + image attribution + media + PDF pages
    media/                        # original embedded images and formula objects (WMF/EMF/PNG)
    ooxml/
      document.xml
      document.xml.rels
    rendered.pdf                  # PDF rendered by soffice (formula images baked in)
    pages/
      001.png, 002.png, ...       # rendered PDF pages as PNG (text/formula transcription)

The PDF pages are the authoritative source for all text and formula transcription.
Word media images are the authoritative source for diagram prompts.
Paragraph stream is the authoritative source for image attribution.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image
import yaml


NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
RELATIONSHIP_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"

# Paragraph markers that separate stem from solution in teacher-edition DOCX.
SOLUTION_MARKERS = re.compile(r"【分析】|【详解】|【小问\d*详解】|【解答】|【解析】")
# Question number at paragraph start, e.g. "1．" / "12." (full/half-width period).
QUESTION_NUMBER = re.compile(r"^(\d+)[．.]")
# Stem wording that declares a figure, e.g. 如图 / 图1 / 下图.
FIGURE_DECLARATION = re.compile(r"如图|下图|上图|图中|图\d{1,2}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def relationship_map(xml_bytes: bytes) -> dict[str, str]:
    """Parse word/_rels/document.xml.rels into {rId: media target}."""
    root = ET.fromstring(xml_bytes)
    return {
        node.attrib["Id"]: node.attrib["Target"]
        for node in root.findall(f"{{{RELATIONSHIP_NAMESPACE}}}Relationship")
        if "Id" in node.attrib and "Target" in node.attrib
    }


def paragraph_records(document_xml: bytes, relationships: dict[str, str]) -> list[dict]:
    """Extract the paragraph stream from OOXML.

    Each paragraph records its index, text, and the media files embedded in it.
    Empty paragraphs are dropped; the rest keep previous/next non-empty text for
    context (used to locate question numbers when image paragraphs are empty).
    """
    root = ET.fromstring(document_xml)
    records: list[dict] = []
    rel_key = f"{{{NAMESPACES['r']}}}embed"
    vml_rel_key = f"{{{NAMESPACES['r']}}}id"
    for index, paragraph in enumerate(root.findall(".//w:p", NAMESPACES)):
        text = "".join(
            node.text or "" for node in paragraph.findall(".//w:t", NAMESPACES)
        ).strip()
        relation_ids = [
            node.attrib.get(rel_key)
            for node in paragraph.findall(".//a:blip", NAMESPACES)
        ]
        relation_ids.extend(
            node.attrib.get(vml_rel_key)
            for node in paragraph.findall(".//v:imagedata", NAMESPACES)
        )
        images: list[str] = []
        for relation_id in relation_ids:
            target = relationships.get(str(relation_id), "")
            if target.startswith("media/") and target not in images:
                images.append(target)
        records.append({"index": index, "text": text, "images": images})

    previous_text = ""
    for record in records:
        record["previous_text"] = previous_text
        if record["text"]:
            previous_text = record["text"]
    next_text = ""
    for record in reversed(records):
        record["next_text"] = next_text
        if record["text"]:
            next_text = record["text"]
    return [record for record in records if record["text"] or record["images"]]


def _is_prompt_media(target: str) -> bool:
    """A media target is a candidate prompt/solution image if not a formula object."""
    lower = target.lower()
    return not (lower.endswith(".wmf") or lower.endswith(".emf"))


def attribute_images(paragraphs: list[dict]) -> list[dict]:
    """Classify each non-formula image into a question bucket with confidence.

    Walks the paragraph stream with a state machine:
      - QUESTION_NUMBER at paragraph start opens a new question (strictly
        increasing numbering filters out 考生须知 preamble and step lists).
      - SOLUTION_MARKERS switch the bucket from prompt to solution.

    Confidence:
      high   - image sits inside one question's stem region and the stem wording
               declares a figure whose count matches the image count.
      medium - image sits inside a question region but the stem figure-declaration
               count disagrees with the image count (e.g. a composite figure, or a
               multi-subquestion figure that the state machine cannot split).
      low    - the image appears in multiple paragraphs, the question numbering is
               not strictly increasing at its location, or it falls outside any
               question region (orphan).
    """
    # First pass: locate strictly-increasing question starts.
    # Word restarts numbering in two legitimate places: the 考生须知 preamble
    # (1-4 before any real question) and chapter headings. Once we are inside the
    # real question sequence, a bare "1．" is an enumeration step inside a
    # solution (e.g. Q12's "1．抽取... 2．抽取..."), NOT a restart — ignore it.
    question_starts: list[tuple[int, int]] = []  # (paragraph_index, question_no)
    prev_q = 0
    in_questions = False  # becomes True once real questions start
    for record in paragraphs:
        text = record["text"]
        m = QUESTION_NUMBER.match(text)
        if not m:
            continue
        n = int(m.group(1))
        if not in_questions:
            # Preamble (考生须知) or pre-question content: accept 1,2,3... but
            # do not start the question sequence until we (re)see 1.
            if n == 1:
                question_starts = []  # discard preamble starts
                question_starts.append((record["index"], n))
                prev_q = 1
                in_questions = True
            elif prev_q and n == prev_q + 1:
                # continuation of preamble (2,3,4) — tracked but overwritten
                question_starts.append((record["index"], n))
                prev_q = n
        else:
            # Inside real questions: only accept strictly increasing.
            if n == prev_q + 1:
                question_starts.append((record["index"], n))
                prev_q = n
            # else: enumeration step (1． 2．) or stray number — ignored.
    # Append sentinel.
    question_starts.append((paragraphs[-1]["index"] + 1 if paragraphs else 0, None))

    # Build per-question stem/solution paragraph ranges keyed by question_no.
    # paragraphs may have gaps in index (empties dropped); map index->position.
    index_to_pos = {rec["index"]: pos for pos, rec in enumerate(paragraphs)}

    attributions: list[dict] = []
    for qi in range(len(question_starts) - 1):
        start_idx, qno = question_starts[qi]
        end_idx, _ = question_starts[qi + 1]
        if qno is None:
            continue
        # Slice paragraph positions belonging to this question.
        positions = [
            pos for rec in paragraphs
            if start_idx <= rec["index"] < end_idx
            for pos in [index_to_pos[rec["index"]]]
        ]
        if not positions:
            continue
        # Find solution boundary inside this question.
        sol_pos = None
        for pos in positions:
            if SOLUTION_MARKERS.search(paragraphs[pos]["text"]):
                sol_pos = pos
                break
        stem_positions = positions if sol_pos is None else [p for p in positions if p < sol_pos]
        sol_positions = [] if sol_pos is None else [p for p in positions if p >= sol_pos]

        stem_text = "".join(paragraphs[p]["text"] for p in stem_positions)
        declared_fig_nums = {int(x) for x in re.findall(r"图(\d{1,2})", stem_text)}
        has_figure_word = bool(FIGURE_DECLARATION.search(stem_text))
        declared_count = max(len(declared_fig_nums), 1 if has_figure_word and not declared_fig_nums else 0)

        def _emit(positions_list: list[int], bucket: str) -> None:
            seen_media: dict[str, int] = {}
            for pos in positions_list:
                for target in paragraphs[pos]["images"]:
                    if not _is_prompt_media(target):
                        continue
                    seen_media[target] = seen_media.get(target, 0) + 1
                    # Confidence.
                    if bucket == "prompt":
                        if declared_count and seen_media[target] == 1:
                            # Compare total prompt image count to declaration below.
                            conf = "medium"
                        else:
                            conf = "medium"
                    else:
                        conf = "high"
                    attributions.append({
                        "media": target,
                        "question_number": qno,
                        "bucket": bucket,
                        "paragraph_index": paragraphs[pos]["index"],
                        "confidence": conf,
                    })

        _emit(stem_positions, "prompt")
        _emit(sol_positions, "solution")

        # Refine prompt confidence now that the full prompt set is known.
        prompt_media = [a for a in attributions if a["question_number"] == qno and a["bucket"] == "prompt"]
        prompt_unique = {a["media"] for a in prompt_media}
        # Mark duplicates low.
        for a in prompt_media:
            occ = sum(1 for r in paragraphs if a["media"] in r["images"])
            if occ > 1:
                a["confidence"] = "low"
        if prompt_media:
            if not declared_count and not has_figure_word:
                # Stem does not declare any figure but images present: suspect.
                for a in prompt_media:
                    a["confidence"] = "medium"
            elif declared_count and len(prompt_unique) == declared_count:
                for a in prompt_media:
                    if a["confidence"] != "low":
                        a["confidence"] = "high"
            elif declared_count and len(prompt_unique) != declared_count:
                for a in prompt_media:
                    if a["confidence"] != "low":
                        a["confidence"] = "medium"

    # Orphan images: media that never appeared in any question region.
    attributed_media = {a["media"] for a in attributions}
    for record in paragraphs:
        for target in record["images"]:
            if _is_prompt_media(target) and target not in attributed_media:
                attributions.append({
                    "media": target,
                    "question_number": None,
                    "bucket": "orphan",
                    "paragraph_index": record["index"],
                    "confidence": "low",
                })
                attributed_media.add(target)

    # Sort by paragraph index for stable output.
    attributions.sort(key=lambda a: (a["paragraph_index"], a["media"]))
    return attributions


def find_soffice(soffice_arg: str | None) -> str:
    """Find soffice executable, raising clear error if missing."""
    executable = soffice_arg or shutil.which("soffice")
    if executable is None:
        raise ValueError(
            "soffice (LibreOffice) is required for DOC→DOCX normalization "
            "and DOCX→PDF rendering. Pass --soffice or add it to PATH."
        )
    return executable


def normalize_doc(source: Path, temporary: Path, soffice: str | None) -> Path:
    """Convert DOC to DOCX via soffice; for DOCX, just copy."""
    if source.suffix.lower() == ".docx":
        target = temporary / "normalized.docx"
        shutil.copy2(source, target)
        return target

    if soffice is None:
        raise ValueError("DOC input requires soffice for normalization")
    profile = temporary / "soffice-profile"
    profile.mkdir()
    conversion_dir = temporary / "converted"
    conversion_dir.mkdir()
    subprocess.run(
        [
            soffice,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(conversion_dir),
            str(source),
        ],
        check=True,
    )
    candidates = sorted(conversion_dir.glob("*.docx"))
    if len(candidates) != 1:
        raise ValueError(f"soffice produced {len(candidates)} DOCX files; expected one")
    target = temporary / "normalized.docx"
    candidates[0].replace(target)
    return target


def render_pdf(docx_path: Path, output_dir: Path, soffice: str, dpi: int) -> tuple[Path, list[dict]]:
    """Convert DOCX to PDF via soffice, then render PDF pages as PNG.

    Returns (pdf_path, page_records).
    """
    # Step 1: DOCX → PDF
    profile_dir = output_dir.parent / ".soffice-pdf-profile"
    profile_dir.mkdir(exist_ok=True)
    pdf_dir = output_dir.parent / ".pdf-temp"
    pdf_dir.mkdir(exist_ok=True)

    subprocess.run(
        [
            soffice,
            f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_dir),
            str(docx_path),
        ],
        check=True,
    )
    pdf_candidates = sorted(pdf_dir.glob("*.pdf"))
    if len(pdf_candidates) != 1:
        raise ValueError(f"soffice produced {len(pdf_candidates)} PDF files; expected one")
    pdf_path = output_dir / "rendered.pdf"
    pdf_candidates[0].replace(pdf_path)
    shutil.rmtree(pdf_dir, ignore_errors=True)

    # Step 2: PDF → PNG pages via pdftoppm
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is None:
        raise ValueError("pdftoppm is required for PDF page rendering but was not found")

    pages_dir = output_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".pdf-pages-", dir=output_dir.parent) as tmp:
        subprocess.run(
            [
                pdftoppm,
                "-png",
                "-r",
                str(dpi),
                str(pdf_path),
                str(Path(tmp) / "page"),
            ],
            check=True,
        )

        def page_number(p: Path) -> int:
            m = re.search(r"-(\d+)\.png$", p.name)
            return int(m.group(1)) if m else 0

        rendered = sorted(Path(tmp).glob("page-*.png"), key=page_number)
        if not rendered:
            raise ValueError("pdftoppm produced no pages from PDF")

        page_records = []
        for index, source_page in enumerate(rendered, start=1):
            target = pages_dir / f"{index:03d}.png"
            source_page.replace(target)
            with Image.open(target) as img:
                w, h = img.size
            page_records.append({
                "path": f"pages/{target.name}",
                "sha256": sha256(target),
                "width_px": w,
                "height_px": h,
            })

    return pdf_path, page_records


def read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise ValueError(f"normalized DOCX is missing {name}") from exc


def extract(source: Path, output_dir: Path, soffice_arg: str | None, dpi: int, no_pdf: bool) -> dict:
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_file():
        raise ValueError(f"Word source not found: {source}")
    if source.suffix.lower() not in {".doc", ".docx"}:
        raise ValueError(f"input must be DOC or DOCX: {source}")
    if output_dir.exists():
        raise ValueError(f"output directory already exists; refusing overwrite: {output_dir}")

    needs_soffice = source.suffix.lower() == ".doc" or not no_pdf
    soffice = find_soffice(soffice_arg) if needs_soffice else None

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}-", dir=output_dir.parent) as name:
        temporary = Path(name)
        normalized = normalize_doc(source, temporary, soffice)
        with zipfile.ZipFile(normalized) as archive:
            document_xml = read_zip_member(archive, "word/document.xml")
            rels_xml = read_zip_member(archive, "word/_rels/document.xml.rels")
            media_names = sorted(
                name for name in archive.namelist() if name.startswith("word/media/")
            )

            output_dir.mkdir()
            try:
                source_copy = output_dir / f"source{source.suffix.lower()}"
                shutil.copy2(source, source_copy)
                normalized_copy = output_dir / "normalized.docx"
                shutil.copy2(normalized, normalized_copy)
                ooxml_dir = output_dir / "ooxml"
                ooxml_dir.mkdir()
                (ooxml_dir / "document.xml").write_bytes(document_xml)
                (ooxml_dir / "document.xml.rels").write_bytes(rels_xml)
                media_dir = output_dir / "media"
                media_dir.mkdir()
                media_records = []
                for archive_name in media_names:
                    target = media_dir / Path(archive_name).name
                    target.write_bytes(archive.read(archive_name))
                    width = height = None
                    try:
                        with Image.open(target) as image:
                            image.verify()
                        with Image.open(target) as image:
                            width, height = image.size
                    except OSError:
                        pass
                    media_records.append(
                        {
                            "path": f"media/{target.name}",
                            "sha256": sha256(target),
                            "width_px": width,
                            "height_px": height,
                        }
                    )

                # Paragraph stream + image attribution (from OOXML structure).
                relationships = relationship_map(rels_xml)
                paragraphs = paragraph_records(document_xml, relationships)
                image_attributions = attribute_images(paragraphs)

                # Render PDF for formula transcription (unless --no-pdf)
                page_records: list[dict] = []
                pdf_info = None
                if not no_pdf:
                    pdf_path, page_records = render_pdf(normalized_copy, output_dir, soffice, dpi)
                    pdf_info = {
                        "path": "rendered.pdf",
                        "sha256": sha256(pdf_path),
                        "dpi": dpi,
                    }

                manifest = {
                    "schema": "math_word_source_extract/v1",
                    "source": {
                        "path": source_copy.name,
                        "format": source.suffix.lower().lstrip("."),
                        "sha256": sha256(source_copy),
                    },
                    "normalized_docx": {
                        "path": normalized_copy.name,
                        "sha256": sha256(normalized_copy),
                    },
                    "media": media_records,
                    "paragraphs": paragraphs,
                    "image_attribution": image_attributions,
                }
                if pdf_info:
                    manifest["rendered_pdf"] = pdf_info
                    manifest["rendered_pages"] = page_records
                (output_dir / "word-source.yaml").write_text(
                    yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=1000),
                    encoding="utf-8",
                )
            except BaseException:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--soffice", help="path to soffice (LibreOffice) executable")
    parser.add_argument("--dpi", type=int, default=180, help="PDF rendering DPI (default: 180)")
    parser.add_argument("--no-pdf", action="store_true",
                        help="skip PDF rendering (formulas will need manual transcription)")
    args = parser.parse_args()
    try:
        manifest = extract(args.source, args.output_dir, args.soffice, args.dpi, args.no_pdf)
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    pages = len(manifest.get("rendered_pages", []))
    pdf_note = f" pdf_pages={pages}" if pages else " (no PDF)"
    paragraphs_n = len(manifest.get("paragraphs", []))
    attributions = manifest.get("image_attribution", [])
    high = sum(1 for a in attributions if a.get("confidence") == "high")
    med = sum(1 for a in attributions if a.get("confidence") == "medium")
    low = sum(1 for a in attributions if a.get("confidence") == "low")
    print(
        f"WORD SOURCE EXTRACTED: media={len(manifest['media'])}"
        f" paragraphs={paragraphs_n}"
        f" attributions={len(attributions)} (high={high} medium={med} low={low})"
        f"{pdf_note} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
