"""Source adapters (capability: source).

Canonical implementations:

- :mod:`.source.extraction`        — :class:`DocxOrPdfSourceExtractor`
- :mod:`.source.image_attribution` — :class:`DocxOrPdfImageAttribution`
- :mod:`.source.source_paper`      — :class:`DeterministicSourcePaperBuilder`

This package replaces the old ``adapters/docx_or_pdf.py`` and ``adapters/source_build.py``
modules (M5 relocation); the three public symbols are re-exported here so the package
acts as the single import surface for the source capability.
"""

from __future__ import annotations

from .extraction import DocxOrPdfSourceExtractor
from .image_attribution import DocxOrPdfImageAttribution
from .source_paper import DeterministicSourcePaperBuilder

__all__ = [
    "DocxOrPdfSourceExtractor",
    "DocxOrPdfImageAttribution",
    "DeterministicSourcePaperBuilder",
]
