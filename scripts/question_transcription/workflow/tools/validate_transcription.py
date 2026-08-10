"""In-process ``validate_transcription`` MCP tool for the whole-paper transcriber.

The Claude Code transcriber route exposes this as a single constrained tool the
agent calls to validate its draft JSON against the authoritative
:class:`QuestionTranscriptionBundle` schema, instead of giving the agent a free
``Bash`` tool to run the validator itself (which induced long multi-turn
"write a script / run it / read it back" loops).

It is wired ONLY into the Claude Code path (architecture §3.2): the SDK's
``create_sdk_mcp_server`` builds an in-process MCP server (no subprocess, no
IPC) that the ``claude`` CLI can call as the ``validate_transcription`` tool.
The OpenCode path is untouched (it relies on PydanticAI's ``output_type``
structured-output validation + ``ModelRetry``).

``claude_agent_sdk`` is imported lazily inside :func:`build_validate_mcp_server`
so importing this module never loads the SDK (offline tests stay network-free),
mirroring :mod:`scripts.infrastructure.ai.claude_code.client`.
"""

from __future__ import annotations

from typing import Any


__all__ = ["build_validate_mcp_server", "validate_transcription_handler"]


async def validate_transcription_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Validate ``args["draft"]`` against ``QuestionTranscriptionBundle``.

    Returns an MCP tool-result dict: ``VALID`` + a short summary on success, or
    the full pydantic ``ValidationError`` text with ``is_error: True`` on failure.
    Callable directly from tests (no SDK required).
    """
    from scripts.question_transcription.contracts import (
        QuestionTranscriptionBundle,
    )
    from pydantic import ValidationError

    draft = args.get("draft")
    if not isinstance(draft, dict):
        return {
            "content": [{"type": "text", "text":
                "validate_transcription: 'draft' 必须是一个 JSON 对象。"}],
            "is_error": True,
        }
    try:
        bundle = QuestionTranscriptionBundle.model_validate(draft)
    except ValidationError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    n_sections = len(bundle.sections)
    n_questions = sum(len(s.questions) for s in bundle.sections)
    return {
        "content": [{"type": "text", "text":
            f"VALID — {n_sections} 个 section，{n_questions} 道题。"
            "请立即把校验通过的 draft JSON 作为最终回复输出。"}],
    }


def build_validate_mcp_server():
    """Build the in-process MCP server exposing ``validate_transcription``.

    Returns the ``McpSdkServerConfig`` produced by
    ``claude_agent_sdk.create_sdk_mcp_server``; pass it as one entry of
    ``ClaudeAgentOptions(mcp_servers={"validator": <this>}, ...)`` and list
    ``"validate_transcription"`` in ``allowed_tools``.
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    validate_transcription = tool(
        "validate_transcription",
        "校验整卷转录 JSON 是否符合 math_question_transcription/v1 schema。"
        "传入你拟输出的完整 JSON 对象（draft）；返回 VALID 表示通过，"
        "返回错误时按错误文本修正后再校验。",
        {"draft": dict},
    )(validate_transcription_handler)

    return create_sdk_mcp_server(
        "transcription-validator", tools=[validate_transcription]
    )
