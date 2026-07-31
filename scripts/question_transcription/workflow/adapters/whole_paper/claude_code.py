"""Claude Code whole-paper transcriber — Claude Code as a PydanticAI Model (ports §7.2).

Resolves the implementation-plan §11 freeze #5 ("Claude Code 非交互执行的权限和输出协议").

This adapter is **structurally symmetric** with :mod:`.opencode`: it exposes Claude Code
as a PydanticAI :class:`~pydantic_ai.models.Model` (:class:`ClaudeCodeModel`, the
sibling of OpenCode's ``OpencodeModel``) and the adapter drives
``Agent(model=ClaudeCodeModel(...), output_type=QuestionTranscriptionBundle).run(prompt)``.
Structured-output validation + ``ModelRetry`` live in the Agent layer — exactly as they
do for the OpenCode adapter — so the Model's ``request()`` only has to "make Claude
behave like an LLM": turn messages into assistant text + usage.

Why routing is verifiable here (and not for OpenCode): the OpenCode server binds the
model server-side in ``~/.config/opencode/opencode.json`` and the per-request
``model_id`` never reaches the server (§7.2 GAP), so it must surface
``routing_unverified``. The Claude SDK binds ``model`` / ``permission_mode`` on every
request, so a non-empty validating response is a real transcription — this adapter
never returns ``routing_unverified``.

Auth: the SDK checks ``ANTHROPIC_API_KEY`` first, then the CLI's stored credentials /
``CLAUDE_CODE_OAUTH_TOKEN``. No credential is invented or logged.

Layout:
- :class:`ClaudeQueryPort` — injectable effect that runs one SDK ``query()`` turn.
  Tests inject a fake; production resolves to :func:`_real_query` (the only place that
  imports ``claude_agent_sdk``).
- :class:`ClaudeCodeModel` — ``pydantic_ai.models.Model`` subclass (sibling of
  ``OpencodeModel``). ``request()`` flattens messages, calls the port, returns
  ``ModelResponse(parts=[TextPart], usage)``.
- :class:`ClaudeCodeTranscriber` — :class:`WholePaperTranscriber`; structurally mirrors
  ``OpencodeGlmTranscriber``: ordered pages → prompt → ``agent.run`` → commit bundle.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

# pydantic_ai is always installed in the repo venv (it is NOT the lazy-imported SDK).
# Importing at module scope lets ClaudeCodeModel subclass Model — same pattern as
# OpencodeModel. Only claude_agent_sdk (in _real_query) stays lazy-imported so offline
# tests never load it.
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models import Model, check_allow_model_requests
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap for contracts)
from ...contracts import (
    ArtifactRef,
    WholePaperFailure,
    WholePaperTranscription,
)
from ...prompts.whole_paper import (
    WHOLE_PAPER_PROMPT_VERSION,
    WHOLE_PAPER_SYSTEM_PROMPT,
    build_user_prompt,
)


ADAPTER_ID = "claude-code"


class _CcsError(Exception):
    """Internal control-flow exception carrying a structured WholePaperFailure."""

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure


# --------------------------------------------------------------------------- #
# Port: one SDK turn (injectable; only _real_query imports claude_agent_sdk)
# --------------------------------------------------------------------------- #


class ClaudeTurn:
    """Result of one SDK ``query()`` turn: assistant text + token usage."""

    __slots__ = ("assistant_text", "input_tokens", "output_tokens")

    def __init__(self, *, assistant_text: str, input_tokens: int, output_tokens: int) -> None:
        self.assistant_text = assistant_text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class ClaudeQueryPort(Protocol):
    """Run one stateless Claude Code agent turn.

    ``system_prompt`` and ``prompt`` are sent as the SDK options.system_prompt and the
    ``query(prompt=...)`` argument respectively (the SDK is stateless and accepts only
    user turns — see module docstring). Production resolves to :func:`_real_query`;
    tests inject a fake and never import the SDK.
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


