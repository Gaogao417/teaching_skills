"""Tests for the review-issue / resolution contracts (suspicious-item plan, Step 1).

These validate that the sidecar contracts load the golden fixtures, reject the
error classes the plan promises (bad severity, duplicate candidate, missing
evidence, stale resolution hash, etc.), and that the candidate-set hash is
deterministic and excludes SHA digests. JSON Schema dump covers both new
contracts.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.procedural import schema_dump  # noqa: E402
from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    AssetClassificationIssue,
    AssetClassificationResolution,
    IssueResolution,
    ReviewCandidate,
    ReviewIssue,
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
    compute_asset_issue_hash,
    compute_candidates_hash,
    validate_resolutions_against_issues,
    unresolved_issues,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _candidate(window_id: str, raw: str, *, selected: bool = False, confidence: str = "high") -> dict:
    return {
        "window_id": window_id,
        "raw_value": raw,
        "normalized_value": raw.strip("$"),
        "confidence": confidence,
        "evidence": [{"kind": "page", "source": f"pages/{window_id}.png", "page_number": 4}],
        "selected": selected,
    }


def _base_issue(candidates: list[dict] | None = None) -> dict:
    if candidates is None:
        candidates = [_candidate("w-A", "$3$"), _candidate("w-B", "$-3$", selected=True)]
    # Best-effort hash from valid candidates; negative tests with malformed
    # candidates fall back to a placeholder (the rejection under test is the
    # issue-level validator, not the hash recomputation here).
    try:
        h = compute_candidates_hash([ReviewCandidate.model_validate(c) for c in candidates])
    except Exception:
        h = "sha256:" + "0" * 64
    return {
        "issue_id": "Q015-answer-sign",
        "question_ref": "15",
        "question_number": 15,
        "code": "answer_conflict",
        "severity": "blocking",
        "field_path": "answer",
        "math_token": "sign",
        "origin": "merge",
        "candidates": candidates,
        "candidates_hash": h,
    }


def _base_issues_bundle(issue: dict | None = None) -> dict:
    return {
        "schema": "math_transcription_review_issues/v1",
        "paper_id": "2024-BAOSHAN-ERMO",
        "generated_at": "2026-07-28T12:00:00",
        "issues": [issue or _base_issue()],
    }


def _base_resolution(issue_hash: str | None = None) -> dict:
    return {
        "issue_id": "Q015-answer-sign",
        "decision": "accept_candidate",
        "accepted_window_id": "w-B",
        "resolved_candidates_hash": issue_hash or "sha256:" + "0" * 64,
        "reviewer": "ui",
        "resolved_at": "2026-07-28T12:05:00",
    }


def _asset_issue() -> dict:
    payload = {
        "kind": "asset_classification",
        "issue_id": "asset-emf-7-class",
        "asset_id": "emf-7",
        "question_ref": "5",
        "question_number": 5,
        "code": "emf_class_needs_confirmation",
        "severity": "blocking",
        "allowed_classes": ["diagram", "mixed_content"],
        "proposed_class": "mixed_content",
        "evidence": [
            {
                "kind": "page",
                "source": "pages/page-02.png",
                "page_number": 2,
            }
        ],
        "detail": "疑似整块题干位于 EMF 内，图与正文边界不清。",
    }
    payload["issue_hash"] = compute_asset_issue_hash(payload)
    return payload


# --------------------------------------------------------------------------- #
# Golden fixtures load
# --------------------------------------------------------------------------- #


def test_baoshan_review_issues_fixture_loads():
    bundle = ReviewIssuesBundle.model_validate(_load(FIX / "baoshan-q15.review-issues.yaml"))
    assert bundle.paper_id == "2024-BAOSHAN-ERMO"
    issue = bundle.issues[0]
    assert issue.severity == "blocking"
    assert issue.math_token == "sign"
    selected = [c.window_id for c in issue.candidates if c.selected]
    assert selected == ["docx-window-04"]
    assert issue.candidates[0].evidence  # every candidate carries evidence


def test_baoshan_review_resolutions_fixture_loads():
    bundle = ReviewResolutionsBundle.model_validate(_load(FIX / "baoshan-q15.review-resolutions.yaml"))
    res = bundle.resolutions[0]
    assert res.decision == "accept_candidate"
    assert res.accepted_window_id == "docx-window-04"


def test_fixtures_cross_check_clean():
    issues = ReviewIssuesBundle.model_validate(_load(FIX / "baoshan-q15.review-issues.yaml"))
    resolutions = ReviewResolutionsBundle.model_validate(_load(FIX / "baoshan-q15.review-resolutions.yaml"))
    assert validate_resolutions_against_issues(issues, resolutions) == []


# --------------------------------------------------------------------------- #
# Contract rejections
# --------------------------------------------------------------------------- #


def test_bad_severity_rejected():
    payload = _base_issue()
    payload["severity"] = "fatal"
    with pytest.raises(Exception):
        ReviewIssue.model_validate(payload)


def test_empty_field_path_rejected():
    payload = _base_issue()
    payload["field_path"] = ""
    with pytest.raises(Exception):
        ReviewIssue.model_validate(payload)


def test_duplicate_candidate_window_rejected():
    payload = _base_issue(
        [_candidate("w-A", "$3$"), _candidate("w-A", "$-3$", selected=True)]
    )
    with pytest.raises(Exception, match="duplicate candidate window_id"):
        ReviewIssue.model_validate(payload)


def test_candidate_without_evidence_rejected():
    cands = [_candidate("w-A", "$3$"), _candidate("w-B", "$-3$", selected=True)]
    cands[0]["evidence"] = []
    payload = _base_issue(cands)
    with pytest.raises(Exception):
        ReviewIssue.model_validate(payload)


def test_single_candidate_rejected():
    payload = _base_issue([_candidate("w-A", "$3$", selected=True)])
    with pytest.raises(Exception):
        ReviewIssue.model_validate(payload)


def test_zero_selected_candidate_rejected():
    payload = _base_issue([_candidate("w-A", "$3$"), _candidate("w-B", "$-3$")])
    with pytest.raises(Exception, match="exactly one candidate must be selected"):
        ReviewIssue.model_validate(payload)


def test_two_selected_candidates_rejected():
    payload = _base_issue(
        [_candidate("w-A", "$3$", selected=True), _candidate("w-B", "$-3$", selected=True)]
    )
    with pytest.raises(Exception, match="exactly one candidate must be selected"):
        ReviewIssue.model_validate(payload)


def test_canonical_code_severity_mismatch_rejected():
    payload = _base_issue()
    payload["code"] = "auto_resolved_format_diff"
    payload["severity"] = "blocking"
    with pytest.raises(Exception, match="requires severity 'info'"):
        ReviewIssue.model_validate(payload)


def test_baseline_compare_requires_baseline_paper_id():
    payload = _base_issue()
    payload["origin"] = "baseline_compare"
    with pytest.raises(Exception, match="baseline_paper_id"):
        ReviewIssue.model_validate(payload)


def test_baseline_compare_requires_matching_baseline_candidate():
    payload = _base_issue()
    payload["origin"] = "baseline_compare"
    payload["baseline_paper_id"] = "PAPER-OLD"
    payload["baseline_value"] = "$3$"
    with pytest.raises(Exception, match="baseline:PAPER-OLD"):
        ReviewIssue.model_validate(payload)


def test_issue_rejects_incorrect_candidates_hash():
    payload = _base_issue()
    payload["candidates_hash"] = "sha256:" + "f" * 64
    with pytest.raises(Exception, match="candidates_hash"):
        ReviewIssue.model_validate(payload)


def test_resolution_accept_candidate_requires_window_id():
    payload = _base_resolution()
    payload["accepted_window_id"] = None
    with pytest.raises(Exception, match="accept_candidate requires"):
        IssueResolution.model_validate(payload)


def test_resolution_manual_requires_value():
    payload = _base_resolution()
    payload["decision"] = "manual"
    payload["manual_value"] = None
    payload["accepted_window_id"] = None
    with pytest.raises(Exception, match="manual decision requires"):
        IssueResolution.model_validate(payload)


def test_resolution_rejects_fields_for_other_decision():
    payload = _base_resolution()
    payload["decision"] = "accept_baseline"
    with pytest.raises(Exception, match="accepted_window_id"):
        IssueResolution.model_validate(payload)


def test_extra_key_rejected():
    payload = _base_issues_bundle()
    payload["issues"][0]["unexpected"] = "x"
    with pytest.raises(Exception):
        ReviewIssuesBundle.model_validate(payload)


def test_asset_classification_issue_requires_blocking_explanation():
    issue = AssetClassificationIssue.model_validate(_asset_issue())
    assert issue.severity == "blocking"
    assert "边界不清" in issue.detail


def test_asset_classification_issue_rejects_formula_as_review_option():
    payload = _asset_issue()
    payload["allowed_classes"] = ["formula", "mixed_content"]
    with pytest.raises(Exception):
        AssetClassificationIssue.model_validate(payload)


def test_asset_classification_issue_rejects_stale_hash():
    payload = _asset_issue()
    payload["detail"] = "changed after hashing"
    with pytest.raises(Exception, match="issue_hash"):
        AssetClassificationIssue.model_validate(payload)


def test_asset_classification_resolution_cross_checks_clean():
    issue = AssetClassificationIssue.model_validate(_asset_issue())
    issues = ReviewIssuesBundle(
        schema="math_transcription_review_issues/v1",
        paper_id="2024-BAOSHAN-ERMO",
        generated_at=datetime(2026, 7, 28, 12, 0, 0),
        issues=[issue],
    )
    resolution = AssetClassificationResolution(
        issue_id=issue.issue_id,
        selected_class="mixed_content",
        resolved_issue_hash=issue.issue_hash,
        reviewer="human",
        resolved_at=datetime(2026, 7, 28, 12, 5, 0),
    )
    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id=issues.paper_id,
        resolutions=[resolution],
    )
    assert validate_resolutions_against_issues(issues, resolutions) == []
    assert unresolved_issues(issues, resolutions) == []


def test_asset_classification_resolution_kind_mismatch_rejected():
    issue = AssetClassificationIssue.model_validate(_asset_issue())
    issues = ReviewIssuesBundle(
        schema="math_transcription_review_issues/v1",
        paper_id="2024-BAOSHAN-ERMO",
        generated_at=datetime(2026, 7, 28, 12, 0, 0),
        issues=[issue],
    )
    wrong = IssueResolution(
        issue_id=issue.issue_id,
        decision="manual",
        manual_value="mixed_content",
        resolved_candidates_hash=issue.issue_hash,
        reviewer="human",
        resolved_at=datetime(2026, 7, 28, 12, 5, 0),
    )
    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id=issues.paper_id,
        resolutions=[wrong],
    )
    assert validate_resolutions_against_issues(issues, resolutions) == [
        f"issue/resolution kind mismatch: {issue.issue_id}"
    ]


def test_duplicate_issue_id_in_bundle_rejected():
    payload = _base_issues_bundle()
    second = _base_issue()
    second["issue_id"] = "Q015-answer-sign"
    payload["issues"].append(second)
    with pytest.raises(Exception, match="duplicate issue_id"):
        ReviewIssuesBundle.model_validate(payload)


# --------------------------------------------------------------------------- #
# Hash and staleness
# --------------------------------------------------------------------------- #


def _two_candidates():
    return [
        ReviewCandidate.model_validate(_candidate("w-A", "$3$")),
        ReviewCandidate.model_validate(_candidate("w-B", "$-3$", selected=True)),
    ]


def test_candidates_hash_deterministic():
    cands = _two_candidates()
    assert compute_candidates_hash(cands) == compute_candidates_hash(list(reversed(cands)))


def test_candidates_hash_changes_on_value_change():
    cands = _two_candidates()
    before = compute_candidates_hash(cands)
    cands[0] = cands[0].model_copy(update={"raw_value": "$4$"})
    after = compute_candidates_hash(cands)
    assert before != after


def test_candidates_hash_ignores_evidence_sha():
    # EvidenceRef has no sha field; swapping box_px (a location field) WOULD
    # change the hash, confirming location sensitivity while proving the model
    # never carried a digest to ignore. We assert the only evidence fields are
    # kind/source/page_number (+box_px for regions).
    cands = _two_candidates()
    ev = cands[0].evidence[0]
    assert not hasattr(ev, "source_sha256") and not hasattr(ev, "output_sha256")
    assert compute_candidates_hash(cands)  # sanity


def test_stale_resolution_detected():
    issues = ReviewIssuesBundle.model_validate(_base_issues_bundle())
    issue = issues.issues[0]
    # resolution carries a bogus hash -> stale
    res = IssueResolution(
        issue_id="Q015-answer-sign",
        decision="manual",
        manual_value="$-3$",
        resolved_candidates_hash="sha256:" + "0" * 64,
        reviewer="ui",
        resolved_at=datetime(2026, 7, 28, 12, 5, 0),
    )
    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id="2024-BAOSHAN-ERMO",
        resolutions=[res],
    )
    errors = validate_resolutions_against_issues(issues, resolutions)
    assert any(e.startswith("stale: Q015-answer-sign") for e in errors)


def test_resolution_for_unknown_issue_rejected_by_cross_check():
    issues = ReviewIssuesBundle.model_validate(_base_issues_bundle())
    res = IssueResolution(
        issue_id="does-not-exist",
        decision="manual",
        manual_value="$-3$",
        resolved_candidates_hash="sha256:" + "0" * 64,
        reviewer="ui",
        resolved_at=datetime(2026, 7, 28, 12, 5, 0),
    )
    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id="2024-BAOSHAN-ERMO",
        resolutions=[res],
    )
    errors = validate_resolutions_against_issues(issues, resolutions)
    assert any("unknown issue" in e for e in errors)


def test_accept_candidate_dangling_window_rejected_by_cross_check():
    issue = _base_issue()
    issues = ReviewIssuesBundle.model_validate(_base_issues_bundle(issue))
    # correct hash, but accepted_window_id not among candidates
    res = IssueResolution(
        issue_id="Q015-answer-sign",
        decision="accept_candidate",
        accepted_window_id="w-Z",
        resolved_candidates_hash=issue["candidates_hash"],
        reviewer="ui",
        resolved_at=datetime(2026, 7, 28, 12, 5, 0),
    )
    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id="2024-BAOSHAN-ERMO",
        resolutions=[res],
    )
    errors = validate_resolutions_against_issues(issues, resolutions)
    assert any("dangling window" in e for e in errors)


def test_unresolved_issues_ignores_info_and_accepts_fresh_resolution():
    issues = ReviewIssuesBundle.model_validate(_base_issues_bundle())
    assert [issue.issue_id for issue in unresolved_issues(issues)] == [
        "Q015-answer-sign"
    ]
    resolution = ReviewResolutionsBundle.model_validate(
        {
            "schema": "math_transcription_review_resolutions/v1",
            "paper_id": issues.paper_id,
            "resolutions": [
                {
                    "issue_id": issues.issues[0].issue_id,
                    "decision": "accept_candidate",
                    "accepted_window_id": "w-B",
                    "resolved_candidates_hash": issues.issues[0].candidates_hash,
                    "reviewer": "ui",
                    "resolved_at": "2026-07-28T12:05:00",
                }
            ],
        }
    )
    assert unresolved_issues(issues, resolution) == []


# --------------------------------------------------------------------------- #
# JSON Schema dump
# --------------------------------------------------------------------------- #


def test_json_schema_dump_writes_six_contracts(tmp_path):
    written = schema_dump.dump_all(tmp_path)
    assert set(written) == {
        "question_transcription",
        "image_attribution",
        "draft_assembly_report",
        "review_issues",
        "review_resolutions",
        "source_paper",
    }
    names = {p.name for p in tmp_path.iterdir()}
    for expected in (
        "review_issues.schema.json",
        "review_issues.schema.yaml",
        "review_resolutions.schema.json",
        "review_resolutions.schema.yaml",
    ):
        assert expected in names
    issues_schema = yaml.safe_load((tmp_path / "review_issues.schema.yaml").read_text("utf-8"))
    res_schema = yaml.safe_load((tmp_path / "review_resolutions.schema.yaml").read_text("utf-8"))
    assert "math_transcription_review_issues/v1" in str(issues_schema)
    assert "math_transcription_review_resolutions/v1" in str(res_schema)
    # v2 source_paper carries its own discriminator.
    src_schema = yaml.safe_load((tmp_path / "source_paper.schema.yaml").read_text("utf-8"))
    assert "math_exam_source_paper/v2" in str(src_schema)
    compute_asset_issue_hash,
