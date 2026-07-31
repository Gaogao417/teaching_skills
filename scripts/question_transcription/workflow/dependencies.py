"""Workflow dependencies — the bound-ports bundle handed to :func:`.graph.build_graph`.

This is the current Python counterpart of the bootstrap dependencies described in
``docs/question-ingestion-architecture.md`` §3.8 and §9. It is built solely by
:mod:`.composition` and consumed by graph construction. Nodes receive bound ports,
never a provider/host discriminator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .artifact_store import ArtifactStore, RunLayout
from .ports.downstream import (
    AssetMaterializer,
    CatalogNotifier,
    DraftProjector,
    EvidenceCompleter,
    StagingAuditor,
    StagingExpander,
)
from .ports.page_text import PageTextExtractor
from .ports.review import FinalReviewReader
from .ports.source import SourceExtractor
from .ports.source_build import SourcePaperBuilder
from .ports.whole_paper import WholePaperTranscriber
from .tracing import TraceSink


__all__ = ["WorkflowDependencies", "DeterministicPorts"]


@dataclass
class DeterministicPorts:
    """The deterministic source/image/staging/review ports in the current layout."""

    source_extractor: SourceExtractor
    source_paper_builder: SourcePaperBuilder
    image_attribution: object  # determinstic image-attribution adapter (ports §8)
    draft_projector: DraftProjector
    evidence_completer: EvidenceCompleter
    staging_expander: StagingExpander
    asset_materializer: AssetMaterializer
    staging_auditor: StagingAuditor
    catalog_notifier: CatalogNotifier
    final_review_reader: FinalReviewReader


@dataclass
class WorkflowDependencies:
    """Everything :func:`build_graph` needs, with adapters already bound+decorated."""

    run_layout: RunLayout
    artifact_store: ArtifactStore
    trace_sink: TraceSink

    page_text_extractor: PageTextExtractor
    whole_paper_transcriber: WholePaperTranscriber
    deterministic: DeterministicPorts

    # Optional staging target override (otherwise derived from the draft path).
    staging_target_root: Optional[str] = None

    # Whole-paper structured-output repair budget (ports §7.4).
    whole_paper_max_repairs: int = 2

    # Whole-paper prompt layout: "interleaved" (default) or "separated"
    # (题卷/答案分文件; architecture §7.4).
    whole_paper_prompt_mode: str = "interleaved"
