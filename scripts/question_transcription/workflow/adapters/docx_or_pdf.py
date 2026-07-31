"""Source-extraction + image-attribution wrappers (ports-design §3, §8).

Wraps the existing deterministic functions (NOT the CLIs — we want exceptions, not
``SystemExit``):

- :func:`extract_docx_source.extract` for DOC/DOCX
- :func:`render_pdf_pages.render` for PDF
- :func:`adapt_docx_images.adapt` / :func:`adapt_pdf_images.adapt` for image attribution

These are bound by the composition root; nodes never see the source kind discriminator
beyond ``state["source_kind"]`` (which routes the *business* branch, not an adapter
host choice).
"""

from __future__ import annotations

from pathlib import Path

from ._common_paths import repo_root  # noqa: F401  (sys.path bootstrap)
from ..contracts import ArtifactRef, ExtractedSource, SourceInput
from ..ports.source import SourceExtractionError


__all__ = ["DocxOrPdfSourceExtractor", "DocxOrPdfImageAttribution"]


class DocxOrPdfSourceExtractor:
    """:class:`SourceExtractor` dispatching on ``source_kind`` (Doc/Docx/Pdf)."""

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
            return None, "unsupported_source_kind", f"source_kind={kind!r}"
        except FileNotFoundError as exc:
            return None, "source_not_found", str(exc)
        except ValueError as exc:
            return None, "normalization_failed", str(exc)
        except Exception as exc:  # pragma: no cover - subprocess failures
            return None, "page_rendering_failed", f"{type(exc).__name__}: {exc}"

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
        return self._materialize_extracted(source, manifest, output_dir, kind="docx")

    def _extract_pdf(self, source: SourceInput):
        import sys

        skill_scripts = repo_root() / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
        if str(skill_scripts) not in sys.path:
            sys.path.insert(0, str(skill_scripts))
        from render_pdf_pages import render as pdf_render  # type: ignore
        from scripts.question_transcription.pdf_source_manifest import (  # type: ignore
            PdfSourceManifest,
        )

        pages_dir = self.store.layout.source_dir / "pages"
        page_paths = pdf_render(Path(source.source_archive), pages_dir, self.dpi)
        # Build a minimal PDF source manifest the page-text branch can consume.
        from ..artifact_store import sha256_file

        pages = [
            {"page_number": i + 1, "source": f"source/pages/{p.name}",
             "sha256": sha256_file(p)}
            for i, p in enumerate(sorted(page_paths))
        ]
        manifest = {
            "schema": "math_pdf_source_manifest/v1",
            "paper_id": source.paper_id,
            "source_archive": source.source_archive,
            "pages": pages,
        }
        return self._materialize_extracted(source, manifest, pages_dir, kind="pdf")

    def _materialize_extracted(self, source, manifest, output_dir, *, kind):
        from ..artifact_store import sha256_file

        page_refs = []
        pages = manifest.get("rendered_pages") or manifest.get("pages") or []
        for p in pages:
            rel = p.get("path") if isinstance(p, dict) else None
            if rel is None:
                continue
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
            if kind == "docx" else "math_pdf_source_manifest/v1"
        )
        source_sha = sha256_file(source.source_archive)
        return (
            ExtractedSource(
                manifest=manifest_ref,
                pages=page_refs,
                media_directory=str(output_dir) if kind == "docx" else None,
                source_sha256=source_sha,
            ),
            None,
            None,
        )


class DocxOrPdfImageAttribution:
    """Deterministic image-attribution adapter (ports §8).

    The ``attribute`` method receives the extracted-source dict and returns
    ``(bundle_ref, structure_status, issues_ref, detail)`` matching the contract the
    ``attribute_images`` node expects.
    """

    def __init__(self, store) -> None:
        self.store = store

    def attribute(self, extracted_source):
        kind = extracted_source.get("source_kind") if isinstance(extracted_source, dict) else None
        # The node passes the ArtifactRef dict for extracted_source; we read the
        # manifest to decide DOCX vs PDF attribution.
        manifest_ref = extracted_source
        try:
            manifest = self.store.read_yaml(
                ArtifactRef.model_validate(manifest_ref)
                if not isinstance(manifest_ref, ArtifactRef)
                else manifest_ref
            ) if isinstance(manifest_ref, (dict, ArtifactRef)) else None
        except Exception:
            manifest = None
        schema = (manifest or {}).get("schema", "")
        try:
            if "word_source" in schema:
                bundle = self._adapt_docx(manifest)
            else:
                bundle = self._adapt_pdf(manifest)
            ref = self.store.commit_yaml(
                "structured/image-attribution.yaml", bundle, "math_image_attribution/v1"
            )
            return ref, "complete", None, None
        except ValueError as exc:
            return None, "failed", None, str(exc)

    def _adapt_docx(self, manifest):
        from scripts.question_transcription.adapt_docx_images import adapt  # type: ignore

        paper_id = manifest.get("paper_id", "unknown")
        source_archive = manifest.get("source", {}).get("path") or manifest.get("source_archive", "")
        return adapt(manifest, paper_id=paper_id, source_archive=source_archive)

    def _adapt_pdf(self, manifest):
        from scripts.question_transcription.adapt_pdf_images import adapt  # type: ignore

        return adapt(manifest, allow_model_accepted=False)
