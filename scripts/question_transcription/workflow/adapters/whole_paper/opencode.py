"""OpenCode glm-5.2 whole-paper transcriber.

This adapter wraps the shared OpenCode infrastructure
(:mod:`scripts.infrastructure.ai.opencode`) into the question-ingestion
:class:`WholePaperTranscriber` port. It owns the ingestion-specific concerns:

- reading ordered page text from the artifact store;
- building the whole-paper prompt for the chosen ``PaperLayout``;
- driving the PydanticAI ``Agent(output_type=QuestionTranscriptionBundle)`` so
  structured-output validation and ``ModelRetry`` are symmetric with Claude Code;
- committing the transcription artifact;
- mapping provider-neutral :class:`ModelFailure` into ``WholePaperFailure``.

It does NOT select the OpenCode server or model — that is bootstrap's job. The
provider transport and the PydanticAI ``Model`` bridge live in shared infrastructure
and are domain-free.

Model binding: the OpenCode server selects the model from its server-side config
(``~/.config/opencode/opencode.json``); the per-request model is not propagated by the
old opencode-agent provider. So this adapter relies on the server config binding
glm-5.2 (verified by the live canary asserting a validated bundle).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import yaml

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
# Shared AI infrastructure (M1). Domain-free: client + PydanticAI Model bridge.
from scripts.infrastructure.ai.contracts import ModelFailure, ModelFailureError
from scripts.infrastructure.ai.opencode.client import OpencodeClient
from scripts.infrastructure.ai.opencode.pydantic_model import (
    OpencodeModel as _InfraOpencodeModel,
)


ADAPTER_ID = "opencode"

# Re-export under the historical name so existing tests/imports keep working until M8.
OpencodeModel = _InfraOpencodeModel


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


class OpencodeGlmTranscriber:
    """:class:`WholePaperTranscriber` backed by the OpenCode server (glm-5.2).

    Self-contained at the ingestion layer: the server's session/message API transport
    and the PydanticAI ``Model`` live in shared infrastructure.
    """

    def __init__(self, *, model: str, server_url: str, agent_type: str, store,
                 timeout_s: float = 180.0, cache_dir=None, http_client=None) -> None:
        self.model = model
        self.server_url = server_url.rstrip("/")
        self.agent_type = agent_type
        self.store = store
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir or (store.layout.cache_dir)
        self.http_client = http_client  # injectable for tests

    # -- WholePaperTranscriber -------------------------------------------- #

    def transcribe(self, request):
        try:
            ordered = self._read_ordered_pages(request)
            mode = getattr(request, "prompt_mode", "interleaved") or "interleaved"
            solution_raw = getattr(request, "solution_page_texts", None) or []
            if mode == "separated" and solution_raw:
                solution = self._read_ordered_pages_from(solution_raw)
                user_prompt = build_user_prompt(
                    paper_id=request.paper_id,
                    source_archive=self._source_archive(request),
                    question_pages=ordered,
                    solution_pages=solution,
                    mode="separated",
                )
            else:
                user_prompt = build_user_prompt(
                    paper_id=request.paper_id,
                    source_archive=self._source_archive(request),
                    ordered_pages=ordered,
                    mode="interleaved",
                )
            bundle = self._run_agent(user_prompt)
        except _OpcError as exc:
            return None, exc.failure
        except Exception as exc:  # pragma: no cover - defensive
            return None, WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
                attempts=1, detail=f"{type(exc).__name__}: {exc}",
            )
        ref = self.store.commit_text(
            "structured/transcription.yaml",
            yaml.safe_dump(bundle.model_dump(by_alias=True, exclude_none=True, mode="json"),
                           allow_unicode=True, sort_keys=False),
            "math_question_transcription/v1",
        )
        return (
            WholePaperTranscription(
                transcription=ref, issues=None,
                execution_id=self._execution_id(ordered),
                model=self.model, prompt_version=WHOLE_PAPER_PROMPT_VERSION,
            ),
            None,
        )

    def repair_structured_output(self, previous_execution_id, validation_errors):
        return None, WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="invalid_structured_output",
            attempts=1, execution_id=previous_execution_id,
            detail="repair delegated to re-transcribe",
        )

    # -- OpenCode server transport ---------------------------------------- #

    def _run_agent(self, user_prompt: str):
        """Drive PydanticAI validation/retry and return a validated bundle."""

        cache_path = self.cache_dir / f"{self._cache_key(user_prompt)}.json" if self.cache_dir else None
        if cache_path and cache_path.exists():
            from scripts.question_transcription.contracts import QuestionTranscriptionBundle

            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return QuestionTranscriptionBundle.model_validate(cached["bundle"])

        from pydantic_ai import Agent
        from scripts.question_transcription.contracts import QuestionTranscriptionBundle

        client = OpencodeClient(
            server_url=self.server_url,
            agent_type=self.agent_type,
            timeout_s=self.timeout_s,
            http_client=self.http_client,
        )
        model_obj = _InfraOpencodeModel(
            model_name=self.model,
            client=client,
        )
        agent = Agent(
            model=model_obj,
            output_type=QuestionTranscriptionBundle,
            instructions=WHOLE_PAPER_SYSTEM_PROMPT,
            retries=1,
            name="whole-paper-transcriber-opencode",
        )

        try:
            result = asyncio.run(agent.run(user_prompt))
        except ModelFailureError as exc:
            raise _OpcError(_map_failure(exc.failure))
        except _OpcError:
            raise
        except Exception as exc:
            raise _OpcError(WholePaperFailure(
                adapter_id=ADAPTER_ID,
                kind="invalid_structured_output",
                attempts=1,
                detail=f"agent.run failed: {type(exc).__name__}: {exc}",
            ))

        bundle = result.output

        if cache_path:
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

    # -- helpers ----------------------------------------------------------- #

    def _read_ordered_pages(self, request):
        return self._read_ordered_pages_from(request.ordered_page_texts)

    def _read_ordered_pages_from(self, extracts) -> list[tuple[int, str]]:
        pages = []
        for extract in extracts:
            text_ref = extract.artifact.text if hasattr(extract, "artifact") else extract["artifact"]["text"]
            ref = ArtifactRef.model_validate(text_ref) if isinstance(text_ref, dict) else text_ref
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
        ref = manifest if isinstance(manifest, ArtifactRef) else ArtifactRef.model_validate(manifest)
        try:
            data = self.store.read_yaml(ref)
            return str(data.get("source_archive") or "")
        except Exception:
            return ""

    def _execution_id(self, ordered) -> str:
        return hashlib.sha256(
            "|".join(text for _, text in ordered).encode("utf-8")
        ).hexdigest()[:16]

    def _cache_key(self, user_prompt: str) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "adapter": ADAPTER_ID,
                    "model": self.model,
                    "agent_type": self.agent_type,
                    "prompt_version": WHOLE_PAPER_PROMPT_VERSION,
                    "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class _OpcError(Exception):
    """Internal control-flow exception carrying a structured WholePaperFailure."""

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure
