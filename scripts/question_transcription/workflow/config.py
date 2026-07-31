"""Runtime adapter configuration — the ONLY module that names provider/host choices.

INVARIANT (design §16.13): :mod:`.state`, graph nodes and subgraphs MUST NOT import
this module. Only :mod:`.composition` imports it, to select and decorate a concrete
adapter before building the graph. ``RuntimeAdapterConfig`` never enters
``WorkflowState`` and is never passed to a node function.

The values here freeze the §11 decisions made for this milestone:

- Page text provider default: ``qwen`` (qwen-vl-ocr, DashScope). MiMo is selectable.
- Whole-paper adapter default: ``opencode`` (glm-5.2 via the OpenCode server, whose
  model is fixed server-side in ``~/.config/opencode/opencode.json``). Direct GLM
  Claude Code is selectable. Claude Code binds per request via
  ``claude-agent-sdk``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


__all__ = [
    "PageTextProviderChoice",
    "WholePaperAdapterChoice",
    "RetryPolicy",
    "PageConcurrencyConfig",
    "DEFAULT_PAGE_TEXT_PROVIDER",
    "DEFAULT_WHOLE_PAPER_ADAPTER",
    "DEFAULT_QWEN_MODEL",
    "DEFAULT_MIMO_MODEL",
    "DEFAULT_OPENCODE_MODEL",
    "DEFAULT_OPENCODE_SERVER_URL",
    "DEFAULT_OPENCODE_AGENT_TYPE",
    "DEFAULT_CLAUDE_CODE_MODEL",
    "DEFAULT_CLAUDE_CODE_TIMEOUT_S",
    "RuntimeAdapterConfig",
    "AdapterProvenance",
]


PageTextProviderChoice = Literal["qwen", "mimo"]
WholePaperAdapterChoice = Literal["opencode", "claude_code"]

DEFAULT_PAGE_TEXT_PROVIDER: PageTextProviderChoice = "qwen"
DEFAULT_WHOLE_PAPER_ADAPTER: WholePaperAdapterChoice = "opencode"

# Page-text model ids (§11 freeze): qwen3.5-ocr is the dedicated OCR model already
# wired through the existing bailian_ocr_client (DASHSCOPE_API_KEY), verified in
# production for faithful per-page plain-text + LaTeX extraction with no question
# structure — the closest fit to the design's OCR-style requirement.
DEFAULT_QWEN_MODEL = "qwen3.5-ocr"
# MiMo v2.5 plain-text model (the existing mimo_client default).
DEFAULT_MIMO_MODEL = "mimo-v2.5"

# Whole-paper GLM-5.2 (§11 freeze): the OpenCode server is configured server-side
# with glm-5.2 in ~/.config/opencode/opencode.json, so the adapter relies on the
# server-side model binding rather than per-request model_id (which opencode-agent's
# provider does not propagate; see ``docs/question-ingestion-architecture.md`` §7.1.
# The agent_type selects a server-side agent config.
DEFAULT_OPENCODE_MODEL = "glm-5.2"
DEFAULT_OPENCODE_SERVER_URL = "http://127.0.0.1:4096"
DEFAULT_OPENCODE_AGENT_TYPE = "build"

# Whole-paper Claude Code (§11 freeze #5 resolved): ``claude-agent-sdk`` drives the
# locally installed ``claude`` CLI and sets model / permission_mode on every request,
# so routing is verifiable by construction (unlike OpenCode's server-side model
# binding). The SDK checks ``ANTHROPIC_API_KEY`` first, then the CLI's stored
# credentials / ``CLAUDE_CODE_OAUTH_TOKEN``.
#
# Model default is ``glm-5.2``: in this deployment the ``claude`` CLI is pointed
# (via ~/.claude/settings.json env: ANTHROPIC_BASE_URL → open.bigmodel.cn/api/anthropic)
# at the GLM Anthropic-compatible gateway, whose real model ids are glm-4.5..glm-5.2.
# The SDK passes the model name verbatim to the gateway (it does NOT apply the CLI's
# ANTHROPIC_DEFAULT_SONNET_MODEL alias remap), so the literal alias must be a model the
# gateway recognizes. ``glm-5.2`` matches the OpenCode adapter for the same gateway
# and is verified end-to-end by the live canary. Override to ``sonnet`` etc. when the
# CLI points at a real Anthropic endpoint.
DEFAULT_CLAUDE_CODE_MODEL = "glm-5.2"
DEFAULT_CLAUDE_CODE_TIMEOUT_S = 300.0


class RetryPolicy(BaseModel):
    """Bounded exponential-backoff retry policy for a decorated adapter."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)
    base_delay_ms: int = Field(default=1000, ge=0)
    max_delay_ms: int = Field(default=30000, ge=1)


class PageConcurrencyConfig(BaseModel):
    """Three-layer page fan-out concurrency budget (ports §6.1)."""

    model_config = ConfigDict(extra="forbid")

    graph_max_concurrency: int = Field(default=4, ge=1)
    provider_max_in_flight: int = Field(default=4, ge=1)
    provider_requests_per_minute: int = Field(default=60, ge=1)
    provider_tokens_per_minute: int = Field(default=0, ge=0)


class AdapterProvenance(BaseModel):
    """Provenance recorded once in the run manifest (NOT used for node routing)."""

    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    model: str
    prompt_version: str
    config_version: str = "v1"


class RuntimeAdapterConfig(BaseModel):
    """Deployment/CLI configuration consumed by :mod:`.composition`.

    Carries the provider/host choice plus the retry/concurrency budgets. Validation
    here is configuration-level; it does not touch the network or read API keys.
    """

    model_config = ConfigDict(extra="forbid")

    page_text_provider: PageTextProviderChoice = DEFAULT_PAGE_TEXT_PROVIDER
    whole_paper_adapter: WholePaperAdapterChoice = DEFAULT_WHOLE_PAPER_ADAPTER

    page_retry: RetryPolicy = Field(default_factory=RetryPolicy)
    whole_paper_retry: RetryPolicy = Field(default_factory=RetryPolicy)
    page_concurrency: PageConcurrencyConfig = Field(default_factory=PageConcurrencyConfig)

    # Model ids (overridable for experiments; defaults frozen above).
    qwen_model: str = DEFAULT_QWEN_MODEL
    mimo_model: str = DEFAULT_MIMO_MODEL
    opencode_model: str = DEFAULT_OPENCODE_MODEL
    opencode_server_url: str = DEFAULT_OPENCODE_SERVER_URL
    opencode_agent_type: str = DEFAULT_OPENCODE_AGENT_TYPE

    # Transitional location for paper layout (architecture §7.4). The target
    # design moves this request semantic out of provider runtime config.
    # "interleaved" = questions and solutions on the same pages (default);
    # "separated"   = question paper and answer/solution file are separate.
    whole_paper_prompt_mode: Literal["interleaved", "separated"] = "interleaved"

    # Claude Code adapter (claude-agent-sdk): per-request model + timeout.
    claude_code_model: str = DEFAULT_CLAUDE_CODE_MODEL
    claude_code_timeout_s: float = Field(default=DEFAULT_CLAUDE_CODE_TIMEOUT_S, gt=0)

    # Whole-paper structured-output repair budget (ports §7.4).
    whole_paper_max_repairs: int = Field(default=2, ge=0)
