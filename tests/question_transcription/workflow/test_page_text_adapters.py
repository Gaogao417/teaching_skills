"""Page-text adapter tests (Lane B).

- offline unit tests use an injected fake BailianOcrClient-style transport (no network);
- the live qwen canary is marked ``live`` and skipped by default (design §8 / AGENTS.md).

These prove the adapter wires the prompt, cache_material, commit path and failure
classification correctly. The real model call is exercised only by the canary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.page_text._common import (
    PAGE_TEXT_PROMPT,
    PAGE_TEXT_PROMPT_VERSION,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.contracts import PageTextJob, ArtifactRef


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


def _job(page_number: int = 1) -> PageTextJob:
    return PageTextJob(
        run_id="r",
        paper_id="p",
        page_number=page_number,
        image=ArtifactRef(
            path=f"source/page-{page_number:03d}.png",
            sha256="sha256:" + "a" * 64,
            schema="image/png",
        ),
        input_fingerprint="sha256:" + "a" * 64,
    )


class _FakeBailianClient:
    """Mimics BailianOcrClient.complete_text (text, cache_hit)."""

    def __init__(self, *, text="fake page text with $x^2$ formula", cache_hit=False):
        self.text = text
        self.cache_hit = cache_hit
        self.calls = 0

    def complete_text(self, *, messages, cache_material):
        self.calls += 1
        assert "page_text_ocr" == cache_material["task"]
        assert cache_material["prompt_version"] == PAGE_TEXT_PROMPT_VERSION
        return self.text, self.cache_hit


def test_qwen_adapter_commits_text_and_sidecar(tmp_path):
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    # write the page image the adapter will read
    (store.layout.root / "source").mkdir(parents=True, exist_ok=True)
    (store.layout.root / "source/page-001.png").write_bytes(b"\x89PNG fake")
    fake = _FakeBailianClient(text="第1页：求函数 $y=2x+1$ 的值。")
    adapter = QwenPageTextExtractor(
        model="qwen3.5-ocr", store=store, client=fake
    )
    extract, failure = adapter.extract(_job(1))
    assert failure is None
    assert extract.artifact.page_number == 1
    text = store.read_text(extract.artifact.text)
    assert "y=2x+1" in text
    side = store.read_yaml(extract.artifact.metadata)
    assert side["model"] == "qwen3.5-ocr"
    assert side["adapter_id"] == "qwen"
    assert side["prompt_version"] == PAGE_TEXT_PROMPT_VERSION


def test_qwen_adapter_blank_text_is_contract_failure(tmp_path):
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    (store.layout.root / "source").mkdir(parents=True, exist_ok=True)
    (store.layout.root / "source/page-002.png").write_bytes(b"\x89PNG fake")
    fake = _FakeBailianClient(text="   \n  ")  # whitespace only
    adapter = QwenPageTextExtractor(model="qwen3.5-ocr", store=store, client=fake)
    extract, failure = adapter.extract(_job(2))
    assert extract is None
    assert failure.kind == "empty_text"


def test_qwen_adapter_missing_image_is_hash_mismatch(tmp_path):
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    adapter = QwenPageTextExtractor(
        model="qwen3.5-ocr", store=store, client=_FakeBailianClient()
    )
    extract, failure = adapter.extract(_job(9))
    assert extract is None
    assert failure.kind == "source_hash_mismatch"


def test_retry_decorator_retries_then_exhausts(tmp_path):
    from scripts.question_transcription.workflow.adapters.decorators import (
        with_page_retry,
    )
    from scripts.question_transcription.workflow.bootstrap.config import RetryPolicy

    calls = {"n": 0}

    class _Flaky:
        def extract(self, job):
            calls["n"] += 1
            return None, __import__(
                "scripts.question_transcription.workflow.contracts", fromlist=["PageTextFailure"]
            ).PageTextFailure(
                adapter_id="qwen", kind="rate_limited", attempts=calls["n"], detail="429"
            )

    policy = RetryPolicy(max_attempts=3, base_delay_ms=1, max_delay_ms=10)
    wrapped = with_page_retry(_Flaky(), policy)  # returns a bare extract() function
    extract, failure = wrapped(_job(1))
    assert extract is None
    assert failure.attempts == 3
    assert calls["n"] == 3


def test_retry_decorator_does_not_retry_non_retryable(tmp_path):
    from scripts.question_transcription.workflow.adapters.decorators import (
        with_page_retry,
    )
    from scripts.question_transcription.workflow.bootstrap.config import RetryPolicy

    calls = {"n": 0}

    class _SourceMismatch:
        def extract(self, job):
            calls["n"] += 1
            return None, __import__(
                "scripts.question_transcription.workflow.contracts", fromlist=["PageTextFailure"]
            ).PageTextFailure(
                adapter_id="qwen", kind="source_hash_mismatch", attempts=1, detail="bad"
            )

    wrapped = with_page_retry(_SourceMismatch(), RetryPolicy(max_attempts=5, base_delay_ms=1))
    _, failure = wrapped(_job(1))
    assert failure.attempts == 1
    assert calls["n"] == 1  # not retried


# --------------------------------------------------------------------------- #
# Live canary (skipped by default; RUN_LIVE=1 + keys required)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_qwen_live_canary_single_page(tmp_path):
    """Real qwen3.5-ocr call on a synthetic text PNG. Requires DASHSCOPE_API_KEY.

    Run with:  RUN_LIVE=1 ./.venv/bin/python -m pytest -m live -k qwen_live
    after `source ~/.zshrc` (so DASHSCOPE_API_KEY is loaded). Never prints the key.
    """

    import os

    from PIL import Image, ImageDraw

    assert os.environ.get("DASHSCOPE_API_KEY"), "DASHSCOPE_API_KEY must be set for live canary"

    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    (store.layout.root / "source").mkdir(parents=True, exist_ok=True)
    # Render a small image with Chinese+LaTeX-ish text.
    img = Image.new("RGB", (800, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 80), "1. 求 y = 2x + 1 当 x = 3 时的值。", fill="black")
    img.save(store.layout.root / "source/page-001.png")
    adapter = QwenPageTextExtractor(model="qwen3.5-ocr", store=store)
    extract, failure = adapter.extract(_job(1))
    assert failure is None, f"live canary failed: {failure}"
    text = store.read_text(extract.artifact.text)
    assert "2x" in text or "2*x" in text or "2x+1" in text.replace(" ", "")
    assert extract.artifact.provenance.model == "qwen3.5-ocr"
