"""Source extraction port (architecture §3.4).

Routes purely on :data:`~.contracts.SourceKind`::

    Doc / Docx  -> DOCX extractor (extract_docx_source)
    Pdf         -> PDF extractor (render_pdf_pages)
    pages       -> page-manifest validator

The port exposes no provider/host choice. Success of ``Extract`` is the gate that
unlocks both the page-text fan-out and the image-attribution branch (design §3.2).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..contracts import ExtractedSource, SourceInput


__all__ = ["SourceExtractionError", "SourceExtractor"]


SourceExtractionError = Literal[
    "unsupported_source_kind",
    "source_not_found",
    "source_already_mutated",
    "normalization_failed",
    "page_rendering_failed",
    "manifest_invalid",
]


@runtime_checkable
class SourceExtractor(Protocol):
    """Extract and freeze the source into page images, media and a manifest."""

    def extract(
        self, source: SourceInput
    ) -> "tuple[ExtractedSource | None, SourceExtractionError | None, str | None]":
        """Freeze ``source``.

        Returns ``(extracted, None, None)`` on success or
        ``(None, error_kind, detail)`` on failure. The adapter is expected to wrap
        the existing ``extract_docx_source.extract`` / ``render_pdf_pages.render``
        functions and translate their exceptions into ``error_kind``.
        """
