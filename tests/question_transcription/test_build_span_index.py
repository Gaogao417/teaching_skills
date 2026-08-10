#!/usr/bin/env python3
"""Tests for the DOCX and PDF span-index builders (§5.2 / §5.3).

The DOCX builder is exercised against a real (tiny) rendered PDF + pdftotext so
its subprocess and page-count checks are covered. The PDF builder runs against a
synthetic prescan manifest. No network.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.procedural.build_docx_span_index import (  # noqa: E402
    _detect_layout,
    _repair_missing_ooxml_numbers,
    _with_builder_issues,
    build_docx_span_index,
)
from scripts.question_transcription.procedural.build_pdf_span_index import (  # noqa: E402
    build_pdf_span_index,
)
from scripts.question_transcription.procedural.question_span_index import (  # noqa: E402
    PageText,
    SourceFingerprint,
    build_index_from_pages,
    load_index,
)


PDF_TEXT_PAGES = [
    "Section One Choice\n1. q1\n2. q2\n3. q3",
    "Section Two Fill\n4. q4\n5. q5",
]


# --------------------------------------------------------------------------- #
# DOCX builder: minimal real rendered.pdf + pdftotext
# --------------------------------------------------------------------------- #


def _make_rendered_pdf(pdf_path: Path, n_pages: int) -> None:
    """Render a minimal multi-page PDF with an extractable text layer.

    Hand-written PDF (no external dep) whose pages carry the text in
    ``PDF_TEXT_PAGES`` so ``pdftotext -layout`` recovers it. Each page uses a
    WinAnsiEncoding content stream with one BT/ET block per line.
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    def _esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    objects: list[str] = []
    # Object 1: Catalog; object 2: Pages (placeholder); fonts/streams follow.
    page_obj_indices: list[int] = []
    obj_index = 3  # pages tree children start at object 3

    # First, emit one page object + one content stream per page, recording refs.
    content_objs: list[int] = []
    for i in range(n_pages):
        text = PDF_TEXT_PAGES[i] if i < len(PDF_TEXT_PAGES) else f"page {i+1}"
        lines = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            lines.append(f"BT /F1 12 Tf 72 {780 - 20 * line_no} Td ({_esc(line)}) Tj ET")
        stream = "\n".join(lines)
        content_objs.append(obj_index)
        objects.append(f"{obj_index} 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj\n")
        obj_index += 1
        page_obj_indices.append(obj_index)
        objects.append(
            f"{obj_index} 0 obj\n<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] /Resources << /Font << /F1 1 0 R >> >> "
            f"/Contents {content_objs[-1]} 0 R >>\nendobj\n"
        )
        obj_index += 1

    kids = " ".join(f"{idx} 0 R" for idx in page_obj_indices)
    # Object 1: font; object 2: pages; object maxobj: catalog.
    font_obj = (
        "1 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>\nendobj\n"
    )
    pages_obj = (
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>\nendobj\n"
    )
    catalog_index = obj_index
    catalog_obj = (
        f"{catalog_index} 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    )

    body = font_obj + pages_obj + "".join(objects) + catalog_obj
    pdf = ["%PDF-1.4"]
    offsets = [len(pdf[0]) + 1]
    for obj in [font_obj, pages_obj, *objects, catalog_obj]:
        offsets.append(offsets[-1] + len(obj))
    xref_start = offsets[-2]
    xref = f"xref\n0 {catalog_index + 1}\n"
    xref += "0000000000 65535 f \n"
    for off in offsets[1:-1]:
        xref += f"{off:010d} 00000 n \n"
    xref += f"trailer\n<< /Size {catalog_index + 1} /Root {catalog_index} 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    pdf_path.write_text(pdf[0] + "\n" + body + xref, encoding="latin-1")


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_docx_builder_builds_ready_index(tmp_path: Path):
    n_pages = len(PDF_TEXT_PAGES)
    word_dir = tmp_path / "word"
    pdf_path = word_dir / "rendered.pdf"
    _make_rendered_pdf(pdf_path, n_pages)

    pages_dir = word_dir / "pages"
    pages_dir.mkdir()
    png_shas: list[str] = []
    for number in range(1, n_pages + 1):
        (pages_dir / f"{number:03d}.png").write_bytes(b"png-bytes-%d" % number)

    # Verify pdftotext round-trips our pages (sanity for the fixture).
    raw = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, text=True, check=True
    )
    assert "1. q1" in raw.stdout and "5. q5" in raw.stdout

    import hashlib

    page_records = [
        {
            "path": f"pages/{number:03d}.png",
            "sha256": f"sha256:{hashlib.sha256(b'png-bytes-%d' % number).hexdigest()}",
            "width_px": 100,
            "height_px": 100,
        }
        for number in range(1, n_pages + 1)
    ]
    word_source = {
        "schema": "math_word_source_extract/v1",
        "rendered_pdf": {"path": "rendered.pdf", "sha256": "sha256:abc", "dpi": 180},
        "rendered_pages": page_records,
        "paragraphs": [{"index": 0, "text": "参考答案", "images": []}],
    }
    (word_dir / "word-source.yaml").write_text(
        yaml.safe_dump(word_source, allow_unicode=True), encoding="utf-8"
    )

    out = tmp_path / "span-index.yaml"
    index = build_docx_span_index(word_dir / "word-source.yaml", output=out)
    assert index.source_kind == "docx"
    assert index.status == "ready"
    assert [q.question_ref for q in index.questions] == ["1", "2", "3", "4", "5"]
    # Output persisted and reloadable.
    reloaded = load_index(out)
    assert reloaded.status == "ready"
    # Fingerprint carries rendered-pdf SHA + per-page PNG SHAs + offset 0.
    assert index.fingerprint.source_sha256 == "sha256:abc"
    assert len(index.fingerprint.page_sha256) == n_pages
    assert index.fingerprint.page_number_offset == 0