async def _real_run(
    *,
    system_prompt: str,
    prompt: str,
    model: str,
    timeout_s: float,
    allowed_tools: list[str],
    permission_mode: str,
) -> ClaudeTurn:
    """The production SDK turn: drive ``claude_agent_sdk.query()``.

    Lazily imported so offline tests never load the SDK. The only place in this module
    that touches ``claude_agent_sdk``.
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
        raise _CcsError(WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
            attempts=1,
            detail=(
                "claude-agent-sdk not importable: "
                f"{exc}. Install with ./.venv/bin/python -m pip install "
                "claude-agent-sdk and ensure the `claude` CLI is on PATH."
            ),
        ))

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,          # per-request: routing verifiable
        allowed_tools=allowed_tools,          # [] — pure transcription, no tools (§14.12)
        permission_mode=permission_mode,      # "default"
        max_turns=1,                          # single assistant turn; we want text, not a tool loop
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
                # ResultMessage.usage is the authoritative aggregate (input/output tokens).
                usage = message.usage
    except TimeoutError as exc:
        raise _CcsError(WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="execution_timed_out",
            attempts=1, detail=f"claude-agent-sdk timed out: {exc}",
        ))
    except _CcsError:
        raise
    except Exception as exc:
        raise _CcsError(WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
            attempts=1, detail=f"{type(exc).__name__}: {exc}",
        ))

    joined = "\n".join(p for p in text_parts if p).strip()
    if not joined:
        raise _CcsError(WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="invalid_structured_output",
            attempts=1, detail="assistant returned empty text",
        ))

    input_tokens, output_tokens = _extract_tokens(usage)
    return ClaudeTurn(
        assistant_text=joined, input_tokens=input_tokens, output_tokens=output_tokens
    )


class _RealClaudeQueryPort:
    """The production :class:`ClaudeQueryPort`: wraps :func:`_real_run` as a ``.run`` method.

    Both the Model and the adapter default to a shared instance of this class, so the
    production path and the injected-fake test path invoke the identical ``port.run(...)``
    interface.
    """

    async def run(self, **kwargs: Any) -> ClaudeTurn:
        return await _real_run(**kwargs)


_REAL_QUERY_PORT: ClaudeQueryPort = _RealClaudeQueryPort()


def _extract_tokens(usage: dict[str, Any] | None) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from a ResultMessage.usage dict."""

    if not isinstance(usage, dict):
        return 0, 0
    return (
        int(usage.get("input_tokens") or usage.get("inputTokens") or 0),
        int(usage.get("output_tokens") or usage.get("outputTokens") or 0),
    )


# --------------------------------------------------------------------------- #
# ClaudeCodeModel — pydantic_ai.Model subclass (sibling of OpencodeModel)
# --------------------------------------------------------------------------- #


