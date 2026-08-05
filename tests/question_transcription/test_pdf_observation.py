from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from scripts.question_transcription.workflow.adapters.source.adapt_pdf_images import adapt as adapt_images
from scripts.question_transcription.adapt_pdf_transcription import (
    adapt as adapt_transcription,
)
from scripts.question_transcription.contracts import (
    ImageAttributionBundle,
    PaperMeta,
    QuestionTranscriptionBundle,
)
from scripts.question_transcription.merge_pdf_observations import (
    merge_observations,
    merge_observations_with_issues,
)
from scripts.question_transcription.mimo_client import MimoClient, extract_json
from scripts.question_transcription.observe_pdf_pages import (
    make_windows,
    observe_windows,
)
from scripts.question_transcription.pdf_observation_contracts import (
    PdfPageObservation,
)
from scripts.question_transcription.workflow.adapters.source.pdf_source_manifest import build_manifest


def _paper(source_archive: str) -> PaperMeta:
    return PaperMeta(
        id="TEST-PDF",
        title="测试卷",
        grade="九年级",
        subject="数学",
        source_archive=source_archive,
        question_bank="../../question-bank.yaml",
    )


def _question(*, page_number: int = 1, stem: str = "求$x+1$的值。") -> dict:
    return {
        "question_ref": "1",
        "question_number": 1,
        "section_ref": "problem",
        "section_title": "解答题",
        "question_type": "problem",
        "points": 5,
        "content": {
            "stem_latex": stem,
            "choices": [],
            "answer": "$2$",
            "clue": "代入。",
            "solution_steps": ["由$x=1$，得$x+1=2$。"],
            "solution_notes": [],
        },
        "question_evidence": [
            {"page_number": page_number, "box_px": [10, 10, 190, 80]}
        ],
        "solution_evidence": [
            {"page_number": page_number, "box_px": [10, 90, 190, 150]}
        ],
        "solution_start_anchor": "1.",
        "solution_end_anchor": "<END_OF_SOURCE>",
        "figures": [
            {
                "local_id": "q1-prompt-1",
                "page_number": page_number,
                "role": "prompt",
                "order": 0,
                "box_px": [100, 20, 180, 75],
                "whiteout_px": [],
                "confidence": "medium",
                "state": "needs_review",
                "needs_human_crop": False,
            }
        ],
        "confidence": {"stem": "high", "formula": "medium"},
        "continues_from_previous": False,
        "continues_to_next": False,
        "notes": [],
    }


def _observation(manifest, paper, *, window_id="p001", question=None):
    return PdfPageObservation.model_validate(
        {
            "schema": "math_pdf_page_observation/v1",
            "paper": paper.model_dump(),
            "provider": {
                "kind": "vision_api",
                "name": "xiaomi-mimo",
                "version": "mimo-v2.5/prompt-v1",
            },
            "prompt_version": "prompt-v1",
            "window_id": window_id,
            "pages": [page.model_dump() for page in manifest.pages],
            "questions": [question or _question()],
        }
    )


@pytest.fixture
def source(tmp_path: Path):
    pages = tmp_path / "pages"
    pages.mkdir()
    paths = []
    for number, color in enumerate(["white", "beige", "lightblue"], start=1):
        path = pages / f"{number:03d}.png"
        Image.new("RGB", (200, 160), color).save(path)
        paths.append(path)
    manifest = build_manifest(
        paper_id="TEST-PDF",
        source_archive=tmp_path.as_posix(),
        page_paths=paths,
    )
    return tmp_path, manifest


def test_manifest_records_real_dimensions_hashes_and_order(source):
    tmp_path, manifest = source
    assert [p.page_number for p in manifest.pages] == [1, 2, 3]
    assert manifest.pages[0].source == "pages/001.png"
    assert (manifest.pages[0].width_px, manifest.pages[0].height_px) == (200, 160)
    assert manifest.pages[0].sha256.startswith("sha256:")
    assert manifest.source_archive == tmp_path.as_posix()


def test_window_generation_overlaps_one_page(source):
    _, manifest = source
    windows = make_windows(manifest.pages, window_size=2, overlap=1)
    assert [[p.page_number for p in window] for window in windows] == [
        [1, 2],
        [2, 3],
        [3],
    ]


