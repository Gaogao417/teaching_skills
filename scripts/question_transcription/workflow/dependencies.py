"""Compatibility shim — dependencies moved to :mod:`.bootstrap.dependencies` (M6).

Re-exports the canonical symbols so existing imports keep working until M8.
"""

from __future__ import annotations

from .bootstrap.dependencies import DeterministicPorts, WorkflowDependencies  # noqa: F401

__all__ = ["WorkflowDependencies", "DeterministicPorts"]
