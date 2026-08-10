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
import re
import shutil
import subprocess
from pathlib import Path
import sys
from typing import Any, Literal, Mapping, Sequence

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.procedural.question_span_index import (
    PageText,
    QuestionSpanIndex,
    RoleMode,
    SourceFingerprint,
    SpanIndexIssue,
    build_index_from_pages,
    dump_index,
)

WORD_SOURCE_SCHEMA = "math_word_source_extract/v1"
Layout = Literal["separated", "interleaved", "unknown"]
_OOXML_QUESTION_NUMBER_RE = re.compile(
    r"^\s*(\d{1,3})(?:[．.]|\s+(?=\S))"
)


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


def _paragraph_text(paragraph: Mapping[str, Any]) -> str:
    text = paragraph.get("text", "")
    return text if isinstance(text, str) else ""


def _detect_layout(paragraphs: Sequence[Mapping[str, Any]]) -> Layout:
    """Classify the two supported DOCX layouts from clean OOXML paragraphs."""
    texts = [_paragraph_text(paragraph) for paragraph in paragraphs]
    n_answer_tag = sum(
        1 for text in texts if text.strip().startswith("【答案】")
    )
    n_ref_heading = sum(
        1 for text in texts if "参考答案" in text or "试题解析" in text
    )
    if n_answer_tag >= 5:
        return "interleaved"
    if n_ref_heading > 0:
        return "separated"
    return "unknown"


def _normalise_probe_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _normalise_semantic_text(text: str) -> str:
    """Drop whitespace/punctuation for a conservative probe fallback."""
    return re.sub(r"[\W_]+", "", text)


def _ooxml_question_paragraphs(
    paragraphs: Sequence[Mapping[str, Any]],
) -> dict[int, str]:
    """Return the first clean OOXML question paragraph for each number."""
    result: dict[int, str] = {}
    for paragraph in paragraphs:
        text = _paragraph_text(paragraph).strip()
        match = _OOXML_QUESTION_NUMBER_RE.match(text)
        if match:
            number = int(match.group(1))
            body = text[match.end() :].lstrip()
            result.setdefault(number, f"{number}．{body}")
    return result


def _question_probe(question_line: str) -> str:
    """Build the whitespace-free 12-character body probe used for page lookup."""
    body = _OOXML_QUESTION_NUMBER_RE.sub("", question_line, count=1)
    return _normalise_probe_text(body)[:12]


