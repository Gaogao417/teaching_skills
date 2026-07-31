"""Composition root — the SOLE place that selects and decorates adapters (design §6).

``bind(config, layout, *, mode) -> WorkflowDependencies``:

1. Picks one concrete page-text adapter (qwen3.5-ocr / MiMo) by ``config.page_text_provider``.
2. Picks one concrete whole-paper adapter (opencode glm-5.2 / claude code / direct GLM
   API) by ``config.whole_paper_adapter``.
3. Wraps each in retry/cache/rate-limit decorators (transport-level; invisible to nodes).
4. Records provenance ONCE in the run manifest (not in state; nodes do not read it).

For offline tests, ``mode="fake"`` short-circuits to the offline fakes regardless of
config, so the graph lifecycle can run without API keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .artifact_store import ArtifactStore, RunLayout, sha256_file
from .config import AdapterProvenance, RuntimeAdapterConfig
from .dependencies import DeterministicPorts, WorkflowDependencies
from .tracing import NullTraceSink, TraceSink, reset as reset_trace


__all__ = ["bind", "BindMode", "build_run_layout"]


BindMode = Literal["fake", "live"]


def build_run_layout(build_root: Path | str, paper_id: str, run_id: str) -> RunLayout:
    layout = RunLayout(build_root, paper_id, run_id)
    layout.ensure()
    return layout


def bind(
    config: RuntimeAdapterConfig,
    layout: RunLayout,
    *,
    mode: BindMode = "live",
    trace_sink: TraceSink | None = None,
) -> WorkflowDependencies:
    """Bind concrete adapters per ``config`` and wrap them; return dependencies.

    ``mode="fake"`` returns the offline test doubles (used by E1-E7 and the CLI's
    ``--dry-run``). ``mode="live"`` imports the real adapter modules lazily so the
    offline suite never loads model SDKs.
    """

    store = ArtifactStore(layout)
    reset_trace(trace_sink)
    if trace_sink is None:
        reset_trace(NullTraceSink())

    if mode == "fake":
        return _bind_fake(store, layout)

    return _bind_live(config, store, layout)


# --------------------------------------------------------------------------- #
# Fake binding (offline)
# --------------------------------------------------------------------------- #


def _bind_fake(store: ArtifactStore, layout: RunLayout) -> WorkflowDependencies:
    from .testsupport.fakes import FakeScenario, build_fake_deps

    return build_fake_deps(store, FakeScenario())


# --------------------------------------------------------------------------- #
# Live binding (real adapters)
# --------------------------------------------------------------------------- #


def _bind_live(
    config: RuntimeAdapterConfig, store: ArtifactStore, layout: RunLayout
) -> WorkflowDependencies:
    page_extractor = _bind_page_text(config, store)
    whole_transcriber = _bind_whole_paper(config, store)
    deterministic = _bind_deterministic(config, store)

    return WorkflowDependencies(
        run_layout=layout,
        artifact_store=store,
        trace_sink=None,
        page_text_extractor=page_extractor,
        whole_paper_transcriber=whole_transcriber,
        deterministic=deterministic,
        whole_paper_max_repairs=config.whole_paper_max_repairs,
    )


def _bind_page_text(config, store):
    from .adapters.page_text.qwen import QwenPageTextExtractor
    from .adapters.page_text.mimo import MimoPageTextExtractor
    from .adapters.decorators import with_page_retry

    if config.page_text_provider == "qwen":
        inner = QwenPageTextExtractor(model=config.qwen_model, store=store)
    else:
        inner = MimoPageTextExtractor(model=config.mimo_model, store=store)
    return with_page_retry(inner, config.page_retry)


def _bind_whole_paper(config, store):
    from .adapters.decorators import with_whole_paper_retry

    if config.whole_paper_adapter == "opencode":
        from .adapters.whole_paper.opencode import OpencodeGlmTranscriber

        inner = OpencodeGlmTranscriber(
            model=config.opencode_model,
            server_url=config.opencode_server_url,
            agent_type=config.opencode_agent_type,
            store=store,
        )
    elif config.whole_paper_adapter == "api":
        from .adapters.whole_paper.glm_api import GlmApiTranscriber

        inner = GlmApiTranscriber(
            model=config.glm_api_model,
            base_url=config.glm_api_base_url,
            store=store,
        )
    else:  # claude_code
        from .adapters.whole_paper.claude_code import ClaudeCodeTranscriber

        inner = ClaudeCodeTranscriber(store=store)
    return with_whole_paper_retry(inner, config.whole_paper_retry)


def _bind_deterministic(config, store):
    from .adapters.source_build import DeterministicSourcePaperBuilder
    from .adapters.docx_or_pdf import (
        DocxOrPdfImageAttribution,
        DocxOrPdfSourceExtractor,
    )
    from .adapters.downstream import (
        DeterministicAssetMaterializer,
        DeterministicCatalogNotifier,
        DeterministicDraftProjector,
        DeterministicEvidenceCompleter,
        DeterministicStagingAuditor,
        DeterministicStagingExpander,
    )
    from .adapters.review import DeterministicFinalReviewReader

    return DeterministicPorts(
        source_extractor=DocxOrPdfSourceExtractor(store),
        source_paper_builder=DeterministicSourcePaperBuilder(store),
        image_attribution=DocxOrPdfImageAttribution(store),
        draft_projector=DeterministicDraftProjector(store),
        evidence_completer=DeterministicEvidenceCompleter(store),
        staging_expander=DeterministicStagingExpander(store),
        asset_materializer=DeterministicAssetMaterializer(store),
        staging_auditor=DeterministicStagingAuditor(store),
        catalog_notifier=DeterministicCatalogNotifier(store),
        final_review_reader=DeterministicFinalReviewReader(store),
    )


def record_provenance(
    store: ArtifactStore,
    config: RuntimeAdapterConfig,
    run_id: str,
    paper_id: str,
) -> None:
    """Write the run manifest with adapter provenance (called once at start)."""

    page_prov = AdapterProvenance(
        adapter_id=config.page_text_provider,
        model=config.qwen_model if config.page_text_provider == "qwen" else config.mimo_model,
        prompt_version="page-text-ocr-v1",
    )
    if config.whole_paper_adapter == "opencode":
        wp_model = config.opencode_model
    elif config.whole_paper_adapter == "api":
        wp_model = config.glm_api_model
    else:
        wp_model = "claude-code"
    whole_prov = AdapterProvenance(
        adapter_id=config.whole_paper_adapter,
        model=wp_model,
        prompt_version="whole-paper-v1",
    )
    store.write_manifest(
        run_id,
        paper_id,
        {
            "page_text": page_prov.model_dump(),
            "whole_paper": whole_prov.model_dump(),
            "page_concurrency": config.page_concurrency.model_dump(),
        },
    )
