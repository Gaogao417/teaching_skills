"""Tests for the unified :class:`StructuredWholePaperTranscriber` (architecture §3.6, M2).

These prove the unification goals:
- the SAME transcriber serves both providers (a fake structured model validates
  the contract identically for opencode and claude-code);
- a provider-neutral :class:`ModelFailure` maps to the right ``WholePaperFailure`` kind;
- structured-output repair is a separate, node-visible lifecycle from transport retry;
- repair reuses the same bound model (no provider switch).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models import Model, check_allow_model_requests
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from scripts.infrastructure.ai.contracts import ModelFailure, ModelFailureError
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


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


VALID_BUNDLE = {
    "schema": "math_question_transcription/v1",
    "paper": {
        "id": "P", "title": "未知", "grade": "初三", "subject": "数学",
        "source_archive": "exam.pdf",
    },
    "sections": [
        {
            "section_ref": "1", "title": "选择题",
            "questions": [
                {
                    "question_ref": "1", "question_number": 1, "question_type": "choice",
                    "points": 4,
                    "content": {"stem_latex": "$2+2=$", "choices": ["3", "4", "5", "6"],
                                 "answer": "B", "clue": "加法"},
                    "evidence": {
                        "question": [{"kind": "page", "source": "exam.pdf", "page_number": 1}],
                        "solution": [{"kind": "page", "source": "exam.pdf", "page_number": 1}],
                        "solution_start_anchor": "1", "solution_end_anchor": "1",
                    },
                }
            ],
        }
    ],
    "provider": {"kind": "agent", "name": "fake", "version": "v1"},
}


class _ScriptedModel(Model):
    """A provider-neutral fake Model returning a queued assistant text per call.

    ``responses`` is a list of either a string (assistant text) or a
    :class:`ModelFailureError` to raise. Records how many times ``request`` was
    invoked so tests can assert transport-retry vs structured-repair separation.
    """

    def __init__(self, responses, *, model_name="fake-model"):
        super().__init__()
        self._responses = list(responses)
        self._model_name = model_name
        self.calls = 0

    @property
    def model_name(self):
        return self._model_name

    @property
    def system(self):
        return "fake"

    async def request(self, messages, model_settings, model_request_parameters):
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        check_allow_model_requests()
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, ModelFailureError):
            raise item
        return ModelResponse(
            parts=[TextPart(content=item)],
            usage=RequestUsage(input_tokens=0, output_tokens=0),
            model_name=self._model_name,
            provider_name="fake",
        )


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "P", "R")
    layout.ensure()
    return ArtifactStore(layout)


def _page_extract(store: ArtifactStore, page_number: int, text: str) -> PageTextExtract:
    txt = store.commit_text(f"pages/page-{page_number:03d}.txt", text, "text/plain")
    side = store.commit_yaml(
        f"pages/page-{page_number:03d}.extract.yaml",
        {"page_number": page_number}, "page-text-extract/v1",
    )
    return PageTextExtract(
        artifact=PageTextArtifact(
            page_number=page_number, text=txt, metadata=side,
            provenance=ExecutionProvenance(
                adapter_id="qwen", model="qwen3.5-ocr", prompt_version="page-text-ocr-v1",
            ),
        )
    )


def _manifest(store: ArtifactStore):
    return store.commit_yaml(
        "source/source-ref.yaml",
        {"schema": "fake", "paper_id": "P", "source_archive": "exam.pdf"}, "fake/v1",
    )


class _Request:
    def __init__(self, store, extracts):
        self.paper_id = "P"
        self.ordered_page_texts = extracts
        self.source_manifest = _manifest(store)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_transcribe_serves_both_providers_with_same_contract(tmp_path):
    """A single fake model yields the same business contract for opencode + claude."""

    store = _store(tmp_path)
    extract = _page_extract(store, 1, "1．选择题：$2+2=$ A．3 B．4 C．5 D．6")

    for adapter_id in ("opencode", "claude-code"):
        store2 = _store(tmp_path / adapter_id)
        extract2 = _page_extract(store2, 1, "1．选择题：$2+2=$ A．3 B．4 C．5 D．6")
        model = _ScriptedModel([json.dumps(VALID_BUNDLE, ensure_ascii=False)])
        t = StructuredWholePaperTranscriber(
            adapter_id=adapter_id, model_name="fake", bound_model=model, store=store2,
            cache_dir=tmp_path / adapter_id / "nocache",
        )
        result, failure = t.transcribe(_Request(store2, [extract2]))

        assert failure is None, getattr(failure, "detail", failure)
        assert result.model == "fake"
        assert result.prompt_version == "whole-paper-v3-terminal-validation"
        data = store2.read_yaml(result.transcription)
        assert data["schema"] == "math_question_transcription/v1"
        assert data["sections"][0]["questions"][0]["content"]["answer"] == "B"


def test_single_stream_carries_question_and_solution_pages(tmp_path):
    """Both question and solution pages are concatenated into one prompt stream.

    The transcriber no longer takes a separated/interleaved mode. All ordered
    pages (e.g. a questions-first page followed by an answers page) are fed into
    one prompt and the agent judges the layout. This test pins that the prompt the
    model receives carries every page's text regardless of layout.
    """
    store = _store(tmp_path)
    question_extract = _page_extract(store, 1, "题目：$2+2=$")
    solution_extract = _page_extract(store, 2, "解答：$2+2=4$，选 B")

    captured: list[str] = []
    original_request = _ScriptedModel.request

    class _CapturingModel(_ScriptedModel):
        async def request(self, messages, model_settings, model_request_parameters):
            # record the flattened prompt the bridge produced
            for m in messages:
                for part in getattr(m, "parts", []):
                    content = getattr(part, "content", None)
                    if isinstance(content, str):
                        captured.append(content)
            return await original_request(self, messages, model_settings, model_request_parameters)

    model = _CapturingModel([json.dumps(VALID_BUNDLE, ensure_ascii=False)])
    t = StructuredWholePaperTranscriber(
        adapter_id="opencode", model_name="fake", bound_model=model, store=store,
        cache_dir=tmp_path / "nocache",
    )
    result, failure = t.transcribe(_Request(
        store, [question_extract, solution_extract],
    ))

    assert failure is None, getattr(failure, "detail", failure)
    assert result is not None
    # The single user prompt carried both pages' text.
    joined = "\n".join(captured)
    assert "$2+2=$" in joined
    assert "选 B" in joined


@pytest.mark.parametrize(
    "mf_kind, domain_kind",
    [
        ("timed_out", "execution_timed_out"),
        ("protocol", "invalid_structured_output"),
        ("unavailable", "transcriber_unavailable"),
        ("authentication", "transcriber_unavailable"),
        ("rate_limited", "transcriber_unavailable"),
    ],
)
def test_model_failure_maps_to_correct_whole_paper_failure(tmp_path, mf_kind, domain_kind):
    store = _store(tmp_path)
    extract = _page_extract(store, 1, "page text")
    model = _ScriptedModel([ModelFailureError(ModelFailure(
        provider="opencode", kind=mf_kind, detail=f"{mf_kind} boom",
    ))])
    t = StructuredWholePaperTranscriber(
        adapter_id="opencode", model_name="fake", bound_model=model, store=store,
        cache_dir=tmp_path / "nocache",
    )

    result, failure = t.transcribe(_Request(store, [extract]))

    assert result is None
    assert failure.kind == domain_kind
    assert failure.adapter_id == "opencode"


def test_repair_is_separate_lifecycle_and_reuses_same_model(tmp_path):
    """``repair_structured_output`` does not call the model (delegates to re-transcribe).

    Repair is node-visible and bounded, distinct from transport retry. It returns a
    failure describing the delegation rather than silently re-running the transport.
    """

    store = _store(tmp_path)
    model = _ScriptedModel([])  # empty — repair must not consume a response
    t = StructuredWholePaperTranscriber(
        adapter_id="claude-code", model_name="fake", bound_model=model, store=store,
        cache_dir=tmp_path / "nocache",
    )

    result, failure = t.repair_structured_output("exec-abc", ["bad shape"])

    assert result is None
    assert failure.kind == "invalid_structured_output"
    assert failure.execution_id == "exec-abc"
    assert "re-transcribe" in failure.detail
    # The model was NOT invoked by repair.
    assert model.calls == 0


def test_invalid_output_after_retry_maps_to_invalid_structured_output(tmp_path):
    """PydanticAI exhausts Agent retries on bad JSON → invalid_structured_output."""

    store = _store(tmp_path)
    extract = _page_extract(store, 1, "page text")
    # Two non-JSON responses exhaust the Agent's retries=1 budget.
    model = _ScriptedModel(["not json {", "still not json {"])
    t = StructuredWholePaperTranscriber(
        adapter_id="opencode", model_name="fake", bound_model=model, store=store,
        cache_dir=tmp_path / "nocache",
    )

    result, failure = t.transcribe(_Request(store, [extract]))

    assert result is None
    assert failure.kind == "invalid_structured_output"
    assert "agent.run failed" in failure.detail
    # Agent retried once (retries=1) → two model calls.
    assert model.calls == 2


def test_cache_hit_skips_model(tmp_path):
    store = _store(tmp_path)
    extract = _page_extract(store, 1, "page text")
    cache_dir = tmp_path / "cache"
    model = _ScriptedModel([json.dumps(VALID_BUNDLE, ensure_ascii=False)])
    t = StructuredWholePaperTranscriber(
        adapter_id="opencode", model_name="fake", bound_model=model, store=store,
        cache_dir=cache_dir,
    )

    t.transcribe(_Request(store, [extract]))
    assert model.calls == 1

    # A second transcribe with identical input hits cache and does NOT call the model.
    model2 = _ScriptedModel([AssertionError("cache should skip the model")])
    t2 = StructuredWholePaperTranscriber(
        adapter_id="opencode", model_name="fake", bound_model=model2, store=store,
        cache_dir=cache_dir,
    )
    result, failure = t2.transcribe(_Request(store, [extract]))
    assert failure is None
    assert result is not None
    assert model2.calls == 0
