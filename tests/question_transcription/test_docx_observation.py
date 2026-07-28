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

from scripts.question_transcription.adapt_docx_transcription import adapt  # noqa: E402
from scripts.question_transcription.contracts import PaperMeta, QuestionTranscriptionBundle  # noqa: E402
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxWindowObservation,
)
from scripts.question_transcription.merge_docx_observations import merge  # noqa: E402
from scripts.question_transcription.observe_docx_pages import (  # noqa: E402
    build_windows,
    discover_pages,
    make_bailian_ocr_provider,
    make_mimo_provider,
    normalize_bailian_ocr_response,
    normalize_observation_field_shapes,
    observe,
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
    first = observe(
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

    second = observe(
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
        observe(
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

    observations = observe(
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
    merged = merge(
        [
            _window("pages-001-002", pages[:2], [q1]),
            _window("pages-002-003", pages[1:], [q2]),
        ],
        paper=_paper(),
    )
    assert merged.conflicts == []
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

    merged = merge(
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
    merged = merge(
        [
            _window("a", pages, [_question(stem="错误候选", confidence="low")]),
            _window("b", pages, [_question(stem="正确候选", confidence="high")]),
        ],
        paper=_paper(),
    )
    assert merged.questions[0].content.stem_latex == "正确候选"
    assert merged.conflicts[0].fields == ["content"]
    with pytest.raises(ValueError, match="unresolved"):
        adapt(merged)
    bundle = adapt(merged, allow_conflicts=True)
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
