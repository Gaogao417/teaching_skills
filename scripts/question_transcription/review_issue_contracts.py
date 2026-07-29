#!/usr/bin/env python3
"""Review issue and resolution contracts for transcription staging.

These are the two paper-level sidecars produced by the review-issues flow
described in the suspicious-item review plan. They persist field-level
candidate conflicts between the observation layer and the staging layer so
that the Review UI can present them for human adjudication.

- ``math_transcription_review_issues/v1`` records every suspicious field: its
  question, field path, severity, all original candidates with their evidence,
  the candidate-set fingerprint and (for baseline comparisons) the old value.
- ``math_transcription_review_resolutions/v1`` records the adjudicated decision
  per issue plus the candidate-set fingerprint at decision time. A resolution
  whose fingerprint no longer matches the issue is stale and must be remade.

The v1 bundle discriminator stays unchanged. Additive issue variants allow the
same sidecar to carry blocking asset-classification adjudication without
breaking existing field-conflict fixtures.

Both bundles join on stable question/asset identifiers with the transcription pipeline. The
candidate-set hash deliberately excludes SHA digests (they are materialize-time
output stamps); only values, windows, confidence and evidence location enter
the fingerprint, so re-materializing an unchanged candidate set never
invalidates a resolution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.question_transcription.contracts import (
    AttributionConfidence,
    EvidenceRef,
    NonEmptyStr,
    QuestionRef,
    Sha256,
)


# --------------------------------------------------------------------------- #
# Shared enums
# --------------------------------------------------------------------------- #

IssueSeverity = Literal["blocking", "warning", "info"]
IssueOrigin = Literal["merge", "baseline_compare", "manual"]
MathToken = Literal[
    "sign",
    "exponent",
    "radicand",
    "fraction",
    "inequality",
    "numeric_value",
    "choice_letter",
]
Confidence = AttributionConfidence  # high / medium / low

# Canonical issue codes and the severity each implies. ``code`` is an open
# NonEmptyStr so the contract can evolve without a bump; codes listed here are
# soft-checked: if present, ``severity`` must match the mapped value. Codes
# absent from this map are accepted with any severity (forward-compatible).
CANONICAL_CODE_SEVERITY: dict[str, IssueSeverity] = {
    "stem_conflict": "blocking",
    "choice_conflict": "blocking",
    "answer_conflict": "blocking",
    "formula_conflict": "blocking",
    "solution_conclusion_conflict": "blocking",
    "question_ref_mismatch": "blocking",
    "existing_staging_stem_mismatch": "blocking",
    "image_crop_needs_confirmation": "warning",
    "evidence_span_needs_confirmation": "warning",
    "auto_resolved_format_diff": "info",
    "emf_class_needs_confirmation": "blocking",
}


class _Strict(BaseModel):
    """Strict base: reject unknown keys so contracts surface typos early."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Candidate (one observed value for a contested field)
# --------------------------------------------------------------------------- #


class ReviewCandidate(_Strict):
    """One observed value for a contested field, with its source evidence.

    Every candidate carries at least one :class:`EvidenceRef` so a reviewer can
    always return to the original page. ``selected`` marks the provisional pick
    emitted by merge; exactly one candidate per issue is selected.
    """

    window_id: NonEmptyStr
    raw_value: NonEmptyStr
    normalized_value: str | None = None
    confidence: Confidence
    evidence: list[EvidenceRef] = Field(min_length=1)
    selected: bool = False


# --------------------------------------------------------------------------- #
# Issue
# --------------------------------------------------------------------------- #


