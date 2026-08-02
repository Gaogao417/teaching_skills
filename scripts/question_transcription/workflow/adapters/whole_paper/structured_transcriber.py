"""Unified whole-paper transcription adapter (architecture §3.6, M2).

A single provider-neutral :class:`StructuredWholePaperTranscriber` serves both the
OpenCode and Claude Code paths. Provider differences are confined to the shared
infrastructure ``Model`` (and its transport): bootstrap binds one
:class:`~scripts.infrastructure.ai.opencode.pydantic_model.OpencodeModel` or
:class:`~scripts.infrastructure.ai.claude_code.pydantic_model.ClaudeCodeModel` and
hands it to this transcriber.

Responsibilities (architecture §3.6):

- read ordered page text from the artifact store;
- build the whole-paper prompt (the agent judges the paper's layout — interleaved
  or questions-first/answers-after — from the page text itself);
- drive ``Agent(model=<bound model>, output_type=QuestionTranscriptionBundle)`` so
  structured-output validation and ``ModelRetry`` are identical across providers;
- commit the transcription artifact with stable schema/path/hash;
- map provider-neutral :class:`~scripts.infrastructure.ai.contracts.ModelFailure`
  into ``WholePaperFailure``.

It does NOT choose OpenCode or Claude Code. It does not perform provider-specific
normalization bypassing the authoritative output contract (architecture §8.2).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic_ai.models import Model

from scripts.utilities.files.atomic_write import atomic_write_text
from scripts.utilities.files.hashing import sha256_hex, stable_json_sha256

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
from scripts.infrastructure.ai.contracts import ModelFailure, ModelFailureError


__all__ = ["StructuredWholePaperTranscriber"]


def _map_failure(failure: ModelFailure, *, adapter_id: str) -> WholePaperFailure:
    """Map a provider-neutral :class:`ModelFailure` to ``WholePaperFailure``.

    Preserves the observable failure kinds of the pre-refactor adapters:
    ``timed_out`` → ``execution_timed_out``; ``protocol`` →
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
        adapter_id=adapter_id,
        kind=domain_kind,
        attempts=failure.attempts,
        detail=failure.detail,
    )


class _TranscriberError(Exception):
    """Internal control-flow exception carrying a structured ``WholePaperFailure``."""

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure


