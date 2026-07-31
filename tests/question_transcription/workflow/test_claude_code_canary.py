"""Claude Code SDK routing canary (design §7.2 / §14.9, ports §15 verification).

Verifies the ``claude-agent-sdk`` drives the locally-installed ``claude`` CLI and
returns structured ``math_question_transcription/v1`` output. Marked ``live`` and
skipped by default.

Routing notes (see docs/question-ingestion-langgraph-ports-design.md §7.2):
- Unlike the OpenCode adapter (whose provider does not propagate per-request
  ``model_id``), the SDK sets ``model`` / ``permission_mode`` / ``output_format`` on
  every request, so a non-empty validating response IS a routing proof.
- Auth: the SDK checks ``ANTHROPIC_API_KEY`` first, then the CLI's stored credentials /
  ``CLAUDE_CODE_OAUTH_TOKEN``. This canary never prints or logs any key material; if no
  credential is available it surfaces ``transcriber_unavailable`` and we skip.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.live
def test_claude_code_routes_and_structures(tmp_path):
    """Live Claude Code SDK canary. Requires the ``claude`` CLI + valid auth.

    Run with:
        source ~/.zshrc 2>/dev/null   # load ANTHROPIC_API_KEY / OAuth if defined there
        RUN_LIVE=1 ./.venv/bin/python -m pytest -m live -k claude_code_canary
    Prereq: ``claude`` CLI installed and logged in (``claude /login``) OR
    ``ANTHROPIC_API_KEY`` set. Never prints the key.
    """

    if shutil.which("claude") is None:
        pytest.skip("`claude` CLI not on PATH")

    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        pytest.skip("claude-agent-sdk not installed in this venv")

    from scripts.question_transcription.workflow.adapters.whole_paper.claude_code import (
        ClaudeCodeTranscriber,
    )
    from scripts.question_transcription.workflow.artifact_store import (
        ArtifactStore,
        RunLayout,
    )
    from scripts.question_transcription.workflow.contracts import (
        ExecutionProvenance,
        PageTextArtifact,
        PageTextExtract,
    )

    layout = RunLayout(tmp_path / "build", "P", "R")
    layout.ensure()
    store = ArtifactStore(layout)
    txt = store.commit_text(
        "pages/page-001.txt",
        "1．选择题：$2+2=$（　）A．3 B．4 C．5 D．6",
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

    adapter = ClaudeCodeTranscriber(
        model="sonnet",
        store=store,
        cache_dir=tmp_path / "nocache",
        timeout_s=300.0,
    )
    transcription, failure = adapter.transcribe(_Req())

    # Auth/network failures are not routing failures: surface them as a skip rather
    # than a hard fail, so the canary only hard-fails when the SDK reached the model
    # but produced bad output.
    if failure is not None and failure.kind == "transcriber_unavailable":
        pytest.skip(f"claude-agent-sdk not reachable/authed: {failure.detail}")
    assert failure is None, f"live canary failed: kind={failure.kind} detail={failure.detail}"

    data = store.read_yaml(transcription.transcription)
    assert data["schema"] == "math_question_transcription/v1"
    assert transcription.model == "sonnet"