class ReviewIssue(_Strict):
    """A single suspicious field awaiting adjudication.

    ``question_ref`` is the stable join key shared with the transcription
    pipeline; ``item_id`` is stamped in once the issue is materialized into a
    staging item (Q0xx). ``candidates_hash`` fingerprints the candidate set so
    resolutions can detect when the underlying candidates changed.
    """

    kind: Literal["field_conflict"] = "field_conflict"
    issue_id: NonEmptyStr
    question_ref: QuestionRef
    item_id: str | None = None
    question_number: int = Field(ge=1)
    code: NonEmptyStr
    severity: IssueSeverity
    field_path: NonEmptyStr
    math_token: MathToken | None = None
    origin: IssueOrigin
    baseline_paper_id: str | None = None
    baseline_value: str | None = None
    candidates: list[ReviewCandidate] = Field(min_length=2)
    candidates_hash: Sha256
    detail: str | None = None

    @model_validator(mode="after")
    def _validate_issue(self) -> "ReviewIssue":
        selected = [c for c in self.candidates if c.selected]
        if len(selected) != 1:
            raise ValueError(
                f"issue {self.issue_id}: exactly one candidate must be selected "
                f"(got {len(selected)})"
            )
        window_ids = [c.window_id for c in self.candidates]
        if len(window_ids) != len(set(window_ids)):
            dupes = sorted({w for w in window_ids if window_ids.count(w) > 1})
            raise ValueError(
                f"issue {self.issue_id}: duplicate candidate window_id {dupes}"
            )
        expected = CANONICAL_CODE_SEVERITY.get(self.code)
        if expected is not None and self.severity != expected:
            raise ValueError(
                f"issue {self.issue_id}: code {self.code!r} requires "
                f"severity {expected!r}, got {self.severity!r}"
            )
        if self.origin == "baseline_compare" and not self.baseline_paper_id:
            raise ValueError(
                f"issue {self.issue_id}: baseline_compare origin requires "
                f"baseline_paper_id"
            )
        if self.origin == "baseline_compare":
            baseline_window = f"baseline:{self.baseline_paper_id}"
            matching = [
                candidate
                for candidate in self.candidates
                if candidate.window_id == baseline_window
            ]
            if len(matching) != 1:
                raise ValueError(
                    f"issue {self.issue_id}: baseline_compare requires exactly one "
                    f"candidate with window_id {baseline_window!r}"
                )
            if self.baseline_value is None or matching[0].raw_value != self.baseline_value:
                raise ValueError(
                    f"issue {self.issue_id}: baseline candidate must match baseline_value"
                )
        expected_hash = compute_candidates_hash(self.candidates)
        if self.candidates_hash != expected_hash:
            raise ValueError(
                f"issue {self.issue_id}: candidates_hash does not match candidates"
            )
        if self.item_id is not None:
            if len(self.item_id) != 4 or self.item_id[0] != "Q" or not self.item_id[1:].isdigit():
                raise ValueError(
                    f"issue {self.issue_id}: item_id must use Q001-style format"
                )
        return self


AssetReviewClass = Literal["diagram", "mixed_content"]


class AssetClassificationIssue(_Strict):
    """A blocking human decision between ``diagram`` and ``mixed_content``.

    The deterministic OLE rule has already excluded ``formula`` before this
    issue exists. ``detail`` is mandatory and records the concrete ambiguity,
    such as an apparent whole-stem EMF or an unclear text/diagram boundary.
    """

    kind: Literal["asset_classification"] = "asset_classification"
    issue_id: NonEmptyStr
    asset_id: NonEmptyStr
    question_ref: QuestionRef | None = None
    question_number: int | None = Field(default=None, ge=1)
    code: Literal["emf_class_needs_confirmation"] = (
        "emf_class_needs_confirmation"
    )
    severity: Literal["blocking"] = "blocking"
    allowed_classes: list[AssetReviewClass] = Field(
        default_factory=lambda: ["diagram", "mixed_content"]
    )
    proposed_class: AssetReviewClass | None = None
    evidence: list[EvidenceRef] = Field(min_length=1)
    detail: NonEmptyStr
    issue_hash: Sha256

    @model_validator(mode="after")
    def _validate_asset_issue(self) -> "AssetClassificationIssue":
        if set(self.allowed_classes) != {"diagram", "mixed_content"} or len(
            self.allowed_classes
        ) != 2:
            raise ValueError(
                f"issue {self.issue_id}: allowed_classes must contain exactly "
                "diagram and mixed_content"
            )
        expected_hash = compute_asset_issue_hash(self)
        if self.issue_hash != expected_hash:
            raise ValueError(
                f"issue {self.issue_id}: issue_hash does not match asset evidence"
            )
        return self


class ReviewIssuesBundle(_Strict):
    """Schema ``math_transcription_review_issues/v1``.

    One paper's review issues. The sidecar is written only when at least one
    conflict exists; an issue-free paper produces no sidecar (so legacy
    staging without one stays compatible).
    """

    schema_: Literal["math_transcription_review_issues/v1"] = Field(alias="schema")
    paper_id: NonEmptyStr
    generated_at: datetime
    issues: list[ReviewIssue | AssetClassificationIssue] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_issue_ids(self) -> "ReviewIssuesBundle":
        ids = [i.issue_id for i in self.issues]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate issue_id in bundle: {dupes}")
        return self


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


