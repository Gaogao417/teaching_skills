"""Compatibility shim — moved to source/source_paper.py (M5). Re-exports the canonical symbols."""

from __future__ import annotations

from .source.source_paper import (  # noqa: F401
    DeterministicSourcePaperBuilder,
    _project_minimal_v2,
)

__all__ = ["DeterministicSourcePaperBuilder"]
