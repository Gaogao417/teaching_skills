"""Compatibility projection tests for SourceQuestion v2."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    QuestionTranscriptionBundle,
)
from scripts.question_transcription.project_source_paper import (  # noqa: E402
    project_image_bundle,
    project_source_to_draft,
    project_transcription_bundle,
)
from scripts.question_transcription.source_contracts import (  # noqa: E402
    ChoiceContent,
    ImageAttributionV2,
    ImageNode,
    ImageRendition,
    QuestionContentV2,
    SourceImageAsset,
    SourcePaper,
    SourceQuestion,
    TargetChoice,
    TargetQuestionStem,
    TextNode,
)

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64
_ARCHIVE = "documents/demo-paper"


def _skeleton() -> QuestionTranscriptionBundle:
    return QuestionTranscriptionBundle.model_validate(
        {
            "schema": "math_question_transcription/v1",
            "paper": {
                "id": "PAPER",
                "title": "图像选项测试卷",
                "grade": "九年级",
                "subject": "数学",
                "source_archive": _ARCHIVE,
                "question_bank": "../../question-bank.yaml",
            },
            "sections": [
                {
                    "section_ref": "I",
                    "title": "选择题",
                    "questions": [
                        {
                            "question_ref": "1",
                            "question_number": 1,
                            "question_type": "choice",
                            "points": 4,
                            "content": {
                                "stem_latex": "旧内容",
                                "choices": ["旧A", "旧B", "旧C", "旧D"],
                                "answer": "A",
                                "clue": "旧",
                            },
                            "evidence": {
                                "question": [
                                    {
                                        "kind": "page",
                                        "source": f"{_ARCHIVE}/pages/1.png",
                                        "page_number": 1,
                                    }
                                ],
                                "solution": [
                                    {
                                        "kind": "page",
                                        "source": f"{_ARCHIVE}/pages/2.png",
                                        "page_number": 2,
                                    }
                                ],
                                "solution_start_anchor": "1.",
                                "solution_end_anchor": "2.",
                            },
                        }
                    ],
                }
            ],
            "provider": {
                "kind": "manual",
                "name": "fixture",
                "version": "v1",
            },
        }
    )


def _source() -> SourcePaper:
    assets = []
    attrs = []
    choices = []
    for key in "ABCD":
        asset_id = f"choice-{key}"
        assets.append(
            SourceImageAsset(
                asset_id=asset_id,
                original_path=f"{_ARCHIVE}/word/media/{asset_id}.png",
                original_sha256=_HASH_A,
                original_media_type="image/png",
                emf_class="diagram",
                rendition=ImageRendition(
                    path=f"{_ARCHIVE}/rend/{asset_id}.png",
                    sha256=_HASH_B,
                    media_type="image/png",
                    width_px=160,
                    height_px=120,
                ),
            )
        )
        choices.append(ChoiceContent(content=[ImageNode(kind="image", asset_id=asset_id)]))
        attrs.append(
            ImageAttributionV2(
                attribution_id=f"attr-{key}",
                asset_id=asset_id,
                question_ref="1",
                target=TargetChoice(choice_key=key),
                order=0,
                confidence="high",
                state="accepted",
            )
        )
    return SourcePaper(
        schema="math_exam_source_paper/v2",
        paper_id="PAPER",
        questions=[
            SourceQuestion(
                question_ref="1",
                question_number=1,
                question_type="choice",
                points=4,
                content=QuestionContentV2(
                    stem=[TextNode(kind="text", text="下列图像正确的是（　）")],
                    choices=choices,
                    answer="B",
                    clue="观察图像。",
                ),
            )
        ],
        assets=assets,
        attributions=attrs,
    )


def test_graphical_choices_project_without_losing_v2_asset_mapping():
    source = _source()
    transcription = project_transcription_bundle(source, _skeleton())
    question = transcription.sections[0].questions[0]
    assert question.content.choices == [
        "选项A见图",
        "选项B见图",
        "选项C见图",
        "选项D见图",
    ]
    assert question.content.answer == "B"

    images = project_image_bundle(source)
    assert [attr.asset_id for attr in images.attributions] == [
        "choice-A",
        "choice-B",
        "choice-C",
        "choice-D",
    ]
    assert [attr.order for attr in images.attributions] == [0, 1, 2, 3]


def test_projected_graphical_choice_runs_existing_draft_assembler():
    draft, report = project_source_to_draft(_source(), _skeleton())
    assert report.errors == []
    item = draft["sections"][0]["items"][0]
    assert len(item["prompt"]) == 4
    assert item["block"]["choices"][1] == "选项B见图"
    assert item["block"]["answer"] == "B"


def _stem_source(*specs) -> SourcePaper:
    """Build a SourcePaper with stem attributions in the given states.

    Each spec is ``(state, confidence)``; one asset/attr pair per spec, all on
    question 1 as prompt images.
    """
    assets: list[SourceImageAsset] = []
    attrs: list[ImageAttributionV2] = []
    for i, (state, confidence) in enumerate(specs):
        asset_id = f"img-{i}"
        assets.append(
            SourceImageAsset(
                asset_id=asset_id,
                original_path=f"{_ARCHIVE}/word/media/{asset_id}.png",
                original_sha256=_HASH_A,
                original_media_type="image/png",
                emf_class="diagram",
                rendition=ImageRendition(
                    path=f"{_ARCHIVE}/rend/{asset_id}.png",
                    sha256=_HASH_B,
                    media_type="image/png",
                    width_px=120,
                    height_px=120,
                ),
            )
        )
        attrs.append(
            ImageAttributionV2(
                attribution_id=f"attr-{i}",
                asset_id=asset_id,
                question_ref="1",
                target=TargetQuestionStem(target="question_stem"),
                order=i,
                confidence=confidence,
                state=state,
            )
        )
    return SourcePaper(
        schema="math_exam_source_paper/v2",
        paper_id="PAPER",
        questions=[
            SourceQuestion(
                question_ref="1",
                question_number=1,
                question_type="problem",
                points=4,
                content=QuestionContentV2(
                    stem=[TextNode(kind="text", text="如图。")],
                    answer="1",
                    clue="c",
                    solution_steps=[
                        {"step_id": "1", "content": [TextNode(kind="text", text="s1")]}
                    ],
                ),
            )
        ],
        assets=assets,
        attributions=attrs,
    )


def test_project_image_bundle_preserves_needs_review_and_drops_rejected():
    """needs_review attributions are projected (state/confidence preserved);
    rejected attributions are not projected."""
    source = _stem_source(
        ("accepted", "high"),
        ("needs_review", "medium"),
        ("needs_review", "low"),
        ("rejected", "high"),
    )
    images = project_image_bundle(source)
    by_id = {a.asset_id: a for a in images.attributions}
    # accepted + 2 needs_review survive; rejected dropped.
    assert sorted(by_id) == ["img-0", "img-1", "img-2"]
    assert by_id["img-0"].state == "accepted"
    assert by_id["img-1"].state == "needs_review"
    assert by_id["img-1"].confidence == "medium"
    assert by_id["img-2"].state == "needs_review"
    assert by_id["img-2"].confidence == "low"
    assert "img-3" not in by_id  # rejected