def test_detect_layout_from_ooxml_paragraphs():
    interleaved = [{"text": f"【答案】第{number}题"} for number in range(1, 6)]
    separated = [{"text": "上海市试题解析"}]
    unknown = [{"text": "一、选择题"}, {"text": "1．题干"}]

    assert _detect_layout(interleaved) == "interleaved"
    assert _detect_layout(separated) == "separated"
    assert _detect_layout(unknown) == "unknown"


def test_ooxml_repair_restores_split_number_in_numeric_order():
    text_pages = [
        "12．第十二题正文\n1 3 ．第十三题正文ABCDEFGHI\n14．第十四题正文"
    ]
    paragraphs = [
        {"text": "12．第十二题正文"},
        {"text": "13．第十三题正文ABCDEFGHI"},
        {"text": "14．第十四题正文"},
        {"text": "参考答案"},
    ]
    fingerprint = SourceFingerprint()
    initial = build_index_from_pages(
        [PageText(page_number=1, text=text_pages[0])],
        source_kind="docx",
        fingerprint=fingerprint,
    )

    repaired_pages, issues, repaired = _repair_missing_ooxml_numbers(
        text_pages, paragraphs, initial
    )
    final = build_index_from_pages(
        [PageText(page_number=1, text=repaired_pages[0])],
        source_kind="docx",
        fingerprint=fingerprint,
    )

    assert repaired is True
    assert issues == []
    assert [question.question_ref for question in final.questions] == [
        "12",
        "13",
        "14",
    ]
    lines = repaired_pages[0].splitlines()
    assert lines.index("12．第十二题正文") < lines.index(
        "13．第十三题正文ABCDEFGHI"
    ) < lines.index("14．第十四题正文")
    assert final.questions[1].question_pages == [1]


