"""Cross-bundle gate for SourceQuestion v2 and review sidecars.

The source contract can represent an unresolved asset so review tooling can
display it. Projection/materialization must use this gate first: any unresolved
blocking issue, stale resolution, or mismatch between the selected asset class
and ``SourceImageAsset.emf_class`` blocks structural output.
"""

from __future__ import annotations

from scripts.question_transcription.review_issue_contracts import (
    AssetClassificationIssue,
    AssetClassificationResolution,
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
    unresolved_issues,
    validate_resolutions_against_issues,
)
from scripts.question_transcription.source_contracts import (
    ChoiceContent,
    ImageNode,
    SourcePaper,
    TargetChoice,
    TargetChoicePanel,
    TargetPartSolutionStep,
    TargetPartStem,
    TargetQuestionSolutionStep,
    TargetQuestionStem,
)


def _target_key(target) -> tuple:
    if isinstance(target, TargetQuestionStem):
        return ("question_stem",)
    if isinstance(target, TargetChoice):
        return ("choice", target.choice_key)
    if isinstance(target, TargetChoicePanel):
        return ("choice_panel",)
    if isinstance(target, TargetPartStem):
        return ("part_stem", target.part_id)
    if isinstance(target, TargetQuestionSolutionStep):
        return ("question_solution_step", target.step_id)
    if isinstance(target, TargetPartSolutionStep):
        return ("part_solution_step", target.part_id, target.step_id)
    raise TypeError(f"unknown image target: {target!r}")


def _expected_content_bindings(source: SourcePaper) -> set[tuple]:
    expected: set[tuple] = set()

    def add_nodes(question_ref: str, target_key: tuple, nodes) -> None:
        for order, node in enumerate(nodes):
            if isinstance(node, ImageNode):
                expected.add(
                    (question_ref, node.asset_id, target_key, order)
                )

    for question in source.questions:
        ref = question.question_ref
        add_nodes(ref, ("question_stem",), question.content.stem)
        for index, choice in enumerate(question.content.choices):
            if isinstance(choice, ChoiceContent):
                add_nodes(ref, ("choice", "ABCD"[index]), choice.content)
        if question.content.choice_panel is not None:
            expected.add(
                (
                    ref,
                    question.content.choice_panel.asset_id,
                    ("choice_panel",),
                    0,
                )
            )
        for step in question.content.solution_steps:
            add_nodes(
                ref,
                ("question_solution_step", step.step_id),
                step.content,
            )
        for part in question.content.parts:
            add_nodes(ref, ("part_stem", part.part_id), part.stem)
            for step in part.solution_steps:
                add_nodes(
                    ref,
                    ("part_solution_step", part.part_id, step.step_id),
                    step.content,
                )
    return expected


def validate_source_review_gate(
    source: SourcePaper,
    issues: ReviewIssuesBundle | None = None,
    resolutions: ReviewResolutionsBundle | None = None,
) -> list[str]:
    """Return all reasons why a source paper is not ready for projection."""

    errors: list[str] = []
    if issues is not None and issues.paper_id != source.paper_id:
        errors.append(
            f"paper_id mismatch: source {source.paper_id} != issues {issues.paper_id}"
        )
    if resolutions is not None and resolutions.paper_id != source.paper_id:
        errors.append(
            "paper_id mismatch: "
            f"source {source.paper_id} != resolutions {resolutions.paper_id}"
        )
    if resolutions is not None and issues is None:
        errors.append("review resolutions provided without review issues")

    issue_by_id = {
        issue.issue_id: issue
        for issue in (issues.issues if issues is not None else [])
    }
    resolution_by_id = {
        resolution.issue_id: resolution
        for resolution in (
            resolutions.resolutions if resolutions is not None else []
        )
    }

    if issues is not None and resolutions is not None:
        errors.extend(validate_resolutions_against_issues(issues, resolutions))

    expected_bindings = _expected_content_bindings(source)
    accepted_bindings = {
        (
            attr.question_ref,
            attr.asset_id,
            _target_key(attr.target),
            attr.order,
        )
        for attr in source.attributions
        if attr.state == "accepted"
    }
    for binding in sorted(expected_bindings - accepted_bindings):
        question_ref, asset_id, target, order = binding
        errors.append(
            f"content image has no accepted attribution: question "
            f"{question_ref}, asset {asset_id}, target {target}, order {order}"
        )
    for binding in sorted(accepted_bindings - expected_bindings):
        question_ref, asset_id, target, order = binding
        errors.append(
            f"accepted attribution has no matching content image: question "
            f"{question_ref}, asset {asset_id}, target {target}, order {order}"
        )

    for asset in source.assets:
        issue_id = asset.review_issue_id
        if asset.emf_class in {"mixed_content", "needs_review"} and not issue_id:
            # Normally caught by SourceImageAsset itself; retained here for
            # callers that construct models without validation.
            errors.append(
                f"asset {asset.asset_id}: {asset.emf_class} requires review_issue_id"
            )
            continue
        if issue_id is None:
            continue

        issue = issue_by_id.get(issue_id)
        if not isinstance(issue, AssetClassificationIssue):
            errors.append(
                f"asset {asset.asset_id}: review issue {issue_id!r} is missing "
                "or is not an asset_classification issue"
            )
            continue
        if issue.asset_id != asset.asset_id:
            errors.append(
                f"asset {asset.asset_id}: issue {issue_id!r} targets "
                f"asset {issue.asset_id!r}"
            )
            continue

        resolution = resolution_by_id.get(issue_id)
        if asset.emf_class == "needs_review":
            errors.append(
                f"asset {asset.asset_id}: classification remains needs_review"
            )
            continue
        if not isinstance(resolution, AssetClassificationResolution):
            errors.append(
                f"asset {asset.asset_id}: classification issue {issue_id!r} "
                "has no asset resolution"
            )
            continue
        if resolution.resolved_issue_hash != issue.issue_hash:
            # The generic cross-check also reports this as stale, but this
            # asset-scoped message identifies the blocking source object.
            errors.append(
                f"asset {asset.asset_id}: classification resolution is stale"
            )
            continue
        if resolution.selected_class != asset.emf_class:
            errors.append(
                f"asset {asset.asset_id}: source class {asset.emf_class!r} "
                f"does not match reviewed class {resolution.selected_class!r}"
            )

    if issues is not None:
        pending = unresolved_issues(issues, resolutions)
        for issue in pending:
            if issue.severity == "blocking":
                errors.append(f"unresolved blocking review issue: {issue.issue_id}")

        source_asset_ids = {asset.asset_id for asset in source.assets}
        for issue in issues.issues:
            if (
                isinstance(issue, AssetClassificationIssue)
                and issue.asset_id not in source_asset_ids
            ):
                errors.append(
                    f"asset classification issue {issue.issue_id!r} targets "
                    f"unknown asset {issue.asset_id!r}"
                )

    return list(dict.fromkeys(errors))


def assert_source_review_ready(
    source: SourcePaper,
    issues: ReviewIssuesBundle | None = None,
    resolutions: ReviewResolutionsBundle | None = None,
) -> None:
    """Raise when projection/materialization would cross an unresolved gate."""

    errors = validate_source_review_gate(source, issues, resolutions)
    if errors:
        raise ValueError("source review gate failed:\n- " + "\n- ".join(errors))


__all__ = ["assert_source_review_ready", "validate_source_review_gate"]
