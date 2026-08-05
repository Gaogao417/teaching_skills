"""Source-extraction wrapper (architecture §3.6 and §5.2).

Wraps the existing deterministic functions (NOT the CLIs — we want exceptions, not
``SystemExit``):

- :func:`extract_docx_source.extract` for DOC/DOCX
- :func:`render_pdf_pages.render` for PDF

These are bound by the composition root; nodes never see the source kind discriminator
beyond ``state["source_kind"]`` (which routes the *business* branch, not an adapter
host choice).
"""

from __future__ import annotations

from pathlib import Path

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap)
from ...contracts import ArtifactRef, ExtractedSource, SourceInput
from ...ports.source import SourceExtractionError


__all__ = ["DocxOrPdfSourceExtractor"]


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
        from .pdf_source_manifest import (
            PdfSourceManifest,
        )

        pages_dir = self.store.layout.source_dir / "pages"
        page_paths = pdf_render(Path(source.source_archive), pages_dir, self.dpi)
        # Build a minimal PDF source manifest the page-text branch can consume.
        from ...infrastructure.artifact_store import sha256_file

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
        from ...infrastructure.artifact_store import sha256_file

        # ``extract_docx_source`` intentionally describes only the copied Word
        # package and therefore does not know the workflow identity.  Freeze the
        # authoritative request metadata at this adapter boundary so sibling
        # branches (notably image attribution) cannot fall back to ``unknown`` or
        # confuse the temporary ``source.docx`` copy with the original archive.
        manifest = dict(manifest)
        manifest["paper_id"] = source.paper_id
        manifest["source_archive"] = source.source_archive

        # Page-image paths in the manifest are relative to ``output_dir`` (e.g.
        # ``pages/001.png`` under ``source/docx/`` for DOCX, or ``source/pages/xxx``
        # for PDF). The downstream page-text adapter resolves refs against the RUN
        # ROOT (``layout.root / job.image.path``), so we must rebase each path to be
        # relative to the run root, not to ``output_dir``.
        try:
            prefix = output_dir.relative_to(self.store.layout.root)
        except ValueError:
            # output_dir is outside the run root (shouldn't happen); keep raw paths.
            prefix = Path()
        prefix_str = prefix.as_posix().strip("/")

        page_refs = []
        pages = manifest.get("rendered_pages") or manifest.get("pages") or []
        for p in pages:
            raw = p.get("path") if isinstance(p, dict) else None
            if raw is None:
                continue
            # Rebase to run-root-relative unless it is already run-root-relative
            # (PDF manifests already emit ``source/pages/...``).
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
