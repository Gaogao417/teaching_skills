"""Compatibility shim — artifact store + run layout moved to :mod:`.infrastructure`.

The canonical home for :class:`RunLayout`, :class:`ArtifactStore` and the
hash/atomic helpers is now ``workflow/infrastructure/{run_layout,artifact_store}.py``
(architecture §3.7). This module re-exports them so existing imports keep working
until M8 removes the shim.
"""

from __future__ import annotations

from .infrastructure.artifact_store import (  # noqa: F401  (canonical re-export)
    ArtifactStore,
    atomic_write_text,
    atomic_write_yaml,
    sha256_bytes,
    sha256_file,
)
from .infrastructure.run_layout import RunLayout  # noqa: F401  (canonical re-export)

__all__ = [
    "RunLayout",
    "ArtifactStore",
    "sha256_file",
    "sha256_bytes",
    "atomic_write_text",
    "atomic_write_yaml",
]
