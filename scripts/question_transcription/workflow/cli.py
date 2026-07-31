"""Compatibility shim — CLI moved to :mod:`.bootstrap.cli` (M6).

Re-exports the canonical symbols so existing imports keep working until M8.
"""

from __future__ import annotations

from .bootstrap.cli import main, resume, start, status  # noqa: F401

__all__ = ["main", "start", "status", "resume"]
