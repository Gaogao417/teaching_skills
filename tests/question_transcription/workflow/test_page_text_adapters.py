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
    looks_truncated,
    stitch_band_texts,
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


class _SequenceBailianClient:
    """按调用顺序依次返回预置响应（第 1 次=整页,其后=条带 0..n）。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    def complete_text(self, *, messages, cache_material):
        index = self.calls
        self.calls += 1
        assert index < len(self.responses), "unexpected extra provider call"
        return self.responses[index], False


def _real_png(path: Path, width: int = 400, height: int = 560) -> None:
    from PIL import Image

    Image.new("RGB", (width, height), "white").save(path)


# --------------------------------------------------------------------------- #
# OCR 截断守卫:looks_truncated / stitch_band_texts（2026-08-19 闵行 Q23(2) 根因）
# --------------------------------------------------------------------------- #


def test_looks_truncated_signatures():
    # 观测到的真实截断:奇数个 $ + 尾部悬在 \cdot 点串上(闵行答案页 page-011)。
    assert looks_truncated("$\\therefore C E \\perp A B$ 又 $\\because \\angle E O B")
    # 省略号/评分点线本身不是确定性截断信号（条带可能恰好裁在分值线上）。
    assert not looks_truncated("证毕 $x$。\n……………………")
    # 未闭合代码围栏 / 未闭合环境
    assert looks_truncated("```latex\n第 1 行\n")
    assert looks_truncated("前文 $x$ 后文 \\begin{aligned} \\frac{1}{2}\n")
    # 健康文本:成对 $、干净收尾
    assert not looks_truncated("1. 求 $y=2x+1$ 当 $x=3$ 时的值。")
    assert not looks_truncated("(A) $\\frac{3}{4}$; (B) $\\frac{4}{3}$。")
    # 空白交给 empty_text 契约,不算截断
    assert not looks_truncated("   \n ")


def test_stitch_band_texts_dedups_overlap():
    band0 = "23. 证明: (1) $\\because AD \\cdot OC = AB \\cdot OD$\n$\\therefore \\frac{AD}{OD} = \\frac{AB}{OC}$\n"
    # band1 头部与 band0 尾部有 1 行重叠(空白归一后相等)
    band1 = "$\\therefore \\frac{AD}{OD}=\\frac{AB}{OC}$\n$\\because AF$ 是 $\\angle BAC$ 的平分线\n"
    stitched = stitch_band_texts([band0, band1])
    assert stitched.count("\\frac{AB}{OC}") == 1
    assert "AF" in stitched and "平分线" in stitched


def test_stitch_band_texts_no_overlap_keeps_all():
    a = "第一段内容。\n"
    b = "第二段内容。\n"
    assert stitch_band_texts([a, b]) == "第一段内容。\n第二段内容。\n"


def test_qwen_adapter_stripe_fallback_recovers_truncated_page(tmp_path):
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-003.png")
    truncated = "$\\therefore CE \\perp AB$ 又 $\\because \\angle EOB"  # 奇数 $
    bands = [
        "23. 证明: (1) $\\because AD \\cdot OC = AB \\cdot OD$。\n",
        "证明: (1) $\\because AD \\cdot OC = AB \\cdot OD$。\n$\\because AF$ 是 $\\angle BAC$ 的平分线, 证得 $AF \\cdot DE = AG \\cdot BC$。\n",
        "证得 $AF \\cdot DE = AG \\cdot BC$。\n24. 解: (1) 设抛物线为 $y = ax^2 + bx + c$。\n",
        "24. 解: (1) 设抛物线为 $y = ax^2 + bx + c$。\n(2) 解方程。\n",
        "(2) 解方程。\n25. 解：分类讨论。\n",
    ]
    fake = _SequenceBailianClient([truncated, *bands])
    adapter = QwenPageTextExtractor(model="qwen3.5-ocr", store=store, client=fake)
    extract, failure = adapter.extract(_job(3))
    assert failure is None, f"unexpected failure: {failure}"
    assert fake.calls == 6  # 整页 1 次 + 条带 5 次
    text = store.read_text(extract.artifact.text)
    # 拼接去重后重叠行只保留一份,但两段独有内容都在
    assert text.count("AD \\cdot OC") == 1
    assert "AF \\cdot DE = AG \\cdot BC" in text
    assert "24. 解" in text
    side = store.read_yaml(extract.artifact.metadata)
    assert side["ocr_enhancement"] == "stripe-fallback"


def test_qwen_adapter_stripe_still_truncated_fails_closed(tmp_path):
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-004.png")
    truncated = "$\\therefore CE \\perp AB$ 又 $\\because \\angle EOB"
    band0_truncated = "$\\because AD$ 又 $\\angle EOB 未闭合"
    fake = _SequenceBailianClient(
        [
            truncated,
            band0_truncated,
            "后续一。",
            "后续二。",
            "后续三。",
            "末尾完整。",
        ]
    )
    adapter = QwenPageTextExtractor(model="qwen3.5-ocr", store=store, client=fake)
    extract, failure = adapter.extract(_job(4))
    assert extract is None
    assert failure.kind == "truncated_page_text"
    assert "stitched stripe text" in failure.detail


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
    wrapped = with_page_retry(_Flaky(), policy)  # returns an object exposing .extract
    extract, failure = wrapped.extract(_job(1))
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
    _, failure = wrapped.extract(_job(1))
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
