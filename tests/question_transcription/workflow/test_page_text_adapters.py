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
    find_sequence_gaps,
    looks_truncated,
    strip_code_fences,
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
# OCR 截断守卫:looks_truncated / find_sequence_gaps（2026-08-19 闵行 Q23(2) 根因）
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


def test_find_sequence_gaps_detects_dropped_choice_label():
    """黄浦 002.png 实测:第 5 题选项行只剩 (A)(B)(D),(C) 被行内丢弃,结构
    完全闭合——只有枚举序列跳号能发现。"""
    text = (
        "4. 在 $\\triangle ABC$ 中,下列条件中能推得 $DE \\parallel BC$ 的是 ( ▲ )\n"
        "(A) $\\frac{DE}{BC}=\\frac{1}{3}$; (B) $\\frac{DE}{BC}=\\frac{1}{4}$; (D) $\\frac{AE}{AC}=\\frac{1}{4}$.\n"
        "5. 已知抛物线 $y=ax^2+bx+c$ 的图像如图所示 ( ▲ )\n"
    )
    gaps = find_sequence_gaps(text)
    assert any("skip C" in g for g in gaps)


def test_find_sequence_gaps_detects_question_number_skip():
    text = "5. 已知抛物线 $y=ax^2+bx+c$……\n7. $(\\vec{a}+\\vec{b})+3(\\frac{1}{3}\\vec{a}-2\\vec{b})=$\n"
    gaps = find_sequence_gaps(text)
    assert any("skip 6" in g for g in gaps)


def test_find_sequence_gaps_clean_pages_pass():
    contiguous = (
        "1. 求 $y=2x+1$ 当 $x=3$ 时的值。\n(A) $1$; (B) $2$; (C) $3$; (D) $4$.\n"
        "2. $(\\vec{a}+\\vec{b})+3(\\frac{1}{3}\\vec{a}-2\\vec{b})=$\n"
    )
    assert find_sequence_gaps(contiguous) == []
    # 新题的选项重新从 A 开始(B→A 是换题,不是跳号)
    two_questions = "(A) $x$; (B) $y$.\n2. 第二题 (A) $p$; (B) $q$.\n"
    assert find_sequence_gaps(two_questions) == []


def test_strip_code_fences_removes_paired_and_stray_fences():
    fenced = "```latex\n23. 证明: (1) $\\because AD \\cdot OC$。\n```"
    stripped = strip_code_fences(fenced)
    assert "```" not in stripped
    assert "23. 证明" in stripped
    stray = "```latex\n第 1 行\n"
    assert "```" not in strip_code_fences(stray)
    assert "第 1 行" in strip_code_fences(stray)


def _write_overrides(pack_dir, payload):
    import yaml

    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "page-text-overrides.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def test_qwen_adapter_flags_suspect_page_without_override(tmp_path):
    """可疑页(截断/跳号)无人工补丁 → 照常提交 OCR 文本,suspect 原因进
    sidecar 上报人工;不自动修复、不失败(2026-08-19 用户裁定)。"""
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-003.png")
    truncated = "$\\therefore CE \\perp AB$ 又 $\\because \\angle EOB"  # 奇数 $
    fake = _SequenceBailianClient([truncated])
    adapter = QwenPageTextExtractor(model="qwen3.5-ocr", store=store, client=fake)
    extract, failure = adapter.extract(_job(3))
    assert failure is None, f"unexpected failure: {failure}"
    assert fake.calls == 1  # 只调一次整页 OCR,没有任何自动重试
    text = store.read_text(extract.artifact.text)
    assert "CE \\perp AB" in text
    side = store.read_yaml(extract.artifact.metadata)
    assert side["ocr_suspect"] == ["truncated"]


def test_qwen_adapter_uses_text_override_for_suspect_page(tmp_path):
    """可疑页有人工文本补丁 → 整页用补丁文本,provenance 记 manual-override。"""
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-004.png")
    pack_dir = tmp_path / "documents" / "PAPER-OVR"
    _write_overrides(
        pack_dir,
        {
            "schema": "math_page_text_overrides/v1",
            "paper_id": "p",
            "overrides": [
                {
                    "page_number": 4,
                    "mode": "text",
                    "text": "23. (2) $\\because AF$ 是 $\\angle BAC$ 的平分线, 证得 $AF \\cdot DE = AG \\cdot BC$。",
                    "note": "答案页 OCR 截断,人工从官方答案 docx 抄录整页",
                    "verified_at": "2026-08-19",
                }
            ],
        },
    )
    truncated = "$\\therefore CE \\perp AB$ 又 $\\because \\angle EOB"
    fake = _SequenceBailianClient([truncated])
    adapter = QwenPageTextExtractor(
        model="qwen3.5-ocr", store=store, client=fake,
        overrides_path=pack_dir / "page-text-overrides.yaml",
    )
    extract, failure = adapter.extract(_job(4))
    assert failure is None, f"unexpected failure: {failure}"
    text = store.read_text(extract.artifact.text)
    assert "AF \\cdot DE = AG \\cdot BC" in text
    side = store.read_yaml(extract.artifact.metadata)
    assert side["ocr_enhancement"] == "manual-override"
    assert "ocr_suspect" not in side