def _repair_missing_ooxml_numbers(
    text_pages: Sequence[str],
    paragraphs: Sequence[Mapping[str, Any]],
    index: QuestionSpanIndex,
) -> tuple[list[str], list[SpanIndexIssue], bool]:
    """Inject clean OOXML question lines for refs missed by ``pdftotext``.

    Page identity still comes exclusively from ``pdftotext``. OOXML contributes
    only a clean number line after a 12-character body probe uniquely locates
    the corresponding page.
    """
    ooxml_questions = _ooxml_question_paragraphs(paragraphs)
    indexed_by_number = {
        question.question_number: question for question in index.questions
    }
    # Supported DOCX papers contain both roles. Repair a ref when either side is
    # absent, not only when the merged ref is absent altogether. A genuinely
    # question-only source has no solution role at all and remains legitimate.
    has_solution_role = any(
        question.solution_pages for question in index.questions
    )
    missing = sorted(
        number
        for number in ooxml_questions
        if number not in indexed_by_number
        or (
            has_solution_role
            and (
                not indexed_by_number[number].question_pages
                or not indexed_by_number[number].solution_pages
            )
        )
    )
    if not missing:
        return list(text_pages), [], False

    normalised_pages = [_normalise_probe_text(text) for text in text_pages]
    injections: dict[int, list[tuple[int, str, str]]] = {}
    issues: list[SpanIndexIssue] = []
    for number in missing:
        line = ooxml_questions[number]
        probe = _question_probe(line)
        matches = [
            page_index
            for page_index, page_text in enumerate(normalised_pages)
            if probe and probe in page_text
        ]
        if not matches:
            # Equation placeholders and punctuation can differ between OOXML
            # and pdftotext (for example ``7 计算： . _____``). Fall back to a
            # number-prefixed semantic probe; including the number keeps short
            # stems such as “计算” specific enough to avoid ordinary prose.
            semantic_probe = _normalise_semantic_text(line)[:13]
            matches = [
                page_index
                for page_index, page_text in enumerate(text_pages)
                if len(semantic_probe) >= 3
                and semantic_probe in _normalise_semantic_text(page_text)
            ]
        if not matches:
            reason = "empty probe" if not probe else "matched no pages"
            issues.append(
                SpanIndexIssue(
                    code="question_ooxml_repair_failed",
                    severity="blocking",
                    detail=(
                        f"OOXML repair for question {number} {reason}; "
                        "could not determine a pdftotext page"
                    ),
                    question_ref=str(number),
                )
            )
            continue
        # The stem is commonly repeated verbatim in the official solution.
        # Inject every matching page; the main role state machine then assigns
        # the clean anchor to question vs solution without OOXML guessing roles.
        for page_index in matches:
            injections.setdefault(page_index, []).append((number, line, probe))

    repaired_pages = list(text_pages)
    for page_index, page_injections in injections.items():
        lines = repaired_pages[page_index].splitlines()
        pending_by_position: dict[int, list[tuple[int, str]]] = {}
        for number, line, probe in page_injections:
            semantic_line_probe = _normalise_semantic_text(line)[:13]
            position = next(
                (
                    line_index
                    for line_index, page_line in enumerate(lines)
                    if probe in _normalise_probe_text(page_line)
                ),
                -1,
            )
            if position < 0 and len(semantic_line_probe) >= 3:
                position = next(
                    (
                        line_index
                        for line_index, page_line in enumerate(lines)
                        if semantic_line_probe
                        in _normalise_semantic_text(page_line)
                    ),
                    -1,
                )
            if position < 0:
                # The probe may cross pdftotext line breaks. Preserve numeric
                # order relative to anchors already recognised on the page.
                position = len(lines)
                for line_index, page_line in enumerate(lines):
                    match = _OOXML_QUESTION_NUMBER_RE.match(page_line)
                    if match and int(match.group(1)) > number:
                        position = line_index
                        break
            pending_by_position.setdefault(position, []).append((number, line))

        for position in sorted(pending_by_position, reverse=True):
            ordered_lines = [
                line
                for _, line in sorted(
                    pending_by_position[position], key=lambda item: item[0]
                )
            ]
            lines[position:position] = ordered_lines
        repaired_pages[page_index] = "\n".join(lines)

    return repaired_pages, issues, bool(injections)


def _with_builder_issues(
    index: QuestionSpanIndex, issues: Sequence[SpanIndexIssue]
) -> QuestionSpanIndex:
    if not issues:
        return index
    status = "needs_review" if index.questions else "failed"
    return index.model_copy(
        update={"issues": [*index.issues, *issues], "status": status}
    )


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
    paragraphs_raw = word_source.get("paragraphs")
    paragraphs: list[Mapping[str, Any]] = (
        [paragraph for paragraph in paragraphs_raw if isinstance(paragraph, Mapping)]
        if isinstance(paragraphs_raw, list)
        else []
    )
    layout = _detect_layout(paragraphs)
    role_mode: RoleMode = layout if layout != "unknown" else "separated"
    index = build_index_from_pages(
        pages,
        source_kind="docx",
        fingerprint=fingerprint,
        role_mode=role_mode,
    )

    repaired_text_pages, repair_issues, repaired = _repair_missing_ooxml_numbers(
        text_pages, paragraphs, index
    )
    if repaired:
        repaired_pages = [
            PageText(
                page_number=page_index + 1 + page_number_offset,
                text=text,
            )
            for page_index, text in enumerate(repaired_text_pages)
        ]
        index = build_index_from_pages(
            repaired_pages,
            source_kind="docx",
            fingerprint=fingerprint,
            role_mode=role_mode,
        )

    builder_issues = list(repair_issues)
    if layout == "unknown":
        builder_issues.append(
            SpanIndexIssue(
                code="layout_unknown",
                severity="blocking",
                detail=(
                    "OOXML paragraphs contain neither at least five 【答案】 "
                    "tags nor a 参考答案/试题解析 heading"
                ),
            )
        )
    index = _with_builder_issues(index, builder_issues)
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