def test_joint_provider_response_and_cache(source, tmp_path):
    root, manifest = source
    calls = []

    def provider(body):
        calls.append(body)
        return {"questions": [_question()]}

    client = MimoClient(provider=provider, cache_dir=tmp_path / "cache")
    paper = _paper(root.as_posix())
    first = observe_windows(
        manifest, paper=paper, client=client, window_size=3, overlap=0
    )
    second = observe_windows(
        manifest, paper=paper, client=client, window_size=3, overlap=0
    )
    assert len(calls) == 1
    assert first == second
    message_content = calls[0]["messages"][1]["content"]
    assert sum(part["type"] == "image_url" for part in message_content) == 3
    assert first[0].questions[0].content is not None
    assert first[0].questions[0].figures[0].box_px == [100, 20, 180, 75]


def test_provider_normalized_bbox_and_nulls_are_normalized(source):
    root, manifest = source
    raw = _question()
    raw["points"] = None
    raw["section_ref"] = ""
    raw["section_title"] = ""
    raw["notes"] = "跨页继续。"
    raw["content"]["choices"] = None
    raw["content"]["clue"] = None
    raw["content"]["solution_notes"] = None
    raw["solution_end_anchor"] = None
    raw["question_evidence"][0]["box_norm"] = [50, 63, 950, 500]
    raw["question_evidence"][0].pop("box_px")
    raw["figures"][0]["box_norm"] = [500, 125, 900, 469]
    raw["figures"][0].pop("box_px")
    raw["figures"][0]["whiteout_px"] = None
    raw["figures"][0]["confidence"] = {
        "role": "high",
        "subject": "medium",
        "label": "high",
    }
    client = MimoClient(provider=lambda _body: {"questions": [raw]})
    observed = observe_windows(
        manifest,
        paper=_paper(root.as_posix()),
        client=client,
        window_size=3,
        overlap=0,
    )[0]
    question = observed.questions[0]
    assert question.points == 0
    assert question.section_ref == "unsectioned"
    assert question.section_title == "未分节"
    assert question.notes == ["跨页继续。"]
    assert question.content.clue == "依据题目条件推导。"
    assert question.solution_end_anchor == "<END_OF_SOURCE>"
    assert question.question_evidence[0].box_px == [10, 10, 190, 80]
    assert question.figures[0].box_px == [100, 20, 180, 75]
    assert question.figures[0].confidence == "medium"
    assert question.figures[0].state == "needs_review"


@pytest.mark.parametrize(
    ("whiteout_norm", "expected"),
    [
        ([0, 0, 0, 0], []),
        ([100, 100, 200, 200], [[20, 16, 40, 32]]),
    ],
)
def test_provider_tolerates_flat_whiteout_norm(source, whiteout_norm, expected):
    root, manifest = source
    raw = _question()
    raw["figures"][0]["whiteout_norm"] = whiteout_norm
    client = MimoClient(provider=lambda _body: {"questions": [raw]})
    observed = observe_windows(
        manifest,
        paper=_paper(root.as_posix()),
        client=client,
        window_size=3,
        overlap=0,
    )[0]
    assert observed.questions[0].figures[0].whiteout_px == expected


def test_mimo_json_extraction_accepts_fence_and_surrounding_text():
    assert extract_json('```json\n{"questions":[]}\n```') == {"questions": []}
    assert extract_json('result: {"questions":[]} done') == {"questions": []}


def test_bbox_is_checked_against_original_page(source):
    root, manifest = source
    question = _question()
    question["figures"][0]["box_px"] = [100, 20, 201, 75]
    with pytest.raises(ValidationError, match="horizontal bounds"):
        _observation(manifest, _paper(root.as_posix()), question=question)


def test_overlap_merge_deduplicates_evidence_and_figure(source):
    root, manifest = source
    paper = _paper(root.as_posix())
    first = _observation(manifest, paper, window_id="a")
    second = _observation(manifest, paper, window_id="b")
    merged = merge_observations([first, second])
    assert merged.source_windows == ["a", "b"]
    assert len(merged.questions) == 1
    assert len(merged.questions[0].question_evidence) == 1
    assert len(merged.questions[0].figures) == 1