class IssueResolution(_Strict):
    """The adjudicated decision for one issue.

    ``resolved_candidates_hash`` must equal the issue's ``candidates_hash`` at
    decision time; once candidates change the resolution is stale.
    """

    kind: Literal["field_conflict"] = "field_conflict"
    issue_id: NonEmptyStr
    decision: Literal["accept_candidate", "accept_baseline", "manual"]
    accepted_window_id: str | None = None
    manual_value: str | None = None
    resolved_candidates_hash: Sha256
    reviewer: NonEmptyStr
    resolved_at: datetime
    note: str | None = None

    @model_validator(mode="after")
    def _validate_decision_fields(self) -> "IssueResolution":
        if self.decision == "accept_candidate" and not self.accepted_window_id:
            raise ValueError(
                f"resolution {self.issue_id}: accept_candidate requires "
                f"accepted_window_id"
            )
        if self.decision == "manual" and not self.manual_value:
            raise ValueError(
                f"resolution {self.issue_id}: manual decision requires manual_value"
            )
        if self.decision != "accept_candidate" and self.accepted_window_id is not None:
            raise ValueError(
                f"resolution {self.issue_id}: accepted_window_id is only valid "
                "for accept_candidate"
            )
        if self.decision != "manual" and self.manual_value is not None:
            raise ValueError(
                f"resolution {self.issue_id}: manual_value is only valid for manual"
            )
        return self


class AssetClassificationResolution(_Strict):
    """A human-confirmed classification for one asset issue."""

    kind: Literal["asset_classification"] = "asset_classification"
    issue_id: NonEmptyStr
    selected_class: AssetReviewClass
    resolved_issue_hash: Sha256
    reviewer: NonEmptyStr
    resolved_at: datetime
    note: str | None = None


class ReviewResolutionsBundle(_Strict):
    """Schema ``math_transcription_review_resolutions/v1``."""

    schema_: Literal["math_transcription_review_resolutions/v1"] = Field(alias="schema")
    paper_id: NonEmptyStr
    resolutions: list[IssueResolution | AssetClassificationResolution] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def _unique_issue_ids(self) -> "ReviewResolutionsBundle":
        ids = [r.issue_id for r in self.resolutions]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate issue_id in resolutions: {dupes}")
        return self


# --------------------------------------------------------------------------- #
# Pure helpers (tested; reused by the resolution applier / audit gate)
# --------------------------------------------------------------------------- #


