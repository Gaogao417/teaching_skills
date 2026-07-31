"""Composition root — the SOLE place that selects and decorates adapters (architecture §6).

``bind(config, layout, *, mode) -> WorkflowDependencies``:

1. Picks one concrete page-text adapter (qwen3.5-ocr / MiMo) by ``config.page_text_provider``.
2. Picks one concrete whole-paper infrastructure model (OpenCode glm-5.2 / Claude Code)
   by ``config.whole_paper_adapter`` and injects it into the unified
   :class:`~..adapters.whole_paper.structured_transcriber.StructuredWholePaperTranscriber`.
3. Wraps each in retry/cache/rate-limit decorators (transport-level; invisible to nodes).
4. Records provenance ONCE in the run manifest (not in state; nodes do not read it).

For offline tests, ``mode="fake"`` short-circuits to the offline fakes regardless of
config, so the graph lifecycle can run without API keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..artifact_store import ArtifactStore, RunLayout, sha256_file
from .config import AdapterProvenance, RuntimeAdapterConfig
from .dependencies import DeterministicPorts, WorkflowDependencies
from ..tracing import NullTraceSink, TraceSink, reset as reset_trace


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
    from ..testsupport.fakes import FakeScenario, build_fake_deps

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
        whole_paper_prompt_mode=config.whole_paper_prompt_mode,
    )


def _bind_page_text(config, store):
    from ..adapters.page_text.qwen import QwenPageTextExtractor
    from ..adapters.page_text.mimo import MimoPageTextExtractor
    from ..adapters.decorators import with_page_retry

    if config.page_text_provider == "qwen":
        inner = QwenPageTextExtractor(model=config.qwen_model, store=store)
    else:
        inner = MimoPageTextExtractor(model=config.mimo_model, store=store)
    return with_page_retry(inner, config.page_retry)


def _bind_whole_paper(config, store):
    from ..adapters.decorators import with_whole_paper_retry
    from ..adapters.whole_paper.structured_transcriber import (
        StructuredWholePaperTranscriber,
    )
    from ..prompts.whole_paper import WHOLE_PAPER_SYSTEM_PROMPT

    bound_model, adapter_id, model_name = _bind_whole_paper_model(config)

    inner = StructuredWholePaperTranscriber(
        adapter_id=adapter_id,
        model_name=model_name,
        bound_model=bound_model,
        store=store,
        system_prompt=WHOLE_PAPER_SYSTEM_PROMPT,
        agent_name=f"whole-paper-transcriber-{adapter_id}",
    )
    return with_whole_paper_retry(inner, config.whole_paper_retry)


def _bind_whole_paper_model(config):
    """Bind one infrastructure ``Model`` for the chosen whole-paper provider.

    Returns ``(bound_model, adapter_id, model_name)``. This is the only place that
    constructs the OpenCode or Claude Code infrastructure model; the unified
    transcriber receives it already bound (architecture §3.8 / §9.5).
    """

    if config.whole_paper_adapter == "opencode":
        from scripts.infrastructure.ai.opencode.client import OpencodeClient
        from scripts.infrastructure.ai.opencode.pydantic_model import OpencodeModel

        client = OpencodeClient(
            server_url=config.opencode_server_url,
            agent_type=config.opencode_agent_type,
        )
        return (
            OpencodeModel(model_name=config.opencode_model, client=client),
            "opencode",
            config.opencode_model,
        )

    # claude_code
    from scripts.infrastructure.ai.claude_code.pydantic_model import ClaudeCodeModel
    from ..prompts.whole_paper import WHOLE_PAPER_SYSTEM_PROMPT

    return (
        ClaudeCodeModel(
            model_name=config.claude_code_model,
            system_prompt=WHOLE_PAPER_SYSTEM_PROMPT,
            timeout_s=config.claude_code_timeout_s,
        ),
        "claude-code",
        config.claude_code_model,
    )


def _bind_deterministic(config, store):
    from ..adapters.source.extraction import DocxOrPdfSourceExtractor
    from ..adapters.source.image_attribution import DocxOrPdfImageAttribution
    from ..adapters.source.source_paper import DeterministicSourcePaperBuilder
    from ..adapters.staging.existing_pipeline import (
        DeterministicAssetMaterializer,
        DeterministicCatalogNotifier,
        DeterministicDraftProjector,
        DeterministicEvidenceCompleter,
        DeterministicStagingAuditor,
        DeterministicStagingExpander,
    )
    from ..adapters.review.filesystem import DeterministicFinalReviewReader

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
    else:
        wp_model = config.claude_code_model
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
