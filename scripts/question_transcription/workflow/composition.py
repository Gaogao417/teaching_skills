"""Compatibility shim — composition moved to :mod:`.bootstrap.composition` (M6).

Re-exports the canonical symbols so existing imports keep working until M8.
"""

from __future__ import annotations

from .bootstrap.composition import (  # noqa: F401
    BindMode,
    bind,
    build_run_layout,
    record_provenance,
)

__all__ = ["bind", "BindMode", "build_run_layout"]
