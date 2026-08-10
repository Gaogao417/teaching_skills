"""OpenCode glm-5.2 routing canary (architecture §7.1 and §11).

Verifies the OpenCode server routes a transcription-style request to a zhipuai GLM
model and returns a validated :class:`QuestionTranscriptionBundle`. Marked ``live``
and skipped by default.

Prerequisites (all server-side; this adapter does NOT call the GLM API directly):
- ``opencode serve --port 4096`` running.
- ``~/.config/opencode/opencode.json`` binds a zhipuai provider (npm
  ``@ai-sdk/openai-compatible`` + the official zhipuai baseURL + a valid key) and
  declares glm-5.2. The model is selected server-side; the per-request model_id is
  not propagated by opencode-agent's provider (design ports §7.2 GAP 3).

Run with:  RUN_LIVE=1 ./.venv/bin/python -m pytest -m live -k opencode_routes
after starting the server. Never prints the key.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.live
def test_opencode_routes_to_glm_and_produces_bundle(tmp_path):
    """The OpenCode adapter must return a validated QuestionTranscriptionBundle."""

    try:
        with urllib.request.urlopen("http://127.0.0.1:4096/", timeout=5) as r:
            assert r.status == 200
    except Exception as exc:
        pytest.skip(f"opencode server not reachable on 4096: {exc}")

    from scripts.infrastructure.ai.opencode.client import OpencodeClient
    from scripts.infrastructure.ai.opencode.pydantic_model import OpencodeModel
    from scripts.question_transcription.workflow.adapters.whole_paper.structured_transcriber import (
        StructuredWholePaperTranscriber,
    )
    from scripts.question_transcription.workflow.infrastructure.artifact_store import (
        ArtifactStore,
    )
    from scripts.question_transcription.workflow.infrastructure.run_layout import (
        RunLayout,
    )
    from scripts.question_transcription.workflow.contracts import (
        ArtifactRef,
        ExecutionProvenance,
        PageTextArtifact,
        PageTextExtract,
    )

    layout = RunLayout(tmp_path / "build", "P", "R")
    layout.ensure()
    store = ArtifactStore(layout)
    txt = store.commit_text(
        "pages/page-001.txt",
        "1．选择题：$2+2=$（　）A．3　B．4　C．5　D．6",
        "text/plain",
    )
    side = store.commit_yaml(
        "pages/page-001.extract.yaml", {"page_number": 1}, "page-text-extract/v1"
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

    bound_model = OpencodeModel(
        model_name="glm-5.2",
        client=OpencodeClient(
            server_url="http://127.0.0.1:4096",
            agent_type="build",
        ),
    )
    adapter = StructuredWholePaperTranscriber(
        adapter_id="opencode",
        model_name="glm-5.2",
        bound_model=bound_model,
        store=store,
        agent_name="whole-paper-transcriber-opencode",
        cache_dir=tmp_path / "nocache",
        cache_key_extras={"agent_type": "build"},
    )
    transcription, failure = adapter.transcribe(_Req())
    assert failure is None, f"live canary failed: {failure.kind}: {failure.detail}"
    data = store.read_yaml(transcription.transcription)
    assert data["schema"] == "math_question_transcription/v1"
    q = data["sections"][0]["questions"][0]
    assert q["question_type"] == "choice"
    assert q["content"]["answer"] in ("B", "b")
