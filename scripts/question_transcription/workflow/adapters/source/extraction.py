"""Source-extraction wrapper (architecture §3.6 and §5.2).

Wraps the existing deterministic functions (NOT the CLIs — we want exceptions, not
``SystemExit``):

- :func:`extract_docx_source.extract` for DOC/DOCX
- :func:`render_pdf_pages.render` for PDF
- pre-rendered page-image directories (``manifest.json`` archives) for PAGES

These are bound by the composition root; nodes never see the source kind discriminator
beyond ``state["source_kind"]`` (which routes the *business* branch, not an adapter
host choice).

Phase 2 additions:

- ``pages`` sources (scanned page-image packs such as 2025-HUANGPU-YIMO) are
  consumed directly from their original page files, with per-file sha256 verified
  against the pack's ``manifest.json`` (fail closed on drift).
- an optional supplementary ``answer_archive`` (DOCX) continues the paper's page
  numbering with the official answer document's rendered pages, for packs whose
  exam archive carries questions only (2020-MINHANG-YIMO).
- an explicit ``non-question-pages.yaml`` declaration next to the original source
  claims cover/QR/blank pages. Claimed pages are excluded from page-text jobs and
  flow into the staging ``paper.yaml`` as the only fail-closed exemption from the
  whole-paper coverage audit.
- a ``source/page-plan.yaml`` artifact records, for every run page, which original
  archive and original page number it came from (lineage for the canonical
  SourceEvidence export).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap)
from ...contracts import (
    ArtifactRef,
    ExtractedSource,
    NonQuestionPageDecl,
    SourceInput,
)
from ...ports.source import SourceExtractionError


__all__ = ["DocxOrPdfSourceExtractor"]


_NUMERIC_STEM = re.compile(r"^\d{1,4}$")
_PAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
# Below this width the qwen OCR quality collapses on text-dense scan pages.
_OCR_UPSCALE_MIN_WIDTH = 1400


class SourceIntegrityError(Exception):
    """A pre-rendered source failed its manifest integrity check (fail closed)."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_non_question_declaration(
    archive_dir: Path,
) -> list[NonQuestionPageDecl]:
    """Read ``non-question-pages.yaml`` next to the original source, if present.

    The declaration is the human-authored claim that specific pages (scan cover,
    QR tail, blank render page) contain no question content. Missing file means
    no claims (strict legacy behaviour); a malformed file is a hard failure so a
    typo can never silently widen the audit exemption.
    """
    declaration_path = archive_dir / "non-question-pages.yaml"
    if not declaration_path.is_file():
        return []
    payload = yaml.safe_load(declaration_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{declaration_path}: root must be a mapping")
    if payload.get("schema") != "math_non_question_pages/v1":
        raise ValueError(
            f"{declaration_path}: schema must be math_non_question_pages/v1"
        )
    pages_raw = payload.get("pages")
    if not isinstance(pages_raw, list) or not pages_raw:
        raise ValueError(f"{declaration_path}: pages must be a non-empty list")
    declared = [
        NonQuestionPageDecl.model_validate(entry) for entry in pages_raw
    ]
    numbers = [entry.page_number for entry in declared]
    if len(numbers) != len(set(numbers)):
        raise ValueError(f"{declaration_path}: duplicate page_number claims")
    return declared


class DocxOrPdfSourceExtractor:
    """:class:`SourceExtractor` dispatching on ``source_kind`` (Doc/Docx/Pdf/Pages)."""

    def __init__(self, store, *, dpi: int = 180, soffice: str | None = None) -> None:
        self.store = store
        self.dpi = dpi
        self.soffice = soffice

    def extract(self, source: SourceInput):
        kind = source.source_kind
        try:
            if kind in ("doc", "docx"):
                return self._extract_docx(source)
            if kind == "pdf":
                return self._extract_pdf(source)
            if kind == "pages":
                return self._extract_pages(source)
            return None, "unsupported_source_kind", f"source_kind={kind!r}"
        except FileNotFoundError as exc:
            return None, "source_not_found", str(exc)
        except ValueError as exc:
            return None, "normalization_failed", str(exc)
        except SourceIntegrityError as exc:
            return None, "source_integrity_failed", str(exc)
        except Exception as exc:  # pragma: no cover - subprocess failures
            return None, "page_rendering_failed", f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    # DOCX (optionally + supplementary answer document)
    # ------------------------------------------------------------------ #

    def _extract_docx(self, source: SourceInput):
        # The extractor writes into a fresh output dir under the run layout.
        output_dir = self.store.layout.source_dir / "docx"
        import sys

        skill_scripts = repo_root() / ".codex/skills/math-docx-question-bank-ingestion/scripts"
        if str(skill_scripts) not in sys.path:
            sys.path.insert(0, str(skill_scripts))
        from extract_docx_source import extract as docx_extract  # type: ignore

        manifest = docx_extract(
            Path(source.source_archive),
            output_dir,
            self.soffice,
            self.dpi,
            False,  # render PDF pages
        )
        answer_archive = source.answer_archive
        page_origins = self._exam_page_origins(manifest, source)
        answer_sha = None
        if answer_archive:
            answer_sha = self._merge_answer_docx_pages(
                manifest,
                Path(answer_archive),
                output_dir,
                page_origins,
                exam_dir=Path(source.source_archive).parent,
            )
        return self._materialize_extracted(
            source,
            manifest,
            output_dir,
            kind="docx",
            page_origins=page_origins,
            answer_archive=answer_archive,
            answer_sha256=answer_sha,
        )

    @staticmethod
    def _exam_page_origins(manifest: dict, source: SourceInput) -> dict[int, dict]:
        origins: dict[int, dict] = {}
        pages = manifest.get("rendered_pages") or []
        for index, page in enumerate(pages, start=1):
            origins[index] = {
                "origin_archive": str(source.source_archive),
                "origin_path": str(page.get("path")),
                "origin_page_number": index,
            }
        return origins

    def _merge_answer_docx_pages(
        self,
        manifest: dict,
        answer_path: Path,
        exam_output_dir: Path,
        page_origins: dict[int, dict],
        *,
        exam_dir: Path | None = None,
    ) -> str:
        """Render the supplementary answer DOCX and continue the page numbering.

        The answer document's rendered pages are copied byte-exact into the exam
        pages directory under continued 3-digit names, so the whole-paper
        transcriber sees one contiguous page set and the word-evidence resolver
        scans a single rendered-pages folder. The page plan records the original
        archive + page number for every merged page.
        """
        import sys

        # Prefer the durable pre-extracted copy inside the pack directory
        # (``<pack>/word-answer/word-source.yaml``): its page PNGs are the
        # artifact://page-image targets the canonical export references, and the
        # pack stays self-contained. Fall back to a run-local re-extraction.
        durable_dir = (exam_dir or answer_path.parent) / "word-answer"
        durable_manifest = durable_dir / "word-source.yaml"
        if durable_manifest.is_file():
            answer_dir = durable_dir
            answer_manifest = yaml.safe_load(
                durable_manifest.read_text(encoding="utf-8")
            )
        else:
            skill_scripts = (
                repo_root() / ".codex/skills/math-docx-question-bank-ingestion/scripts"
            )
            if str(skill_scripts) not in sys.path:
                sys.path.insert(0, str(skill_scripts))
            from extract_docx_source import extract as docx_extract  # type: ignore

            answer_dir = self.store.layout.source_dir / "docx-answer"
            answer_manifest = docx_extract(
                answer_path, answer_dir, self.soffice, self.dpi, False
            )
        answer_pages = answer_manifest.get("rendered_pages") or []
        if not answer_pages:
            raise ValueError(f"answer document produced no rendered pages: {answer_path}")

        exam_pages = manifest.setdefault("rendered_pages", [])
        if not exam_pages:
            raise ValueError("exam manifest has no rendered pages to continue")
        width = len(str(Path(str(exam_pages[0].get("path"))).stem))
        exam_pages_dir = exam_output_dir / "pages"
        next_number = len(exam_pages) + 1
        for offset, page in enumerate(answer_pages):
            page_number = next_number + offset
            source_file = answer_dir / str(page.get("path"))
            if not source_file.is_file():
                raise FileNotFoundError(f"answer rendered page missing: {source_file}")
            target = exam_pages_dir / f"{page_number:0{width}d}{source_file.suffix or '.png'}"
            shutil.copyfile(source_file, target)
            copied_sha = sha256_file(target)
            expected_sha = str(page.get("sha256") or "")
            if expected_sha and copied_sha != expected_sha:
                raise SourceIntegrityError(
                    f"answer page copy hash mismatch: {target} "
                    f"expected {expected_sha} got {copied_sha}"
                )
            exam_pages.append(
                {
                    "path": f"pages/{target.name}",
                    "sha256": copied_sha,
                    "width_px": page.get("width_px"),
                    "height_px": page.get("height_px"),
                }
            )
            page_origins[page_number] = {
                "origin_archive": str(answer_path),
                "origin_path": str(page.get("path")),
                "origin_page_number": offset + 1,
            }
        return sha256_file(answer_path)

    # ------------------------------------------------------------------ #
    # PDF
    # ------------------------------------------------------------------ #

    def _extract_pdf(self, source: SourceInput):
        import sys

        skill_scripts = repo_root() / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
        if str(skill_scripts) not in sys.path:
            sys.path.insert(0, str(skill_scripts))
        from render_pdf_pages import render as pdf_render  # type: ignore
        from .pdf_source_manifest import (
            build_manifest,
        )

        pages_dir = self.store.layout.source_dir / "pages"
        page_paths = pdf_render(Path(source.source_archive), pages_dir, self.dpi)
        manifest = build_manifest(
            paper_id=source.paper_id,
            source_archive=source.source_archive,
            page_paths=sorted(page_paths),
            pdf_path=Path(source.source_archive),
            dpi=self.dpi,
            engine="pdftoppm",
        ).model_dump(by_alias=True, exclude_none=True)
        page_origins = {
            index: {
                "origin_archive": str(source.source_archive),
                "origin_path": str(page.get("source")),
                "origin_page_number": index,
            }
            for index, page in enumerate(manifest.get("pages") or [], start=1)
        }
        return self._materialize_extracted(
            source,
            manifest,
            pages_dir,
            kind="pdf",
            page_origins=page_origins,
        )

    # ------------------------------------------------------------------ #
    # Pre-rendered page-image packs (scanned volumes)
    # ------------------------------------------------------------------ #

    def _extract_pages(self, source: SourceInput):
        """Consume a pre-rendered page-image pack directly from its original files.

        The pack directory must carry a ``manifest.json`` with per-image sha256
        (the WeChat-article extraction manifest); every page file is verified
        against it before anything is copied (fail closed — a tampered page is a
        source-integrity failure, never a silently re-hashed input). Page files
        are the numeric-stem images listed in the manifest; byte-exact copies go
        to the run's ``source/pages/`` so the artifact store stays self-contained
        while the originals remain untouched.
        """
        archive_dir = Path(source.source_archive)
        if not archive_dir.is_dir():
            raise FileNotFoundError(f"pages source archive is not a directory: {archive_dir}")

        manifest_json_path = archive_dir / "manifest.json"
        if not manifest_json_path.is_file():
            raise FileNotFoundError(
                f"pages source requires manifest.json next to the page images: {archive_dir}"
            )
        extraction = json.loads(manifest_json_path.read_text(encoding="utf-8"))
        if not isinstance(extraction, dict):
            raise ValueError(f"{manifest_json_path}: root must be a mapping")
        images = extraction.get("images")
        if not isinstance(images, list) or not images:
            raise ValueError(f"{manifest_json_path}: images must be a non-empty list")

        def _normalize_sha(value: str, *, label: str) -> str:
            # manifest.json (WeChat extraction) stores bare hex; canonical
            # artifacts store the sha256: prefix. Accept both.
            text = str(value or "").strip()
            if text.startswith("sha256:"):
                return text
            if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                return f"sha256:{text}"
            raise SourceIntegrityError(
                f"{manifest_json_path}: images[{label}] sha256 malformed: {value!r}"
            )

        page_files: list[tuple[int, str, str]] = []  # (page_number, file, sha256)
        for entry in images:
            if not isinstance(entry, dict):
                raise ValueError(f"{manifest_json_path}: images[] entries must be mappings")
            name = str(entry.get("file") or "")
            if not name:
                raise ValueError(f"{manifest_json_path}: images[] entry missing file")
            stem = Path(name).stem
            if not _NUMERIC_STEM.match(stem):
                continue  # non-page asset (html, report, …) — never a page
            page_files.append(
                (int(stem), name, _normalize_sha(entry.get("sha256"), label=name))
            )
        if not page_files:
            raise ValueError(f"{manifest_json_path}: no numeric-stem page images listed")
        page_files.sort(key=lambda item: item[0])
        numbers = [item[0] for item in page_files]
        if numbers != sorted(set(numbers)):
            raise ValueError(f"{manifest_json_path}: page numbers must be unique")

        pages_dir = self.store.layout.source_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        pages_payload = []
        enhancements: dict[int, str] = {}
        for page_number, name, expected_sha in page_files:
            original = archive_dir / name
            if not original.is_file():
                raise FileNotFoundError(f"page image listed in manifest.json is missing: {original}")
            actual_sha = sha256_file(original)
            if actual_sha != expected_sha:
                raise SourceIntegrityError(
                    f"page image sha256 drift vs manifest.json: {original} "
                    f"expected {expected_sha} got {actual_sha}"
                )
            # OCR normalization for low-resolution WeChat scans: qwen3.5-ocr
            # returned near-empty text for dense 1080px pages (2025-HUANGPU
            # page 5 dropped a whole question); a 2x LANCZOS upscale of the
            # run copy restores full text. Originals stay untouched — the
            # integrity check above ran against the pack bytes, and the page
            # plan records the enhancement for provenance.
            from PIL import Image as _PilImage

            with _PilImage.open(original) as image:
                width, height = image.size
            target = pages_dir / name
            if width < _OCR_UPSCALE_MIN_WIDTH:
                with _PilImage.open(original) as image:
                    resized = image.resize(
                        (width * 2, height * 2), _PilImage.LANCZOS
                    )
                    resized.save(target)
                enhancements[page_number] = "2x-lanczos"
            else:
                shutil.copyfile(original, target)
            pages_payload.append((page_number, name, actual_sha))

        from PIL import Image as _Image

        pages = []
        for page_number, name, page_sha in pages_payload:
            with _Image.open(pages_dir / name) as image:
                width, height = image.size
            pages.append(
                {
                    "page_number": page_number,
                    "source": name,
                    "width_px": width,
                    "height_px": height,
                    "sha256": page_sha,
                }
            )
        # The pack's own numeric-stem numbering (001.jpg cover = page 1 …) is
        # authoritative: the non-question declaration and the transcription
        # evidence both reference these numbers, not 1..N by list order.
        manifest = {
            "schema": "math_pdf_source/v1",
            "paper_id": source.paper_id,
            "source_archive": str(archive_dir),
            "source": {"path": "<pre-rendered-pages>", "sha256": None},
            # dpi is nominal for pre-rendered packs (mirrors pdf_source_manifest's
            # own pre_rendered default); the contract floor is 72.
            "render": {"engine": "pre_rendered", "dpi": 180},
            "pages": pages,
        }
        from scripts.question_transcription.pdf_observation_contracts import (
            PdfSourceManifest,
        )

        PdfSourceManifest.model_validate(manifest)
        page_origins = {
            page["page_number"]: {
                "origin_archive": str(archive_dir),
                "origin_path": page["source"],
                "origin_page_number": page["page_number"],
            }
            for page in pages
        }
        return self._materialize_extracted(
            source,
            manifest,
            pages_dir,
            kind="pages",
            page_origins=page_origins,
            ocr_enhancements=enhancements,
        )

    # ------------------------------------------------------------------ #
    # Shared materialization
    # ------------------------------------------------------------------ #

    def _materialize_extracted(
        self,
        source,
        manifest,
        output_dir,
        *,
        kind,
        page_origins: dict[int, dict] | None = None,
        answer_archive: str | None = None,
        answer_sha256: str | None = None,
        ocr_enhancements: dict[int, str] | None = None,
    ):
        # ``extract_docx_source`` intentionally describes only the copied Word
        # package and therefore does not know the workflow identity.  Freeze the
        # authoritative request metadata at this adapter boundary so sibling
        # branches (notably image attribution) cannot fall back to ``unknown`` or
        # confuse the temporary ``source.docx`` copy with the original archive.
        manifest = dict(manifest)
        manifest["paper_id"] = source.paper_id
        manifest["source_archive"] = source.source_archive

        # Page-image paths in the manifest are relative to ``output_dir`` (e.g.
        # ``pages/001.png`` under ``source/docx/`` for DOCX, or page file names
        # for pre-rendered packs). The downstream page-text adapter resolves refs
        # against the RUN ROOT (``layout.root / job.image.path``), so we must
        # rebase each path to be relative to the run root, not to ``output_dir``.
        try:
            prefix = output_dir.relative_to(self.store.layout.root)
        except ValueError:
            # output_dir is outside the run root (shouldn't happen); keep raw paths.
            prefix = Path()
        prefix_str = prefix.as_posix().strip("/")

        page_refs = []
        pages = manifest.get("rendered_pages") or manifest.get("pages") or []
        for p in pages:
            # DOCX manifests key page paths by ``path``; PDF/pages manifests by
            # ``source``. Both must resolve — an entry without either is a bug.
            raw = p.get("path") if isinstance(p, dict) else None
            if raw is None and isinstance(p, dict):
                raw = p.get("source")
            if raw is None:
                continue
            # Rebase to run-root-relative unless it is already run-root-relative
            # (PDF/pages manifests already emit archive-relative names).
            if prefix_str and not str(raw).startswith(prefix_str):
                rel = f"{prefix_str}/{raw}" if prefix_str else str(raw)
            else:
                rel = str(raw)
            abs_path = self.store.layout.root / rel
            page_refs.append(
                ArtifactRef(
                    path=rel,
                    sha256=sha256_file(abs_path) if abs_path.exists() else p.get("sha256", "sha256:" + "0" * 64),
                    schema="image/png",
                )
            )
        if not page_refs:
            return None, "page_rendering_failed", "no page images produced"
        manifest_ref = self.store.commit_yaml(
            "source/source-ref.yaml", manifest, "math_word_source_extract/v1"
            if kind == "docx" else "math_pdf_source/v1"
        )

        # Explicit non-question-page claims live next to the ORIGINAL source
        # files (exam archive dir for docx; the pack dir itself for pages).
        archive_dir = (
            Path(source.source_archive).parent
            if kind in ("doc", "docx", "pdf")
            else Path(source.source_archive)
        )
        declared = read_non_question_declaration(archive_dir)
        declared_numbers = {entry.page_number for entry in declared}
        page_count = len(page_refs)
        # Page numbers are the 1-based index into the run page set; a claim
        # outside it can never be honoured and must fail loudly here rather
        # than confusing the audit later.
        out_of_range = sorted(
            number for number in declared_numbers if number < 1 or number > page_count
        )
        if out_of_range:
            return None, "normalization_failed", (
                f"non-question-pages.yaml declares page(s) {out_of_range} outside "
                f"the extracted 1..{page_count} page set"
            )

        # For pre-rendered packs the archive path IS a directory; the pack's
        # identity anchor is its integrity manifest (every page file inside is
        # already hash-verified against it above).
        if kind == "pages":
            source_sha = sha256_file(Path(source.source_archive) / "manifest.json")
        else:
            source_sha = sha256_file(source.source_archive)

        page_plan = {
            "schema": "math_page_plan/v1",
            "paper_id": source.paper_id,
            "sources": [
                {
                    "role": "primary",
                    "path": str(source.source_archive),
                    "sha256": source_sha,
                }
            ],
            "pages": [
                {
                    "page_number": index + 1,
                    "run_path": ref.path,
                    **(page_origins or {}).get(index + 1, {}),
                    **(
                        {"ocr_enhancement": (ocr_enhancements or {})[index + 1]}
                        if (index + 1) in (ocr_enhancements or {})
                        else {}
                    ),
                }
                for index, ref in enumerate(page_refs)
            ],
            "non_question_pages": [
                entry.model_dump(mode="json", exclude_none=True) for entry in declared
            ],
        }
        if answer_archive:
            page_plan["sources"].append(
                {
                    "role": "answer_supplement",
                    "path": str(answer_archive),
                    "sha256": answer_sha256 or sha256_file(answer_archive),
                }
            )
        page_plan_ref = self.store.commit_yaml(
            "source/page-plan.yaml", page_plan, "math_page_plan/v1"
        )

        return (
            ExtractedSource(
                manifest=manifest_ref,
                pages=page_refs,
                media_directory=str(output_dir) if kind in ("doc", "docx") else None,
                source_sha256=source_sha,
                non_question_pages=declared,
                page_plan=page_plan_ref,
                answer_source=answer_archive,
                answer_sha256=answer_sha256,
            ),
            None,
            None,
        )
