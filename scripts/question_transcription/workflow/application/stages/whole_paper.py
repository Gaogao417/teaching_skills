"""Whole-paper application stage helpers (architecture §3.4, M4).

Pure, framework-agnostic page-coverage validation for the whole-paper transcription
stage. The LangGraph node wrapper calls :func:`validate_page_coverage` and then the
bound :class:`WholePaperTranscriber`.
"""

from __future__ import annotations

from ...contracts import PageTextExtract


__all__ = ["validate_page_coverage"]


def validate_page_coverage(
    extracts: list[PageTextExtract],
) -> "tuple[list[PageTextExtract] | None, str | None]":
    """Ensure exact, ordered, non-duplicate coverage (ports §6.4 / §7.3).

    Returns ``(ordered_extracts, None)`` on success or ``(None, error)`` on failure.
    """

    if not extracts:
        return None, "no page text extracts"
    page_numbers = [e.artifact.page_number for e in extracts]
    if len(page_numbers) != len(set(page_numbers)):
        return None, f"duplicate page numbers: {page_numbers}"
    if page_numbers != sorted(page_numbers):
        return sorted(extracts, key=lambda e: e.artifact.page_number), None
    return extracts, None