def test_ooxml_repair_accepts_number_space_body_and_equation_noise():
    text_pages = ["7 计算：  . _____．\n【答案】结果"]
    paragraphs = [{"text": "7 计算：_____．"}]
    fingerprint = SourceFingerprint()
    initial = build_index_from_pages(
        [PageText(page_number=1, text=text_pages[0])],
        source_kind="docx",
        fingerprint=fingerprint,
        role_mode="interleaved",
    )

    repaired_pages, issues, repaired = _repair_missing_ooxml_numbers(
        text_pages, paragraphs, initial
    )
    final = build_index_from_pages(
        [PageText(page_number=1, text=repaired_pages[0])],
        source_kind="docx",
        fingerprint=fingerprint,
        role_mode="interleaved",
    )

    assert repaired is True
    assert issues == []
    assert repaired_pages[0].splitlines()[0] == "7．计算：_____．"
    assert final.questions[0].question_pages == [1]
    assert final.questions[0].solution_pages == [1]


def test_ooxml_repair_failure_is_blocking_and_needs_review():
    text_pages = ["1．第一题正文\n3．第三题正文"]
    paragraphs = [
        {"text": "1．第一题正文"},
        {"text": "2．此探针不存在于任何页面"},
        {"text": "3．第三题正文"},
    ]
    index = build_index_from_pages(
        [PageText(page_number=1, text=text_pages[0])],
        source_kind="docx",
        fingerprint=SourceFingerprint(),
    )

    _, issues, repaired = _repair_missing_ooxml_numbers(
        text_pages, paragraphs, index
    )
    downgraded = _with_builder_issues(index, issues)

    assert repaired is False
    assert downgraded.status == "needs_review"
    assert any(
        issue.code == "question_ooxml_repair_failed"
        and issue.severity == "blocking"
        for issue in downgraded.issues
    )


