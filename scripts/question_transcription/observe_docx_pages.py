#!/usr/bin/env python3
"""Observe rendered DOCX pages in batched multimodal windows.

Two entry points coexist during the index-rollout:

* :func:`observe` (new) — driven by a ``math_question_span_index/v1``. The span
  index fixes exactly which pages each first-round batch sees and which question
  refs it must return, so the provider no longer自由发现题目. Missing / unexpected
  / duplicate refs trigger a定点补读 (targeted repair) of just the affected
  question; already-good questions are frozen and never re-run. This is the path
  ``docs/question-span-index-redesign.md`` §7.2 prescribes.
* :func:`observe_windows` (legacy) — the old overlapping-window flow with the
  OOXML 全文 hint. Retained for one migration cycle and prints a deprecation
  notice; ``--overlap`` is no longer honoured (a non-zero value hard-errors).

The provider boundary is unchanged: a callable receives ``prompt`` and
``image_paths`` keyword arguments and returns a mapping. Tests inject a
deterministic fake; production uses MiMo for mathematical transcription.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxPage,
    DocxWindowObservation,
)
from scripts.question_transcription.question_span_index import (  # noqa: E402
    ObservationBatch,
    QuestionSpanIndex,
    build_observation_batches,
    load_index,
)

ProviderCallable = Callable[..., Mapping[str, Any]]

_BAILIAN_TYPE_MAP = {
    "选择题": "choice",
    "填空题": "fill_blank",
    "简答题": "short_answer",
    "问答题": "problem",
    "解答题": "problem",
    "计算题": "problem",
    "证明题": "problem",
}

_CHOICE_LABEL = re.compile(
    r"^\s*(?:(?P<plain>[A-Da-d]|[0-3])\s*[.、．]\s*|"
    r"[（(]\s*(?P<paren>[A-Da-d]|[0-3])\s*[）)]\s*)(?P<body>.*)$",
    re.DOTALL,
)


def _strip_ordered_choice_labels(choices: Sequence[Any]) -> list[Any]:
    """Remove provider-added A-D/0-3 labels only when the full sequence agrees.

    Requiring all four ordered labels avoids rewriting a legitimate option body
    that merely begins with a letter followed by punctuation.
    """
    if len(choices) != 4:
        return list(choices)
    if all(isinstance(choice, Mapping) for choice in choices):
        labels = [str(choice.get("label") or "").strip().upper() for choice in choices]
        bodies = [choice.get("content") for choice in choices]
        if labels in (["A", "B", "C", "D"], ["0", "1", "2", "3"]) and all(
            isinstance(body, str) and body.strip() for body in bodies
        ):
            return [body.strip() for body in bodies]
        return list(choices)
    if not all(isinstance(choice, str) for choice in choices):
        return list(choices)
    matches = [_CHOICE_LABEL.match(choice) for choice in choices]
    if any(match is None for match in matches):
        return list(choices)
    labels = [
        (match.group("plain") or match.group("paren")).upper()  # type: ignore[union-attr]
        for match in matches
    ]
    if labels not in (["A", "B", "C", "D"], ["0", "1", "2", "3"]):
        return list(choices)
    return [match.group("body").strip() for match in matches]  # type: ignore[union-attr]


def _normalize_text_items(value: Any, *, mapping_keys: Sequence[str]) -> Any:
    """Normalize provider wrapper objects without changing their text."""
    if not isinstance(value, list):
        return value
    normalized: list[Any] = []
    for item in value:
        if not isinstance(item, Mapping):
            normalized.append(item)
            continue
        text = next(
            (
                item.get(key)
                for key in mapping_keys
                if isinstance(item.get(key), str) and item.get(key).strip()
            ),
            None,
        )
        normalized.append(text.strip() if isinstance(text, str) else item)
    return normalized


def make_mimo_provider(client: Any) -> ProviderCallable:
    """Wrap ``MimoClient.complete_json`` behind the observation callable API."""

    def provider(*, prompt: str, image_paths: Sequence[Path]) -> Mapping[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        hashes: list[str] = []
        for path in image_paths:
            raw = path.read_bytes()
            hashes.append(hashlib.sha256(raw).hexdigest())
            suffix = path.suffix.lower()
            media_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
            encoded = base64.b64encode(raw).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                }
            )
        normalized, _ = client.complete_json(
            messages=[{"role": "user", "content": content}],
            cache_material={
                "task": "docx_math_page_observation",
                "prompt": prompt,
                "image_sha256": hashes,
            },
        )
        return normalized

    return provider


def make_bailian_ocr_provider(client: Any) -> ProviderCallable:
    """Wrap ``BailianOcrClient.complete_json`` behind the callable API."""

    def provider(*, prompt: str, image_paths: Sequence[Path]) -> Mapping[str, Any]:
        content: list[dict[str, Any]] = []
        hashes: list[str] = []
        for path in image_paths:
            raw = path.read_bytes()
            hashes.append(hashlib.sha256(raw).hexdigest())
            suffix = path.suffix.lower()
            media_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
            encoded = base64.b64encode(raw).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                    "min_pixels": 32 * 32 * 3,
                    "max_pixels": 32 * 32 * 8192,
                }
            )
        content.append({"type": "text", "text": prompt})
        normalized, _ = client.complete_json(
            messages=[{"role": "user", "content": content}],
            cache_material={
                "task": "docx_page_ocr_observation",
                "prompt": prompt,
                "image_sha256": hashes,
            },
        )
        return normalized

    return provider


def _native_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return str(value.get("text") or "").strip()
    return ""


def _native_text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [text for item in value if (text := _native_text(item))]


def _explicit_answer(texts: Sequence[str]) -> str:
    for text in reversed(texts):
        matches = re.findall(r"(?:答案|答)\s*[：:]\s*([^\n。；;]+)", text)
        if matches:
            return matches[-1].strip()
    return texts[-1] if texts else "原卷本页未显示答案"


def normalize_bailian_ocr_response(
    raw: Mapping[str, Any],
    *,
    pages: Sequence[DocxPage],
) -> dict[str, Any]:
    """Convert Qwen3.5-OCR's native exam JSON into our strict contract.

    Qwen3.5-OCR does not support structured-output mode.  Its native exam
    response includes ``question/stem/option/answer`` plus OCR positioning.
    Positions are intentionally discarded: DOCX assets come from OOXML media,
    and page evidence is the only permitted evidence type here.
    """
    if "questions" in raw:
        return dict(raw)
    native_keys = {"question", "stem", "option", "answer", "type"}
    if not native_keys.issubset(raw):
        return dict(raw)
    if len(pages) != 1:
        raise ValueError(
            "BaiLian native exam JSON can only be normalized for one page; "
            "run DOCX OCR with --window-size 1 --overlap 0"
        )

    page = pages[0]
    stem = _native_text(raw.get("question")) or _native_text(raw.get("stem"))
    match = re.match(r"\s*(\d+)", stem)
    if not match:
        raise ValueError("BaiLian native exam JSON has no leading question number")
    question_ref = match.group(1)
    type_label = _native_text(raw.get("type")) or "问答题"
    question_type = _BAILIAN_TYPE_MAP.get(type_label, "problem")
    choices = _native_text_list(raw.get("option"))
    answer_texts = _native_text_list(raw.get("answer"))
    page_evidence = {
        "kind": "page",
        "source": page.source,
        "page_number": page.page_number,
    }
    solution_steps = answer_texts if question_type in {"problem", "short_answer"} else []
    if question_type in {"problem", "short_answer"} and not solution_steps:
        solution_steps = ["原卷本页未显示解答，需与后续页合并复核。"]

    normalized = {
        key: raw[key]
        for key in ("schema", "window_id", "pages", "provider")
        if key in raw
    }
    normalized["questions"] = [
        {
            "question_ref": question_ref,
            "question_number": int(question_ref),
            "question_type": question_type,
            "points": 0,
            "section_ref": "ocr-import",
            "section_title": type_label,
            "content": {
                "stem_latex": stem,
                "choices": choices,
                "answer": _explicit_answer(answer_texts),
                "clue": "原卷未提供提示",
                "solution_steps": solution_steps,
                "solution_notes": [
                    "百炼 Qwen3.5-OCR 原生结果已确定性适配；公式与跨页边界需复核。"
                ],
            },
            "evidence": {
                "question": [page_evidence],
                "solution": [page_evidence],
                "solution_start_anchor": "OCR answer",
                "solution_end_anchor": "page end",
            },
            "transcription_confidence": {
                "stem": "medium",
                "formula": "medium",
                "solution_steps": "medium",
            },
        }
    ]
    return normalized


def normalize_observation_field_shapes(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize harmless provider shape drift without rewriting content."""
    normalized = dict(raw)
    question_keys = {
        "question_ref",
        "question_number",
        "question_type",
        "points",
        "section_ref",
        "section_title",
        "content",
        "evidence",
        "transcription_confidence",
    }
    if "questions" not in normalized and {
        "question_ref",
        "content",
        "evidence",
    }.issubset(normalized):
        question = {
            key: normalized.pop(key)
            for key in list(normalized)
            if key in question_keys
        }
        normalized["questions"] = [question]
    questions = normalized.get("questions")
    if not isinstance(questions, list):
        return normalized

    section_titles = {
        "choice": "选择题",
        "fillin": "填空题",
        "short_answer": "解答题",
        "problem": "解答题",
    }
    normalized_questions: list[Any] = []
    for item in questions:
        if not isinstance(item, Mapping):
            normalized_questions.append(item)
            continue
        question = dict(item)
        number = question.get("question_number")
        if isinstance(number, str) and number.strip().isdigit():
            question["question_number"] = int(number)
        points = question.get("points")
        if points is None or (isinstance(points, str) and not points.strip()):
            question["points"] = 0
        elif isinstance(points, str) and points.strip().isdigit():
            question["points"] = int(points.strip())

        question_type = str(question.get("question_type") or "")
        if question_type == "fill_blank":
            question_type = "fillin"
            question["question_type"] = question_type
        if not str(question.get("section_ref") or "").strip():
            question["section_ref"] = f"section-{question_type or 'questions'}"
        if not str(question.get("section_title") or "").strip():
            question["section_title"] = section_titles.get(question_type, "试题")

        content_value = question.get("content")
        if isinstance(content_value, Mapping):
            content = dict(content_value)
            for field in ("choices", "solution_steps", "solution_notes"):
                value = content.get(field)
                if value is None or value == "":
                    content[field] = []
                elif isinstance(value, str):
                    content[field] = [value]
            content["solution_steps"] = _normalize_text_items(
                content.get("solution_steps"), mapping_keys=("step", "content", "text")
            )
            content["solution_notes"] = _normalize_text_items(
                content.get("solution_notes"), mapping_keys=("note", "content", "text")
            )
            choices = content.get("choices")
            if isinstance(choices, list):
                content["choices"] = _strip_ordered_choice_labels(choices)
            for field in ("stem_latex", "answer"):
                value = content.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    content[field] = None
            if not str(content.get("clue") or "").strip():
                content["clue"] = "原卷未提供提示"
            question["content"] = content
        evidence_value = question.get("evidence")
        if isinstance(evidence_value, Mapping):
            evidence = dict(evidence_value)
            for field in ("question", "solution"):
                if evidence.get(field) is None:
                    evidence[field] = []
            for field in ("solution_start_anchor", "solution_end_anchor"):
                value = evidence.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    evidence[field] = None
            question["evidence"] = evidence
        normalized_questions.append(question)

    normalized["questions"] = normalized_questions
    return normalized


