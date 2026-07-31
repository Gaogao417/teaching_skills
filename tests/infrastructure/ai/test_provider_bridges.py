"""Offline tests for the shared AI infrastructure (architecture §3.2, M1.6).

These tests inject a fake transport (httpx for OpenCode, a fake query port for Claude
Code) and assert the provider-neutral boundary:

- the OpenCode client performs the two-step session/message POST and classifies HTTP
  errors into provider-neutral ``ModelFailure`` kinds;
- the Claude client port surfaces SDK/transport failures as ``ModelFailureError``;
- both PydanticAI ``Model`` bridges are concrete, ``provider=None``, and turn messages
  into a ``ModelResponse`` carrying assistant text + usage;
- the bridges stay domain-free: a small NON-math pydantic output schema driven through
  a PydanticAI ``Agent`` round-trips, proving the infrastructure does not depend on
  the question-ingestion domain.

No network, no API key, no ``claude_agent_sdk`` import.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai.models import ModelRequestParameters

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.infrastructure.ai.contracts import ModelFailure, ModelFailureError
from scripts.infrastructure.ai.claude_code.client import (
    ADAPTER_ID as CLAUDE_ID,
    ClaudeTurn,
)
from scripts.infrastructure.ai.claude_code.pydantic_model import ClaudeCodeModel
from scripts.infrastructure.ai.opencode.client import (
    OpencodeClient,
    extract_opencode_text,
)
from scripts.infrastructure.ai.opencode.pydantic_model import OpencodeModel


def _mrp() -> ModelRequestParameters:
    """A default ``ModelRequestParameters`` for direct ``request()`` calls."""

    return ModelRequestParameters()


# --------------------------------------------------------------------------- #
# OpenCode client transport
# --------------------------------------------------------------------------- #


class _QueuedHttpClient:
    """Minimal httpx-like client with queued message responses + recorded posts."""

    def __init__(self, message_responses: list[str], *, session_status=200):
        self.message_responses = list(message_responses)
        self.posts: list[tuple[str, dict]] = []
        self.session_status = session_status
        self._sessions = 0

    def post(self, url: str, json: dict):
        self.posts.append((url, json))
        if url.endswith("/session"):
            self._sessions += 1
            if self.session_status != 200:
                return httpx.Response(self.session_status, text="boom")
            return httpx.Response(200, json={"id": f"session-{self._sessions}"})
        response = self.message_responses.pop(0)
        return httpx.Response(200, json={"parts": [{"type": "text", "text": response}]})


def test_opencode_client_does_session_then_message_two_step():
    client = _QueuedHttpClient(["hello world"])
    transport = OpencodeClient(
        server_url="http://127.0.0.1:4096", agent_type="build", http_client=client
    )

    raw = transport.send_message("a prompt")

    assert extract_opencode_text(raw) == "hello world"
    assert len(client.posts) == 2
    assert client.posts[0][0].endswith("/session")
    assert client.posts[1][0].endswith("/message")
    assert client.posts[1][1]["agent"] == "build"
    assert client.posts[1][1]["parts"][0]["text"] == "a prompt"
    assert client.posts[1][1]["messageID"].startswith("msg_")


def test_opencode_client_classifies_http_errors_as_model_failure():
    client = _QueuedHttpClient([], session_status=503)
    transport = OpencodeClient(
        server_url="http://127.0.0.1:4096", agent_type="build", http_client=client
    )

    with pytest.raises(ModelFailureError) as exc:
        transport.send_message("prompt")

    assert exc.value.failure.provider == "opencode"
    assert exc.value.failure.kind == "unavailable"
    assert "503" in exc.value.failure.detail


def test_opencode_client_rate_limit_and_auth_kinds():
    for status, expected in [(401, "authentication"), (429, "rate_limited"), (500, "unavailable")]:
        client = _QueuedHttpClient([], session_status=status)
        transport = OpencodeClient(
            server_url="http://x", agent_type="build", http_client=client
        )
        with pytest.raises(ModelFailureError) as exc:
            transport.send_message("p")
        assert exc.value.failure.kind == expected, status


# --------------------------------------------------------------------------- #
# OpenCode PydanticAI model bridge (domain-free)
# --------------------------------------------------------------------------- #


class _DummyPart:
    """Minimal stand-in for a PydanticAI message part carrying text content."""

    def __init__(self, content: str, part_type: str) -> None:
        self.content = content
        self._part_type = part_type

    @property
    def __class__(self):  # make type(part).__name__ return the configured name
        cls = type(self)
        cls.__name__ = self._part_type
        return cls


class _DummyMessage:
    """Minimal stand-in for a PydanticAI ModelMessage with one part."""

    def __init__(self, text: str, *, part_type: str = "UserPromptPart") -> None:
        self.parts = [_DummyPart(text, part_type)]


def _opencode_model(client: _QueuedHttpClient) -> OpencodeModel:
    return OpencodeModel(
        model_name="glm-5.2",
        client=OpencodeClient(server_url="http://x", agent_type="build", http_client=client),
    )


def test_opencode_model_is_concrete_and_providerless():
    from pydantic_ai.models import Model

    model = OpencodeModel(model_name="glm-5.2", send_message=lambda _: {})
    assert issubclass(OpencodeModel, Model)
    assert not OpencodeModel.__abstractmethods__
    assert model.provider is None
    assert model.model_name == "glm-5.2"
    assert model.system == "opencode"


def test_opencode_model_request_returns_text_response():
    model = _opencode_model(_QueuedHttpClient(["assistant answer"]))

    response = asyncio.run(model.request([_DummyMessage("hi")], None, _mrp()))

    assert response.parts[0].content == "assistant answer"
    assert response.model_name == "glm-5.2"
    assert response.provider_name == "opencode"


def test_opencode_model_empty_text_is_protocol_failure():
    model = _opencode_model(_QueuedHttpClient(["   "]))

    with pytest.raises(ModelFailureError) as exc:
        asyncio.run(model.request([_DummyMessage("hi")], None, _mrp()))

    assert exc.value.failure.kind == "protocol"


# --------------------------------------------------------------------------- #
# Claude client port + PydanticAI model bridge (domain-free)
# --------------------------------------------------------------------------- #


class _FakeClaudePort:
    async def run(self, **kwargs):
        return ClaudeTurn(assistant_text=kwargs.get("prompt", ""), input_tokens=2, output_tokens=3)


def _raising_port(error: Exception):
    class _Port:
        async def run(self, **kwargs):
            raise error
    return _Port()


def test_claude_model_is_concrete_and_providerless():
    from pydantic_ai.models import Model

    model = ClaudeCodeModel(model_name="sonnet", system_prompt="s")
    assert issubclass(ClaudeCodeModel, Model)
    assert not ClaudeCodeModel.__abstractmethods__
    assert model.provider is None
    assert model.system == "claude-code"


def test_claude_model_request_carries_assistant_text_and_usage():
    model = ClaudeCodeModel(
        model_name="sonnet", query_port=_FakeClaudePort(), system_prompt="sys"
    )

    response = asyncio.run(model.request([_DummyMessage("hello")], None, _mrp()))

    # The bridge flattens the message to a role-prefixed prompt for the stateless SDK.
    assert response.parts[0].content == "[user]\nhello"
    assert response.usage.input_tokens == 2
    assert response.usage.output_tokens == 3
    assert response.provider_name == "claude-code"


def test_claude_model_surfaces_model_failure_error():
    port = _raising_port(ModelFailureError(ModelFailure(
        provider=CLAUDE_ID, kind="timed_out", detail="slow",
    )))
    model = ClaudeCodeModel(model_name="sonnet", query_port=port)

    with pytest.raises(ModelFailureError) as exc:
        asyncio.run(model.request([_DummyMessage("hi")], None, _mrp()))

    assert exc.value.failure.kind == "timed_out"


# --------------------------------------------------------------------------- #
# Domain-free proof: a non-math pydantic output round-trips through the Agent loop
# --------------------------------------------------------------------------- #


class ColorFact(BaseModel):
    """A deliberately non-math output schema: the infrastructure must not care."""

    color: str
    hex_code: str


def test_agent_roundtrip_with_non_math_schema_via_opencode():
    """The OpenCode bridge + PydanticAI Agent validate a NON-math pydantic model.

    This proves shared infrastructure is domain-free: it does not import or require
    ``QuestionTranscriptionBundle``.
    """

    from pydantic_ai import Agent

    payload = json.dumps({"color": "azure", "hex_code": "#007FFF"})
    model = _opencode_model(_QueuedHttpClient([payload]))
    agent = Agent(model=model, output_type=ColorFact, retries=1, name="color-fact")

    result = asyncio.run(agent.run("Give me an azure fact"))

    assert isinstance(result.output, ColorFact)
    assert result.output.color == "azure"
    assert result.output.hex_code == "#007FFF"
