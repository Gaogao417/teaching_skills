"""Offline tests for the OpenCode Model/Agent validation chain."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.infrastructure.ai.opencode.client import OpencodeClient
from scripts.infrastructure.ai.opencode.pydantic_model import OpencodeModel
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
    "provider": {"kind": "agent", "name": "glm-5.2", "version": "v1"},
}


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "P", "R")
    layout.ensure()
    return ArtifactStore(layout)


def _request(store: ArtifactStore):
    text = store.commit_text(
        "pages/page-001.txt",
        "1．选择题：$2+2=$（　）A．3 B．4 C．5 D．6",
        "text/plain",
    )
    metadata = store.commit_yaml(
        "pages/page-001.extract.yaml", {"page_number": 1}, "page-text-extract/v1"
    )
    extract = PageTextExtract(
        artifact=PageTextArtifact(
            page_number=1,
            text=text,
            metadata=metadata,
            provenance=ExecutionProvenance(
                adapter_id="qwen",
                model="qwen3.5-ocr",
                prompt_version="page-text-ocr-v1",
            ),
        )
    )
    manifest = store.commit_yaml(
        "source/source-ref.yaml",
        {"schema": "fake", "paper_id": "P", "source_archive": "exam.pdf"},
        "fake/v1",
    )

    class _Request:
        paper_id = "P"
        ordered_page_texts = [extract]
        source_manifest = manifest

    return _Request()


class _HttpClient:
    """Minimal injected OpenCode HTTP client with queued assistant responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.messages: list[dict] = []
        self.sessions = 0

    def post(self, url: str, json: dict):
        if url.endswith("/session"):
            self.sessions += 1
            return httpx.Response(200, json={"id": f"session-{self.sessions}"})
        self.messages.append(json)
        response = self.responses.pop(0)
        return httpx.Response(
            200,
            json={"parts": [{"type": "text", "text": response}]},
        )


def _adapter(store, client, cache_dir):
    """Build the real OpenCode transcriber chain with an injected HTTP client.

    Mirrors composition.py: a provider-neutral :class:`StructuredWholePaperTranscriber`
    fed an :class:`OpencodeModel`. ``cache_key_extras`` preserves the agent_type cache
    partitioning the pre-unification adapter used.
    """
    opencode_client = OpencodeClient(
        server_url="http://127.0.0.1:4096",
        agent_type="build",
        http_client=client,
    )
    bound_model = OpencodeModel(model_name="glm-5.2", client=opencode_client)
    return StructuredWholePaperTranscriber(
        adapter_id="opencode",
        model_name="glm-5.2",
        bound_model=bound_model,
        store=store,
        agent_name="whole-paper-transcriber-opencode",
        cache_dir=cache_dir,
        cache_key_extras={"agent_type": "build"},
    )


def test_model_is_concrete_and_providerless():
    from pydantic_ai.models import Model

    model = OpencodeModel(model_name="glm-5.2", send_message=lambda _: {})

    assert issubclass(OpencodeModel, Model)
    assert not OpencodeModel.__abstractmethods__
    assert model.provider is None


def test_transcribe_runs_agent_and_commits_valid_bundle(tmp_path):
    store = _store(tmp_path)
    client = _HttpClient([json.dumps(VALID_BUNDLE, ensure_ascii=False)])
    adapter = _adapter(store, client, tmp_path / "nocache")

    transcription, failure = adapter.transcribe(_request(store))

    assert failure is None, getattr(failure, "detail", failure)
    assert transcription.model == "glm-5.2"
    assert len(client.messages) == 1
    assert client.messages[0]["agent"] == "build"
    assert "$2+2=$" in client.messages[0]["parts"][0]["text"]
    bundle = store.read_yaml(transcription.transcription)
    assert bundle["sections"][0]["questions"][0]["content"]["answer"] == "B"


def test_agent_retries_invalid_output_then_accepts_valid_bundle(tmp_path):
    store = _store(tmp_path)
    client = _HttpClient(
        ["not valid json", json.dumps(VALID_BUNDLE, ensure_ascii=False)]
    )
    adapter = _adapter(store, client, tmp_path / "nocache")

    transcription, failure = adapter.transcribe(_request(store))

    assert failure is None, getattr(failure, "detail", failure)
    assert transcription is not None
    assert len(client.messages) == 2
    retry_prompt = client.messages[1]["parts"][0]["text"]
    assert "not valid json" in retry_prompt


def test_agent_retry_exhaustion_maps_to_invalid_structured_output(tmp_path):
    store = _store(tmp_path)
    client = _HttpClient(["bad output one", "bad output two"])
    adapter = _adapter(store, client, tmp_path / "nocache")

    transcription, failure = adapter.transcribe(_request(store))

    assert transcription is None
    assert failure.kind == "invalid_structured_output"
    assert "agent.run failed" in failure.detail
    assert len(client.messages) == 2