def build_windows(page_numbers: Sequence[int], *, size: int = 3, overlap: int = 1) -> list[list[int]]:
    """Return deterministic overlapping windows, without a short duplicate tail.

    .. deprecated::
        Retained for one migration cycle. The span-index flow
        (:func:`observe` + :func:`build_observation_batches`) replaces this with
        non-overlapping first-round batches; ``overlap`` is no longer honoured
        there.
    """
    if size < 1:
        raise ValueError("window size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    numbers = list(page_numbers)
    if not numbers:
        return []
    step = size - overlap
    result: list[list[int]] = []
    for start in range(0, len(numbers), step):
        window = numbers[start : start + size]
        if result and window and window[-1] <= result[-1][-1]:
            break
        result.append(window)
        if start + size >= len(numbers):
            break
    return result


def discover_pages(
    word_source_path: Path,
    *,
    source_archive: str,
    source_subdir: str = "word",
    page_number_offset: int = 0,
) -> list[DocxPage]:
    """Describe immutable PNG pages next to ``word-source.yaml``."""
    if page_number_offset < 0:
        raise ValueError("page_number_offset must be non-negative")
    source_subdir = source_subdir.strip().strip("/")
    if not source_subdir:
        raise ValueError("source_subdir must be non-empty")
    pages_dir = word_source_path.parent / "pages"
    paths = sorted(pages_dir.glob("*.png"))
    if not paths:
        raise ValueError(f"no rendered PNG pages found under {pages_dir}")
    pages: list[DocxPage] = []
    for path in paths:
        try:
            local_page_number = int(path.stem)
        except ValueError as exc:
            raise ValueError(f"page filename must be numeric: {path.name}") from exc
        page_number = local_page_number + page_number_offset
        raw = path.read_bytes()
        with Image.open(path) as image:
            width, height = image.size
        pages.append(
            DocxPage(
                page_number=page_number,
                source=(
                    f"{source_archive.rstrip('/')}/{source_subdir}/pages/{path.name}"
                ),
                width_px=width,
                height_px=height,
                sha256=f"sha256:{hashlib.sha256(raw).hexdigest()}",
            )
        )
    return pages


def _paragraph_hint(word_source: Mapping[str, Any], *, max_chars: int = 12000) -> str:
    """Concatenate OOXML paragraph text as a positioning hint (legacy).

    .. deprecated::
        The span-index flow deliberately does NOT inject the OOXML 全文 — it was
        a串线 source (every window saw the same 12000-char prefix). Retained only
        for :func:`observe_windows`.
    """
    texts = [
        str(p.get("text") or "").strip()
        for p in (word_source.get("paragraphs") or [])
        if isinstance(p, Mapping) and str(p.get("text") or "").strip()
    ]
    return "\n".join(texts)[:max_chars]


def _prompt(window: Sequence[DocxPage], paragraph_hint: str) -> str:
    """Build the legacy overlapping-window prompt (includes the OOXML hint).

    .. deprecated:: use :func:`_batch_prompt` with the span-index flow instead.
    """
    page_map = "\n".join(
        f"- 第 {index} 张图 = page_number {page.page_number}, source={page.source}"
        for index, page in enumerate(window, start=1)
    )
    return (
        "你是数学试卷多模态转录器。输入图像由 DOCX 渲染而来。"
        "只转录页面上真实可见的题干、选项、答案、分析/提示和原解答；"
        "公式必须转为 LaTeX。不要返回 bbox，不要描述插图，不要补写不存在的解法。"
        "只返回一个合法 JSON 对象，不要 Markdown 代码围栏。"
        "JSON 顶层必须是 {\"questions\": [...]}，绝不能把单题或 content 字段直接放在顶层。"
        "每个窗口允许只看到题干或只看到解答，"
        "但不得把题干页伪装成解答证据，也不得补写不可见的解答。"
        "每题严格包含 question_ref、question_number、"
        "question_type、points、section_ref、section_title、content、evidence、"
        "transcription_confidence。content 严格包含 stem_latex、choices、answer、"
        "clue、solution_steps、solution_notes；若页面没有提示文字，clue 写“原卷未提供提示”。"
        "当前窗口不可见的 stem_latex/answer 写 null，不可见的 choices/solution_steps/"
        "solution_notes 写空数组。"
        "evidence 严格包含 question、solution、solution_start_anchor、solution_end_anchor；"
        "question 和 solution 的每一项只含 kind=\"page\"、source、page_number。"
        "当前窗口未显示对应角色时 evidence 数组写空，未显示解答起止锚点时 anchor 写 null。"
        "只要 solution 非空，两个 anchor 就必须抄录该窗口图像中解答起点和结束边界处"
        "真实可见的短文本（题号、【解析】、公式或末句均可），不得留空或概括改写。"
        "transcription_confidence 的 stem、formula、solution_steps 只能为 high/medium/low。"
        "question_type 只能为 choice、fillin、short_answer、problem；"
        "页面未标分时 points 必须写整数 0；section_ref 和 section_title 不得为空；"
        "choices、solution_steps、solution_notes 必须始终是 JSON 数组，即使只有一项或为空。"
        "question_ref 使用原卷题号，不创建 Q001。"
        "重叠窗口中只报告当前图像可见或跨图连续的题；无法确认的字符不要猜，"
        "在 solution_notes 中注明疑点并降低对应 confidence。\n"
        "图像与页面对应关系：\n"
        f"{page_map}\n"
        "下面的 OOXML 文本只作定位提示，最终内容必须以页面图像为准：\n"
        f"{paragraph_hint}"
    )


def _cache_key(
    pages: Sequence[DocxPage], *, provider_name: str, provider_version: str, prompt_version: str
) -> str:
    payload = {
        # Include page identity as well as bytes: two visually identical blank
        # pages are still different positions in the document/window.
        "pages": [
            {"page_number": p.page_number, "source": p.source, "sha256": p.sha256}
            for p in pages
        ],
        "provider": provider_name,
        "provider_version": provider_version,
        "prompt_version": prompt_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def observe_windows(
    word_source_path: Path,
    *,
    source_archive: str,
    provider: ProviderCallable,
    provider_name: str,
    provider_version: str,
    provider_kind: str = "vision_api",
    prompt_version: str = "docx-observation-v1",
    window_size: int = 3,
    overlap: int = 1,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    source_subdir: str = "word",
    page_number_offset: int = 0,
) -> list[DocxWindowObservation]:
    """Legacy overlapping-window observation flow (now deprecated)."""
    word_source = yaml.safe_load(word_source_path.read_text(encoding="utf-8"))
    if not isinstance(word_source, Mapping):
        raise ValueError("word-source root must be a mapping")
    if word_source.get("schema") != "math_word_source_extract/v1":
        raise ValueError("word-source schema must be math_word_source_extract/v1")

    pages = discover_pages(
        word_source_path,
        source_archive=source_archive,
        source_subdir=source_subdir,
        page_number_offset=page_number_offset,
    )
    if page_start is not None:
        pages = [page for page in pages if page.page_number >= page_start]
    if page_end is not None:
        pages = [page for page in pages if page.page_number <= page_end]
    if not pages:
        raise ValueError("selected page range contains no rendered pages")
    pages_by_number = {p.page_number: p for p in pages}
    physical_by_number = {
        int(path.stem) + page_number_offset: path
        for path in sorted((word_source_path.parent / "pages").glob("*.png"))
    }
    hint = _paragraph_hint(word_source)
    observations: list[DocxWindowObservation] = []
    for numbers in build_windows([p.page_number for p in pages], size=window_size, overlap=overlap):
        window_pages = [pages_by_number[n] for n in numbers]
        window_id = f"pages-{numbers[0]:03d}-{numbers[-1]:03d}"
        key = _cache_key(
            window_pages,
            provider_name=provider_name,
            provider_version=provider_version,
            prompt_version=prompt_version,
        )
        cache_path = cache_dir / f"{key}.json" if cache_dir else None
        if cache_path and cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            raw = dict(
                provider(
                    prompt=_prompt(window_pages, hint),
                    image_paths=[physical_by_number[n] for n in numbers],
                )
            )
            raw.setdefault("schema", "math_docx_window_observation/v1")
            raw.setdefault("window_id", window_id)
            raw.setdefault("pages", [p.model_dump() for p in window_pages])
            raw.setdefault(
                "provider",
                {"kind": provider_kind, "name": provider_name, "version": provider_version},
            )
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
        raw = normalize_bailian_ocr_response(raw, pages=window_pages)
        raw = normalize_observation_field_shapes(raw)
        observation = DocxWindowObservation.model_validate(raw)
        observations.append(observation)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{observation.window_id}.yaml"
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                yaml.safe_dump(
                    observation.model_dump(by_alias=True, exclude_none=True),
                    allow_unicode=True,
                    sort_keys=False,
                    width=1000,
                ),
                encoding="utf-8",
            )
            temporary.replace(path)
    return observations


# --------------------------------------------------------------------------- #
# Span-index-driven observation (§7.1 / §7.2)
# --------------------------------------------------------------------------- #

SPAN_INDEX_PROMPT_VERSION = "docx-observation-v2"


def _validate_span_index(
    index: QuestionSpanIndex,
    *,
    source_kind: str,
    page_sha_by_number: Mapping[int, str],
    source_sha256: str | None,
    page_number_offset: int,
) -> None:
    """Reject an index that does not match the current input (§7.1)."""
    if index.source_kind != source_kind:
        raise ValueError(
            f"span index source_kind {index.source_kind!r} != expected {source_kind!r}"
        )
    if index.status != "ready":
        raise ValueError(
            f"span index status must be 'ready' for observation, got {index.status!r}"
        )
    if index.fingerprint.page_number_offset != page_number_offset:
        raise ValueError(
            f"span index page_number_offset {index.fingerprint.page_number_offset} "
            f"!= input offset {page_number_offset}"
        )
    if source_sha256 and index.fingerprint.source_sha256:
        if index.fingerprint.source_sha256 != source_sha256:
            raise ValueError("span index source SHA does not match the input PDF")
    # Every page the index references must be present with a matching SHA.
    index_page_sha = {
        number: sha for number, sha in zip(index.page_numbers, index.fingerprint.page_sha256)
    }
    for number, sha in page_sha_by_number.items():
        if number not in index_page_sha:
            raise ValueError(f"page {number} is missing from the span index")
        if index_page_sha[number] != sha:
            raise ValueError(
                f"span index page {number} SHA does not match the rendered page"
            )


def _batch_prompt(
    batch: ObservationBatch,
    window_pages: Sequence[DocxPage],
) -> str:
    """Build the per-batch prompt for the span-index flow (§7.1).

    The prompt carries the真实 page_number mapping, the exact expected question
    refs, the single batch role, each question's role-internal page set, and the
    "只返回预期题号;不得创建/合并/借用" constraint. It does NOT contain the OOXML
    全文.
    """
    page_map = "\n".join(
        f"- 第 {index} 张图 = page_number {page.page_number}, source={page.source}"
        for index, page in enumerate(window_pages, start=1)
    )
    expected = ", ".join(batch.expected_question_refs)
    role_label = "题干" if batch.role == "question" else "官方解答"
    role_rule = (
        "本批只要求转录题干(stem_latex/choices);不可见的解答字段写 null/[]。"
        if batch.role == "question"
        else "本批只要求转录官方解答(answer/solution_steps);不可见的题干字段写 null/[]。"
    )
    return (
        "你是数学试卷多模态转录器。输入图像由 DOCX 渲染而来。"
        "只转录页面上真实可见的内容,公式必须转为 LaTeX。不要返回 bbox,不要描述插图,"
        "不要补写不存在的解法。只返回一个合法 JSON 对象,不要 Markdown 代码围栏。"
        "JSON 顶层必须是 {\"questions\": [...]}。"
        f"本批统一角色:{role_label}。{role_rule}\n"
        f"本批必须且只能返回以下预期题号:{expected}。"
        "只返回预期题号;不得创建、合并、借用、拆分或省略任何题号。"
        "若某预期题号在本批页面确实不可见,仍必须为它返回一个 question_ref 正确的占位条目,"
        "并在 solution_notes 注明\"本批未见\",以便定点补读,绝不能遗漏题号或臆造内容。\n"
        "每个题目对象严格包含 question_ref、question_number、question_type、points、"
        "section_ref、section_title、content、evidence、transcription_confidence。"
        "content 含 stem_latex、choices、answer、clue、solution_steps、solution_notes;"
        "evidence 含 question、solution、solution_start_anchor、solution_end_anchor,"
        "其中 question/solution 每项只含 kind=\"page\"、source、page_number。"
        "question_ref 使用原卷题号,不创建 Q001。\n"
        "图像与页面对应关系:\n"
        f"{page_map}"
    )


def _question_refs(raw: Mapping[str, Any]) -> list[str]:
    return [
        str(q.get("question_ref"))
        for q in (raw.get("questions") or [])
        if isinstance(q, Mapping) and q.get("question_ref") is not None
    ]


def _repair_key(
    batch: ObservationBatch,
    *,
    provider_name: str,
    provider_version: str,
    prompt_version: str,
) -> str:
    payload = {
        "batch_id": batch.batch_id,
        "role": batch.role,
        "pages": batch.page_numbers,
        "expected": batch.expected_question_refs,
        "provider": provider_name,
        "provider_version": provider_version,
        "prompt_version": prompt_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _select_question(raw: Mapping[str, Any], ref: str) -> dict[str, Any] | None:
    """Return the (single) question dict for ``ref`` from a provider payload."""
    matches = [
        q
        for q in (raw.get("questions") or [])
        if isinstance(q, Mapping) and str(q.get("question_ref")) == ref
    ]
    if len(matches) == 1:
        return dict(matches[0])  # type: ignore[return-value]
    return None


def _finalize_batch_observation(
    batch: ObservationBatch,
    frozen: dict[str, Mapping[str, Any]],
    *,
    window_pages: Sequence[DocxPage],
    provider_name: str,
    provider_version: str,
    provider_kind: str,
    prompt_version: str,
) -> DocxWindowObservation:
    """Assemble a validated :class:`DocxWindowObservation` from frozen questions."""
    raw: dict[str, Any] = {
        "schema": "math_docx_window_observation/v1",
        "window_id": batch.batch_id,
        "pages": [p.model_dump() for p in window_pages],
        "provider": {"kind": provider_kind, "name": provider_name, "version": provider_version},
        "questions": [dict(frozen[ref]) for ref in batch.expected_question_refs],
    }
    raw = normalize_observation_field_shapes(raw)
    return DocxWindowObservation.model_validate(raw)


def _observe_batch(
    batch: ObservationBatch,
    *,
    window_pages: Sequence[DocxPage],
    image_paths: Sequence[Path],
    provider: ProviderCallable,
    provider_name: str,
    provider_version: str,
    provider_kind: str,
    prompt_version: str,
    max_repairs: int = 1,
    repair_dir: Path | None = None,
    repair_log: list[dict[str, Any]] | None = None,
) -> DocxWindowObservation:
    """Observe one batch with freeze + targeted repair (§7.1).

    Returns a validated observation whose questions exactly equal the batch's
    expected refs. Raises :class:`ValueError` if a blocking mismatch cannot be
    repaired within ``max_repairs``. Before that, no normal observation file is
    produced (the caller only writes after this returns).
    """
    expected_refs = list(batch.expected_question_refs)
    prompt = _batch_prompt(batch, window_pages)

    raw = dict(provider(prompt=prompt, image_paths=image_paths))
    frozen: dict[str, Mapping[str, Any]] = {}
    history: list[dict[str, Any]] = []

    def _record(stage: str, payload_raw: Mapping[str, Any] | None, diffs: Mapping[str, Any]) -> None:
        # Never persist secrets: only question refs and sanitized diffs.
        history.append(
            {
                "stage": stage,
                "returned_refs": _question_refs(payload_raw) if payload_raw else [],
                **{k: sorted(v) for k, v in diffs.items()},
            }
        )

    def _classify(payload_raw: Mapping[str, Any]) -> tuple[set[str], set[str], set[str], set[str]]:
        refs = _question_refs(payload_raw)
        counts: dict[str, int] = {}
        for ref in refs:
            counts[ref] = counts.get(ref, 0) + 1
        returned = set(refs)
        missing = set(expected_refs) - returned
        unexpected = returned - set(expected_refs)
        duplicate = {ref for ref, count in counts.items() if count > 1}
        good = {ref for ref in expected_refs if ref in returned and ref not in duplicate and counts.get(ref, 0) == 1}
        return missing, unexpected, duplicate, good

    missing, unexpected, duplicate, good = _classify(raw)
    _record("first_round", raw, {"missing": missing, "unexpected": unexpected, "duplicate": duplicate})

    # Freeze the questions that are exactly right; they are never re-run.
    for ref in sorted(good):
        question = _select_question(raw, ref)
        if question is not None:
            frozen[ref] = question

    repairs_done = 0
    while True:
        outstanding = [ref for ref in expected_refs if ref not in frozen]
        if not outstanding:
            break
        if repairs_done >= max_repairs:
            detail = (
                f"batch {batch.batch_id} could not be repaired within "
                f"{max_repairs} attempt(s); still missing/duplicated: {sorted(outstanding)}"
            )
            if repair_dir is not None:
                _atomic_write_repair_meta(
                    repair_dir / f"{batch.batch_id}.repair.yaml",
                    batch=batch,
                    prompt_version=prompt_version,
                    frozen_refs=sorted(frozen),
                    history=history,
                    status="blocking",
                    detail=detail,
                )
            if repair_log is not None:
                repair_log.append({"batch_id": batch.batch_id, "status": "blocking", "detail": detail})
            raise ValueError(detail)
        repairs_done += 1

        # Targeted repair: only the outstanding question(s). §7.1 rules 3-5: the
        # repair prompt's expected set is exactly the missing/duplicate refs, and
        # the page set is the batch's pages (the index already narrowed them).
        repair_batch = ObservationBatch(
            batch_id=f"{batch.batch_id}-repair-{repairs_done}",
            role=batch.role,
            page_numbers=list(batch.page_numbers),
            expected_question_refs=outstanding,
        )
        repair_raw = dict(provider(prompt=_batch_prompt(repair_batch, window_pages), image_paths=image_paths))
        r_missing, r_unexpected, r_duplicate, r_good = _classify(repair_raw)
        _record(
            f"repair_{repairs_done}",
            repair_raw,
            {"missing": r_missing, "unexpected": r_unexpected, "duplicate": r_duplicate},
        )
        # Isolate unexpected payloads: they never enter the candidate pool.
        for ref in sorted(r_good):
            question = _select_question(repair_raw, ref)
            if question is not None:
                frozen[ref] = question

    observation = _finalize_batch_observation(
        batch,
        frozen,
        window_pages=window_pages,
        provider_name=provider_name,
        provider_version=provider_version,
        provider_kind=provider_kind,
        prompt_version=prompt_version,
    )
    if repair_dir is not None and (len(history) > 1 or any(h.get("missing") or h.get("unexpected") or h.get("duplicate") for h in history)):
        _atomic_write_repair_meta(
            repair_dir / f"{batch.batch_id}.repair.yaml",
            batch=batch,
            prompt_version=prompt_version,
            frozen_refs=sorted(frozen),
            history=history,
            status="repaired",
            detail="",
        )
    if repair_log is not None and repairs_done:
        repair_log.append({"batch_id": batch.batch_id, "status": "repaired", "repairs": repairs_done})
    return observation


def _atomic_write_repair_meta(
    path: Path,
    *,
    batch: ObservationBatch,
    prompt_version: str,
    frozen_refs: list[str],
    history: list[dict[str, Any]],
    status: str,
    detail: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_id": batch.batch_id,
        "role": batch.role,
        "page_numbers": batch.page_numbers,
        "expected_question_refs": batch.expected_question_refs,
        "prompt_version": prompt_version,
        "frozen_refs": frozen_refs,
        "history": history,
        "status": status,
        "detail": detail,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    tmp.replace(path)


def observe(
    word_source_path: Path,
    *,
    source_archive: str,
    span_index: QuestionSpanIndex,
    provider: ProviderCallable,
    provider_name: str,
    provider_version: str,
    provider_kind: str = "vision_api",
    prompt_version: str = SPAN_INDEX_PROMPT_VERSION,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
    target_batch_pages: int = 6,
    max_batch_pages: int = 8,
    target_batch_questions: int = 12,
    max_repairs: int = 1,
    source_subdir: str = "word",
    page_number_offset: int = 0,
) -> list[DocxWindowObservation]:
    """Observe DOCX pages driven by a span index (§7.2).

    Replaces the legacy overlapping-window flow. The span index fixes the batch
    plan (via :func:`build_observation_batches`); each first-round batch has a
    disjoint page set and an exact expected-ref set. The provider must return
    exactly those refs; missing / unexpected / duplicate refs trigger a定点补读
    of only the affected question while already-good questions stay frozen. A
    normal observation file is written only after a batch fully resolves, so a
    glob into ``output_dir`` never matches an unresolved batch.
    """
    word_source = yaml.safe_load(word_source_path.read_text(encoding="utf-8"))
    if not isinstance(word_source, Mapping):
        raise ValueError("word-source root must be a mapping")
    if word_source.get("schema") != "math_word_source_extract/v1":
        raise ValueError("word-source schema must be math_word_source_extract/v1")

    pages = discover_pages(
        word_source_path,
        source_archive=source_archive,
        source_subdir=source_subdir,
        page_number_offset=page_number_offset,
    )
    page_sha_by_number = {p.page_number: p.sha256 for p in pages}
    pages_by_number = {p.page_number: p for p in pages}
    physical_by_number = {
        int(path.stem) + page_number_offset: path
        for path in sorted((word_source_path.parent / "pages").glob("*.png"))
    }

    source_sha = None
    rendered_pdf = word_source.get("rendered_pdf")
    if isinstance(rendered_pdf, Mapping):
        source_sha = rendered_pdf.get("sha256")
    _validate_span_index(
        span_index,
        source_kind="docx",
        page_sha_by_number=page_sha_by_number,
        source_sha256=source_sha,
        page_number_offset=page_number_offset,
    )

    batches = build_observation_batches(
        span_index,
        target_page_count=target_batch_pages,
        hard_page_limit=max_batch_pages,
        target_question_count=target_batch_questions,
    )
    if not batches:
        raise ValueError("span index produced no observation batches")

    repair_dir = output_dir / "_repair" if output_dir is not None else None
    observations: list[DocxWindowObservation] = []
    repair_log: list[dict[str, Any]] = []
    for batch in batches:
        window_pages = [pages_by_number[n] for n in batch.page_numbers]
        image_paths = [physical_by_number[n] for n in batch.page_numbers]
        observation = _observe_batch(
            batch,
            window_pages=window_pages,
            image_paths=image_paths,
            provider=provider,
            provider_name=provider_name,
            provider_version=provider_version,
            provider_kind=provider_kind,
            prompt_version=prompt_version,
            max_repairs=max_repairs,
            repair_dir=repair_dir,
            repair_log=repair_log,
        )
        observations.append(observation)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{observation.window_id}.yaml"
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                yaml.safe_dump(
                    observation.model_dump(by_alias=True, exclude_none=True),
                    allow_unicode=True,
                    sort_keys=False,
                    width=1000,
                ),
                encoding="utf-8",
            )
            tmp.replace(path)
    if repair_dir is not None and repair_log:
        _atomic_write_repair_meta(
            repair_dir / "_summary.repair.yaml",
            batch=ObservationBatch(
                batch_id="_summary",
                role="question",
                page_numbers=[],
                expected_question_refs=[],
            ),
            prompt_version=prompt_version,
            frozen_refs=[],
            history=repair_log,
            status="summary",
            detail="",
        )
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description="Observe DOCX pages.")
    parser.add_argument("--word-source", type=Path, required=True)
    parser.add_argument("--source-archive", required=True)
    parser.add_argument(
        "--span-index",
        type=Path,
        default=None,
        help="math_question_span_index/v1 path. When given, the new span-index "
        "batch flow is used (recommended). Without it the legacy overlapping-"
        "window flow runs (deprecated).",
    )
    provider_group = parser.add_mutually_exclusive_group(required=True)
    provider_group.add_argument("--responses", type=Path, nargs="+")
    provider_group.add_argument("--mimo", action="store_true")
    provider_group.add_argument("--bailian-ocr", action="store_true")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    # New span-index flow knobs.
    parser.add_argument("--target-batch-pages", type=int, default=6)
    parser.add_argument("--max-batch-pages", type=int, default=8)
    parser.add_argument("--target-batch-questions", type=int, default=12)
    parser.add_argument("--max-repairs", type=int, default=1)
    # Legacy overlapping-window knobs (deprecation).
    parser.add_argument("--window-size", type=int)
    parser.add_argument("--overlap", type=int)
    parser.add_argument("--page-start", type=int)
    parser.add_argument("--page-end", type=int)
    parser.add_argument(
        "--source-subdir",
        default="word",
        help="evidence subdirectory below source archive (for example word-answers)",
    )
    parser.add_argument(
        "--page-number-offset",
        type=int,
        default=0,
        help="add this offset to local rendered page numbers",
    )
    args = parser.parse_args()

    queued = [json.loads(p.read_text(encoding="utf-8")) for p in (args.responses or [])]

    def _build_provider() -> tuple[ProviderCallable, str, str, str]:
        if args.mimo:
            from scripts.question_transcription.mimo_client import MimoClient

            client = MimoClient(cache_dir=args.cache_dir)
            return make_mimo_provider(client), "xiaomi-mimo", client.model, "vision_api"
        if args.bailian_ocr:
            from scripts.question_transcription.bailian_ocr_client import (
                BAILIAN_OCR_MODEL,
                BailianOcrClient,
            )

            provider_callable = make_bailian_ocr_provider(
                BailianOcrClient(cache_dir=args.cache_dir)
            )
            return provider_callable, "bailian-qwen-ocr", BAILIAN_OCR_MODEL, "ocr"

        def injected_provider(**_: Any) -> Mapping[str, Any]:
            if not queued:
                raise ValueError("not enough injected response files for batches")
            return queued.pop(0)

        return injected_provider, "injected", "v1", "manual"

    provider_callable, provider_name, provider_version, provider_kind = _build_provider()

    if args.span_index is not None:
        # New span-index flow. Bailian OCR formal downgrade is single-page only;
        # a multi-page batch must be rejected rather than faked.
        if args.bailian_ocr and args.max_batch_pages > 1:
            print(
                "ERROR: BaiLian OCR formal downgrade only supports single-page "
                "batches; use --max-batch-pages 1 or MiMo for multi-page batches.",
                file=sys.stderr,
            )
            return 2
        try:
            index = load_index(args.span_index)
            observations = observe(
                args.word_source,
                source_archive=args.source_archive,
                span_index=index,
                provider=provider_callable,
                provider_name=provider_name,
                provider_version=provider_version,
                provider_kind=provider_kind,
                cache_dir=args.cache_dir,
                output_dir=args.output_dir,
                target_batch_pages=args.target_batch_pages,
                max_batch_pages=args.max_batch_pages,
                target_batch_questions=args.target_batch_questions,
                max_repairs=args.max_repairs,
                source_subdir=args.source_subdir,
                page_number_offset=args.page_number_offset,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.responses and queued:
            raise ValueError("more response files than batches")
        print(
            f"DOCX BATCHES OBSERVED: batches={len(observations)} output={args.output_dir}"
        )
        return 0

    # Legacy overlapping-window flow (deprecated).
    import warnings

    warnings.warn(
        "observe_docx_pages without --span-index is deprecated and injects the "
        "OOXML 全文 hint; switch to the span-index flow.",
        DeprecationWarning,
        stacklevel=2,
    )
    if args.overlap is not None and args.overlap != 0:
        print(
            "ERROR: --overlap is no longer honoured; the span-index flow uses "
            "non-overlapping first-round batches. Pass --overlap 0 or migrate.",
            file=sys.stderr,
        )
        return 2
    window_size = args.window_size if args.window_size is not None else 3
    observations = observe_windows(
        args.word_source,
        source_archive=args.source_archive,
        provider=provider_callable,
        provider_name=provider_name,
        provider_version=provider_version,
        provider_kind=provider_kind,
        window_size=window_size,
        overlap=0,
        cache_dir=args.cache_dir,
        output_dir=args.output_dir,
        page_start=args.page_start,
        page_end=args.page_end,
        source_subdir=args.source_subdir,
        page_number_offset=args.page_number_offset,
    )
    if args.responses and queued:
        raise ValueError("more response files than page windows")
    print(f"DOCX WINDOWS OBSERVED: windows={len(observations)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
