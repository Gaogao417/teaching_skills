from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from PIL import Image
import yaml

from scripts.question_transcription.build_review_staging import (
    build_review_staging,
)
from scripts.question_transcription.apply_review_resolutions import apply_resolutions
from scripts.question_transcription.compare_existing_staging import compare_existing
from scripts.question_transcription.contracts import (
    ImageAttributionBundle,
    RegionEvidence,
)
from scripts.question_transcription.review_issue_contracts import (
    IssueResolution,
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
)
from scripts.question_transcription.review_issue_engine import (
    FieldCandidate,
    build_issue,
)


ROOT = Path(__file__).resolve().parents[2]


def test_review_staging_is_materialized_pending_and_stamped(tmp_path: Path) -> None:
    source = ROOT / "documents/高一/01-yziAF5kAbRtk3MMO/002.png"
    width, height = Image.open(source).size
    digest = f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"
    relative_archive = "documents/高一/01-yziAF5kAbRtk3MMO"
    evidence = RegionEvidence(
        kind="region",
        source=f"{relative_archive}/002.png",
        page_number=1,
        box_px=[0, 0, min(100, width), min(100, height)],
    )
    issue = build_issue(
        question_ref="1",
        question_number=1,
        field_path="content.answer",
        candidates=[
            FieldCandidate("p001", "$1$", "medium", (evidence,)),
            FieldCandidate("p001-overlap", "$-1$", "high", (evidence,)),
        ],
        selected_value="$-1$",
    )
    assert issue is not None
    issues = ReviewIssuesBundle(
        schema="math_transcription_review_issues/v1",
        paper_id="REVIEW-PDF",
        generated_at=datetime.now(timezone.utc),
        issues=[issue],
    )
    observation = {
        "schema": "math_pdf_merged_observation/v1",
        "paper": {
            "id": "REVIEW-PDF",
            "title": "审核测试卷",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": relative_archive,
            "question_bank": "../../question-bank.yaml",
        },
        "provider": {
            "kind": "vision_api",
            "name": "fake-vl",
            "version": "v1",
        },
        "prompt_version": "v1",
        "pages": [
            {
                "page_number": 1,
                "source": "002.png",
                "width_px": width,
                "height_px": height,
                "sha256": digest,
            }
        ],
        "questions": [
            {
                "question_ref": "1",
                "question_number": 1,
                "section_ref": "fillin",
                "section_title": "填空题",
                "question_type": "fillin",
                "points": 4,
                "content": {
                    "stem_latex": "若$x=1$，则$x=$____。",
                    "choices": [],
                    "answer": "$-1$",
                    "clue": "直接读取。",
                    "solution_steps": ["原答案为$-1$。"],
                    "solution_notes": [],
                },
                "question_evidence": [
                    {"page_number": 1, "box_px": [0, 0, min(100, width), min(50, height)]}
                ],
                "solution_evidence": [
                    {"page_number": 1, "box_px": [0, min(50, height - 1), min(100, width), min(100, height)]}
                ],
                "solution_start_anchor": "1.",
                "solution_end_anchor": "<END_OF_SOURCE>",
                "figures": [],
                "confidence": {"stem": "high", "formula": "high"},
            }
        ],
        "source_windows": ["p001", "p001-overlap"],
        "conflicts": ["content.answer"],
    }
    images = ImageAttributionBundle(
        schema="math_image_attribution/v1",
        paper_id="REVIEW-PDF",
        assets=[],
        attributions=[],
    )

    staging = build_review_staging(
        observation,
        images,
        issues,
        tmp_path / "review-staging",
        repo_root=ROOT,
    )
    sidecar = yaml.safe_load(
        (staging / "review-issues.yaml").read_text(encoding="utf-8")
    )
    source_yaml = yaml.safe_load(
        (staging / "items/Q001/source.yaml").read_text(encoding="utf-8")
    )
    assert sidecar["issues"][0]["item_id"] == "Q001"
    assert source_yaml["transcription"]["question_status"] == "pending"
    assert source_yaml["transcription"]["official_solution_status"] == "pending"
    assert source_yaml["transcription"]["human_review"] == "pending"
    assert (staging / "paper.yaml").is_file()
    assert (staging / "paper-map.yaml").is_file()
    assert (staging / "items/Q001/student.resolved.assignment.yaml").is_file()
    audit_script = (
        ROOT
        / ".codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py"
    )
    structural = subprocess.run(
        [
            sys.executable,
            str(audit_script),
            str(staging),
            "--repo-root",
            str(ROOT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert structural.returncode == 0, structural.stdout + structural.stderr
    approved = subprocess.run(
        [
            sys.executable,
            str(audit_script),
            str(staging),
            "--repo-root",
            str(ROOT),
            "--require-approved-review",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert approved.returncode == 1
    assert "review-issues.yaml" in approved.stdout + approved.stderr


def test_baseline_comparison_is_non_authoritative_until_explicit_resolution(
    tmp_path: Path,
) -> None:
    source = ROOT / "documents/高一/01-yziAF5kAbRtk3MMO/002.png"
    width, height = Image.open(source).size
    digest = f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"
    archive = "documents/高一/01-yziAF5kAbRtk3MMO"
    observation_payload = {
        "schema": "math_pdf_merged_observation/v1",
        "paper": {
            "id": "BASELINE-PAPER",
            "title": "基线测试卷",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": archive,
            "question_bank": "../../question-bank.yaml",
        },
        "provider": {"kind": "vision_api", "name": "fake-vl", "version": "v1"},
        "prompt_version": "v1",
        "pages": [{
            "page_number": 1,
            "source": "002.png",
            "width_px": width,
            "height_px": height,
            "sha256": digest,
        }],
        "questions": [{
            "question_ref": "1",
            "question_number": 1,
            "section_ref": "fillin",
            "section_title": "填空题",
            "question_type": "fillin",
            "points": 4,
            "content": {
                "stem_latex": "求$x$。",
                "choices": [],
                "answer": "$-1$",
                "clue": "读取。",
                "solution_steps": ["得$x=-1$。"],
                "solution_notes": [],
            },
            "question_evidence": [{"page_number": 1, "box_px": [0, 0, 100, 50]}],
            "solution_evidence": [{"page_number": 1, "box_px": [0, 50, 100, 100]}],
            "solution_start_anchor": "1.",
            "solution_end_anchor": "<END_OF_SOURCE>",
            "figures": [],
            "confidence": {"stem": "high", "formula": "high"},
        }],
        "source_windows": ["p001"],
        "conflicts": [],
    }
    from scripts.question_transcription.pdf_observation_contracts import (
        MergedPdfObservation,
    )

    observation = MergedPdfObservation.model_validate(observation_payload)
    baseline = tmp_path / "baseline"
    (baseline / "items/Q001").mkdir(parents=True)
    (baseline / "paper.yaml").write_text(
        yaml.safe_dump({
            "schema": "math_exam_paper/v1",
            "paper": {"id": "BASELINE-PAPER", "title": "旧卷", "grade": "九年级", "subject": "数学"},
            "question_bank": "../../question-bank.yaml",
            "sections": [{"id": "fillin", "title": "填空题", "item_ids": ["Q001"]}],
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (baseline / "items/Q001/source.yaml").write_text(
        yaml.safe_dump({
            "schema": "math_exam_item_source/v1",
            "item_id": "Q001",
            "question_number": 1,
            "crops": {
                "question_evidence": [{
                    "source": f"{archive}/002.png",
                    "page_number": 1,
                    "box_px": [0, 0, 100, 50],
                }],
                "official_solution": [{
                    "source": f"{archive}/002.png",
                    "page_number": 1,
                    "box_px": [0, 50, 100, 100],
                }],
            },
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (baseline / "items/Q001/teacher.resolved.assignment.yaml").write_text(
        yaml.safe_dump({
            "sections": [{
                "type": "practice",
                "blocks": [{
                    "stem_latex": "求$x$。",
                    "choices": [],
                    "answer": "$1$",
                    "solution_steps": ["得$x=-1$。"],
                }],
            }],
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    issues = compare_existing(observation, baseline)
    assert issues is not None
    answer_issue = next(
        issue for issue in issues.issues if issue.field_path == "content.answer"
    )
    selected = next(candidate for candidate in answer_issue.candidates if candidate.selected)
    assert selected.raw_value == "$-1$"
    assert answer_issue.baseline_value == "$1$"

    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id="BASELINE-PAPER",
        resolutions=[
            IssueResolution(
                issue_id=answer_issue.issue_id,
                decision="accept_baseline",
                resolved_candidates_hash=answer_issue.candidates_hash,
                reviewer="test",
                resolved_at=datetime.now(timezone.utc),
            )
        ],
    )
    # Only the answer differs, so one explicit resolution makes the observation
    # conflict-free and applies the old value by human choice, not by comparator trust.
    resolved = apply_resolutions(observation, issues, resolutions)
    assert resolved.questions[0].content.answer == "$1$"
    assert resolved.conflicts == []