def test_overlap_merge_preserves_text_and_bbox_conflicts_for_review(source):
    root, manifest = source
    paper = _paper(root.as_posix())
    first = _observation(manifest, paper, window_id="a")
    changed_text = _question(stem="不同文本")
    merged, issues = merge_observations_with_issues(
        [first, _observation(manifest, paper, window_id="b", question=changed_text)]
    )
    assert merged.conflicts == ["1"]
    assert issues is not None
    assert any(issue.code == "stem_conflict" for issue in issues.issues)
    with pytest.raises(ValueError, match="unresolved"):
        adapt_transcription(merged)
    changed_box = _question()
    changed_box["figures"][0]["box_px"] = [99, 20, 180, 75]
    merged_box, box_issues = merge_observations_with_issues(
        [first, _observation(manifest, paper, window_id="c", question=changed_box)]
    )
    assert merged_box.conflicts == ["1"]
    assert box_issues is not None
    assert any(
        issue.code == "image_crop_needs_confirmation"
        for issue in box_issues.issues
    )


def test_one_observation_splits_into_both_public_bundles(source):
    root, manifest = source
    merged = merge_observations(
        [_observation(manifest, _paper(root.as_posix()))]
    )
    transcription = QuestionTranscriptionBundle.model_validate(
        adapt_transcription(merged)
    )
    images = ImageAttributionBundle.model_validate(adapt_images(merged))
    assert transcription.refs() == ["1"]
    assert transcription.sections[0].questions[0].content.solution_steps == [
        "由$x=1$，得$x+1=2$。"
    ]
    attribution = images.attributions[0]
    assert attribution.crop.box_px == [100, 20, 180, 75]
    assert attribution.confidence == "medium"
    assert attribution.state == "needs_review"
    assert len(images.assets) == 3
    assert images.assets[1].disposition == "ignored"


def test_model_accepted_figure_requires_explicit_confirmation(source):
    root, manifest = source
    question = _question()
    question["figures"][0]["confidence"] = "high"
    question["figures"][0]["state"] = "accepted"
    merged = merge_observations(
        [
            _observation(
                manifest, _paper(root.as_posix()), question=question
            )
        ]
    )
    guarded = ImageAttributionBundle.model_validate(adapt_images(merged))
    assert guarded.attributions[0].state == "needs_review"
    assert (
        guarded.attributions[0].provider.evidence[
            "model_acceptance_downgraded"
        ]
        is True
    )
    confirmed = ImageAttributionBundle.model_validate(
        adapt_images(merged, allow_model_accepted=True)
    )
    assert confirmed.attributions[0].state == "accepted"


def test_text_and_image_fail_independently(source):
    root, manifest = source
    question = _question()
    question["content"] = None
    merged = merge_observations(
        [_observation(manifest, _paper(root.as_posix()), question=question)]
    )
    images = ImageAttributionBundle.model_validate(adapt_images(merged))
    assert len(images.attributions) == 1
    with pytest.raises(ValueError, match="transcription content missing"):
        adapt_transcription(merged)

    no_figure = _question()
    no_figure["figures"] = []
    merged_text = merge_observations(
        [_observation(manifest, _paper(root.as_posix()), question=no_figure)]
    )
    transcription = QuestionTranscriptionBundle.model_validate(
        adapt_transcription(merged_text)
    )
    assert transcription.refs() == ["1"]
    assert ImageAttributionBundle.model_validate(
        adapt_images(merged_text)
    ).attributions == []


# =========================================================================== #
# Span-index-driven observation (§7.1 / §7.3 / §10.1)
# =========================================================================== #

from scripts.question_transcription.observe_pdf_pages import observe as observe_with_index  # noqa: E402
from scripts.question_transcription.question_span_index import (  # noqa: E402
    IndexedQuestion,
    QuestionSpanIndex,
    SourceFingerprint,
)


def _index(questions: list[IndexedQuestion], page_shas: list[str]) -> QuestionSpanIndex:
    # The index must list every source page (page_numbers is the full page set of
    # the source), even when a question only spans a subset.
    page_numbers = list(range(1, len(page_shas) + 1))
    return QuestionSpanIndex(
        schema="math_question_span_index/v1",
        source_kind="pdf",
        page_numbers=page_numbers,
        fingerprint=SourceFingerprint(page_sha256=page_shas),
        status="ready",
        questions=questions,
        issues=[],
    )


def _pdf_question(ref: str, *, page_number: int = 1) -> dict:
    q = _question(page_number=page_number)
    q["question_ref"] = ref
    q["question_number"] = int(ref)
    return q


def _shas(manifest) -> list[str]:
    return [page.sha256 for page in manifest.pages]


