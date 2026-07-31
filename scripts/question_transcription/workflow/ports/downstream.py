"""Compatibility shim — the deterministic staging ports moved to :mod:`.staging`.

The stable business name for this pipeline is *staging* (architecture §8.1 naming).
This module re-exports the canonical symbols so existing imports
(``from ..ports.downstream import StageFailure`` etc.) keep working until M8 removes
the shim.
"""

from __future__ import annotations

from .staging import (  # noqa: F401  (canonical re-export)
    AssetMaterializer,
    CatalogNotifier,
    DraftProjector,
    EvidenceCompleter,
    StageFailure,
    StagingAuditor,
    StagingExpander,
)

__all__ = [
    "StageFailure",
    "DraftProjector",
    "EvidenceCompleter",
    "StagingExpander",
    "AssetMaterializer",
    "StagingAuditor",
    "CatalogNotifier",
]
