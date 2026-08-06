#!/usr/bin/env python3
"""Apply fresh review resolutions and emit a conflict-free observation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxObservationBundle,
)
from scripts.question_transcription.pdf_observation_contracts import (  # noqa: E402
    MergedPdfObservation,
)
from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
    unresolved_issues,
    validate_resolutions_against_issues,
)
from scripts.question_transcription.procedural.review_issue_engine import (  # noqa: E402
    decode_value,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def _canonical_path(field_path: str, question: dict[str, Any] | None = None) -> str:
    if "." in field_path or field_path in {
        "question_number",
        "question_type",
        "points",
        "section_ref",
        "section_title",
    }:
        return field_path
    if field_path in {
        "stem_latex",
        "choices",
        "answer",
        "clue",
        "solution_steps",
        "solution_notes",
    }:
        return f"content.{field_path}"
    if field_path in {"solution_start_anchor", "solution_end_anchor"}:
        return (
            f"evidence.{field_path}"
            if question is not None and "evidence" in question
            else field_path
        )
    return field_path


def _get_path(target: dict[str, Any], path: str) -> Any:
    current: Any = target
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"resolution field does not exist: {path}")
        current = current[token]
    return current


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    tokens = path.split(".")
    current: Any = target
    for token in tokens[:-1]:
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"resolution field does not exist: {path}")
        current = current[token]
    if not isinstance(current, dict) or tokens[-1] not in current:
        raise ValueError(f"resolution field does not exist: {path}")
    current[tokens[-1]] = value


def _apply_figure_value(
    question: dict[str, Any], path: str, chosen_raw: str
) -> None:
    _, role, order_text = path.split(".", 2)
    order = int(order_text)
    figure = next(
        (
            value
            for value in question.get("figures", [])
            if value.get("role") == role and int(value.get("order", 0)) == order
        ),
        None,
    )
    if figure is None:
        raise ValueError(f"resolution figure does not exist: {path}")
    decoded = decode_value(
        chosen_raw,
        {
            "page_number": figure.get("page_number"),
            "box_px": figure.get("box_px"),
            "whiteout_px": figure.get("whiteout_px", []),
        },
    )
    for key in ("page_number", "box_px", "whiteout_px"):
        figure[key] = decoded[key]


def apply_resolutions(
    observation: DocxObservationBundle | MergedPdfObservation,
    issues: ReviewIssuesBundle,
    resolutions: ReviewResolutionsBundle,
) -> DocxObservationBundle | MergedPdfObservation:
    if observation.paper.id != issues.paper_id or issues.paper_id != resolutions.paper_id:
        raise ValueError("observation/issues/resolutions paper_id mismatch")
    cross_errors = validate_resolutions_against_issues(issues, resolutions)
    if cross_errors:
        raise ValueError("; ".join(cross_errors))
    pending = unresolved_issues(issues, resolutions)
    if pending:
        raise ValueError(
            "unresolved review issues: "
            + ", ".join(issue.issue_id for issue in pending)
        )

    raw = observation.model_dump(by_alias=True, exclude_none=True, mode="json")
    question_by_ref = {
        str(question["question_ref"]): question for question in raw["questions"]
    }
    issue_by_id = {issue.issue_id: issue for issue in issues.issues}
    chosen_by_field: dict[tuple[str, str], str] = {}
    for resolution in resolutions.resolutions:
        issue = issue_by_id[resolution.issue_id]
        if issue.severity == "info":
            continue
        if resolution.decision == "accept_candidate":
            candidate = next(
                candidate
                for candidate in issue.candidates
                if candidate.window_id == resolution.accepted_window_id
            )
            chosen_raw = candidate.raw_value
        elif resolution.decision == "accept_baseline":
            if issue.baseline_value is None:
                raise ValueError(
                    f"{issue.issue_id}: accept_baseline requires baseline_value"
                )
            chosen_raw = issue.baseline_value
        else:
            assert resolution.manual_value is not None
            chosen_raw = resolution.manual_value

        question = question_by_ref.get(issue.question_ref)
        if question is None:
            raise ValueError(f"issue references unknown question: {issue.question_ref}")
        path = _canonical_path(issue.field_path, question)
        key = (issue.question_ref, path)
        previous = chosen_by_field.get(key)
        if previous is not None and previous != chosen_raw:
            raise ValueError(
                f"conflicting resolutions for {issue.question_ref} {path}"
            )
        chosen_by_field[key] = chosen_raw
        if path.startswith("figures."):
            _apply_figure_value(question, path, chosen_raw)
            continue
        current = _get_path(question, path)
        _set_path(question, path, decode_value(chosen_raw, current))

    if raw["schema"] == "math_docx_observation/v1":
        raw["conflicts"] = []
        return DocxObservationBundle.model_validate(raw)
    if raw["schema"] == "math_pdf_merged_observation/v1":
        raw["conflicts"] = []
        return MergedPdfObservation.model_validate(raw)
    raise ValueError(f"unsupported observation schema: {raw['schema']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw_observation = _load_yaml(args.observation)
    if raw_observation.get("schema") == "math_docx_observation/v1":
        observation: DocxObservationBundle | MergedPdfObservation = (
            DocxObservationBundle.model_validate(raw_observation)
        )
    elif raw_observation.get("schema") == "math_pdf_merged_observation/v1":
        observation = MergedPdfObservation.model_validate(raw_observation)
    else:
        raise SystemExit(
            f"unsupported observation schema: {raw_observation.get('schema')}"
        )
    issues = ReviewIssuesBundle.model_validate(_load_yaml(args.issues))
    resolutions = ReviewResolutionsBundle.model_validate(
        _load_yaml(args.resolutions)
    )
    try:
        resolved = apply_resolutions(observation, issues, resolutions)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(
            resolved.model_dump(by_alias=True, exclude_none=True, mode="json"),
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    print(f"REVIEW RESOLUTIONS APPLIED: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
