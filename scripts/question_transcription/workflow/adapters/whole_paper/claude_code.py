"""Claude Code whole-paper transcriber — compatibility shim (M2).

The real transcription logic now lives in
:class:`~.structured_transcriber.StructuredWholePaperTranscriber`, shared with the
OpenCode path. This module keeps the historical public API (``ClaudeCodeTranscriber``,
``ClaudeCodeModel``, ``ClaudeTurn``, ``ClaudeQueryPort``, ``ADAPTER_ID``) so existing
callers and tests continue to work; it only binds the Claude Code infrastructure model
and hands it to the unified transcriber. It will be removed in M8 once all callers move
to the unified entry point.

Provider transport and the PydanticAI ``Model`` live in shared infrastructure
(:mod:`scripts.infrastructure.ai.claude_code`) and are domain-free.
"""

from __future__ import annotations

from pathlib import Path

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap for contracts)
from ...prompts.whole_paper import WHOLE_PAPER_SYSTEM_PROMPT
# Shared AI infrastructure (M1). Domain-free: query port + PydanticAI Model bridge.
from scripts.infrastructure.ai.claude_code.client import (
    ADAPTER_ID,
    ClaudeQueryPort,
    ClaudeTurn,
)
from scripts.infrastructure.ai.claude_code.pydantic_model import (
    ClaudeCodeModel as _InfraClaudeCodeModel,
)
from .structured_transcriber import StructuredWholePaperTranscriber


# Re-export under the historical names so existing tests/imports keep working until M8.
ClaudeCodeModel = _InfraClaudeCodeModel


class ClaudeCodeTranscriber:
    """:class:`WholePaperTranscriber` backed by Claude Code.

    Compatibility wrapper: binds the Claude Code infrastructure model and delegates to
    :class:`StructuredWholePaperTranscriber`. Behaviour is identical to the pre-M2
    standalone adapter (including the cache-key shape).
    """

    def __init__(
        self,
        *,
        model: str,
        store,
        timeout_s: float = 300.0,
        cache_dir: Path | None = None,
        permission_mode: str = "default",
        query_port: ClaudeQueryPort | None = None,
        **_kwargs,
    ) -> None:
        bound_model = _InfraClaudeCodeModel(
            model_name=model,
            query_port=query_port,
            system_prompt=WHOLE_PAPER_SYSTEM_PROMPT,
            timeout_s=timeout_s,
            permission_mode=permission_mode,
        )
        self._inner = StructuredWholePaperTranscriber(
            adapter_id=ADAPTER_ID,
            model_name=model,
            bound_model=bound_model,
            store=store,
            agent_name="whole-paper-transcriber-claude-code",
            cache_dir=cache_dir if cache_dir is not None else store.layout.cache_dir,
        )

    def transcribe(self, request):
        return self._inner.transcribe(request)

    def repair_structured_output(self, previous_execution_id, validation_errors):
        return self._inner.repair_structured_output(previous_execution_id, validation_errors)