def _convert_messages_to_prompt(messages: list[Any]) -> str:
    """Flatten PydanticAI ``ModelMessage`` into a single prompt string.

    The Claude SDK ``query()`` is **stateless**: its streaming input only accepts
    ``type:"user"`` turns (no assistant turns), and ``options`` carries no history.
    So we cannot replay a prior assistant turn as an assistant turn. Instead we render
    the whole conversation as one ordered text transcript (role-prefixed) — the only
    faithful mapping for a stateless SDK. The Agent's retry path re-enters ``request``
    with ``[user, assistant-text, retry-prompt(user)]``, which this flattens in order.

    Part roles follow ``OpencodeModel._convert_messages`` (system/user/assistant), with
    tool/retry parts folded in as user content (they are instructions to the model).
    """

    blocks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, list):
                # Some parts carry structured content; join string fragments.
                content = "\n".join(
                    getattr(c, "text", c) if not isinstance(c, str) else c
                    for c in content
                )
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

    Mirrors :class:`opencode_agent_server.opencode_model.OpencodeModel`: implements the
    three abstract members (``model_name`` / ``system`` / ``request``). ``request()``
    is the only path the Agent uses for ``output_type`` validation; ``request_stream``
    is inherited from ``Model`` (not overridden).
    """

    def __init__(
        self,
        *,
        model_name: str,
        query_port: ClaudeQueryPort | None = None,
        system_prompt: str = WHOLE_PAPER_SYSTEM_PROMPT,
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

        prompt = _convert_messages_to_prompt(messages) or ""

        try:
            turn = await self._query_port.run(
                system_prompt=self._system_prompt,
                prompt=prompt,
                model=self._model_name,
                timeout_s=self._timeout_s,
                allowed_tools=self._allowed_tools,
                permission_mode=self._permission_mode,
            )
        except _CcsError as exc:
            # Surface the structured failure out of the Model so the Agent / adapter can
            # translate it; pydantic_ai lets request() raise.
            raise

        usage = RequestUsage(
            input_tokens=turn.input_tokens, output_tokens=turn.output_tokens
        )
        return ModelResponse(
            parts=[TextPart(content=turn.assistant_text)],
            usage=usage,
            model_name=self._model_name,
            provider_name="claude-code",
        )


# --------------------------------------------------------------------------- #
# ClaudeCodeTranscriber — WholePaperTranscriber (mirrors OpencodeGlmTranscriber)
# --------------------------------------------------------------------------- #


class ClaudeCodeTranscriber:
    """:class:`WholePaperTranscriber` driving a PydanticAI ``Agent``.

    Structurally mirrors ``OpencodeGlmTranscriber``: read ordered page text, build the
    shared whole-paper prompt, run the Agent with ``output_type=QuestionTranscriptionBundle``,
    commit the validated bundle. The only difference from the OpenCode adapter is the
    inner Model (``ClaudeCodeModel``) and therefore the host.
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
        self.model = model
        self.store = store
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir or store.layout.cache_dir
        self.permission_mode = permission_mode
        # None → the real SDK query; tests inject a fake.
        self._query_port = query_port

    def transcribe(self, request):
        try:
            ordered = self._read_ordered_pages(request)
            user_prompt = build_user_prompt(
                paper_id=request.paper_id,
                source_archive=self._source_archive(request),
                ordered_pages=ordered,
            )
            bundle = self._run_agent(user_prompt, request.paper_id)
        except _CcsError as exc:
            return None, exc.failure
        except Exception as exc:  # pragma: no cover - defensive
            return None, WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
                attempts=1, detail=f"{type(exc).__name__}: {exc}",
            )

        import yaml as _yaml

        ref = self.store.commit_text(
            "structured/transcription.yaml",
            _yaml.safe_dump(
                bundle.model_dump(by_alias=True, exclude_none=True, mode="json"),
                allow_unicode=True,
                sort_keys=False,
            ),
            "math_question_transcription/v1",
        )
        return (
            WholePaperTranscription(
                transcription=ref,
                issues=None,
                execution_id=self._execution_id(ordered),
                model=self.model,
                prompt_version=WHOLE_PAPER_PROMPT_VERSION,
            ),
            None,
        )

    def repair_structured_output(self, previous_execution_id, validation_errors):
        # Schema repair is delegated to re-transcribe, matching OpencodeGlmTranscriber
        # (ports §7.4): each Claude SDK query is a fresh stateless session, and the
        # Agent's own ModelRetry already exhausted its in-run budget before we get here.
        return None, WholePaperFailure(
            adapter_id=ADAPTER_ID,
            kind="invalid_structured_output",
            attempts=1,
            execution_id=previous_execution_id,
            detail="repair delegated to re-transcribe",
        )

    # -- internals -------------------------------------------------------- #

    def _read_ordered_pages(self, request):
        pages = []
        for extract in request.ordered_page_texts:
            text_ref = (
                extract.artifact.text
                if hasattr(extract, "artifact")
                else extract["artifact"]["text"]
            )
            ref = (
                ArtifactRef.model_validate(text_ref)
                if isinstance(text_ref, dict)
                else text_ref
            )
            page_number = (
                extract.artifact.page_number
                if hasattr(extract, "artifact")
                else extract["artifact"]["page_number"]
            )
            pages.append((page_number, self.store.read_text(ref)))
        return pages

    def _source_archive(self, request) -> str:
        manifest = request.source_manifest
        if manifest is None:
            return ""
        ref = (
            manifest if isinstance(manifest, ArtifactRef)
            else ArtifactRef.model_validate(manifest)
        )
        try:
            data = self.store.read_yaml(ref)
            return str(data.get("source_archive") or "")
        except Exception:
            return ""

    def _execution_id(self, ordered) -> str:
        return hashlib.sha256(
            "|".join(text for _, text in ordered).encode("utf-8")
        ).hexdigest()[:16]

    def _run_agent(self, user_prompt: str, paper_id: str):
        """Build the Agent and run it; return a validated ``QuestionTranscriptionBundle``."""

        cache_path = self.cache_dir / f"{self._cache_key(user_prompt)}.json"
        if cache_path.exists():
            from scripts.question_transcription.contracts import (
                QuestionTranscriptionBundle,
            )

            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return QuestionTranscriptionBundle.model_validate(cached["bundle"])

        port = self._query_port or _REAL_QUERY_PORT
        model_obj = ClaudeCodeModel(
            model_name=self.model,
            query_port=port,
            timeout_s=self.timeout_s,
            permission_mode=self.permission_mode,
        )

        from pydantic_ai import Agent
        from scripts.question_transcription.contracts import (
            QuestionTranscriptionBundle,
        )

        agent = Agent(
            model=model_obj,
            output_type=QuestionTranscriptionBundle,
            instructions=WHOLE_PAPER_SYSTEM_PROMPT,
            retries=1,
            name="whole-paper-transcriber-claude-code",
        )

        try:
            result = asyncio.run(agent.run(user_prompt))
        except _CcsError:
            raise
        except Exception as exc:
            # PydanticAI wraps model/output failures (e.g. ValidationError on the
            # final turn after retries) — surface as invalid_structured_output.
            raise _CcsError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="invalid_structured_output",
                attempts=1, detail=f"agent.run failed: {type(exc).__name__}: {exc}",
            ))

        bundle = result.output
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {"bundle": bundle.model_dump(by_alias=True, mode="json")},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        tmp.replace(cache_path)
        return bundle

    def _cache_key(self, user_prompt: str) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "adapter": ADAPTER_ID,
                    "model": self.model,
                    "prompt_version": WHOLE_PAPER_PROMPT_VERSION,
                    "user_prompt_sha256": hashlib.sha256(
                        user_prompt.encode("utf-8")
                    ).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
