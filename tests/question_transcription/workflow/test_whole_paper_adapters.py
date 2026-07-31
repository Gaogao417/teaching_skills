"""Whole-paper adapter tests (Lane C).

- offline unit test uses an injected fake httpx response (no network);
- live direct-GLM-API canary is marked ``live`` and skipped by default.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.artifact_store import ArtifactStore, RunLayout
from scripts.question_transcription.workflow.contracts import (
    ArtifactRef,
    ExecutionProvenance,
    PageTextArtifact,
    PageTextExtract,
)


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


def _extract(store: ArtifactStore, page_number: int, text: str) -> PageTextExtract:
    ref = store.commit_text(f"pages/page-{page_number:03d}.txt", text, "text/plain")
    side = store.commit_yaml(
        f"pages/page-{page_number:03d}.extract.yaml",
        {"page_number": page_number}, "page-text-extract/v1",
    )
    return PageTextExtract(
        artifact=PageTextArtifact(
            page_number=page_number, text=ref, metadata=side,
            provenance=ExecutionProvenance(
                adapter_id="qwen", model="qwen3.5-ocr", prompt_version="page-text-ocr-v1"
            ),
        )
    )


class _FakeRequest:
    def __init__(self, paper_id, extracts, manifest_ref):
        self.paper_id = paper_id
        self.ordered_page_texts = extracts
        self.source_manifest = manifest_ref


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.is_error = status >= 400
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_glm_api_adapter_validates_and_commits(tmp_path):
    from scripts.question_transcription.workflow.adapters.whole_paper.glm_api import (
        GlmApiTranscriber,
    )

    store = _store(tmp_path)
    extracts = [
        _extract(store, 1, "1．选择题：函数 $y=2x$ 的图像过点（　）\nA．(0,0) B．(1,2) C．(2,1) D．(0,1)"),
    ]
    manifest = store.commit_yaml(
        "source/source-ref.yaml",
        {"schema": "fake", "paper_id": "P", "source_archive": "exam.pdf"}, "fake/v1",
    )
    bundle_json = {
        "schema": "math_question_transcription/v1",
        "paper": {"id": "P", "title": "t", "grade": "初三", "source_archive": "exam.pdf"},
        "sections": [{
            "section_ref": "1", "title": "一",
            "questions": [{
                "question_ref": "1", "question_number": 1, "question_type": "choice",
                "points": 3,
                "content": {"stem_latex": "函数 $y=2x$ 的图像过点（　）",
                            "choices": ["(0,0)", "(1,2)", "(2,1)", "(0,1)"],
                            "answer": "B", "clue": "c"},
                "evidence": {"question": [{"kind": "page", "source": "p", "page_number": 1}],
                             "solution": [{"kind": "page", "source": "p", "page_number": 1}],
                             "solution_start_anchor": "a", "solution_end_anchor": "b"},
            }],
        }],
        "provider": {"kind": "agent", "name": "glm-5.2", "version": "v1"},
    }

    class _FakeClient:
        def __init__(self, *_a, **_kw):
            pass

        def post(self, url, *, headers=None, json=None):
            return _FakeResponse({"choices": [{"message": {"content": __import__("json").dumps(bundle_json)}}]})

    adapter = GlmApiTranscriber(
        model="glm-5.2", base_url="https://x", store=store,
        api_key="fake", http_client=_FakeClient(),
    )
    request = _FakeRequest("P", extracts, manifest)
    transcription, failure = adapter.transcribe(request)
    assert failure is None, failure
    data = store.read_yaml(transcription.transcription)
    assert data["schema"] == "math_question_transcription/v1"
    assert data["paper"]["id"] == "P"
    assert data["sections"][0]["questions"][0]["question_type"] == "choice"


def test_glm_api_adapter_missing_key_is_unavailable(tmp_path):
    from scripts.question_transcription.workflow.adapters.whole_paper.glm_api import (
        GlmApiTranscriber,
    )

    store = _store(tmp_path)
    extracts = [_extract(store, 1, "page text")]
    manifest = store.commit_yaml("source/source-ref.yaml", {}, "fake/v1")
    adapter = GlmApiTranscriber(
        model="glm-5.2", base_url="https://x", store=store, api_key=None,
        cache_dir=tmp_path / "nocache",  # force a real call attempt
    )
    _, failure = adapter.transcribe(_FakeRequest("P", extracts, manifest))
    assert failure.kind == "transcriber_unavailable"


# --------------------------------------------------------------------------- #
# Live canary (skipped by default)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_glm_api_live_canary_whole_paper(tmp_path):
    """Real GLM-5.2 API call on two synthetic page texts. Requires ZHIPUAI_API_KEY.

    Run with:  RUN_LIVE=1 ./.venv/bin/python -m pytest -m live -k glm_api_live
    after `source ~/.zshrc` (so ZHIPUAI_API_KEY is loaded). Never prints the key.
    """

    import os

    assert os.environ.get("ZHIPUAI_API_KEY"), "ZHIPUAI_API_KEY must be set for live canary"

    from scripts.question_transcription.workflow.adapters.whole_paper.glm_api import (
        GlmApiTranscriber,
    )

    store = _store(tmp_path)
    extracts = [
        _extract(store, 1, "1．（选择题）函数 $y=2x+1$ 当 $x=1$ 时的值为（　）\nA．2　B．3　C．1　D．0"),
    ]
    manifest = store.commit_yaml(
        "source/source-ref.yaml",
        {"schema": "fake", "paper_id": "LIVE", "source_archive": "exam.pdf"}, "fake/v1",
    )
    adapter = GlmApiTranscriber(
        model="glm-5.2",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        store=store,
        cache_dir=tmp_path / "nocache",
    )
    transcription, failure = adapter.transcribe(_FakeRequest("LIVE", extracts, manifest))
    assert failure is None, f"live canary failed: {failure}"
    data = store.read_yaml(transcription.transcription)
    assert data["sections"][0]["questions"][0]["question_type"] == "choice"
    assert data["sections"][0]["questions"][0]["content"]["answer"] in ("B", "b")