def test_docx_builder_unknown_layout_is_needs_review(tmp_path: Path, monkeypatch):
    word_dir = tmp_path / "word"
    word_dir.mkdir()
    (word_dir / "rendered.pdf").write_bytes(b"%PDF-1.4")
    pages_dir = word_dir / "pages"
    pages_dir.mkdir()
    (pages_dir / "001.png").write_bytes(b"one-page")
    (word_dir / "word-source.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_word_source_extract/v1",
                "rendered_pdf": {"path": "rendered.pdf", "sha256": "sha256:abc"},
                "rendered_pages": [{"path": "pages/001.png"}],
                "paragraphs": [{"index": 0, "text": "1．第一题", "images": []}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.question_transcription.procedural.build_docx_span_index._require_pdftotext",
        lambda: "pdftotext",
    )
    monkeypatch.setattr(
        "scripts.question_transcription.procedural.build_docx_span_index._run_pdftotext",
        lambda executable, pdf_path: ["1．第一题"],
    )

    index = build_docx_span_index(
        word_dir / "word-source.yaml", output=tmp_path / "span-index.yaml"
    )

    assert index.status == "needs_review"
    assert any(issue.code == "layout_unknown" for issue in index.issues)


def test_docx_builder_rejects_missing_pdftotext(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "scripts.question_transcription.procedural.build_docx_span_index.shutil.which",
        lambda name: None,
    )
    word_dir = tmp_path / "word"
    word_dir.mkdir()
    # Minimal manifest so we get past the rendered_pdf check to the pdftotext guard.
    (word_dir / "word-source.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_word_source_extract/v1",
                "rendered_pdf": {"path": "rendered.pdf"},
                "rendered_pages": [{"path": "pages/001.png"}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (word_dir / "rendered.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(RuntimeError, match="pdftotext"):
        build_docx_span_index(
            word_dir / "word-source.yaml", output=tmp_path / "out.yaml"
        )


def test_docx_builder_rejects_page_count_mismatch(tmp_path: Path):
    word_dir = tmp_path / "word"
    word_dir.mkdir()
    # rendered_pages says 3 but pages/ has 1 PNG.
    (pages_dir := word_dir / "pages").mkdir()
    (pages_dir / "001.png").write_bytes(b"x")
    (word_dir / "rendered.pdf").write_bytes(b"%PDF-1.4")  # not a real pdf
    (word_dir / "word-source.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_word_source_extract/v1",
                "rendered_pdf": {"path": "rendered.pdf"},
                "rendered_pages": [
                    {"path": f"pages/{n:03d}.png"} for n in (1, 2, 3)
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    # pdftotext will fail on the fake pdf -> RuntimeError (non-zero exit).
    with pytest.raises(RuntimeError):
        build_docx_span_index(
            word_dir / "word-source.yaml", output=tmp_path / "out.yaml"
        )


def test_docx_builder_rejects_no_pdf(tmp_path: Path):
    word_dir = tmp_path / "word"
    word_dir.mkdir()
    (word_dir / "word-source.yaml").write_text(
        yaml.safe_dump({"schema": "math_word_source_extract/v1"}, allow_unicode=True),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="rendered_pdf"):
        build_docx_span_index(
            word_dir / "word-source.yaml", output=tmp_path / "out.yaml"
        )


def test_docx_builder_rejects_bad_schema(tmp_path: Path):
    word_dir = tmp_path / "word"
    word_dir.mkdir()
    (word_dir / "word-source.yaml").write_text(
        yaml.safe_dump({"schema": "something_else"}, allow_unicode=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema"):
        build_docx_span_index(
            word_dir / "word-source.yaml", output=tmp_path / "out.yaml"
        )


# --------------------------------------------------------------------------- #
# PDF builder: synthetic prescan manifest
# --------------------------------------------------------------------------- #


def _write_prescan(tmp_path: Path, *, page_numbers: list[int]) -> Path:
    prescan_dir = tmp_path / "prescan"
    prescan_dir.mkdir()
    pages = []
    for number in page_numbers:
        text = f"选择题\n{number}. 题" if number <= 2 else f"{number}. 题"
        (prescan_dir / f"page-{number:03d}.txt").write_text(text, encoding="utf-8")
        pages.append(
            {
                "page_number": number,
                "physical_page_number": number,
                "page_sha256": f"sha256:{number:064x}",
                "text_file": f"page-{number:03d}.txt",
                "prompt_version": "pdf-prescan-v1",
                "model": "qwen3.5-ocr",
            }
        )
    manifest_path = prescan_dir / "prescan-manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "math_pdf_prescan/v1",
                "paper_id": "T",
                "source_archive": tmp_path.as_posix(),
                "prompt": "p",
                "prompt_version": "pdf-prescan-v1",
                "model": "qwen3.5-ocr",
                "page_number_offset": 0,
                "pages": pages,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_pdf_builder_builds_index_from_prescan(tmp_path: Path):
    prescan = _write_prescan(tmp_path, page_numbers=[1, 2, 3])
    out = tmp_path / "pdf.span-index.yaml"
    index = build_pdf_span_index(prescan, output=out)
    assert index.source_kind == "pdf"
    assert index.status == "ready"
    assert [q.question_ref for q in index.questions] == ["1", "2", "3"]
    reloaded = load_index(out)
    assert reloaded.source_kind == "pdf"


def test_pdf_builder_rejects_gaps_in_page_numbers(tmp_path: Path):
    prescan = _write_prescan(tmp_path, page_numbers=[1, 3])  # gap at 2
    with pytest.raises(ValueError, match="contiguous"):
        build_pdf_span_index(prescan, output=tmp_path / "out.yaml")


def test_pdf_builder_rejects_non_ascending_page_numbers(tmp_path: Path):
    prescan = _write_prescan(tmp_path, page_numbers=[2, 1])
    with pytest.raises(ValueError, match="ascending"):
        build_pdf_span_index(prescan, output=tmp_path / "out.yaml")


def test_pdf_builder_rejects_missing_text_file(tmp_path: Path):
    prescan = _write_prescan(tmp_path, page_numbers=[1])
    # Delete the referenced text file.
    (tmp_path / "prescan" / "page-001.txt").unlink()
    with pytest.raises(RuntimeError, match="page text not found"):
        build_pdf_span_index(prescan, output=tmp_path / "out.yaml")


def test_pdf_builder_rejects_empty_prescan(tmp_path: Path):
    prescan_dir = tmp_path / "prescan"
    prescan_dir.mkdir()
    manifest = prescan_dir / "prescan-manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {"schema": "math_pdf_prescan/v1", "pages": []}, allow_unicode=True
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no prescan page"):
        build_pdf_span_index(manifest, output=tmp_path / "out.yaml")
