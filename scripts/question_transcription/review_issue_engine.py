#!/usr/bin/env python3
"""Shared deterministic helpers for transcription review issues.

The engine deliberately does not decide which mathematical value is correct.
It only removes a narrow set of presentation-only differences, classifies
remaining disagreements, and packages every candidate with source evidence for
human adjudication.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from scripts.question_transcription.contracts import EvidenceRef
from scripts.question_transcription.review_issue_contracts import (
    MathToken,
    ReviewCandidate,
    ReviewIssue,
    compute_candidates_hash,
)


_CONFIDENCE_SCORE = {"low": 0, "medium": 1, "high": 2}
_TRAILING_PUNCTUATION = re.compile(r"[。．.;；]+$")
_WHITESPACE = re.compile(r"\s+")
_EXPONENT = re.compile(r"\^\{?[-+]?\d+\}?")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class FieldCandidate:
    window_id: str
    value: Any
    confidence: str
    evidence: tuple[EvidenceRef, ...]


def raw_value(value: Any) -> str:
    """Return a stable, reversible textual representation."""

    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_value(value: str, current: Any) -> Any:
    """Decode a resolution value according to the field's current shape."""

    if isinstance(current, str) or current is None:
        return value
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("list/mapping resolution must be valid JSON") from exc
    if isinstance(current, list) and not isinstance(decoded, list):
        raise ValueError("resolution must decode to a list")
    if isinstance(current, dict) and not isinstance(decoded, dict):
        raise ValueError("resolution must decode to a mapping")
    if isinstance(current, (int, float)) and not isinstance(decoded, type(current)):
        raise ValueError("resolution has the wrong numeric type")
    return decoded


def normalize_value(value: Any) -> str:
    """Normalize presentation-only differences without doing algebra.

    This intentionally does *not* simplify expressions, reorder terms, change
    signs, or compare mathematical equivalence.
    """

    if isinstance(value, list):
        return json.dumps(
            [normalize_value(item) for item in value],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if isinstance(value, dict):
        return json.dumps(
            {
                str(key): normalize_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    text = str(value)
    text = (
        text.replace("\\dfrac", "\\frac")
        .replace("\\tfrac", "\\frac")
        .replace("\\left", "")
        .replace("\\right", "")
        .replace("−", "-")
        .replace("–", "-")
        .replace("，", ",")
        .replace("；", ";")
        .replace("：", ":")
        .strip()
    )
    if len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        text = text[1:-1]
    if text.startswith(r"\(") and text.endswith(r"\)"):
        text = text[2:-2]
    text = _WHITESPACE.sub("", text)
    return _TRAILING_PUNCTUATION.sub("", text)


def classify_math_token(values: Iterable[str]) -> MathToken | None:
    """Classify a narrow mathematical token difference for UI highlighting."""

    unique = list(dict.fromkeys(values))
    if len(unique) < 2:
        return None

    def collapsed(pattern: re.Pattern[str] | str, replacement: str = "") -> set[str]:
        return {re.sub(pattern, replacement, value) for value in unique}

    if len(collapsed(r"(?<!\\)[+-]")) == 1:
        return "sign"
    if any("^" in value for value in unique) and len(collapsed(_EXPONENT, "^")) == 1:
        return "exponent"
    if any(r"\sqrt" in value for value in unique):
        return "radicand"
    if any(r"\frac" in value for value in unique):
        return "fraction"
    if any(
        marker in value
        for value in unique
        for marker in ("<", ">", r"\le", r"\ge", "≤", "≥")
    ):
        return "inequality"
    stripped = {value.strip("$").strip() for value in unique}
    if stripped and stripped.issubset({"A", "B", "C", "D"}):
        return "choice_letter"
    if len(collapsed(_NUMBER, "#")) == 1:
        return "numeric_value"
    return None


def issue_code(field_path: str) -> tuple[str, str]:
    """Return ``(code, severity)`` for a field path."""

    normalized = field_path.removeprefix("content.")
    if normalized == "stem_latex":
        return "stem_conflict", "blocking"
    if normalized == "choices":
        return "choice_conflict", "blocking"
    if normalized == "answer":
        return "answer_conflict", "blocking"
    if normalized in {"solution_steps", "solution_notes", "clue"}:
        return "solution_conclusion_conflict", "blocking"
    if normalized in {
        "solution_start_anchor",
        "solution_end_anchor",
        "evidence",
        "evidence.solution_start_anchor",
        "evidence.solution_end_anchor",
    }:
        return "evidence_span_needs_confirmation", "warning"
    if normalized in {
        "question_ref",
        "question_number",
        "question_type",
        "section_ref",
        "section_title",
        "points",
    }:
        return "question_ref_mismatch", "blocking"
    if normalized.startswith("figures"):
        return "image_crop_needs_confirmation", "warning"
    return "formula_conflict", "blocking"


def build_issue(
    *,
    question_ref: str,
    question_number: int,
    field_path: str,
    candidates: list[FieldCandidate],
    selected_value: Any,
    issue_id: str | None = None,
    origin: str = "merge",
    baseline_paper_id: str | None = None,
    baseline_value: str | None = None,
    detail: str | None = None,
    code_override: str | None = None,
    severity_override: str | None = None,
) -> ReviewIssue | None:
    """Build one issue, or ``None`` when every candidate is truly identical."""

    present = [candidate for candidate in candidates if candidate.value is not None]
    if len(present) < 2:
        return None
    raw = [raw_value(candidate.value) for candidate in present]
    normalized = [normalize_value(candidate.value) for candidate in present]
    if len(set(raw)) == 1:
        return None
    format_only = len(set(normalized)) == 1
    code, severity = (
        ("auto_resolved_format_diff", "info")
        if format_only
        else issue_code(field_path)
    )
    if code_override is not None:
        code = code_override
    if severity_override is not None:
        severity = severity_override

    selected_raw = raw_value(selected_value)
    selected_index = next(
        (
            index
            for index, candidate_raw in enumerate(raw)
            if candidate_raw == selected_raw
        ),
        0,
    )
    review_candidates = [
        ReviewCandidate(
            window_id=candidate.window_id,
            raw_value=candidate_raw,
            normalized_value=candidate_normalized,
            confidence=candidate.confidence,
            evidence=list(candidate.evidence),
            selected=index == selected_index,
        )
        for index, (candidate, candidate_raw, candidate_normalized) in enumerate(
            zip(present, raw, normalized, strict=True)
        )
    ]
    token = None if format_only else classify_math_token(normalized)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", field_path).strip("-").lower()
    actual_issue_id = issue_id or f"Q{question_number:03d}-{slug}"
    digest = compute_candidates_hash(review_candidates)
    return ReviewIssue(
        issue_id=actual_issue_id,
        question_ref=question_ref,
        question_number=question_number,
        code=code,
        severity=severity,
        field_path=field_path,
        math_token=token,
        origin=origin,
        baseline_paper_id=baseline_paper_id,
        baseline_value=baseline_value,
        candidates=review_candidates,
        candidates_hash=digest,
        detail=detail,
    )


def choose_by_confidence(candidates: list[FieldCandidate]) -> FieldCandidate:
    """Preserve the existing deterministic provisional-selection behavior."""

    if not candidates:
        raise ValueError("at least one field candidate is required")
    return sorted(
        candidates,
        key=lambda candidate: (
            -_CONFIDENCE_SCORE[candidate.confidence],
            raw_value(candidate.value),
            candidate.window_id,
        ),
    )[0]
