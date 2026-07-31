"""Page-text extraction business port (ports-design §4).

A bound ``PageTextExtractor`` performs OCR-style plain-text extraction of a single
page image: transcribe visible words in reading order, render formulae as LaTeX,
preserve necessary line breaks, and **nothing else** (no question boundaries, no
answer fields, no attribution, no SourceQuestion — ports §2.1).

Real adapters implementing this port:

- :class:`~..adapters.page_text.qwen.QwenPageTextExtractor` -> qwen-vl-ocr (DashScope)
- :class:`~..adapters.page_text.mimo.MimoPageTextExtractor` -> MiMo v2.5

Both share the same prompt semantics. The node only knows "extract this page"; it
does not know which provider was bound at the composition root.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import PageTextExtract, PageTextFailure, PageTextJob


__all__ = ["PageTextExtractor"]


@runtime_checkable
class PageTextExtractor(Protocol):
    """Extract plain text from one page image (OCR-style, no question structure)."""

    def extract(
        self, job: PageTextJob
    ) -> "tuple[PageTextExtract | None, PageTextFailure | None]":
        """Extract ``job``.

        Returns ``(extract, None)`` on success — ``extract`` must have non-blank
        ``.txt`` content, else the barrier treats it as a contract failure — or
        ``(None, failure)`` after the bound retry/cache/limiter decorators are
        exhausted. No provider switch happens here.
        """
