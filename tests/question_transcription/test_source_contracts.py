"""Tests for the additive SourceQuestion v2 contracts.

These pin the structural rules the v2 layer promises and that the plan's
rollout depends on:

- An image-only stem is representable after the whole block has been confirmed
  as ``mixed_content`` and is preserved without text extraction.
- Choice questions use ``choices`` (four entries) OR ``choice_panel``, not both.
- An unconfirmed ``choice_panel`` mapping is the default and must be flagged so
  the assembler can block promotion.
- Multi-part questions carry their own ``part_id``/stem/steps; parts are
  forbidden on choice/fillin.
- Image attribution targets pin exactly the keys their role requires
  (``part_solution_step`` needs both ``part_id`` and ``step_id``).
- A shared asset is referenced by multiple targets through one ``asset_id``;
  the asset record is not duplicated.
- JSON Schema for ``math_exam_source_paper/v2`` dumps.

v1 is untouched here; see ``test_contracts.py`` for the frozen v1 layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.source_contracts import (  # noqa: E402
    ChoiceContent,
    ChoicePanel,
    ChoicePanelMapping,
    ImageAttributionV2,
    ImageCrop,
    ImageNode,
    ImageRendition,
    OleFormulaBinding,
    QuestionContentV2,
    QuestionPart,
    SolutionStep,
    SourceImageAsset,
    SourcePaper,
    SourceQuestion,
    TargetChoice,
    TargetPartSolutionStep,
    TargetPartStem,
    TargetQuestionStem,
    TargetQuestionSolutionStep,
    TextNode,
)


# --------------------------------------------------------------------------- #
# Builders for the common cases in the plan's contract-fixture matrix
# --------------------------------------------------------------------------- #

_PNG_HASH = "sha256:" + "a" * 64
_PNG_HASH_B = "sha256:" + "b" * 64


def _asset(asset_id: str = "img-1", emf_class: str = "diagram") -> SourceImageAsset:
    return SourceImageAsset(
        asset_id=asset_id,
        original_path=f"word/media/{asset_id}.png",
        original_sha256=_PNG_HASH,
        original_media_type="image/png",
        emf_class=emf_class,
        review_issue_id=(
            f"issue-{asset_id}"
            if emf_class in {"mixed_content", "needs_review"}
            else None
        ),
        rendition=ImageRendition(
            path=f"rend/{asset_id}.png",
            sha256=_PNG_HASH_B,
            media_type="image/png",
            width_px=200,
            height_px=100,
        ),
    )


def _vector_asset(
    asset_id: str,
    emf_class: str,
    *,
    embedded: bool,
    review_issue_id: str | None = None,
) -> SourceImageAsset:
    return SourceImageAsset(
        asset_id=asset_id,
        original_path=f"word/media/{asset_id}.emf",
        original_sha256=_PNG_HASH,
        original_media_type="image/x-emf",
        emf_class=emf_class,
        ole_binding=OleFormulaBinding(
            embedded=embedded,
            relationship_id=f"rId-{asset_id}" if embedded else None,
        ),
        review_issue_id=review_issue_id,
        rendition=ImageRendition(
            path=f"rend/{asset_id}.png",
            sha256=_PNG_HASH_B,
            media_type="image/png",
            width_px=200,
            height_px=100,
        ),
    )


def _text(s: str) -> TextNode:
    return TextNode(kind="text", text=s)


def _img(asset_id: str) -> ImageNode:
    return ImageNode(kind="image", asset_id=asset_id)


def _question(**overrides) -> SourceQuestion:
    base = dict(
        question_ref="1",
        question_number=1,
        question_type="fillin",
        points=3,
        content=QuestionContentV2(
            stem=[_text("计算 $2+2$ 的值。")],
            answer="$4$",
            clue="c",
        ),
    )
    base.update(overrides)
    return SourceQuestion(**base)


def _paper(questions, assets=None, attributions=None) -> SourcePaper:
    return SourcePaper(
        schema="math_exam_source_paper/v2",
        paper_id="TEST-PAPER",
        questions=questions,
        assets=assets or [],
        attributions=attributions or [],
    )


# --------------------------------------------------------------------------- #
# Pure-text question (the common baseline)
# --------------------------------------------------------------------------- #


def test_plain_text_fillin_loads():
    q = _question()
    paper = _paper([q])
    assert paper.schema_ == "math_exam_source_paper/v2"
    assert paper.questions[0].content.stem[0].kind == "text"


# --------------------------------------------------------------------------- #
# Whole-question single figure (question_stem target)
# --------------------------------------------------------------------------- #


def test_whole_question_single_figure():
    asset = _asset("stem-1")
    attr = ImageAttributionV2(
        attribution_id="att-1",
        asset_id="stem-1",
        question_ref="1",
        target=TargetQuestionStem(),
        order=1,
        confidence="high",
        state="accepted",
    )
    q = _question(
        content=QuestionContentV2(
            stem=[_text("如图，在$\\triangle ABC$中，"), _img("stem-1")],
            answer="$5$",
            clue="c",
        )
    )
    paper = _paper([q], assets=[asset], attributions=[attr])
    assert paper.attributions[0].target.target == "question_stem"


# --------------------------------------------------------------------------- #
# Four independent choice figures (choice targets with choice_key)
# --------------------------------------------------------------------------- #


def test_four_independent_choice_figures():
    assets = [_asset(f"ch-{k}") for k in "ABCD"]
    attrs = [
        ImageAttributionV2(
            attribution_id=f"att-{k}",
            asset_id=f"ch-{k}",
            question_ref="1",
            target=TargetChoice(choice_key=k),  # type: ignore[arg-type]
            order=0,
            confidence="high",
            state="accepted",
        )
        for k in "ABCD"
    ]
    q = _question(
        question_type="choice",
        content=QuestionContentV2(
            stem=[_text("下列函数图象正确的是（）")],
            choices=[
                ChoiceContent(content=[_img("ch-A")]),
                ChoiceContent(content=[_img("ch-B")]),
                ChoiceContent(content=[_img("ch-C")]),
                ChoiceContent(content=[_img("ch-D")]),
            ],
            answer="B",
            clue="c",
        ),
    )
    paper = _paper([q], assets=assets, attributions=attrs)
    keys = {a.target.choice_key for a in paper.attributions}
    assert keys == {"A", "B", "C", "D"}


# --------------------------------------------------------------------------- #
# Synthetic choice panel (unconfirmed mapping is the default)
# --------------------------------------------------------------------------- #


def test_choice_panel_default_unconfirmed():
    panel = ChoicePanel(
        asset_id="panel-1",
        mapping=ChoicePanelMapping(
            A="$y=x$", B="$y=x^2$", C="$y=\\sqrt{x}$", D="$y=1/x$"
        ),
    )
    assert panel.mapping.confirmed is False
    q = _question(
        question_type="choice",
        content=QuestionContentV2(
            stem=[_text("如图四个图象，正确的是（）")],
            choice_panel=panel,
            answer="A",
            clue="c",
        ),
    )
    paper = _paper([q], assets=[_asset("panel-1")])
    assert paper.questions[0].content.choice_panel is not None


def test_choice_panel_confirmed_must_be_explicit():
    # A human can confirm a panel; the default is False, but True is allowed
    # once a reviewer sets it. This pins that the field exists and is mutable.
    panel = ChoicePanelMapping(A="a", B="b", C="c", D="d", confirmed=True)
    assert panel.confirmed is True


# --------------------------------------------------------------------------- #
# Multi-part question with per-part stem figure
# --------------------------------------------------------------------------- #


def test_multi_part_with_part_stem_figure():
    asset = _asset("part-1-fig")
    attr = ImageAttributionV2(
        attribution_id="att-p1",
        asset_id="part-1-fig",
        question_ref="1",
        target=TargetPartStem(part_id="1"),
        order=1,
        confidence="high",
        state="accepted",
    )
    part = QuestionPart(
        part_id="1",
        label="(1)",
        stem=[_text("求$AB$的长。如图"), _img("part-1-fig")],
        solution_steps=[SolutionStep(step_id="1", content=[_text("设$AB=x$。")])],
    )
    q = _question(
        question_type="problem",
        content=QuestionContentV2(
            stem=[_text("已知抛物线...")],
            answer="$5$",
            clue="c",
            parts=[part],
        ),
    )
    paper = _paper([q], assets=[asset], attributions=[attr])
    assert paper.questions[0].content.parts[0].part_id == "1"


# --------------------------------------------------------------------------- #
# Solution-step figure (question-level and part-level)
# --------------------------------------------------------------------------- #


def test_solution_step_figure_question_level():
    asset = _asset("sol-fig")
    attr = ImageAttributionV2(
        attribution_id="att-s1",
        asset_id="sol-fig",
        question_ref="1",
        target=TargetQuestionSolutionStep(step_id="2"),
        order=1,
        confidence="high",
        state="accepted",
    )
    q = _question(
        question_type="problem",
        content=QuestionContentV2(
            stem=[_text("证明...")],
            answer="证毕",
            clue="c",
            solution_steps=[
                SolutionStep(step_id="1", content=[_text("作辅助线。")]),
                SolutionStep(
                    step_id="2", content=[_text("如图所示"), _img("sol-fig")]
                ),
            ],
        ),
    )
    paper = _paper([q], assets=[asset], attributions=[attr])
    assert paper.attributions[0].target.target == "question_solution_step"


def test_solution_step_figure_part_level():
    asset = _asset("psol-fig")
    # part_solution_step needs BOTH part_id and step_id
    attr = ImageAttributionV2(
        attribution_id="att-ps1",
        asset_id="psol-fig",
        question_ref="1",
        target=TargetPartSolutionStep(part_id="1", step_id="1"),
        order=1,
        confidence="high",
        state="accepted",
    )
    part = QuestionPart(
        part_id="1",
        label="(1)",
        stem=[_text("求证")],
        solution_steps=[
            SolutionStep(step_id="1", content=[_text("由"), _img("psol-fig")])
        ],
    )
    q = _question(
        question_type="problem",
        content=QuestionContentV2(
            stem=[_text("已知...")], answer="证毕", clue="c", parts=[part]
        ),
    )
    paper = _paper([q], assets=[asset], attributions=[attr])
    t = paper.attributions[0].target
    assert t.target == "part_solution_step"
    assert t.part_id == "1" and t.step_id == "1"


# --------------------------------------------------------------------------- #
# Shared asset referenced by multiple targets (asset record not duplicated)
# --------------------------------------------------------------------------- #


def test_shared_asset_referenced_once():
    asset = _asset("shared-1")
    # Same figure appears in the stem AND in a solution step.
    attrs = [
        ImageAttributionV2(
            attribution_id="att-a",
            asset_id="shared-1",
            question_ref="1",
            target=TargetQuestionStem(),
            order=1,
            confidence="high",
            state="accepted",
        ),
        ImageAttributionV2(
            attribution_id="att-b",
            asset_id="shared-1",
            question_ref="1",
            target=TargetQuestionSolutionStep(step_id="1"),
            order=0,
            confidence="high",
            state="accepted",
        ),
    ]
    q = _question(
        question_type="problem",
        content=QuestionContentV2(
            stem=[_text("如图"), _img("shared-1")],
            answer="x",
            clue="c",
            solution_steps=[
                SolutionStep(step_id="1", content=[_text("见"), _img("shared-1")])
            ],
        ),
    )
    paper = _paper([q], assets=[asset], attributions=attrs)
    # One asset record, two attributions pointing at it.
    assert len(paper.assets) == 1
    assert len(paper.attributions) == 2
    assert {a.asset_id for a in paper.attributions} == {"shared-1"}


# --------------------------------------------------------------------------- #
# EMF classification: mixed_content is first-class, not needs_review
# --------------------------------------------------------------------------- #


def test_mixed_content_emf_is_accepted_class():
    asset = _asset("emf-1", emf_class="mixed_content")
    # mixed_content produces an image node; it is not auto-rejected.
    q = _question(
        content=QuestionContentV2(
            stem=[_text("如图，"), _img("emf-1")], answer="x", clue="c"
        )
    )
    paper = _paper([q], assets=[asset])
    assert paper.assets[0].emf_class == "mixed_content"


# --------------------------------------------------------------------------- #
# Contract rejections
# --------------------------------------------------------------------------- #


def test_image_only_stem_is_representable_as_confirmed_mixed_content():
    content = QuestionContentV2(stem=[_img("only-fig")], answer="x", clue="c")
    paper = _paper(
        [_question(content=content)],
        assets=[_asset("only-fig", emf_class="mixed_content")],
    )
    assert paper.questions[0].content.stem[0].kind == "image"


def test_ole_bound_vector_is_formula():
    asset = _vector_asset("formula-1", "formula", embedded=True)
    assert asset.emf_class == "formula"


def test_unbound_vector_is_diagram():
    asset = _vector_asset("diagram-1", "diagram", embedded=False)
    assert asset.emf_class == "diagram"


def test_vector_requires_ole_binding_evidence():
    with pytest.raises(Exception, match="ole_binding evidence is required"):
        SourceImageAsset(
            asset_id="emf-no-evidence",
            original_path="word/media/no-evidence.emf",
            original_sha256=_PNG_HASH,
            original_media_type="image/x-emf",
            emf_class="diagram",
        )


def test_formula_without_ole_binding_rejected():
    with pytest.raises(Exception, match="formula requires"):
        _vector_asset("formula-unbound", "formula", embedded=False)


def test_ole_bound_diagram_rejected():
    with pytest.raises(Exception, match="must be classified formula"):
        _vector_asset("diagram-bound", "diagram", embedded=True)


def test_mixed_content_requires_review_issue():
    with pytest.raises(Exception, match="requires review_issue_id"):
        _vector_asset("mixed-1", "mixed_content", embedded=False)


def test_needs_review_requires_review_issue():
    with pytest.raises(Exception, match="requires review_issue_id"):
        _vector_asset("pending-1", "needs_review", embedded=False)


def test_reviewed_diagram_may_retain_review_issue_trace():
    asset = _vector_asset(
        "reviewed-diagram",
        "diagram",
        embedded=False,
        review_issue_id="issue-reviewed-diagram",
    )
    assert asset.review_issue_id == "issue-reviewed-diagram"


def test_decorative_class_rejected():
    with pytest.raises(Exception):
        _asset("decorative-1", emf_class="decorative")


def test_observer_authority_fields_rejected():
    payload = _asset("legacy-fields").model_dump()
    payload["emf_class_provider"] = "observer"
    payload["gdi_record_hint"] = "text records"
    with pytest.raises(Exception):
        SourceImageAsset.model_validate(payload)


def test_formula_asset_cannot_be_content_image():
    q = _question(
        content=QuestionContentV2(
            stem=[_img("formula-1")],
            answer="x",
            clue="c",
        )
    )
    with pytest.raises(Exception, match="must not appear as a content image"):
        _paper([q], assets=[_vector_asset("formula-1", "formula", embedded=True)])


def test_empty_stem_rejected():
    with pytest.raises(Exception, match="stem"):
        QuestionContentV2(stem=[], answer="x", clue="c")


def test_choices_and_panel_mutually_exclusive():
    with pytest.raises(Exception, match="not both"):
        QuestionContentV2(
            stem=[_text("x")],
            choices=["1", "2", "3", "4"],
            choice_panel=ChoicePanel(
                asset_id="p", mapping=ChoicePanelMapping(A="1", B="2", C="3", D="4")
            ),
            answer="A",
            clue="c",
        )


def test_choices_must_be_four_when_present():
    with pytest.raises(Exception, match="exactly four"):
        QuestionContentV2(
            stem=[_text("x")], choices=["1", "2", "3"], answer="A", clue="c"
        )


def test_choice_question_requires_choices_or_panel():
    with pytest.raises(Exception, match="requires choices or choice_panel"):
        _question(
            question_type="choice",
            content=QuestionContentV2(stem=[_text("x")], answer="A", clue="c"),
        )


def test_problem_requires_solution_steps_or_part_steps():
    with pytest.raises(Exception, match="solution_steps"):
        _question(
            question_type="problem",
            content=QuestionContentV2(stem=[_text("x")], answer="A", clue="c"),
        )


def test_choice_question_forbids_parts():
    with pytest.raises(Exception, match="must not carry parts"):
        _question(
            question_type="choice",
            content=QuestionContentV2(
                stem=[_text("x")],
                choices=["1", "2", "3", "4"],
                answer="A",
                clue="c",
                parts=[
                    QuestionPart(part_id="1", label="(1)", stem=[_text("p")])
                ],
            ),
        )


def test_part_id_zero_rejected():
    with pytest.raises(Exception):
        QuestionPart(part_id="0", label="(1)", stem=[_text("x")])


def test_step_id_zero_rejected():
    with pytest.raises(Exception):
        SolutionStep(step_id="0", content=[_text("x")])


def test_full_crop_must_not_carry_box():
    with pytest.raises(Exception, match="full crop"):
        ImageCrop(kind="full", box_px=[0, 0, 10, 10])


def test_region_crop_requires_positive_area():
    with pytest.raises(Exception, match="positive area"):
        ImageCrop(kind="region", box_px=[10, 10, 5, 20])  # left >= right


def test_part_solution_step_requires_both_ids():
    # part_solution_step without part_id must fail to even construct.
    with pytest.raises(Exception):
        TargetPartSolutionStep(step_id="1")  # missing part_id


def test_duplicate_question_ref_rejected():
    q = _question(question_ref="5")
    q2 = _question(question_ref="5", question_number=6)
    with pytest.raises(Exception, match="duplicate question_ref"):
        _paper([q, q2])


def test_duplicate_asset_id_rejected():
    a = _asset("dup")
    a2 = _asset("dup")
    with pytest.raises(Exception, match="duplicate asset_id"):
        _paper([_question()], assets=[a, a2])


def test_attribution_unknown_asset_rejected():
    attr = ImageAttributionV2(
        attribution_id="att-x",
        asset_id="no-such-asset",
        question_ref="1",
        target=TargetQuestionStem(),
        order=0,
        confidence="high",
        state="accepted",
    )
    with pytest.raises(Exception, match="not in assets"):
        _paper([_question()], attributions=[attr])


def test_extra_key_rejected():
    payload = _paper([_question()]).model_dump(by_alias=True)
    payload["unexpected"] = "x"
    with pytest.raises(Exception):
        SourcePaper.model_validate(payload)


# --------------------------------------------------------------------------- #
# JSON Schema dump (v2 contract mirrors to JSON Schema like the v1 ones)
# --------------------------------------------------------------------------- #


def test_source_paper_json_schema_has_v2_discriminator():
    schema = SourcePaper.model_json_schema()
    # The schema const is nested under properties.schema.const
    consts = schema.get("properties", {}).get("schema", {}).get("const")
    assert consts == "math_exam_source_paper/v2"