def compute_candidates_hash(candidates: list[ReviewCandidate]) -> Sha256:
    """Fingerprint a candidate set independent of order and output SHA digests.

    Candidates are sorted by ``window_id`` before hashing so reordering never
    changes the result. Only value-bearing fields enter the digest: ``window_id``,
    ``raw_value``, ``normalized_value``, ``confidence`` and, per evidence, the
    ``source`` path, ``page_number`` and ``box_px``. SHA digests are deliberately
    excluded -- they are materialize-time output stamps, so including them would
    invalidate resolutions every time staging is re-materialized.
    """
    serialized = [
        {
            "window_id": c.window_id,
            "raw_value": c.raw_value,
            "normalized_value": c.normalized_value,
            "confidence": c.confidence,
            "evidence": [
                {
                    "kind": getattr(ev, "kind", None),
                    "source": ev.source,
                    "page_number": ev.page_number,
                    "box_px": getattr(ev, "box_px", None),
                }
                for ev in c.evidence
            ],
        }
        for c in sorted(candidates, key=lambda c: c.window_id)
    ]
    payload = json.dumps(serialized, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_asset_issue_hash(
    issue: AssetClassificationIssue | dict,
) -> Sha256:
    """Fingerprint the evidence and explanation behind an asset decision."""

    if isinstance(issue, AssetClassificationIssue):
        payload_source = {
            "asset_id": issue.asset_id,
            "question_ref": issue.question_ref,
            "question_number": issue.question_number,
            "allowed_classes": sorted(issue.allowed_classes),
            "proposed_class": issue.proposed_class,
            "evidence": issue.evidence,
            "detail": issue.detail,
        }
    else:
        payload_source = issue
    evidence = payload_source.get("evidence", [])
    serialized_evidence = []
    for ev in evidence:
        ev_data = ev if isinstance(ev, dict) else ev.model_dump()
        serialized_evidence.append(
            {
                "kind": ev_data.get("kind"),
                "source": ev_data.get("source"),
                "page_number": ev_data.get("page_number"),
                "box_px": ev_data.get("box_px"),
            }
        )
    serialized = {
        "asset_id": payload_source.get("asset_id"),
        "question_ref": payload_source.get("question_ref"),
        "question_number": payload_source.get("question_number"),
        "allowed_classes": sorted(
            payload_source.get(
                "allowed_classes", ["diagram", "mixed_content"]
            )
        ),
        "proposed_class": payload_source.get("proposed_class"),
        "evidence": serialized_evidence,
        "detail": payload_source.get("detail"),
    }
    payload = json.dumps(serialized, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def validate_resolutions_against_issues(
    issues: ReviewIssuesBundle, resolutions: ReviewResolutionsBundle
) -> list[str]:
    """Cross-check a resolutions bundle against its issues.

    Returns a list of human-readable error strings; an empty list means every
    resolution is consistent. Stale resolutions (candidate set changed since
    decision) are reported as ``stale: <issue_id>``.
    """
    errors: list[str] = []
    if issues.paper_id != resolutions.paper_id:
        errors.append(
            f"paper_id mismatch: {issues.paper_id} != {resolutions.paper_id}"
        )
    by_id = {issue.issue_id: issue for issue in issues.issues}
    for res in resolutions.resolutions:
        issue = by_id.get(res.issue_id)
        if issue is None:
            errors.append(f"unknown issue: {res.issue_id}")
            continue
        if isinstance(issue, ReviewIssue) and isinstance(res, IssueResolution):
            expected = compute_candidates_hash(issue.candidates)
            if res.resolved_candidates_hash != expected:
                errors.append(f"stale: {res.issue_id}")
                continue
            if res.decision == "accept_candidate":
                window_ids = {c.window_id for c in issue.candidates}
                if res.accepted_window_id not in window_ids:
                    errors.append(
                        f"dangling window: {res.issue_id} -> "
                        f"{res.accepted_window_id}"
                    )
        elif isinstance(issue, AssetClassificationIssue) and isinstance(
            res, AssetClassificationResolution
        ):
            expected = compute_asset_issue_hash(issue)
            if res.resolved_issue_hash != expected:
                errors.append(f"stale: {res.issue_id}")
                continue
            if res.selected_class not in issue.allowed_classes:
                errors.append(
                    f"invalid asset class: {res.issue_id} -> {res.selected_class}"
                )
        else:
            errors.append(
                f"issue/resolution kind mismatch: {res.issue_id}"
            )
    return errors


def unresolved_issues(
    issues: ReviewIssuesBundle,
    resolutions: ReviewResolutionsBundle | None = None,
    *,
    include_info: bool = False,
) -> list[ReviewIssue | AssetClassificationIssue]:
    """Return issues that still require a fresh, valid adjudication.

    ``info`` issues are audit-only by default. Blocking and warning issues both
    require an explicit resolution before a review staging can be rebuilt into
    normal staging.
    """

    resolution_by_id = {
        resolution.issue_id: resolution
        for resolution in (resolutions.resolutions if resolutions else [])
    }
    pending: list[ReviewIssue | AssetClassificationIssue] = []
    for issue in issues.issues:
        if issue.severity == "info" and not include_info:
            continue
        resolution = resolution_by_id.get(issue.issue_id)
        if resolution is None:
            pending.append(issue)
            continue
        one = ReviewResolutionsBundle(
            schema="math_transcription_review_resolutions/v1",
            paper_id=issues.paper_id,
            resolutions=[resolution],
        )
        if validate_resolutions_against_issues(issues, one):
            pending.append(issue)
    return pending


__all__ = [
    "AssetClassificationIssue",
    "AssetClassificationResolution",
    "AssetReviewClass",
    "IssueResolution",
    "ReviewCandidate",
    "ReviewIssue",
    "ReviewIssuesBundle",
    "ReviewResolutionsBundle",
    "compute_asset_issue_hash",
    "compute_candidates_hash",
    "unresolved_issues",
    "validate_resolutions_against_issues",
]
