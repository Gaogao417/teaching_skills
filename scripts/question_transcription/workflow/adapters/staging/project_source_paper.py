#!/usr/bin/env python3
"""Compatibility projector from SourceQuestion v2 to the frozen v1 pipeline.

``SourcePaper`` remains authoritative. The v1 transcription and image bundles
produced here exist only so the current DraftAssembler/materializer can keep
running while downstream consumers learn RichContent. Image placement inside
text is therefore flattened conservatively; the exact ordered text/image
structure stays in ``paper.source.yaml``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .assemble_paper_draft import assemble
from scripts.question_transcription.contracts import (
    Attribution,
    AttributionAsset,
    AttributionProvider,
    FullCrop,
    ImageAttributionBundle,
    Provider,
    QuestionContent,
    QuestionTranscriptionBundle,
    RegionCrop,
    TranscriptionQuestion,
)
from scripts.question_transcription.review_issue_contracts import (
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
)
from scripts.question_transcription.source_contracts import (
    ChoiceContent,
    ImageAttributionV2,
    ImageNode,
    QuestionContentV2,
    RichContent,
    SourcePaper,
    SourceQuestion,
    TargetChoice,
    TargetChoicePanel,
    TargetPartSolutionStep,
    TargetPartStem,
    TargetQuestionSolutionStep,
    TargetQuestionStem,
    TextNode,
)
from .source_review_validation import (
    assert_source_review_ready,
)


def _text_only(nodes: RichContent, fallback: str) -> str:
    text = "".join(node.text for node in nodes if isinstance(node, TextNode))
    return text if text.strip() else fallback


def _project_content(content: QuestionContentV2) -> QuestionContent:
    stem_chunks = [_text_only(content.stem, "见题图。")]
    for part in content.parts:
        stem_chunks.append(f"{part.label}{_text_only(part.stem, '见小问题图。')}")
    stem = "\n".join(stem_chunks)

    choices: list[str] = []
    if content.choices:
        for index, choice in enumerate(content.choices):
            key = "ABCD"[index]
            if isinstance(choice, str):
                choices.append(choice)
            elif isinstance(choice, ChoiceContent):
                choices.append(_text_only(choice.content, f"选项{key}见图"))
    elif content.choice_panel is not None:
        mapping = content.choice_panel.mapping
        if not mapping.confirmed:
            raise ValueError("choice_panel mapping must be human-confirmed")
        choices = [mapping.A, mapping.B, mapping.C, mapping.D]

    steps = [
        _text_only(step.content, "见解答图。") for step in content.solution_steps
    ]
    for part in content.parts:
        steps.extend(
            f"{part.label}{_text_only(step.content, '见小问解答图。')}"
            for step in part.solution_steps
        )

    # The v1 contract requires problem/short_answer steps. SourceQuestion
    # already enforces the same invariant, including part-level steps.
    return QuestionContent(
        stem_latex=stem,
        choices=choices,
        answer=content.answer,
        clue=content.clue,
        solution_steps=steps,
    )


def project_transcription_bundle(
    source: SourcePaper,
    skeleton: QuestionTranscriptionBundle,
) -> QuestionTranscriptionBundle:
    """Overlay authoritative v2 content onto a v1 metadata/evidence skeleton."""

    if source.paper_id != skeleton.paper.id:
        raise ValueError(
            f"paper_id mismatch: source {source.paper_id} != skeleton {skeleton.paper.id}"
        )
    source_by_ref = {question.question_ref: question for question in source.questions}
    skeleton_refs = skeleton.refs()
    if set(source_by_ref) != set(skeleton_refs):
        missing = sorted(set(skeleton_refs) - set(source_by_ref))
        extra = sorted(set(source_by_ref) - set(skeleton_refs))
        raise ValueError(
            f"source/skeleton question_ref mismatch: missing={missing}, extra={extra}"
        )

    payload = skeleton.model_dump(by_alias=True, exclude_none=True)
    for section in payload["sections"]:
        projected_questions = []
        for old in section["questions"]:
            src: SourceQuestion = source_by_ref[old["question_ref"]]
            projected = TranscriptionQuestion(
                question_ref=src.question_ref,
                question_number=src.question_number,
                question_type=src.question_type,
                points=src.points,
                content=_project_content(src.content),
                evidence=old["evidence"],
            )
            projected_questions.append(
                projected.model_dump(by_alias=True, exclude_none=True)
            )
        section["questions"] = projected_questions
    payload["provider"] = Provider(
        kind="manual",
        name="source-question-v2-projector",
        version="v1",
    ).model_dump()
    return QuestionTranscriptionBundle.model_validate(payload)


def _target_role(attr: ImageAttributionV2) -> str:
    if isinstance(
        attr.target, (TargetQuestionSolutionStep, TargetPartSolutionStep)
    ):
        return "solution"
    return "prompt"


def _target_sort_key(attr: ImageAttributionV2) -> tuple:
    target = attr.target
    if isinstance(target, TargetQuestionStem):
        return (0, 0, 0, attr.order, attr.attribution_id)
    if isinstance(target, TargetChoice):
        return (
            1,
            "ABCD".index(target.choice_key),
            0,
            attr.order,
            attr.attribution_id,
        )
    if isinstance(target, TargetChoicePanel):
        return (2, 0, 0, attr.order, attr.attribution_id)
    if isinstance(target, TargetPartStem):
        return (3, int(target.part_id), 0, attr.order, attr.attribution_id)
    if isinstance(target, TargetQuestionSolutionStep):
        return (4, int(target.step_id), 0, attr.order, attr.attribution_id)
    return (
        5,
        int(target.part_id),
        int(target.step_id),
        attr.order,
        attr.attribution_id,
    )


def project_image_bundle(source: SourcePaper) -> ImageAttributionBundle:
    """Flatten accepted AND needs_review v2 targets into v1 prompt/solution
    attribution order.

    Attribution-level ``needs_review`` (asset is fine but the attribution is
    uncertain) is projected alongside ``accepted`` so it flows downstream into
    the draft and staging, where the Review UI surfaces it for human
    confirmation. ``rejected``/unknown attributions are not projected.
    """

    asset_by_id = {asset.asset_id: asset for asset in source.assets}
    projected = [
        attr for attr in source.attributions
        if attr.state in ("accepted", "needs_review")
    ]
    grouped: dict[tuple[str, str], list[ImageAttributionV2]] = defaultdict(list)
    for attr in projected:
        grouped[(attr.question_ref, _target_role(attr))].append(attr)

    projected_assets: list[AttributionAsset] = []
    used_asset_ids = sorted({attr.asset_id for attr in projected})
    for asset_id in used_asset_ids:
        asset = asset_by_id[asset_id]
        if asset.rendition is None:
            raise ValueError(
                f"asset {asset_id!r} referenced by a projected attribution "
                f"has no display rendition"
            )
        projected_assets.append(
            AttributionAsset(
                asset_id=asset_id,
                source=asset.rendition.path,
                sha256=asset.rendition.sha256,
                media_type=asset.rendition.media_type,
                width_px=asset.rendition.width_px,
                height_px=asset.rendition.height_px,
                disposition="attributed",
            )
        )

    projected_attributions: list[Attribution] = []
    provider = AttributionProvider(
        kind="manual",
        name="source-question-v2-projector",
        version="v1",
        evidence={"source_schema": "math_exam_source_paper/v2"},
    )
    for (question_ref, role), attrs in sorted(grouped.items()):
        for order, attr in enumerate(sorted(attrs, key=_target_sort_key)):
            crop = (
                FullCrop(kind="full")
                if attr.crop.kind == "full"
                else RegionCrop(
                    kind="region",
                    box_px=attr.crop.box_px,
                    whiteout_px=attr.crop.whiteout_px,
                )
            )
            projected_attributions.append(
                Attribution(
                    attribution_id=attr.attribution_id,
                    asset_id=attr.asset_id,
                    question_ref=question_ref,
                    role=role,
                    crop=crop,
                    order=order,
                    confidence=attr.confidence,
                    # Preserve the original attribution state so needs_review
                    # attributions stay marked pending downstream.
                    state=attr.state,
                    provider=provider,
                )
            )

    return ImageAttributionBundle(
        schema="math_image_attribution/v1",
        paper_id=source.paper_id,
        assets=projected_assets,
        attributions=projected_attributions,
    )


def _projected_solution_step_index(
    question: SourceQuestion,
    attr: ImageAttributionV2,
) -> int:
    """Map a v2 solution target to the flattened v1 solution_steps index."""

    target = attr.target
    if isinstance(target, TargetQuestionSolutionStep):
        for index, step in enumerate(question.content.solution_steps):
            if step.step_id == target.step_id:
                return index
        raise ValueError(
            f"question {question.question_ref}: unknown solution step {target.step_id}"
        )
    if isinstance(target, TargetPartSolutionStep):
        offset = len(question.content.solution_steps)
        for part in question.content.parts:
            if part.part_id == target.part_id:
                for local_index, step in enumerate(part.solution_steps):
                    if step.step_id == target.step_id:
                        return offset + local_index
                raise ValueError(
                    f"question {question.question_ref} part {target.part_id}: "
                    f"unknown solution step {target.step_id}"
                )
            offset += len(part.solution_steps)
    raise ValueError(
        f"attribution {attr.attribution_id} is not a solution-step target"
    )


def _stamp_solution_assignment_paths(
    draft: dict[str, Any],
    source: SourcePaper,
    skeleton: QuestionTranscriptionBundle,
) -> None:
    """Preserve v2 step targets when projecting into the scalar v1 draft."""

    items = [
        item
        for section in draft.get("sections", [])
        for item in section.get("items", [])
    ]
    skeleton_questions = [
        question
        for section in skeleton.sections
        for question in section.questions
    ]
    if len(items) != len(skeleton_questions):
        raise ValueError("draft/skeleton question count mismatch while placing solution images")
    item_by_ref = {
        question.question_ref: item
        for question, item in zip(skeleton_questions, items, strict=True)
    }
    source_by_ref = {question.question_ref: question for question in source.questions}
    attrs_by_ref: dict[str, list[ImageAttributionV2]] = defaultdict(list)
    for attr in source.attributions:
        if (
            attr.state in ("accepted", "needs_review")
            and isinstance(
                attr.target, (TargetQuestionSolutionStep, TargetPartSolutionStep)
            )
        ):
            attrs_by_ref[attr.question_ref].append(attr)

    for question_ref, attrs in attrs_by_ref.items():
        item = item_by_ref[question_ref]
        crops = item.get("solution") or []
        ordered = sorted(attrs, key=_target_sort_key)
        if len(crops) != len(ordered):
            raise ValueError(
                f"question {question_ref}: projected solution crop/target count mismatch"
            )
        question = source_by_ref[question_ref]
        for crop, attr in zip(crops, ordered, strict=True):
            index = _projected_solution_step_index(question, attr)
            crop["assignment_path"] = f"/solution_steps/{index}/diagram_col"


def project_source_to_draft(
    source: SourcePaper,
    skeleton: QuestionTranscriptionBundle,
    issues: ReviewIssuesBundle | None = None,
    resolutions: ReviewResolutionsBundle | None = None,
):
    """Gate, project, then invoke the existing deterministic DraftAssembler."""

    assert_source_review_ready(source, issues, resolutions)
    transcription = project_transcription_bundle(source, skeleton)
    images = project_image_bundle(source)
    draft, report = assemble(transcription, images)
    if draft is None or report.errors:
        details = "; ".join(error.detail for error in report.errors)
        raise ValueError(f"v1 DraftAssembler rejected projected source: {details}")
    _stamp_solution_assignment_paths(draft, source, skeleton)
    return draft, report


__all__ = [
    "project_image_bundle",
    "project_source_to_draft",
    "project_transcription_bundle",
]


def _load_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--skeleton", type=Path, required=True)
    parser.add_argument("--issues", type=Path)
    parser.add_argument("--resolutions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = SourcePaper.model_validate(_load_mapping(args.source))
        skeleton = QuestionTranscriptionBundle.model_validate(
            _load_mapping(args.skeleton)
        )
        issues = (
            ReviewIssuesBundle.model_validate(_load_mapping(args.issues))
            if args.issues
            else None
        )
        resolutions = (
            ReviewResolutionsBundle.model_validate(
                _load_mapping(args.resolutions)
            )
            if args.resolutions
            else None
        )
        draft, report = project_source_to_draft(
            source, skeleton, issues, resolutions
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(draft, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    report_payload = report.model_copy(
        update={"draft_path": str(args.output)}
    ).model_dump(by_alias=True, exclude_none=True)
    args.report.write_text(
        yaml.safe_dump(
            report_payload, allow_unicode=True, sort_keys=False, width=1000
        ),
        encoding="utf-8",
    )
    print(f"SOURCE PROJECTED: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
