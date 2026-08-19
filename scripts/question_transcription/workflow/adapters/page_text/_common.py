"""Shared OCR prompt + helpers for page-text adapters (architecture §5.1).

The prompt is the single source of truth for what the page-text contract allows:
visible words in reading order, LaTeX formulae, necessary line breaks — and nothing
else. Both qwen and MiMo adapters feed the same prompt so cache keys and provenance
are comparable.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from ...contracts import (
    ArtifactRef,
    ExecutionProvenance,
    PageTextArtifact,
    PageTextExtract,
    PageTextJob,
)


PAGE_TEXT_PROMPT_VERSION = "page-text-ocr-v2"

PAGE_TEXT_PROMPT = (
    "你是数学试卷逐页 OCR 抄录器。只按视觉阅读顺序忠实抄录本页全部可见文字。\n"
    "要求:\n"
    "1. 数学公式写成 LaTeX。\n"
    "2. 保留必要的换行。\n"
    "3. 题号保持原样(如 `1．`、`2.`、`(1)`),不要识别题目边界。\n"
    "4. 不要识别 bbox、不要判断题型、不要生成答案字段、不要解释或纠错。\n"
    "5. 不要补全、不要合并多页。\n"
    "6. 直接输出该页的纯文本,不要 JSON、不要 Markdown 代码围栏、不要任何前言或结论。\n"
    "7. 评分点后的虚线点串(⋯⋯/……/.....)不要逐点抄录,省略为一个「……」即可;\n"
    "   分值标注(如 (1分))保留。\n"
)

# --- OCR 截断守卫（2026-08-19 闵行 Q23(2) 根因）-------------------------------
# qwen3.5-ocr 对长而密的公式页（官方解答页）会在输出中段悄悄截断：观测特征是
# 1) 行内公式定界符 ``$`` 计数为奇数（有一个 ``$`` 没闭合）；2) 代码围栏或 \begin/\end
# 环境不闭合。截断的页文本会让整卷转写模型把真实存在的内容标成
# 「未出现在所给逐页文本中」，因此必须在页文本层确定性检出。


def looks_truncated(text: str) -> bool:
    """页文本是否带有 OCR 输出截断的确定性特征。

    空白文本不算（空文本由 ``empty_text`` 契约处理）。误报的代价只是多跑
    一次条带降级，漏报的代价是解答内容静默丢失，所以判定从严。
    """
    if not text or not text.strip():
        return False
    if text.count("```") % 2 == 1:
        return True
    if text.count("\\begin{") != text.count("\\end{"):
        return True
    # 行内公式定界：去掉代码围栏内容后 ``$`` 必须成对。
    outside_fence = re.sub(r"```.*?```", "", text, flags=re.S)
    if outside_fence.count("$") % 2 == 1:
        return True
    # 不能把尾部省略号/评分点虚线单独当作截断：横条带经常恰好裁在答案
    # 分值点线上，完整页也可能以这类点串结束。没有未闭合结构时应放行。
    return False


# 选项标签:（A）/(A)/A./A、/A． 形式(与 audit_staging 的 EMBEDDED_CHOICE_LABEL
# 同源口径;数字标签要求后不接数字,排除 3.14 这类选项正文)。
_OPTION_LABEL_RE = re.compile(
    r"[（(]\s*(?:[A-Da-d]|[0-3])\s*[）)]"
    r"|(?:\b[A-Da-d])\s*[、．.]"
    r"|(?:\b[0-3])\s*\.(?!\d)"
)
# 行首题号:1./1．/1、/1␣ 形式(最多两位;不匹配 2020.1 这类年份——两位回溯
# 后无分隔符即不命中)。
_QUESTION_NUMBER_RE = re.compile(r"^(\d{1,2})\s*[.．、]\s*", re.M)


def _labels_in_order(text: str) -> list[int]:
    values: list[int] = []
    for match in _OPTION_LABEL_RE.finditer(text):
        token = match.group(0)
        glyph = next(ch for ch in token if ch.isalnum())
        values.append(int(glyph) if glyph.isdigit() else ord(glyph.upper()) - ord("A"))
    return values


def find_sequence_gaps(text: str) -> list[str]:
    """行内内容缺失的确定性信号:枚举序列跳号。

    OCR 可以把一行的中段悄悄丢掉而结构完全闭合(2026-08-19 黄浦 002.png:
    第 5 题选项行只剩 (A)(B)(D),(C) 整个消失,``$`` 依然成对、收尾干净,
    :func:`looks_truncated` 对此天然失明)。枚举序列不会合法跳号:

    - 选项标签序列 A..D / 0..3 内出现跳号(如 A,B,D 缺 C);
    - 行首题号序列内出现跳号(如 5→7 缺 6,源真缺题的情形由 staging 层的
      missing-questions.yaml 声明豁免;这里只负责触发条带降级尽力找回)。
    """
    issues: list[str] = []
    option_values = _labels_in_order(text)
    for prev, following in zip(option_values, option_values[1:]):
        if prev < following and following - prev > 1 and following <= 3:
            missing = ", ".join(
                chr(ord("A") + v) for v in range(prev + 1, following)
            )
            issues.append(f"choice labels skip {missing}")
            break
    numbers = [int(m.group(1)) for m in _QUESTION_NUMBER_RE.finditer(text)]
    for prev, following in zip(numbers, numbers[1:]):
        if prev < following and following - prev > 1 and following <= 30:
            issues.append(
                f"question numbers skip {prev + 1}-{following - 1}"
                if following - prev > 2
                else f"question numbers skip {prev + 1}"
            )
            break
    return issues


_FENCE_LINE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*$")


def strip_code_fences(text: str) -> str:
    """去掉模型违反提示词加上的 ```/```latex 围栏行，只保留内容。

    围栏不是页面内容:围栏不闭合会让 :func:`looks_truncated` 误判,围栏内
    才是真正的抄录文本(2026-08-19 闵行答案页输出实测)。未配对的围栏行也
    一并移除(内容保留)。
    """
    lines = [line for line in text.splitlines() if not _FENCE_LINE_RE.match(line)]
    return "\n".join(lines)


_SHA_PREFIX_RE = re.compile(r"^sha256:")

# Markers of a "role leak": the model echoed the OCR persona / asked for the image
# instead of transcribing it (observed with MiMo vision on some pages). These short
# strings are the persona the prompt assigns ("你是数学试卷逐页 OCR 抄录器"), reflected
# back as "我是…", plus the canonical "please provide the image" refusal. A real page
# transcript never contains them, so a hit means the provider produced no usable text.
_ROLE_LEAK_MARKERS = (
    "我是数学试卷逐页 OCR 抄录器",
    "我是数学试卷逐页OCR抄录器",
    "请提供图片",
    "请提供需要处理的图片",
    "请提供试卷图片",
)


def is_role_leak_response(text: str | None) -> bool:
    """True when ``text`` is a persona echo / image request, not a page transcript.

    Vision OCR models occasionally reply with the assistant persona assigned by the
    prompt ("我是数学试卷逐页 OCR 抄录器…请提供图片") instead of reading the page. Such a
    reply is non-empty (so it bypasses the blank-text guard) but carries zero page
    content; treating it as ``invalid_response`` lets the workflow fail the page loudly
    rather than silently dropping its coverage.
    """

    if not text:
        return False
    return any(marker in text for marker in _ROLE_LEAK_MARKERS)


def image_to_data_url(path: Path) -> tuple[str, str]:
    """Return ``(data_url, media_type)`` for a page image (PNG default)."""

    suffix = path.suffix.lower()
    media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    data = path.read_bytes()
    url = f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
    return url, media_type


def build_messages(image_data_url: str) -> list[dict]:
    """OpenAI-style multimodal chat messages for one page image + OCR prompt."""

    return [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": PAGE_TEXT_PROMPT},
            ],
        }
    ]


def commit_extract(
    *,
    job: PageTextJob,
    text: str,
    store,
    model: str,
    adapter_id: str,
    prompt_version: str,
    cache_hit: bool,
    ocr_enhancement: str | None = None,
    ocr_suspect: list[str] | None = None,
) -> PageTextExtract:
    """Commit ``page-NNN.txt`` + sidecar and return the typed extract."""

    text_ref = store.commit_text(
        f"pages/page-{job.page_number:03d}.txt", text, "text/plain"
    )
    sidecar = {
        "page_number": job.page_number,
        "run_id": job.run_id,
        "paper_id": job.paper_id,
        "source_image": job.image.model_dump(mode="json"),
        "input_fingerprint": job.input_fingerprint,
        "model": model,
        "adapter_id": adapter_id,
        "prompt_version": prompt_version,
        "cache_hit": cache_hit,
    }
    if ocr_enhancement is not None:
        sidecar["ocr_enhancement"] = ocr_enhancement
    if ocr_suspect:
        sidecar["ocr_suspect"] = ocr_suspect
    side_ref = store.commit_yaml(
        f"pages/page-{job.page_number:03d}.extract.yaml",
        sidecar,
        "page-text-extract/v1",
    )
    return PageTextExtract(
        artifact=PageTextArtifact(
            page_number=job.page_number,
            text=text_ref,
            metadata=side_ref,
            provenance=ExecutionProvenance(
                adapter_id=adapter_id, model=model, prompt_version=prompt_version
            ),
        )
    )