class StructuredWholePaperTranscriber:
    """:class:`WholePaperTranscriber` driving a PydanticAI ``Agent``.

    The bound ``model`` (an OpenCode or Claude Code infrastructure ``Model``) is the
    only provider-specific input; everything else is shared ingestion logic. The same
    instance serves both providers, so structured-output validation, ``ModelRetry``
    and the prompt are provider-symmetric.
    """

    def __init__(
        self,
        *,
        adapter_id: str,
        model_name: str,
        bound_model: Model,
        store,
        system_prompt: str = WHOLE_PAPER_SYSTEM_PROMPT,
        agent_name: str = "whole-paper-transcriber",
        cache_dir: Path | None = None,
        cache_key_extras: dict[str, Any] | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.model_name = model_name
        self.bound_model = bound_model
        self.store = store
        self.system_prompt = system_prompt
        self.agent_name = agent_name
        self.cache_dir = cache_dir if cache_dir is not None else store.layout.cache_dir
        # Provider-specific identity folded into the cache key (e.g. OpenCode agent_type)
        # to preserve the pre-unification cache partitioning. Identity only — never read
        # for behaviour.
        self._cache_key_extras = dict(cache_key_extras or {})

    # -- WholePaperTranscriber -------------------------------------------- #

    def transcribe(self, request):
        try:
            ordered = self._read_ordered_pages(request)
            user_prompt = build_user_prompt(
                paper_id=request.paper_id,
                source_archive=self._source_archive(request),
                ordered_pages=ordered,
            )
            bundle = self._run_agent(user_prompt)
        except _TranscriberError as exc:
            return None, exc.failure
        except Exception as exc:  # pragma: no cover - defensive
            return None, WholePaperFailure(
                adapter_id=self.adapter_id, kind="transcriber_unavailable",
                attempts=1, detail=f"{type(exc).__name__}: {exc}",
            )

        ref = self.store.commit_text(
            "structured/transcription.yaml",
            yaml.safe_dump(
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
                model=self.model_name,
                prompt_version=WHOLE_PAPER_PROMPT_VERSION,
            ),
            None,
        )

    def repair_structured_output(self, previous_execution_id, validation_errors):
        # Schema repair is delegated to re-transcribe (ports §7.4): each provider turn
        # is a fresh session and the Agent's own ModelRetry already exhausted its
        # in-run budget before we get here. Keeps repair a separate, node-visible
        # lifecycle from transport retry.
        return None, WholePaperFailure(
            adapter_id=self.adapter_id,
            kind="invalid_structured_output",
            attempts=1,
            execution_id=previous_execution_id,
            detail="repair delegated to re-transcribe",
        )

    # -- internals -------------------------------------------------------- #

    def _run_agent(self, user_prompt: str):
        """Drive PydanticAI validation/retry and return a validated bundle."""

        cache_path = self.cache_dir / f"{self._cache_key(user_prompt)}.json"
        if cache_path.exists():
            from scripts.question_transcription.contracts import (
                QuestionTranscriptionBundle,
            )

            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return QuestionTranscriptionBundle.model_validate(cached["bundle"])

        from pydantic_ai import Agent
        from scripts.question_transcription.contracts import (
            QuestionTranscriptionBundle,
        )

        agent = Agent(
            model=self.bound_model,
            output_type=QuestionTranscriptionBundle,
            instructions=self.system_prompt,
            retries=1,
            name=self.agent_name,
        )

        try:
            result = asyncio.run(agent.run(user_prompt))
        except ModelFailureError as exc:
            raise _TranscriberError(_map_failure(exc.failure, adapter_id=self.adapter_id))
        except _TranscriberError:
            raise
        except Exception as exc:
            raise _TranscriberError(WholePaperFailure(
                adapter_id=self.adapter_id,
                kind="invalid_structured_output",
                attempts=1,
                detail=f"agent.run failed: {type(exc).__name__}: {exc}",
            ))

        bundle = result.output
        atomic_write_text(
            cache_path,
            json.dumps(
                {"bundle": bundle.model_dump(by_alias=True, mode="json")},
                ensure_ascii=False,
            ),
        )
        return bundle

    def _read_ordered_pages(self, request) -> list[tuple[int, str]]:
        return self._read_ordered_pages_from(request.ordered_page_texts)

    def _read_ordered_pages_from(self, extracts) -> list[tuple[int, str]]:
        pages = []
        for extract in extracts:
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
        # ``source_archive`` is a NonEmptyStr in the output contract. When the
        # manifest omits it, fall back to ``paper_id`` rather than returning "" —
        # an empty value would force the model to emit "" and trip a PydanticAI
        # retry, re-generating the entire 20k-char JSON for a single field.
        manifest = request.source_manifest
        if manifest is not None:
            ref = (
                manifest if isinstance(manifest, ArtifactRef)
                else ArtifactRef.model_validate(manifest)
            )
            try:
                data = self.store.read_yaml(ref)
                value = str(data.get("source_archive") or "")
                if value:
                    return value
            except Exception:
                pass
        return request.paper_id

    def _execution_id(self, ordered) -> str:
        return sha256_hex(
            "|".join(text for _, text in ordered).encode("utf-8")
        )[:16]

    def _cache_key(self, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "adapter": self.adapter_id,
            "model": self.model_name,
            "prompt_version": WHOLE_PAPER_PROMPT_VERSION,
            "user_prompt_sha256": sha256_hex(user_prompt.encode("utf-8")),
        }
        payload.update(self._cache_key_extras)
        return stable_json_sha256(payload)
