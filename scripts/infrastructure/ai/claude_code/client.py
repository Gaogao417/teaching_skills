"""Claude Agent SDK query boundary (architecture §3.2, M1.4).

Defines the injectable effect that runs one stateless ``claude_agent_sdk.query()``
turn and the production implementation. Only :func:`_real_run` imports
``claude_agent_sdk`` (lazily), so importing this module never loads the SDK and the
offline suite stays network-free.

This module is domain-free. It does not know that the prompt is a math question; it
returns assistant text + token usage (:class:`ClaudeTurn`), or raises a
provider-neutral :class:`~scripts.infrastructure.ai.contracts.ModelFailureError`.

Why routing is verifiable here (and not for OpenCode): the OpenCode server binds the
model server-side and the per-request ``model_id`` never reaches the server, so it
must surface a routing failure; the Claude SDK binds ``model`` /
``permission_mode`` on every request, so a non-empty validating response is real.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..contracts import ModelFailure, ModelFailureError, ModelFailureKind


__all__ = ["ClaudeTurn", "ClaudeQueryPort", "RealClaudeQueryPort", "real_run"]


ADAPTER_ID = "claude-code"


class ClaudeTurn:
    """Result of one SDK ``query()`` turn: assistant text + token usage."""

    __slots__ = ("assistant_text", "input_tokens", "output_tokens")

    def __init__(self, *, assistant_text: str, input_tokens: int, output_tokens: int) -> None:
        self.assistant_text = assistant_text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class ClaudeQueryPort(Protocol):
    """Run one stateless Claude Code agent turn.

    ``system_prompt`` and ``prompt`` are sent as the SDK ``options.system_prompt`` and
    the ``query(prompt=...)`` argument respectively (the SDK is stateless and accepts
    only user turns). Production resolves to :class:`RealClaudeQueryPort`; tests inject
    a fake and never import the SDK.
    """

    async def run(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        timeout_s: float,
        allowed_tools: list[str],
        permission_mode: str,
    ) -> ClaudeTurn: ...


def _extract_tokens(usage: dict[str, Any] | None) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from a ``ResultMessage.usage`` dict."""

    if not isinstance(usage, dict):
        return 0, 0
    return (
        int(usage.get("input_tokens") or usage.get("inputTokens") or 0),
        int(usage.get("output_tokens") or usage.get("outputTokens") or 0),
    )


async def real_run(
    *,
    system_prompt: str,
    prompt: str,
    model: str,
    timeout_s: float,
    allowed_tools: list[str],
    permission_mode: str,
) -> ClaudeTurn:
    """The production SDK turn: drive ``claude_agent_sdk.query()``.

    Lazily imported so offline tests never load the SDK. The only place in this
    package that touches ``claude_agent_sdk``.
    """

    try:
        from claude_agent_sdk import (  # type: ignore[import-not-found]
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )
    except ImportError as exc:
        raise ModelFailureError(ModelFailure(
            provider=ADAPTER_ID, kind="unavailable",
            detail=(
                f"claude-agent-sdk not importable: {exc}. Install with "
                "./.venv/bin/python -m pip install claude-agent-sdk and ensure the "
                "`claude` CLI is on PATH."
            ),
        ))

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,          # per-request: routing verifiable
        allowed_tools=allowed_tools,          # [] — pure text, no tools
        permission_mode=permission_mode,      # "default"
        max_turns=1,                          # single assistant turn
    )

    try:
        text_parts: list[str] = []
        usage: dict[str, Any] | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
            elif isinstance(message, ResultMessage):
                # ResultMessage.usage is the authoritative aggregate (input/output).
                usage = message.usage
    except TimeoutError as exc:
        raise ModelFailureError(ModelFailure(
            provider=ADAPTER_ID, kind="timed_out",
            detail=f"claude-agent-sdk timed out: {exc}",
        ))
    except ModelFailureError:
        raise
    except Exception as exc:
        low = str(exc).lower()
        kind: ModelFailureKind = "timed_out" if "timeout" in low else "unavailable"
        raise ModelFailureError(ModelFailure(
            provider=ADAPTER_ID, kind=kind,
            detail=f"{type(exc).__name__}: {exc}",
        ))

    joined = "\n".join(p for p in text_parts if p).strip()
    if not joined:
        raise ModelFailureError(ModelFailure(
            provider=ADAPTER_ID, kind="protocol",
            detail="assistant returned empty text",
        ))

    input_tokens, output_tokens = _extract_tokens(usage)
    return ClaudeTurn(
        assistant_text=joined, input_tokens=input_tokens, output_tokens=output_tokens
    )


class RealClaudeQueryPort:
    """The production :class:`ClaudeQueryPort`: wraps :func:`real_run` as a ``.run`` method.

    Both the Model and the adapter default to a shared instance of this class, so the
    production path and the injected-fake test path invoke the identical
    ``port.run(...)`` interface.
    """

    async def run(self, **kwargs: Any) -> ClaudeTurn:
        return await real_run(**kwargs)
