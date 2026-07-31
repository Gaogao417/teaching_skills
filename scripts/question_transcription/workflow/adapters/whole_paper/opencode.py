"""OpenCode glm-5.2 whole-paper transcriber (ports-design §7.2).

Uses the ``opencode-agent-server`` PydanticAI stack: ``OpencodeModel(model_name)``
+ ``Agent(output_type=QuestionTranscriptionBundle)`` + ``agent.run(prompt)``. The
model is bound **server-side** in ``~/.config/opencode/opencode.json`` (the
opencode-agent provider does not propagate per-request ``model_id`` to the server —
see docs/question-ingestion-langgraph-ports-design.md §7.2 GAP 3), so this adapter
relies on the server config selecting glm-5.2.

Routing verification (design §7.2 / §14.9): the live canary asserts the response is
non-empty structured JSON validating as ``QuestionTranscriptionBundle``; a live run
that fails routing surfaces ``routing_unverified``. The adapter needs the
opencode-agent package importable (add its src to sys.path) and a running opencode
server.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .._common_paths import repo_root  # noqa: F401
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


ADAPTER_ID = "opencode"
OPENCODE_AGENT_ROOT = Path("/Users/gaochong/develop/opencode-agent")


class _OpcError(Exception):
    """Internal control-flow exception carrying a structured WholePaperFailure."""

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure


class OpencodeGlmTranscriber:
    """:class:`WholePaperTranscriber` backed by OpenCode + PydanticAI."""

    def __init__(self, *, model: str, server_url: str, agent_type: str, store,
                 timeout_s: float = 300.0, cache_dir: Path | None = None) -> None:
        self.model = model
        self.server_url = server_url
        self.agent_type = agent_type
        self.store = store
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir or (store.layout.cache_dir)

    def transcribe(self, request):
        try:
            ordered = self._read_ordered_pages(request)
            user_prompt = build_user_prompt(
                paper_id=request.paper_id,
                source_archive=self._source_archive(request),
                ordered_pages=ordered,
            )
            bundle = self._run_agent(user_prompt, request.paper_id)
        except _OpcError as exc:
            return None, exc.failure
        except Exception as exc:  # pragma: no cover - defensive
            return None, WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
                attempts=1, detail=f"{type(exc).__name__}: {exc}",
            )
        import yaml as _yaml

        ref = self.store.commit_text(
            "structured/transcription.yaml",
            _yaml.safe_dump(bundle.model_dump(by_alias=True, exclude_none=True, mode="json"),
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

    # -- internals -------------------------------------------------------- #

    def _read_ordered_pages(self, request):
        pages = []
        for extract in request.ordered_page_texts:
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

    def _run_agent(self, user_prompt: str, paper_id: str):
        """Run the OpenCode PydanticAI agent and return a validated bundle.

        Imports are lazy so offline tests never load the opencode-agent package.
        """

        # Cache: content-addressed on the prompt; skip the agent if we've seen it.
        cache_path = self.cache_dir / f"{self._cache_key(user_prompt)}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            from scripts.question_transcription.contracts import QuestionTranscriptionBundle

            return QuestionTranscriptionBundle.model_validate(cached["bundle"])

        self._ensure_agent_importable()
        try:
            import asyncio

            from opencode_agent_server.engine.agent_factory import create_agent
            from opencode_agent_server.opencode_model import OpencodeModel
            from scripts.question_transcription.contracts import QuestionTranscriptionBundle
        except ImportError as exc:
            raise _OpcError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="routing_unverified",
                attempts=1, detail=f"opencode-agent not importable: {exc}",
            ))

        model = OpencodeModel(
            model_name=self.model,
            server_url=self.server_url,
            api_key="",
            timeout=self.timeout_s,
        )
        model._metadata = getattr(model, "_metadata", {}) or {}
        model._metadata["opencode_agent"] = self.agent_type
        agent = create_agent(
            model=model,
            output_type=QuestionTranscriptionBundle,
            instructions=WHOLE_PAPER_SYSTEM_PROMPT,
            name="whole-paper-transcriber",
        )

        try:
            result = asyncio.run(agent.run(user_prompt, output_type=QuestionTranscriptionBundle))
            bundle = result.output
        except Exception as exc:
            raise _OpcError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="execution_timed_out" if "timeout" in str(exc).lower() else "invalid_structured_output",
                attempts=1, detail=f"agent run failed: {exc}",
            ))
        finally:
            close = getattr(model, "close", None)
            if close is not None:
                try:
                    asyncio.run(close())
                except Exception:
                    pass

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"bundle": bundle.model_dump(mode="json")}, ensure_ascii=False),
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
                    "agent_type": self.agent_type,
                    "prompt_version": WHOLE_PAPER_PROMPT_VERSION,
                    "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _ensure_agent_importable() -> None:
        src = OPENCODE_AGENT_ROOT / "packages/opencode-agent-server/src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
