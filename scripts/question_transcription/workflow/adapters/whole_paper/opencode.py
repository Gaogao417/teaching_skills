"""OpenCode glm-5.2 whole-paper transcriber — compatibility shim (M2).

The real transcription logic now lives in
:class:`~.structured_transcriber.StructuredWholePaperTranscriber`, shared with the
Claude Code path. This module keeps the historical public API
(``OpencodeGlmTranscriber``, ``OpencodeModel``, ``ADAPTER_ID``) so existing callers and
tests continue to work; it only binds the OpenCode infrastructure model and hands it
to the unified transcriber. It will be removed in M8 once all callers move to the
unified entry point.

Provider transport and the PydanticAI ``Model`` live in shared infrastructure
(:mod:`scripts.infrastructure.ai.opencode`) and are domain-free.
"""

from __future__ import annotations

from pathlib import Path

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap for contracts)
# Shared AI infrastructure (M1). Domain-free: client + PydanticAI Model bridge.
from scripts.infrastructure.ai.opencode.client import OpencodeClient
from scripts.infrastructure.ai.opencode.pydantic_model import (
    OpencodeModel as _InfraOpencodeModel,
)
from .structured_transcriber import StructuredWholePaperTranscriber


ADAPTER_ID = "opencode"

# Re-export under the historical name so existing tests/imports keep working until M8.
OpencodeModel = _InfraOpencodeModel


class OpencodeGlmTranscriber:
    """:class:`WholePaperTranscriber` backed by the OpenCode server (glm-5.2).

    Compatibility wrapper: binds the OpenCode infrastructure model and delegates to
    :class:`StructuredWholePaperTranscriber`. Behaviour is identical to the
    pre-M2 standalone adapter.
    """

    def __init__(self, *, model: str, server_url: str, agent_type: str, store,
                 timeout_s: float = 180.0, cache_dir=None, http_client=None) -> None:
        client = OpencodeClient(
            server_url=server_url,
            agent_type=agent_type,
            timeout_s=timeout_s,
            http_client=http_client,
        )
        bound_model = _InfraOpencodeModel(model_name=model, client=client)
        self._inner = StructuredWholePaperTranscriber(
            adapter_id=ADAPTER_ID,
            model_name=model,
            bound_model=bound_model,
            store=store,
            agent_name="whole-paper-transcriber-opencode",
            cache_dir=cache_dir if cache_dir is not None else store.layout.cache_dir,
            # Preserve the pre-M2 OpenCode cache partitioning by agent_type.
            cache_key_extras={"agent_type": agent_type},
        )

    def transcribe(self, request):
        return self._inner.transcribe(request)

    def repair_structured_output(self, previous_execution_id, validation_errors):
        return self._inner.repair_structured_output(previous_execution_id, validation_errors)
