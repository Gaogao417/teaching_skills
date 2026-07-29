"""DOCX multimodal observation, overlap merge, and transcription adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.adapt_docx_transcription import (  # noqa: E402
    adapt,
    adapt_for_review_staging,
)
from scripts.question_transcription.contracts import PaperMeta, QuestionTranscriptionBundle  # noqa: E402
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxWindowObservation,
)
from scripts.question_transcription.merge_docx_observations import (  # noqa: E402
    merge,
    merge_with_issues,
)
from scripts.question_transcription.observe_docx_pages import (  # noqa: E402
    build_windows,
    discover_pages,
    make_bailian_ocr_provider,
    make_mimo_provider,
    normalize_bailian_ocr_response,
    normalize_observation_field_shapes,
    observe_windows,
)
from scripts.question_transcription.bailian_ocr_client import (  # noqa: E402
    BAILIAN_OCR_MODEL,
    BailianOcrClient,
)


def _paper() -> PaperMeta:
    return PaperMeta.model_validate(
        {
            "id": "PAPER",
            "title": "测试试卷",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": "documents/test",
        }
    )


def _question(
    ref: str = "18",
    *,
    stem: str = "求$x$。",
    confidence: str = "high",
    question_pages: list[int] | None = None,
) -> dict:
    question_pages = question_pages or [1]
    return {
        "question_ref": ref,
        "question_number": int(ref),
        "question_type": "problem",
        "points": 4,
        "section_ref": "problems",
        "section_title": "解答题",
        "content": {
            "stem_latex": stem,
            "choices": [],
            "answer": "$x=1$",
            "clue": "移项。",
            "solution_steps": ["移项得$x=1$。"],
            "solution_notes": [],
        },
        "evidence": {
            "question": [
                {
                    "kind": "page",
                    "source": f"documents/test/word/pages/{page:03d}.png",
                    "page_number": page,
                }
                for page in question_pages
            ],
            "solution": [
                {
                    "kind": "page",
                    "source": "documents/test/word/pages/002.png",
                    "page_number": 2,
                }
            ],
            "solution_start_anchor": "解：",
            "solution_end_anchor": "19.",
        },
        "transcription_confidence": {
            "stem": confidence,
            "formula": confidence,
            "solution_steps": confidence,
        },
    }


def _window(window_id: str, pages: list[dict], questions: list[dict]) -> DocxWindowObservation:
    return DocxWindowObservation.model_validate(
        {
            "schema": "math_docx_window_observation/v1",
            "window_id": window_id,
            "pages": pages,
            "questions": questions,
            "provider": {"kind": "vision_api", "name": "fake", "version": "v1"},
        }
    )


def _make_word_source(tmp_path: Path, page_count: int = 5) -> Path:
    word = tmp_path / "word"
    pages = word / "pages"
    pages.mkdir(parents=True)
    for number in range(1, page_count + 1):
        Image.new("RGB", (64, 80), (255, 255, 255)).save(pages / f"{number:03d}.png")
    path = word / "word-source.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "math_word_source_extract/v1",
                "paragraphs": [{"index": 0, "text": "18. 求x", "images": []}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def test_build_windows_has_overlap_without_duplicate_tail():
    assert build_windows([1, 2, 3, 4, 5], size=3, overlap=1) == [
        [1, 2, 3],
        [3, 4, 5],
    ]
    assert build_windows([1, 2], size=3, overlap=1) == [[1, 2]]
    with pytest.raises(ValueError):
        build_windows([1], size=3, overlap=3)


def test_discover_pages_records_dimensions_and_hash(tmp_path: Path):
    source = _make_word_source(tmp_path, 2)
    pages = discover_pages(source, source_archive="documents/test")
    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].source == "documents/test/word/pages/001.png"
    assert (pages[0].width_px, pages[0].height_px) == (64, 80)
    assert pages[0].sha256.startswith("sha256:")


def test_observe_injected_provider_and_cache(tmp_path: Path):
    source = _make_word_source(tmp_path)
    calls: list[list[str]] = []

    def provider(*, prompt, image_paths):
        calls.append([p.name for p in image_paths])
        assert "OOXML" in prompt
        return {"questions": []}

    cache = tmp_path / "cache"
    first = observe_windows(
        source,
        source_archive="documents/test",
        provider=provider,
        provider_name="fake",
        provider_version="v1",
        window_size=3,
        overlap=1,
        cache_dir=cache,
    )
    assert [item.window_id for item in first] == ["pages-001-003", "pages-003-005"]
    assert calls == [["001.png", "002.png", "003.png"], ["003.png", "004.png", "005.png"]]

    def must_not_run(**_):
        raise AssertionError("cache miss")

    second = observe_windows(
        source,
        source_archive="documents/test",
        provider=must_not_run,
        provider_name="fake",
        provider_version="v1",
        window_size=3,
        overlap=1,
        cache_dir=cache,
    )
    assert [x.model_dump(mode="json") for x in first] == [
        x.model_dump(mode="json") for x in second
    ]


def test_failed_image_attribution_does_not_block_text_observation(tmp_path: Path):
    source = _make_word_source(tmp_path, 1)
    word_source = yaml.safe_load(source.read_text(encoding="utf-8"))
    word_source.update(
        {
            "image_attribution_status": "failed",
            "image_attribution": [],
            "image_attribution_error": {
                "code": "question_number_state_lost",
                "detail": "expected question 5, found question 36",
            },
        }
    )
    source.write_text(
        yaml.safe_dump(word_source, allow_unicode=True),
        encoding="utf-8",
    )
    calls = 0

    def provider(**_):
        nonlocal calls
        calls += 1
        question = _question(ref="1")
        question["evidence"]["solution"] = [
            {
                "kind": "page",
                "source": "documents/test/word/pages/001.png",
                "page_number": 1,
            }
        ]
        return {"questions": [question]}

    result = observe_windows(
        source,
        source_archive="documents/test",
        provider=provider,
        provider_name="fake",
        provider_version="v1",
        window_size=1,
        overlap=0,
    )
    assert calls == 1
    assert [window.window_id for window in result] == ["pages-001-001"]
    merged, issues = merge_with_issues(result, paper=_paper())
    assert issues is None
    assert adapt(merged).refs() == ["1"]


def test_separated_sources_get_continuous_pages_and_distinct_evidence_paths(
    tmp_path: Path,
):
    exam_source = _make_word_source(tmp_path / "exam", 2)
    answer_source = _make_word_source(tmp_path / "answers", 2)

    exam_pages = discover_pages(
        exam_source,
        source_archive="documents/test",
        source_subdir="word",
    )
    answer_pages = discover_pages(
        answer_source,
        source_archive="documents/test",
        source_subdir="word-answers",
        page_number_offset=2,
    )

    assert [page.page_number for page in exam_pages + answer_pages] == [1, 2, 3, 4]
    assert exam_pages[0].source == "documents/test/word/pages/001.png"
    assert answer_pages[0].source == "documents/test/word-answers/pages/001.png"


def test_observe_persists_valid_windows_before_later_provider_failure(tmp_path: Path):
    source = _make_word_source(tmp_path, 5)
    calls = 0

    def provider(**_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"questions": []}
        return {"questions": "invalid"}

    output_dir = tmp_path / "windows"
    with pytest.raises(Exception):
        observe_windows(
            source,
            source_archive="documents/test",
            provider=provider,
            provider_name="fake",
            provider_version="v1",
            window_size=3,
            overlap=1,
            output_dir=output_dir,
        )
    assert (output_dir / "pages-001-003.yaml").is_file()
    assert not (output_dir / "pages-003-005.yaml").exists()


def test_observe_can_limit_page_range_for_resumable_batches(tmp_path: Path):
    source = _make_word_source(tmp_path, 7)
    seen: list[list[str]] = []

    def provider(*, image_paths, **_):
        seen.append([path.name for path in image_paths])
        return {"questions": []}

    observations = observe_windows(
        source,
        source_archive="documents/test",
        provider=provider,
        provider_name="fake",
        provider_version="v1",
        window_size=3,
        overlap=1,
        page_start=3,
        page_end=5,
    )
    assert [item.window_id for item in observations] == ["pages-003-005"]
    assert seen == [["003.png", "004.png", "005.png"]]


def test_bailian_wrapper_sends_images_and_ocr_limits(tmp_path: Path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(image_path)

    class FakeClient:
        def complete_json(self, *, messages, cache_material):
            content = messages[0]["content"]
            assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
            assert content[0]["min_pixels"] == 3072
            assert content[0]["max_pixels"] == 8388608
            assert content[1] == {"type": "text", "text": "prompt"}
            assert cache_material["task"] == "docx_page_ocr_observation"
            return {"questions": []}, False

    provider = make_bailian_ocr_provider(FakeClient())
    assert provider(prompt="prompt", image_paths=[image_path]) == {"questions": []}


def test_mimo_wrapper_sends_math_page_without_bbox_request(tmp_path: Path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(image_path)

    class FakeClient:
        def complete_json(self, *, messages, cache_material):
            content = messages[0]["content"]
            assert content[0] == {"type": "text", "text": "prompt"}
            assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
            assert "min_pixels" not in content[1]
            assert cache_material["task"] == "docx_math_page_observation"
            return {"questions": []}, False

    provider = make_mimo_provider(FakeClient())
    assert provider(prompt="prompt", image_paths=[image_path]) == {"questions": []}


def test_mimo_shape_drift_is_normalized_without_rewriting_formula():
    formula = "由 $(x+1/x)^2=x^2+2+1/x^2$。"
    normalized = normalize_observation_field_shapes(
        {
            "questions": [
                {
                    "question_ref": "18",
                    "question_number": "18",
                    "question_type": "short_answer",
                    "points": "",
                    "section_ref": "",
                    "section_title": "",
                    "content": {
                        "stem_latex": "求值。",
                        "choices": [],
                        "answer": "23",
                        "clue": "",
                        "solution_steps": formula,
                        "solution_notes": "",
                    },
                }
            ]
        }
    )
    question = normalized["questions"][0]
    assert question["question_number"] == 18
    assert question["points"] == 0
    assert question["section_ref"] == "section-short_answer"
    assert question["section_title"] == "解答题"
    assert question["content"]["solution_steps"] == [formula]
    assert question["content"]["solution_notes"] == []
    assert question["content"]["clue"] == "原卷未提供提示"


def test_mimo_fill_blank_alias_is_normalized_to_contract_value():
    normalized = normalize_observation_field_shapes(
        {
            "questions": [
                {
                    "question_type": "fill_blank",
                    "section_ref": "",
                    "section_title": "",
                    "content": {"choices": []},
                }
            ]
        }
    )
    question = normalized["questions"][0]
    assert question["question_type"] == "fillin"
    assert question["section_ref"] == "section-fillin"
    assert question["section_title"] == "填空题"


def test_mimo_single_top_level_question_is_wrapped():
    normalized = normalize_observation_field_shapes(
        {
            "schema": "math_docx_window_observation/v1",
            "question_ref": "18",
            "question_number": 18,
            "question_type": "fillin",
            "points": 4,
            "section_ref": "two",
            "section_title": "填空题",
            "content": {"stem_latex": "求值。", "answer": "1", "clue": "代入。"},
            "evidence": {"question": [{"kind": "page", "source": "p.png", "page_number": 1}]},
            "transcription_confidence": {
                "stem": "high",
                "formula": "high",
                "solution_steps": "medium",
            },
        }
    )
    assert normalized["questions"][0]["question_ref"] == "18"
    assert "question_ref" not in normalized


def test_mimo_ordered_choice_labels_are_stripped_without_rewriting_formulas():
    normalized = normalize_observation_field_shapes(
        {
            "questions": [
                {
                    "content": {
                        "choices": [
                            r"A. $\sqrt{\frac{a}{9}}$",
                            r"B、$\sqrt{9a}$",
                            r"（C）$\sqrt{3a}$",
                            r"(D) $\sqrt{12a}$",
                        ]
                    }
                }
            ]
        }
    )
    assert normalized["questions"][0]["content"]["choices"] == [
        r"$\sqrt{\frac{a}{9}}$",
        r"$\sqrt{9a}$",
        r"$\sqrt{3a}$",
        r"$\sqrt{12a}$",
    ]


def test_mimo_structured_choice_labels_are_stripped():
    normalized = normalize_observation_field_shapes(
        {
            "questions": [
                {
                    "content": {
                        "choices": [
                            {"label": "A", "content": "$x=1$"},
                            {"label": "B", "content": "$x=2$"},
                            {"label": "C", "content": "$x=3$"},
                            {"label": "D", "content": "$x=4$"},
                        ]
                    }
                }
            ]
        }
    )
    assert normalized["questions"][0]["content"]["choices"] == [
        "$x=1$",
        "$x=2$",
        "$x=3$",
        "$x=4$",
    ]


def test_mimo_structured_solution_steps_are_unwrapped_without_text_changes():
    formula = r"$x=6-3\sqrt{3}$"
    normalized = normalize_observation_field_shapes(
        {
            "questions": [
                {
                    "content": {
                        "solution_steps": [
                            {"step": formula},
                            {"content": "第二步"},
                            {"text": "第三步"},
                        ],
                        "solution_notes": [{"note": "原卷疑似笔误"}],
                    }
                }
            ]
        }
    )
    content = normalized["questions"][0]["content"]
    assert content["solution_steps"] == [formula, "第二步", "第三步"]
    assert content["solution_notes"] == ["原卷疑似笔误"]


def test_mimo_choice_prefix_is_preserved_without_complete_ordered_labels():
    choices = ["A. 公司", "另一家公司", "第三家公司", "第四家公司"]
    normalized = normalize_observation_field_shapes(
        {"questions": [{"content": {"choices": choices}}]}
    )
    assert normalized["questions"][0]["content"]["choices"] == choices


def test_bailian_client_uses_fixed_best_model_and_cache(tmp_path: Path):
    calls: list[dict] = []

    def fake_provider(body):
        calls.append(body)
        return "```json\n{\"questions\": []}\n```"

    client = BailianOcrClient(
        api_key="not-logged",
        cache_dir=tmp_path,
        provider=fake_provider,
    )
    messages = [{"role": "user", "content": [{"type": "text", "text": "prompt"}]}]
    first, first_cached = client.complete_json(
        messages=messages,
        cache_material={"page_sha256": ["abc"], "prompt_version": "v1"},
    )
    second, second_cached = client.complete_json(
        messages=messages,
        cache_material={"page_sha256": ["abc"], "prompt_version": "v1"},
    )
    assert client.model == BAILIAN_OCR_MODEL == "qwen3.5-ocr"
    assert calls[0]["model"] == "qwen3.5-ocr"
    assert calls[0]["max_tokens"] == 16384
    assert first == second == {"questions": []}
    assert first_cached is False
    assert second_cached is True


def test_bailian_native_exam_json_is_normalized_without_bbox(tmp_path: Path):
    source = _make_word_source(tmp_path, 1)
    page = discover_pages(source, source_archive="documents/test")[0]
    normalized = normalize_bailian_ocr_response(
        {
            "question": "18. 已知 \\(x+1/x=5\\)，求值。",
            "stem": {
                "text": "18. 已知 x+1/x=5，求值。",
                "pos_list": [{"rotate_rect": [1, 2, 3, 4, 0]}],
            },
            "option": [],
            "figure": [],
            "answer": [
                {
                    "text": "解：平方后化简。\\n答案：23",
                    "pos_list": [{"rotate_rect": [5, 6, 7, 8, 0]}],
                }
            ],
            "type": "问答题",
            "subquestion": [],
        },
        pages=[page],
    )
    question = normalized["questions"][0]
    assert question["question_ref"] == "18"
    assert question["content"]["answer"] == "23"
    assert question["transcription_confidence"]["formula"] == "medium"
    assert "pos_list" not in json.dumps(normalized, ensure_ascii=False)
    assert "rotate_rect" not in json.dumps(normalized, ensure_ascii=False)


def test_merge_overlapping_identical_question_unions_evidence(tmp_path: Path):
    source = _make_word_source(tmp_path, 3)
    pages = [p.model_dump(mode="json") for p in discover_pages(source, source_archive="documents/test")]
    q1 = _question(question_pages=[1])
    q2 = _question(question_pages=[2])
    merged, issues = merge_with_issues(
        [
            _window("pages-001-002", pages[:2], [q1]),
            _window("pages-002-003", pages[1:], [q2]),
        ],
        paper=_paper(),
    )
    assert merged.conflicts == []
    assert issues is None
    assert len(merged.questions) == 1
    assert [e.page_number for e in merged.questions[0].evidence.question] == [1, 2]


def test_merge_separated_layout_combines_question_and_solution_fragments(tmp_path: Path):
    source = _make_word_source(tmp_path, 6)
    pages = [
        page.model_dump(mode="json")
        for page in discover_pages(source, source_archive="documents/test")
    ]
    base = _question(ref="1")
    question_fragment = {
        **base,
        "content": {
            "stem_latex": "方程 $x+1=2$ 的解是（ ）",
            "choices": ["$0$", "$1$", "$2$", "$3$"],
            "answer": None,
            "clue": "原卷未提供提示",
            "solution_steps": [],
            "solution_notes": [],
        },
        "evidence": {
            "question": [
                {
                    "kind": "page",
                    "source": "documents/test/word/pages/001.png",
                    "page_number": 1,
                }
            ],
            "solution": [],
            "solution_start_anchor": None,
            "solution_end_anchor": None,
        },
    }
    question_fragment["question_type"] = "choice"
    solution_fragment = {
        **base,
        "content": {
            "stem_latex": None,
            "choices": [],
            "answer": "B",
            "clue": None,
            "solution_steps": ["由 $x+1=2$，得 $x=1$。"],
            "solution_notes": [],
        },
        "evidence": {
            "question": [],
            "solution": [
                {
                    "kind": "page",
                    "source": "documents/test/word/pages/006.png",
                    "page_number": 6,
                }
            ],
            "solution_start_anchor": "1. B",
            "solution_end_anchor": "2. C",
        },
    }
    solution_fragment["question_type"] = "choice"

    merged, issues = merge_with_issues(
        [
            _window("questions-001", pages[:1], [question_fragment]),
            _window("answers-006", pages[5:], [solution_fragment]),
        ],
        paper=_paper(),
    )
    assert merged.conflicts == []
    question = merged.questions[0]
    assert question.content.stem_latex == "方程 $x+1=2$ 的解是（ ）"
    assert question.content.answer == "B"
    assert question.content.solution_steps == ["由 $x+1=2$，得 $x=1$。"]
    assert [item.page_number for item in question.evidence.question] == [1]
    assert [item.page_number for item in question.evidence.solution] == [6]
    assert adapt(merged).refs() == ["1"]


def test_merge_rejects_question_without_complementary_solution_fragment(tmp_path: Path):
    source = _make_word_source(tmp_path, 1)
    pages = [
        page.model_dump(mode="json")
        for page in discover_pages(source, source_archive="documents/test")
    ]
    base = _question(ref="1")
    fragment = {
        **base,
        "content": {
            "stem_latex": "填空：$x=1$。",
            "choices": [],
            "answer": "1",
            "clue": "原卷未提供提示",
            "solution_steps": [],
            "solution_notes": [],
        },
        "evidence": {
            "question": [
                {
                    "kind": "page",
                    "source": "documents/test/word/pages/001.png",
                    "page_number": 1,
                }
            ],
            "solution": [],
            "solution_start_anchor": None,
            "solution_end_anchor": None,
        },
    }
    fragment["question_type"] = "fillin"
    with pytest.raises(ValueError, match="incomplete merged question 1"):
        merge([_window("questions-001", pages, [fragment])], paper=_paper())


def test_merge_conflict_selects_higher_confidence_and_adapter_blocks(tmp_path: Path):
    source = _make_word_source(tmp_path, 2)
    pages = [p.model_dump(mode="json") for p in discover_pages(source, source_archive="documents/test")]
    merged, issues = merge_with_issues(
        [
            _window("a", pages, [_question(stem="错误候选", confidence="low")]),
            _window("b", pages, [_question(stem="正确候选", confidence="high")]),
        ],
        paper=_paper(),
    )
    assert merged.questions[0].content.stem_latex == "正确候选"
    assert merged.conflicts[0].fields == ["content.stem_latex"]
    assert issues is not None
    assert issues.issues[0].code == "stem_conflict"
    assert {candidate.raw_value for candidate in issues.issues[0].candidates} == {
        "错误候选",
        "正确候选",
    }
    with pytest.raises(ValueError, match="unresolved"):
        adapt(merged)
    bundle = adapt_for_review_staging(merged)
    assert bundle.sections[0].questions[0].content.stem_latex == "正确候选"


def test_adapter_groups_sections_and_rejects_low_confidence(tmp_path: Path):
    source = _make_word_source(tmp_path, 2)
    pages = [p.model_dump(mode="json") for p in discover_pages(source, source_archive="documents/test")]
    merged = merge(
        [_window("a", pages, [_question(confidence="low")])],
        paper=_paper(),
    )
    with pytest.raises(ValueError, match="low-confidence"):
        adapt(merged)
    bundle = adapt(merged, allow_low_confidence=True)
    assert isinstance(bundle, QuestionTranscriptionBundle)
    assert bundle.refs() == ["18"]
    assert bundle.sections[0].section_ref == "problems"


def test_window_contract_rejects_duplicate_question_ref(tmp_path: Path):
    source = _make_word_source(tmp_path, 1)
    pages = [p.model_dump(mode="json") for p in discover_pages(source, source_archive="documents/test")]
    with pytest.raises(ValueError, match="duplicate question_ref"):
        _window("a", pages, [_question(), _question()])


# =========================================================================== #
# Span-index-driven observation (§7.1 / §7.2 / §10.1)
# =========================================================================== #

from scripts.question_transcription.observe_docx_pages import (  # noqa: E402
    SPAN_INDEX_PROMPT_VERSION,
    observe as observe_with_index,
)
from scripts.question_transcription.question_span_index import (  # noqa: E402
    IndexedQuestion,
    QuestionSpanIndex,
    SourceFingerprint,
)


def _index(
    questions: list[IndexedQuestion],
    *,
    page_numbers: list[int] | None = None,
    page_shas: list[str] | None = None,
    offset: int = 0,
    status: str = "ready",
) -> QuestionSpanIndex:
    if page_numbers is None:
        page_numbers = sorted(
            {p for q in questions for p in (*q.question_pages, *q.solution_pages)}
        )
    return QuestionSpanIndex(
        schema="math_question_span_index/v1",
        source_kind="docx",
        page_numbers=page_numbers,
        fingerprint=SourceFingerprint(page_sha256=page_shas or [], page_number_offset=offset),
        status=status,
        questions=questions,
        issues=[],
    )


def _q(ref: str, pages: list[int], *, hint: str = "problem") -> IndexedQuestion:
    return IndexedQuestion(
        question_ref=ref,
        question_number=int(ref),
        question_pages=pages,
        question_type_hint=hint,  # type: ignore[arg-type]
    )


def _question_payload(ref: str, *, page: int = 1) -> dict:
    """A minimal valid question dict for the span-index flow."""
    return {
        "question_ref": ref,
        "question_number": int(ref),
        "question_type": "problem",
        "points": 4,
        "section_ref": "problems",
        "section_title": "解答题",
        "content": {
            "stem_latex": f"题{ref}",
            "choices": [],
            "answer": f"ans{ref}",
            "clue": "原卷未提供提示",
            "solution_steps": [f"step{ref}"],
            "solution_notes": [],
        },
        "evidence": {
            "question": [
                {"kind": "page", "source": f"documents/test/word/pages/{page:03d}.png", "page_number": page}
            ],
            "solution": [],
            "solution_start_anchor": None,
            "solution_end_anchor": None,
        },
        "transcription_confidence": {"stem": "high", "formula": "high", "solution_steps": "high"},
    }


def _word_source_with_pages(tmp_path: Path, page_count: int) -> tuple[Path, list[str]]:
    source = _make_word_source(tmp_path, page_count)
    # _make_word_source writes identical white pages; re-read their SHAs.
    pages_dir = source.parent / "pages"
    shas = []
    import hashlib

    for n in range(1, page_count + 1):
        raw = (pages_dir / f"{n:03d}.png").read_bytes()
        shas.append(f"sha256:{hashlib.sha256(raw).hexdigest()}")
    return source, shas


def test_span_observe_prompt_has_no_ooxml_and_carries_expected_refs(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 2)
    index = _index([_q("1", [1]), _q("2", [2])], page_shas=shas)
    seen_prompts: list[str] = []

    def provider(*, prompt, image_paths):
        seen_prompts.append(prompt)
        # Return exactly the expected refs for the batch.
        refs_in_prompt = [r for r in ("1", "2") if r in prompt]
        return {"questions": [_question_payload(r) for r in refs_in_prompt]}

    observe_with_index(
        source,
        source_archive="documents/test",
        span_index=index,
        provider=provider,
        provider_name="fake",
        provider_version="v1",
    )
    # §7.1: prompt must NOT contain the OOXML 全文 hint.
    assert all("OOXML" not in p for p in seen_prompts)
    # §7.1: prompt carries the expected question refs and the page mapping.
    assert all("1" in p for p in seen_prompts)
    assert all("page_number" in p for p in seen_prompts)


def test_span_observe_exact_match_passes(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 2)
    index = _index([_q("1", [1]), _q("2", [2])], page_shas=shas)
    calls: list[str] = []

    def provider(*, prompt, image_paths):
        refs = [r for r in ("1", "2") if r in prompt]
        calls.append(",".join(refs))
        return {"questions": [_question_payload(r) for r in refs]}

    observations = observe_with_index(
        source,
        source_archive="documents/test",
        span_index=index,
        provider=provider,
        provider_name="fake",
        provider_version="v1",
    )
    all_refs = [q.question_ref for obs in observations for q in obs.questions]
    assert sorted(all_refs) == ["1", "2"]


def test_span_observe_missing_triggers_targeted_repair_only_for_missing(tmp_path: Path):
    # Put both questions on page 1 so they land in one batch (shared page =>
    # one non-splittable component), exercising repair within a single batch.
    source, shas = _word_source_with_pages(tmp_path, 1)
    index = _index([_q("1", [1]), _q("2", [1])], page_shas=shas)

    def _expected_refs(prompt: str) -> list[str]:
        # The prompt lists expected refs after "以下预期题号:" up to the first "。".
        segment = prompt.split("以下预期题号:", 1)[1]
        segment = segment.split("。", 1)[0]
        return [tok.strip() for tok in segment.split(",") if tok.strip()]

    def provider(*, prompt, image_paths):
        expected = _expected_refs(prompt)
        if expected == ["1", "2"]:
            # First round: return only "1", omit "2".
            return {"questions": [_question_payload("1")]}
        # Repair round: prompt's expected set is only the missing ref "2".
        assert expected == ["2"], expected
        return {"questions": [_question_payload("2")]}

    observations = observe_with_index(
        source,
        source_archive="documents/test",
        span_index=index,
        provider=provider,
        provider_name="fake",
        provider_version="v1",
        max_repairs=1,
    )
    all_refs = [q.question_ref for obs in observations for q in obs.questions]
    assert sorted(all_refs) == ["1", "2"]


def test_span_observe_unexpected_is_isolated_not_into_observation(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 1)
    index = _index([_q("1", [1])], page_shas=shas)

    def provider(*, prompt, image_paths):
        # Return the expected "1" plus an unexpected "99".
        return {"questions": [_question_payload("1"), _question_payload("99", page=1)]}

    observations = observe_with_index(
        source,
        source_archive="documents/test",
        span_index=index,
        provider=provider,
        provider_name="fake",
        provider_version="v1",
    )
    refs = [q.question_ref for obs in observations for q in obs.questions]
    assert "99" not in refs  # isolated
    assert refs == ["1"]


def test_span_observe_duplicate_over_repair_limit_is_blocking(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 1)
    index = _index([_q("1", [1])], page_shas=shas)

    def provider(*, prompt, image_paths):
        # Always return two copies of "1" -> duplicate, never resolves.
        return {"questions": [_question_payload("1"), _question_payload("1")]}

    with pytest.raises(ValueError, match="could not be repaired"):
        observe_with_index(
            source,
            source_archive="documents/test",
            span_index=index,
            provider=provider,
            provider_name="fake",
            provider_version="v1",
            max_repairs=1,
            output_dir=tmp_path / "out",
        )
    # §7.1: before resolution, no normal observation file is produced.
    assert list((tmp_path / "out").glob("*.yaml")) == [] or all(
        p.name.startswith("_") for p in (tmp_path / "out").glob("*.yaml")
    )


def test_span_observe_no_normal_file_before_resolution(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 1)
    index = _index([_q("1", [1]), _q("2", [1])], page_shas=shas)

    def provider(*, prompt, image_paths):
        # Never return "2" -> blocking after max_repairs.
        return {"questions": [_question_payload("1")]}

    out = tmp_path / "out"
    with pytest.raises(ValueError):
        observe_with_index(
            source,
            source_archive="documents/test",
            span_index=index,
            provider=provider,
            provider_name="fake",
            provider_version="v1",
            max_repairs=0,
            output_dir=out,
        )
    # Only repair metadata may exist; no normal *.yaml observation.
    normal = [p for p in out.glob("*.yaml") if not p.name.startswith("_")]
    assert normal == []


def test_span_observe_rejects_stale_fingerprint_before_provider_call(tmp_path: Path):
    source, _shas = _word_source_with_pages(tmp_path, 1)
    # Index whose page SHA is wrong relative to the rendered page.
    index = _index([_q("1", [1])], page_shas=["sha256:" + "0" * 64])
    calls = []

    def provider(*, prompt, image_paths):
        calls.append(1)
        return {"questions": []}

    with pytest.raises(ValueError, match="SHA"):
        observe_with_index(
            source,
            source_archive="documents/test",
            span_index=index,
            provider=provider,
            provider_name="fake",
            provider_version="v1",
        )
    assert calls == []  # failed before any provider call


def test_span_observe_rejects_non_ready_status(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 1)
    index = _index([_q("1", [1])], page_shas=shas, status="needs_review")
    with pytest.raises(ValueError, match="ready"):
        observe_with_index(
            source,
            source_archive="documents/test",
            span_index=index,
            provider=lambda **_: {"questions": []},
            provider_name="fake",
            provider_version="v1",
        )


def test_span_oberve_question_and_solution_batches_never_mix(tmp_path: Path):
    source, shas = _word_source_with_pages(tmp_path, 2)
    q1 = _q("1", [1])
    q1.solution_pages = [2]
    index = _index([q1], page_shas=shas)

    roles: list[str] = []

    def provider(*, prompt, image_paths):
        roles.append("solution" if "官方解答" in prompt else "question")
        # Return expected for whichever role, with the matching non-empty evidence.
        if "官方解答" in prompt:
            payload = _question_payload("1", page=2)
            payload["evidence"]["question"] = []
            payload["evidence"]["solution"] = [
                {"kind": "page", "source": "documents/test/word/pages/002.png", "page_number": 2}
            ]
            return {"questions": [payload]}
        payload = _question_payload("1", page=1)
        payload["evidence"]["solution"] = []
        return {"questions": [payload]}

    observe_with_index(
        source,
        source_archive="documents/test",
        span_index=index,
        provider=provider,
        provider_name="fake",
        provider_version="v1",
    )
    # Question and solution are separate batches; roles recorded distinctly.
    assert "question" in roles and "solution" in roles


def test_cli_rejects_nonzero_overlap(tmp_path: Path):
    import subprocess

    source = _make_word_source(tmp_path, 1)
    # A real (empty) injected response so argument parsing reaches the overlap guard.
    response_file = tmp_path / "resp.json"
    response_file.write_text('{"questions": []}', encoding="utf-8")
    result = subprocess.run(
        [
            "./.venv/bin/python",
            "scripts/question_transcription/observe_docx_pages.py",
            "--word-source",
            str(source),
            "--source-archive",
            "documents/test",
            "--responses",
            str(response_file),
            "--output-dir",
            str(tmp_path / "out"),
            "--overlap",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "overlap" in result.stderr.lower()


def test_span_observe_question_only_then_solution_merges(tmp_path: Path):
    """§10.1: DOCX question-only / solution-only batches still merge via the
    existing merge path into a complete question."""
    from scripts.question_transcription.merge_docx_observations import merge

    source, shas = _word_source_with_pages(tmp_path, 2)
    q1 = _q("1", [1])
    q1.solution_pages = [2]
    index = _index([q1], page_shas=shas)

    def provider(*, prompt, image_paths):
        if "官方解答" in prompt:
            payload = _question_payload("1", page=2)
            payload["content"]["stem_latex"] = None  # solution-only batch
            payload["evidence"]["question"] = []
            payload["evidence"]["solution"] = [
                {"kind": "page", "source": "documents/test/word/pages/002.png", "page_number": 2}
            ]
            payload["evidence"]["solution_start_anchor"] = "解："
            payload["evidence"]["solution_end_anchor"] = "<END>"
            return {"questions": [payload]}
        payload = _question_payload("1", page=1)
        payload["evidence"]["solution"] = []
        payload["evidence"]["solution_start_anchor"] = "解："
        payload["evidence"]["solution_end_anchor"] = "<END>"
        return {"questions": [payload]}

    observations = observe_with_index(
        source,
        source_archive="documents/test",
        span_index=index,
        provider=provider,
        provider_name="fake",
        provider_version="v1",
    )
    merged = merge(observations, paper=_paper())
    # The merged question has both question and solution evidence.
    q = merged.questions[0]
    assert q.evidence.question and q.evidence.solution
