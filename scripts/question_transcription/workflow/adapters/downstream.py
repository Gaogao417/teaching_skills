"""Compatibility shim — moved to staging/existing_pipeline.py (M5). Re-exports the canonical symbols."""

from __future__ import annotations

from .staging.existing_pipeline import (  # noqa: F401
    DeterministicAssetMaterializer,
    DeterministicCatalogNotifier,
    DeterministicDraftProjector,
    DeterministicEvidenceCompleter,
    DeterministicStagingAuditor,
    DeterministicStagingExpander,
)

__all__ = [
    "DeterministicDraftProjector",
    "DeterministicEvidenceCompleter",
    "DeterministicStagingExpander",
    "DeterministicAssetMaterializer",
    "DeterministicStagingAuditor",
    "DeterministicCatalogNotifier",
]
