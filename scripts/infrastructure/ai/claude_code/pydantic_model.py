"""Claude Code PydanticAI ``Model`` bridge (architecture §3.2, M1.5).

:class:`ClaudeCodeModel` subclasses the installed PydanticAI 2.x :class:`Model` with
``provider=None`` and turns one ``claude_agent_sdk.query()`` turn (via the injectable
:class:`~scripts.infrastructure.ai.claude_code.client.ClaudeQueryPort`) into the
``request()`` member the Agent calls. Structured-output validation + ``ModelRetry``
live in the Agent layer — exactly as for the OpenCode bridge — so the Model's
``request()`` only has to "make Claude behave like an LLM": turn messages into
assistant text + usage.

The bridge is domain-free: ``system_prompt`` is a caller-supplied constructor
parameter (the ingestion transcriber passes its math-question system prompt), never a
hard-coded domain default. Failures surface as provider-neutral
:class:`~scripts.infrastructure.ai.contracts.ModelFailureError`.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models import Model, check_allow_model_requests
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from ..contracts import ModelFailureError
from .client import ADAPTER_ID, ClaudeQueryPort, ClaudeTurn, RealClaudeQueryPort


__all__ = ["ClaudeCodeModel", "convert_messages_to_prompt"]


def convert_messages_to_prompt(messages: list[Any]) -> str:
    """Flatten PydanticAI ``ModelMessage`` into a single prompt string.

    The Claude SDK ``query()`` is **stateless**: its streaming input only accepts
    ``type:"user"`` turns (no assistant turns), and ``options`` carries no history.
    So we cannot replay a prior assistant turn as an assistant turn. Instead we render
    the whole conversation as one ordered text transcript (role-prefixed) — the only
    faithful mapping for a stateless SDK. The Agent's retry path re-enters ``request``
    with ``[user, assistant-text, retry-prompt(user)]``, which this flattens in order.

    Part roles follow the OpenCode bridge (system/user/assistant), with tool/retry
    parts folded in as user content (they are instructions to the model).
    """

    blocks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, list):
                fragments: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        fragments.append(item)
                    elif isinstance(getattr(item, "text", None), str):
                        fragments.append(item.text)
                    elif isinstance(item, dict):
                        fragments.append(json.dumps(item, ensure_ascii=False))
                    else:
                        fragments.append(str(item))
                content = "\n".join(fragments)
            if not isinstance(content, str) or not content.strip():
                continue
            part_type = type(part).__name__
            if "System" in part_type or "Instruction" in part_type:
                role = "system"
            elif "User" in part_type:
                role = "user"
            elif "Text" in part_type:
                role = "assistant"
            else:
                # RetryPrompt / ToolReturn / ToolCall etc. → model-facing instruction
                role = "user"
            blocks.append(f"[{role}]\n{content.strip()}")
    return "\n\n".join(blocks)


class ClaudeCodeModel(Model):
    """PydanticAI ``Model`` backed by ``claude_agent_sdk.query``.

    Mirrors :class:`~scripts.infrastructure.ai.opencode.pydantic_model.OpencodeModel`:
    implements the three abstract members (``model_name`` / ``system`` / ``request``).
    ``request()`` is the only path the Agent uses for ``output_type`` validation;
    ``request_stream`` is inherited from ``Model`` (not overridden).
    """

    def __init__(
        self,
        *,
        model_name: str,
        query_port: ClaudeQueryPort | None = None,
        system_prompt: str = "",
        timeout_s: float = 300.0,
        allowed_tools: list[str] | None = None,
        permission_mode: str = "default",
        settings: ModelSettings | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self._model_name = model_name
        # None → the production SDK port (resolved here so request() always has a port).
        self._query_port = query_port or _REAL_QUERY_PORT
        self._system_prompt = system_prompt
        self._timeout_s = timeout_s
        self._allowed_tools = list(allowed_tools or [])
        self._permission_mode = permission_mode

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return "claude-code"

    async def request(
        self,
        messages: list[Any],
        model_settings: ModelSettings | None,
        model_request_parameters: Any,
    ) -> ModelResponse:
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        check_allow_model_requests()

        prompt = convert_messages_to_prompt(messages) or ""

        turn: ClaudeTurn = await self._query_port.run(
            system_prompt=self._system_prompt,
            prompt=prompt,
            model=self._model_name,
            timeout_s=self._timeout_s,
            allowed_tools=self._allowed_tools,
            permission_mode=self._permission_mode,
        )

        usage = RequestUsage(
            input_tokens=turn.input_tokens, output_tokens=turn.output_tokens
        )
        return ModelResponse(
            parts=[TextPart(content=turn.assistant_text)],
            usage=usage,
            model_name=self._model_name,
            provider_name="claude-code",
        )


_REAL_QUERY_PORT: ClaudeQueryPort = RealClaudeQueryPort()
