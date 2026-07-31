"""Claude Code whole-paper transcriber (architecture §3.2 and §3.6).

This adapter wraps the shared Claude Code infrastructure
(:mod:`scripts.infrastructure.ai.claude_code`) into the question-ingestion
:class:`WholePaperTranscriber` port. It is structurally symmetric with
:mod:`.opencode`: it drives
``Agent(model=ClaudeCodeModel(...), output_type=QuestionTranscriptionBundle).run()``
so structured-output validation + ``ModelRetry`` live in the Agent layer (symmetric
with OpenCode). The Model's ``request()`` only has to "make Claude behave like an
LLM": turn messages into assistant text + usage.

The provider transport (``claude_agent_sdk.query()``) and the PydanticAI ``Model``
bridge now live in shared infrastructure and are domain-free. This adapter owns the
ingestion-specific concerns: page-text reading, whole-paper prompt build, the Agent
output contract, artifact commit, and provider-neutral → domain failure mapping.

Why routing is verifiable here (and not for OpenCode): the OpenCode server binds the
model server-side and the per-request ``model_id`` never reaches the server, so it
must surface a routing failure; the Claude SDK binds ``model`` / ``permission_mode``
on every request, so a non-empty validating response is a real transcription — this
adapter never returns a routing failure.

Auth: the SDK checks ``ANTHROPIC_API_KEY`` first, then the CLI's stored credentials /
``CLAUDE_CODE_OAUTH_TOKEN``. No credential is invented or logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import yaml as _yaml

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
# Shared AI infrastructure (M1). Domain-free: query port + PydanticAI Model bridge.
from scripts.infrastructure.ai.claude_code.client import (
    ADAPTER_ID,
    ClaudeQueryPort,
    ClaudeTurn,
    RealClaudeQueryPort,
)
from scripts.infrastructure.ai.claude_code.pydantic_model import (
    ClaudeCodeModel as _InfraClaudeCodeModel,
)
from scripts.infrastructure.ai.contracts import ModelFailure, ModelFailureError


# Re-export under the historical names so existing tests/imports keep working until M8.
ClaudeCodeModel = _InfraClaudeCodeModel


def _map_failure(failure: ModelFailure) -> WholePaperFailure:
    """Map a provider-neutral :class:`ModelFailure` to ``WholePaperFailure``.

    Preserves the observable failure kinds of the pre-refactor adapter:
    ``timed_out`` → ``execution_timed_out``; ``protocol`` (empty/protocol) →
    ``invalid_structured_output``; everything else → ``transcriber_unavailable``.
    """

    kind = failure.kind
    if kind == "timed_out":
        domain_kind = "execution_timed_out"
    elif kind == "protocol":
        domain_kind = "invalid_structured_output"
    else:
        domain_kind = "transcriber_unavailable"
    return WholePaperFailure(
        adapter_id=ADAPTER_ID,
        kind=domain_kind,
        attempts=failure.attempts,
        detail=failure.detail,
    )


class _CcsError(Exception):
    """Internal control-flow exception carrying a structured WholePaperFailure.

    Retained as the adapter's intra-adapter control-flow carrier so the public
    ``transcribe``/``_run_agent`` shape is unchanged. It is raised only after mapping
    a :class:`ModelFailureError` (or a defensive exception) to a ``WholePaperFailure``.
    """

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure


class ClaudeCodeTranscriber:
    """:class:`WholePaperTranscriber` driving a PydanticAI ``Agent``.

    Structurally mirrors :class:`.opencode.OpencodeGlmTranscriber`: read ordered page
    text, build the shared whole-paper prompt, run the Agent with
    ``output_type=QuestionTranscriptionBundle``, commit the validated bundle. The only
    difference from the OpenCode adapter is the inner Model (``ClaudeCodeModel``) and
    therefore the host.
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
        model_obj = _InfraClaudeCodeModel(
            model_name=self.model,
            query_port=port,
            system_prompt=WHOLE_PAPER_SYSTEM_PROMPT,
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
        except ModelFailureError as exc:
            raise _CcsError(_map_failure(exc.failure))
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


_REAL_QUERY_PORT: ClaudeQueryPort = RealClaudeQueryPort()