def test_qwen_adapter_uses_image_override_for_suspect_page(tmp_path):
    """可疑页有人工截图补丁 → 只对这张手工小图做一次 OCR(小图输出预算
    低,不触发密集页截断),作为该页文本。"""
    from PIL import Image

    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-005.png")
    pack_dir = tmp_path / "documents" / "PAPER-OVR-IMG"
    pack_dir.mkdir(parents=True)
    Image.new("RGB", (600, 200), "white").save(pack_dir / "answer-23-crop.png")
    _write_overrides(
        pack_dir,
        {
            "schema": "math_page_text_overrides/v1",
            "paper_id": "p",
            "overrides": [
                {
                    "page_number": 5,
                    "mode": "image",
                    "image": "answer-23-crop.png",
                    "note": "手工截取第 23 题第 (2) 问答案区域",
                    "verified_at": "2026-08-19",
                }
            ],
        },
    )
    truncated = "$\\therefore CE \\perp AB$ 又 $\\because \\angle EOB"
    cropped = "证得 $AF \\cdot DE = AG \\cdot BC$。"
    fake = _SequenceBailianClient([truncated, cropped])
    adapter = QwenPageTextExtractor(
        model="qwen3.5-ocr", store=store, client=fake,
        overrides_path=pack_dir / "page-text-overrides.yaml",
    )
    extract, failure = adapter.extract(_job(5))
    assert failure is None, f"unexpected failure: {failure}"
    assert fake.calls == 2  # 整页 1 次 + 手工截图 1 次
    text = store.read_text(extract.artifact.text)
    assert "AG \\cdot BC" in text
    side = store.read_yaml(extract.artifact.metadata)
    assert side["ocr_enhancement"] == "manual-override"


def test_qwen_adapter_rejects_foreign_paper_override(tmp_path):
    """补丁文件 paper_id 与 run 不符 → 结构化失败(不静默用错卷的补丁)。"""
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-006.png")
    pack_dir = tmp_path / "documents" / "PAPER-OTHER"
    _write_overrides(
        pack_dir,
        {
            "schema": "math_page_text_overrides/v1",
            "paper_id": "PAPER-OTHER",
            "overrides": [
                {
                    "page_number": 6,
                    "mode": "text",
                    "text": "别卷的内容",
                    "note": "误放",
                    "verified_at": "2026-08-19",
                }
            ],
        },
    )
    truncated = "$\\therefore CE \\perp AB$ 又 $\\because \\angle EOB"
    fake = _SequenceBailianClient([truncated])
    adapter = QwenPageTextExtractor(
        model="qwen3.5-ocr", store=store, client=fake,
        overrides_path=pack_dir / "page-text-overrides.yaml",
    )
    extract, failure = adapter.extract(_job(6))
    assert extract is None
    assert failure.kind == "invalid_response"
    assert "paper_id" in failure.detail


def test_qwen_adapter_clean_page_has_no_suspect_flag(tmp_path):
    from scripts.question_transcription.workflow.adapters.page_text.qwen import (
        QwenPageTextExtractor,
    )

    store = _store(tmp_path)
    src = store.layout.root / "source"
    src.mkdir(parents=True, exist_ok=True)
    _real_png(src / "page-007.png")
    clean = "1. 求 $y=2x+1$ 当 $x=3$ 时的值。\n(A) $4$; (B) $5$; (C) $6$; (D) $7$。\n"
    fake = _SequenceBailianClient([clean])
    adapter = QwenPageTextExtractor(model="qwen3.5-ocr", store=store, client=fake)
    extract, failure = adapter.extract(_job(7))
    assert failure is None
    side = store.read_yaml(extract.artifact.metadata)
    assert "ocr_suspect" not in side
    assert "ocr_enhancement" not in side


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
