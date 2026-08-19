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

import asyncio
import json
from typing import Any, Protocol

from ..contracts import ModelFailure, ModelFailureError, ModelFailureKind


__all__ = ["ClaudeTurn", "ClaudeQueryPort", "RealClaudeQueryPort", "real_run"]


ADAPTER_ID = "claude-code"


class ClaudeTurn:
    """Result of one SDK ``query()`` turn: assistant text + token usage."""

    __slots__ = (
        "assistant_text",
        "input_tokens",
        "output_tokens",
        "model_name",
        "session_id",
    )

    def __init__(
        self,
        *,
        assistant_text: str,
        input_tokens: int,
        output_tokens: int,
        model_name: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.assistant_text = assistant_text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model_name = model_name
        self.session_id = session_id


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
        max_turns: int = 1,
        mcp_servers: dict | None = None,
        effort: str | None = None,
        max_thinking_tokens: int | None = None,
        terminal_tool_name: str | None = None,
        terminal_tool_input_key: str | None = None,
        terminal_tool_success_marker: str | None = None,
    ) -> ClaudeTurn: ...


def _extract_tokens(usage: dict[str, Any] | None) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from a ``ResultMessage.usage`` dict."""

    if not isinstance(usage, dict):
        return 0, 0
    return (
        int(usage.get("input_tokens") or usage.get("inputTokens") or 0),
        int(usage.get("output_tokens") or usage.get("outputTokens") or 0),
    )


def _tool_response_text(response: Any) -> str:
    """Flatten an SDK PostToolUse response enough to detect a success marker."""

    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return "\n".join(
            _tool_response_text(value)
            for key, value in response.items()
            if key in {"content", "text", "result"}
        )
    if isinstance(response, list):
        return "\n".join(_tool_response_text(value) for value in response)
    return ""


def _tool_name_matches(actual: str, configured: str) -> bool:
    """Match an MCP short name against its SDK-qualified tool name."""

    return actual == configured or actual.endswith(f"__{configured}")


async def real_run(
    *,
    system_prompt: str,
    prompt: str,
    model: str,
    timeout_s: float,
    allowed_tools: list[str],
    permission_mode: str,
    max_turns: int = 1,
    mcp_servers: dict | None = None,
    effort: str | None = None,
    max_thinking_tokens: int | None = None,
    terminal_tool_name: str | None = None,
    terminal_tool_input_key: str | None = None,
    terminal_tool_success_marker: str | None = None,
) -> ClaudeTurn:
    """The production SDK turn: drive ``claude_agent_sdk.query()``.

    Lazily imported so offline tests never load the SDK. The only place in this
    package that touches ``claude_agent_sdk``.
    """

    try:
        from claude_agent_sdk import (  # type: ignore[import-not-found]
            AssistantMessage,
            ClaudeAgentOptions,
            HookMatcher,
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

    terminal_output: Any | None = None

    async def _stop_after_terminal_tool(
        hook_input: dict[str, Any],
        _tool_use_id: str | None,
        _context: Any,
    ) -> dict[str, Any]:
        """Stop before the model re-emits an already validated large payload."""

        nonlocal terminal_output
        if not terminal_tool_name or not terminal_tool_input_key:
            return {}
        actual_name = str(hook_input.get("tool_name") or "")
        if not _tool_name_matches(actual_name, terminal_tool_name):
            return {}
        response_text = _tool_response_text(hook_input.get("tool_response"))
        marker = terminal_tool_success_marker or ""
        if marker and marker not in response_text:
            return {}
        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict) or terminal_tool_input_key not in tool_input:
            return {}
        terminal_output = tool_input[terminal_tool_input_key]
        return {
            "continue_": False,
            "stopReason": "terminal tool accepted the final structured output",
        }

    hooks = {}
    if terminal_tool_name:
        hooks = {
            "PostToolUse": [
                HookMatcher(matcher=None, hooks=[_stop_after_terminal_tool])
            ]
        }

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,          # per-request: routing verifiable
        allowed_tools=allowed_tools,          # tools the agent may call (e.g. self-check)
        permission_mode=permission_mode,      # "acceptEdits" auto-approves tools headless
        max_turns=max_turns,                  # >1 lets the agent self-check then answer
        mcp_servers=mcp_servers or {},        # in-process MCP tools (e.g. validate_transcription)
        effort=effort,
        max_thinking_tokens=max_thinking_tokens,
        hooks=hooks,
    )

    try:
        # With max_turns>1 the agent may emit several AssistantMessages (e.g. tool-call
        # turns interleaved with prose like "let me check..."). Only the LAST
        # AssistantMessage carries the final JSON answer; earlier text turns would
        # pollute the output if concatenated. Track per-turn text and keep only the
        # most recent non-empty turn.
        last_turn_text: list[str] = []
        usage: dict[str, Any] | None = None
        actual_model: str | None = None
        session_id: str | None = None
        async with asyncio.timeout(timeout_s):
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    actual_model = str(getattr(message, "model", "") or "") or actual_model
                    session_id = getattr(message, "session_id", None) or session_id
                    turn_text = [
                        block.text for block in message.content
                        if isinstance(block, TextBlock) and block.text
                    ]
                    if turn_text:
                        last_turn_text = turn_text
                elif isinstance(message, ResultMessage):
                    # ResultMessage.usage is the authoritative aggregate
                    # (input/output); session_id lets callers correlate the local
                    # ~/.claude JSONL without timestamp guessing.
                    usage = message.usage
                    session_id = message.session_id or session_id
    except TimeoutError as exc:
        raise ModelFailureError(ModelFailure(
            provider=ADAPTER_ID, kind="timed_out",
            detail=f"claude-agent-sdk timed out after {timeout_s:g}s: {exc}",
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

    if terminal_output is not None:
        joined = json.dumps(terminal_output, ensure_ascii=False, separators=(",", ":"))
    else:
        joined = "\n".join(p for p in last_turn_text if p).strip()
    if not joined:
        raise ModelFailureError(ModelFailure(
            provider=ADAPTER_ID, kind="protocol",
            detail="assistant returned empty text",
        ))

    input_tokens, output_tokens = _extract_tokens(usage)
    return ClaudeTurn(
        assistant_text=joined,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_name=actual_model or model,
        session_id=session_id,
    )


class RealClaudeQueryPort:
    """The production :class:`ClaudeQueryPort`: wraps :func:`real_run` as a ``.run`` method.

    Both the Model and the adapter default to a shared instance of this class, so the
    production path and the injected-fake test path invoke the identical
    ``port.run(...)`` interface.
    """

    async def run(self, **kwargs: Any) -> ClaudeTurn:
        return await real_run(**kwargs)
