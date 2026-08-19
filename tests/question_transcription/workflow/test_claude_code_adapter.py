"""Offline tests for the Claude Code whole-paper adapter (ports §7.2, C4).

The bound model is the Claude Code infrastructure :class:`ClaudeCodeModel`, which
drives ``Agent(model=..., output_type=QuestionTranscriptionBundle).run()`` — the
same provider-neutral :class:`StructuredWholePaperTranscriber` that the OpenCode path
uses. The SDK turn is an injectable :class:`ClaudeQueryPort`, so these tests never
import ``claude_agent_sdk`` nor reach the network/CLI. They assert the adapter:

- builds the provider-agnostic prompt from ordered page text + manifest;
- runs the Agent and commits a validated ``QuestionTranscriptionBundle`` with correct
  provenance / execution_id;
- short-circuits on a content-addressed cache hit;
- maps a non-JSON assistant turn (Agent exhausts output retries) to
  ``invalid_structured_output``;
- maps an SDK import failure (raised by the real query port) to
  ``transcriber_unavailable``;
- honors the ``repair_structured_output`` contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.infrastructure.ai.claude_code.client import (
    ADAPTER_ID,
    ClaudeTurn,
)
from scripts.infrastructure.ai.claude_code.pydantic_model import ClaudeCodeModel
from scripts.question_transcription.workflow.adapters.whole_paper.structured_transcriber import (
    StructuredWholePaperTranscriber,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.contracts import (
    ExecutionProvenance,
    PageTextArtifact,
    PageTextExtract,
)
from scripts.question_transcription.workflow.prompts.whole_paper import (
    WHOLE_PAPER_PROMPT_VERSION,
    WHOLE_PAPER_SYSTEM_PROMPT,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _adapter(
    store,
    *,
    cache_dir,
    query_port,
    allowed_tools=None,
    max_turns=1,
    permission_mode="default",
    effort=None,
    max_thinking_tokens=None,
):
    """Build the real Claude Code transcriber chain with an injected query port.

    This mirrors what composition.py binds: a provider-neutral
    :class:`StructuredWholePaperTranscriber` fed a :class:`ClaudeCodeModel`. The
    fake ``query_port`` replaces the SDK so no CLI/network is touched.
    """
    bound_model = ClaudeCodeModel(
        model_name="sonnet",
        query_port=query_port,
        system_prompt=WHOLE_PAPER_SYSTEM_PROMPT,
        allowed_tools=allowed_tools,
        max_turns=max_turns,
        permission_mode=permission_mode,
        effort=effort,
        max_thinking_tokens=max_thinking_tokens,
    )
    return StructuredWholePaperTranscriber(
        adapter_id=ADAPTER_ID,
        model_name="sonnet",
        bound_model=bound_model,
        store=store,
        agent_name="whole-paper-transcriber-claude-code",
        cache_dir=cache_dir,
    )


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "P", "R")
    layout.ensure()
    return ArtifactStore(layout)


def _make_request(store: ArtifactStore, page_text: str):
    """Build a minimal whole-paper request with one ordered page text."""

    txt = store.commit_text("pages/page-001.txt", page_text, "text/plain")
    side = store.commit_yaml(
        "pages/page-001.extract.yaml",
        {"page_number": 1},
        "page-text-extract/v1",
    )
    extract = PageTextExtract(
        artifact=PageTextArtifact(
            page_number=1,
            text=txt,
            metadata=side,
            provenance=ExecutionProvenance(
                adapter_id="qwen", model="qwen3.5-ocr", prompt_version="page-text-ocr-v1"
            ),
        )
    )
    manifest = store.commit_yaml(
        "source/source-ref.yaml",
        {"schema": "fake", "paper_id": "P", "source_archive": "exam.pdf"},
        "fake/v1",
    )

    class _Req:
        paper_id = "P"
        ordered_page_texts = [extract]
        source_manifest = manifest

    return _Req()


VALID_BUNDLE = {
    "schema": "math_question_transcription/v1",
    "paper": {
        "id": "P",
        "title": "未知",
        "grade": "初三",
        "subject": "数学",
        "source_archive": "exam.pdf",
    },
    "sections": [
        {
            "section_ref": "1",
            "title": "选择题",
            "questions": [
                {
                    "question_ref": "1",
                    "question_number": 1,
                    "question_type": "choice",
                    "points": 4,
                    "content": {
                        "stem_latex": "$2+2=$",
                        "choices": ["3", "4", "5", "6"],
                        "answer": "B",
                        "clue": "加法",
                    },
                    "evidence": {
                        "question": [
                            {"kind": "page", "source": "exam.pdf", "page_number": 1}
                        ],
                        "solution": [
                            {"kind": "page", "source": "exam.pdf", "page_number": 1}
                        ],
                        "solution_start_anchor": "1",
                        "solution_end_anchor": "1",
                    },
                }
            ],
        }
    ],
    "provider": {"kind": "agent", "name": "claude-code", "version": "v1"},
}


def _fake_port(
    response: str | Exception,
    *,
    captured: dict | None = None,
    actual_model: str | None = None,
):
    """A ``ClaudeQueryPort`` that records calls and yields a canned assistant turn.

    ``response`` is either the assistant text (a valid bundle JSON string) or an
    Exception to raise. Real transport failures surface from shared infrastructure as
    a provider-neutral :class:`ModelFailureError`; tests emulate that here.
    """

    cap = captured if captured is not None else {}

    class _Port:
        async def run(self, **kwargs):
            cap.update(kwargs)
            if isinstance(response, Exception):
                raise response
            return ClaudeTurn(
                assistant_text=response,
                input_tokens=10,
                output_tokens=5,
                model_name=actual_model,
            )

    return _Port(), cap


def _model_failure(kind: str, detail: str):
    """Build a provider-neutral ``ModelFailureError`` for the port to raise.

    The adapter maps ``timed_out`` → ``execution_timed_out`` and everything else →
    ``transcriber_unavailable`` (and ``protocol`` → ``invalid_structured_output``),
    so these tests assert the same observable domain failure as before.
    """
    from scripts.infrastructure.ai.contracts import ModelFailure, ModelFailureError

    return ModelFailureError(ModelFailure(
        provider=ADAPTER_ID, kind=kind, attempts=1, detail=detail,
    ))


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_transcribe_runs_agent_and_commits_valid_bundle(tmp_path):
    store = _store(tmp_path)
    request = _make_request(store, "1．选择题：$2+2=$（　）A．3 B．4 C．5 D．6")
    port, captured = _fake_port(
        json.dumps(VALID_BUNDLE, ensure_ascii=False), captured={}
    )
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.transcribe(request)

    assert failure is None, getattr(failure, "detail", failure)
    assert transcription.model == "sonnet"
    assert transcription.prompt_version == WHOLE_PAPER_PROMPT_VERSION
    assert transcription.execution_id and len(transcription.execution_id) == 16

    # Committed artifact is a valid v1 bundle.
    data = store.read_yaml(transcription.transcription)
    assert data["schema"] == "math_question_transcription/v1"
    assert data["sections"][0]["questions"][0]["question_ref"] == "1"

    # The port received the per-request model binding (routing verifiable) and the
    # flattened prompt carrying the page text + paper metadata.
    assert captured["model"] == "sonnet"
    assert captured["system_prompt"]   # WHOLE_PAPER_SYSTEM_PROMPT
    assert "$2+2=$" in captured["prompt"]
    assert "exam.pdf" in captured["prompt"]


def test_transcribe_persists_gateway_resolved_model(tmp_path):
    store = _store(tmp_path)
    request = _make_request(store, "1．选择题：$2+2=$（　）A．3 B．4 C．5 D．6")
    port, _ = _fake_port(
        json.dumps(VALID_BUNDLE, ensure_ascii=False), actual_model="glm-5.3"
    )
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.transcribe(request)

    assert failure is None
    assert transcription.model == "glm-5.3"
    data = store.read_yaml(transcription.transcription)
    assert data["provider"]["name"] == "glm-5.3"


def test_transcribe_cache_hit_short_circuits(tmp_path):
    store = _store(tmp_path)
    request = _make_request(store, "1．选择题：$2+2=$ A．3 B．4 C．5 D．6")
    calls = {"n": 0}

    class _CountingPort:
        async def run(self, **kw):
            calls["n"] += 1
            return ClaudeTurn(
                assistant_text=json.dumps(VALID_BUNDLE, ensure_ascii=False),
                input_tokens=1, output_tokens=1,
            )

    cache_dir = tmp_path / "cache"
    adapter = _adapter(store, cache_dir=cache_dir, query_port=_CountingPort())
    adapter.transcribe(request)  # populate cache
    assert calls["n"] == 1

    # Second transcribe with the SAME input must hit cache and skip the agent (a port
    # that would raise if called proves it isn't called).
    class _ExplodingPort:
        async def run(self, **kw):
            raise AssertionError("cache hit should skip the port entirely")

    adapter2 = _adapter(store, cache_dir=cache_dir, query_port=_ExplodingPort())
    transcription, failure = adapter2.transcribe(request)
    assert failure is None, failure.detail
    assert calls["n"] == 1  # unchanged — cache hit
    data = store.read_yaml(transcription.transcription)
    assert data["schema"] == "math_question_transcription/v1"


def test_transcribe_non_json_maps_to_invalid_structured_output(tmp_path):
    store = _store(tmp_path)
    request = _make_request(store, "garbled page text")
    port, _ = _fake_port("not json at all {{{")
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.transcribe(request)

    assert transcription is None
    assert failure is not None
    assert failure.adapter_id == ADAPTER_ID
    assert failure.kind == "invalid_structured_output"
    # The Agent's output validation failed after exhausting retries.
    assert "agent.run failed" in failure.detail or "validation" in failure.detail.lower()


def test_transcribe_sdk_failure_maps_to_transcriber_unavailable(tmp_path):
    store = _store(tmp_path)
    request = _make_request(store, "page text")
    # The real port surfaces transport failures as a provider-neutral ModelFailureError;
    # emulate an SDK/auth miss (mapped by the adapter to transcriber_unavailable).
    port, _ = _fake_port(_model_failure("unavailable", "claude CLI not found"))
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.transcribe(request)

    assert transcription is None
    assert failure is not None
    assert failure.kind == "transcriber_unavailable"
    assert "claude CLI not found" in failure.detail


def test_transcribe_timeout_maps_to_execution_timed_out(tmp_path):
    store = _store(tmp_path)
    request = _make_request(store, "page text")
    port, _ = _fake_port(_model_failure("timed_out", "timed out after 300s"))
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.transcribe(request)

    assert transcription is None
    assert failure.kind == "execution_timed_out"
    assert "300s" in failure.detail


def test_repair_structured_output_contract(tmp_path):
    store = _store(tmp_path)
    port, _ = _fake_port(json.dumps(VALID_BUNDLE, ensure_ascii=False))
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.repair_structured_output("exec-123", ["bad shape"])

    assert transcription is None
    assert failure is not None
    assert failure.kind == "invalid_structured_output"
    assert failure.execution_id == "exec-123"
    assert "re-transcribe" in failure.detail


def test_model_is_pydantic_ai_model_subclass():
    """The Model must be a real pydantic_ai.Model subclass (sibling of OpencodeModel)."""
    from pydantic_ai.models import Model

    model = ClaudeCodeModel(model_name="sonnet")

    assert issubclass(ClaudeCodeModel, Model)
    # All abstract members satisfied.
    assert not ClaudeCodeModel.__abstractmethods__
    assert model.provider is None


def test_tools_and_max_turns_propagate_to_port(tmp_path):
    """allowed_tools / max_turns / permission_mode must reach the query port.

    These reach the bound claude_agent_sdk options verbatim. The production
    default is the constrained validator only; this test
    passes an explicit list to prove the value is forwarded unchanged.
    """
    store = _store(tmp_path)
    request = _make_request(store, "1．选择题：$2+2=$ A．3 B．4 C．5 D．6")
    port, captured = _fake_port(
        json.dumps(VALID_BUNDLE, ensure_ascii=False), captured={}
    )
    adapter = _adapter(
        store, cache_dir=tmp_path / "nocache", query_port=port,
        allowed_tools=["Bash(python:*)"], max_turns=6, permission_mode="acceptEdits",
        effort="high", max_thinking_tokens=12000,
    )

    transcription, failure = adapter.transcribe(request)
    assert failure is None, getattr(failure, "detail", failure)

    assert captured["allowed_tools"] == ["Bash(python:*)"]
    assert captured["max_turns"] == 6
    assert captured["permission_mode"] == "acceptEdits"
    assert captured["effort"] == "high"
    assert captured["max_thinking_tokens"] == 12000


def test_source_archive_falls_back_to_paper_id_when_manifest_empty(tmp_path):
    """An empty/missing source_archive must fall back to paper_id, not "".

    Without this, the model copies the empty manifest value, trips NonEmptyStr
    validation, and PydanticAI retries — re-generating the entire 20k-char JSON.
    """
    store = _store(tmp_path)

    txt = store.commit_text("pages/page-001.txt", "1．选择题：$2+2=$ A．3 B．4 C．5 D．6", "text/plain")
    side = store.commit_yaml(
        "pages/page-001.extract.yaml", {"page_number": 1}, "page-text-extract/v1",
    )
    extract = PageTextExtract(
        artifact=PageTextArtifact(
            page_number=1, text=txt, metadata=side,
            provenance=ExecutionProvenance(
                adapter_id="qwen", model="qwen3.5-ocr", prompt_version="page-text-ocr-v1",
            ),
        )
    )
    # Manifest with an EMPTY source_archive — the case that triggered the bug.
    manifest = store.commit_yaml(
        "source/source-ref.yaml",
        {"schema": "fake", "paper_id": "JIADING-ERMO", "source_archive": ""},
        "fake/v1",
    )

    class _Req:
        paper_id = "JIADING-ERMO"
        ordered_page_texts = [extract]
        source_manifest = manifest

    port, captured = _fake_port(
        json.dumps(VALID_BUNDLE, ensure_ascii=False), captured={}
    )
    adapter = _adapter(store, cache_dir=tmp_path / "nocache", query_port=port)

    transcription, failure = adapter.transcribe(_Req())
    assert failure is None, getattr(failure, "detail", failure)

    # The user prompt fed to the model must carry paper_id, not an empty value.
    assert "source_archive: JIADING-ERMO" in captured["prompt"]
    assert "source_archive: \n" not in captured["prompt"]  # not empty