def test_pdf_span_observe_exact_match_passes(source, tmp_path):
    root, manifest = source
    index = _index(
        [IndexedQuestion(question_ref="1", question_number=1, question_pages=[1])],
        _shas(manifest),
    )

    def provider(body):
        return {"questions": [_pdf_question("1", page_number=1)]}

    client = MimoClient(provider=provider, cache_dir=tmp_path / "cache")
    observations = observe_with_index(
        manifest, paper=_paper(root.as_posix()), span_index=index, client=client
    )
    refs = [q.question_ref for obs in observations for q in obs.questions]
    assert refs == ["1"]
    # §7.1: bbox is preserved (MiMo joint text+bbox regression).
    assert observations[0].questions[0].figures[0].box_px == [100, 20, 180, 75]


def test_pdf_span_observe_prompt_carries_expected_refs_and_role(source, tmp_path):
    root, manifest = source
    index = _index(
        [IndexedQuestion(question_ref="1", question_number=1, question_pages=[1])],
        _shas(manifest),
    )
    seen: list[str] = []

    def provider(body):
        seen.append(body["messages"][1]["content"][0]["text"])
        return {"questions": [_pdf_question("1")]}

    client = MimoClient(provider=provider, cache_dir=tmp_path / "cache")
    observe_with_index(
        manifest, paper=_paper(root.as_posix()), span_index=index, client=client
    )
    # §7.1: prompt carries the expected question refs and the role label.
    assert any("预期题号：1" in p for p in seen)
    assert any("题干" in p for p in seen)


def test_pdf_span_observe_missing_triggers_targeted_page_repair(source, tmp_path):
    root, manifest = source
    index = _index(
        [
            IndexedQuestion(question_ref="1", question_number=1, question_pages=[1]),
            IndexedQuestion(question_ref="2", question_number=2, question_pages=[2]),
        ],
        _shas(manifest),
    )
    first_done = {"v": False}
    image_counts: list[int] = []

    def provider(body):
        content = body["messages"][1]["content"]
        text = content[0]["text"]
        image_counts.append(sum(item["type"] == "image_url" for item in content))
        is_repair = "repair" in text
        if not is_repair and not first_done["v"]:
            first_done["v"] = True
            # First round freezes Q1 and omits Q2.
            return {"questions": [_pdf_question("1", page_number=1)]}
        return {"questions": [_pdf_question("2", page_number=2)]}

    client = MimoClient(provider=provider, cache_dir=tmp_path / "cache")
    observations = observe_with_index(
        manifest, paper=_paper(root.as_posix()), span_index=index, client=client, max_repairs=1
    )
    refs = [q.question_ref for obs in observations for q in obs.questions]
    assert refs == ["1", "2"]
    assert image_counts == [2, 1]


def test_pdf_span_observe_unexpected_is_isolated(source, tmp_path):
    root, manifest = source
    index = _index(
        [IndexedQuestion(question_ref="1", question_number=1, question_pages=[1])],
        _shas(manifest),
    )

    def provider(body):
        # Return expected "1" plus an unexpected "99".
        return {"questions": [_pdf_question("1"), _pdf_question("99")]}

    client = MimoClient(provider=provider, cache_dir=tmp_path / "cache")
    observations = observe_with_index(
        manifest, paper=_paper(root.as_posix()), span_index=index, client=client
    )
    refs = [q.question_ref for obs in observations for q in obs.questions]
    assert "99" not in refs
    assert refs == ["1"]


def test_pdf_span_observe_rejects_stale_fingerprint(source, tmp_path):
    root, manifest = source
    index = _index(
        [IndexedQuestion(question_ref="1", question_number=1, question_pages=[1])],
        ["sha256:" + "0" * 64] * len(manifest.pages),
    )
    client = MimoClient(provider=lambda body: {"questions": []}, cache_dir=tmp_path / "cache")
    with pytest.raises(ValueError, match="SHA"):
        observe_with_index(
            manifest, paper=_paper(root.as_posix()), span_index=index, client=client
        )


def test_pdf_span_observe_content_null_tolerated(source, tmp_path):
    """§7.3: content=null is tolerated for question-only / solution-only pages."""
    root, manifest = source
    index = _index(
        [IndexedQuestion(question_ref="1", question_number=1, question_pages=[1])],
        _shas(manifest),
    )

    def provider(body):
        q = _pdf_question("1")
        q["content"] = None  # question-only page segment
        return {"questions": [q]}

    client = MimoClient(provider=provider, cache_dir=tmp_path / "cache")
    observations = observe_with_index(
        manifest, paper=_paper(root.as_posix()), span_index=index, client=client
    )
    assert observations[0].questions[0].content is None
