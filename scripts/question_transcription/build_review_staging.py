#!/usr/bin/env python3
"""Build an isolated, non-promotable staging paper for transcription review."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.adapt_docx_transcription import (  # noqa: E402
    adapt as adapt_docx,
    adapt_for_review_staging as adapt_docx_for_review,
)
from scripts.question_transcription.adapt_pdf_transcription import (  # noqa: E402
    adapt as adapt_pdf,
    adapt_for_review_staging as adapt_pdf_for_review,
)
from scripts.question_transcription.workflow.adapters.staging.assemble_paper_draft import assemble  # noqa: E402
from scripts.question_transcription.contracts import ImageAttributionBundle  # noqa: E402
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxObservationBundle,
)
from scripts.question_transcription.pdf_observation_contracts import (  # noqa: E402
    MergedPdfObservation,
)
from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    ReviewIssue,
    ReviewIssuesBundle,
)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def _dump(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load workflow module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_review_staging(
    observation_payload: dict[str, Any],
    images: ImageAttributionBundle,
    issues: ReviewIssuesBundle,
    staging_dir: Path,
    *,
    repo_root: Path,
) -> Path:
    """Materialize provisional values in an unmistakable quarantine directory."""

    staging_dir = staging_dir.resolve()
    repo_root = repo_root.resolve()
    if staging_dir.exists() and any(staging_dir.iterdir()):
        raise ValueError(f"review staging must be new or empty: {staging_dir}")
    schema = observation_payload.get("schema")
    if schema == "math_docx_observation/v1":
        observation = DocxObservationBundle.model_validate(observation_payload)
        transcription = (
            adapt_docx_for_review(observation)
            if observation.conflicts
            else adapt_docx(observation, allow_low_confidence=True)
        )
    elif schema == "math_pdf_merged_observation/v1":
        observation = MergedPdfObservation.model_validate(observation_payload)
        transcription_payload = (
            adapt_pdf_for_review(observation)
            if observation.conflicts
            else adapt_pdf(observation)
        )
        transcription = __import__(
            "scripts.question_transcription.contracts",
            fromlist=["QuestionTranscriptionBundle"],
        ).QuestionTranscriptionBundle.model_validate(transcription_payload)
    else:
        raise ValueError(f"unsupported observation schema: {schema}")
    if transcription.paper.id != issues.paper_id or images.paper_id != issues.paper_id:
        raise ValueError("observation/images/issues paper_id mismatch")

    draft, report = assemble(transcription, images)
    if draft is None or report.errors:
        raise ValueError(
            "draft assembly failed: "
            + "; ".join(error.detail for error in report.errors)
        )
    ref_to_item: dict[str, str] = {}
    question_refs = [
        question.question_ref
        for section in transcription.sections
        for question in section.questions
    ]
    for index, question_ref in enumerate(question_refs, start=1):
        ref_to_item[question_ref] = f"Q{index:03d}"
    for section in draft["sections"]:
        for item in section["items"]:
            item["transcription"] = {
                "question_status": "pending",
                "official_solution_status": "pending",
                "prompt_status": "author_pass",
                "prompt_review_notes": [],
            }

    stamped = issues.model_copy(deep=True)
    for issue in stamped.issues:
        if isinstance(issue, ReviewIssue):
            issue.item_id = ref_to_item[issue.question_ref]

    staging_dir.mkdir(parents=True, exist_ok=True)
    draft_path = staging_dir / "paper.draft.yaml"
    _dump(draft_path, draft)
    _dump(
        staging_dir / "assembly-report.yaml",
        report.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )
    _dump(
        staging_dir / "review-issues.yaml",
        stamped.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )

    expand = _load_module(
        repo_root
        / ".codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py",
        "_review_expand_staging_draft",
    )
    materialize = _load_module(
        repo_root
        / ".codex/skills/math-pdf-question-bank-ingestion/scripts/materialize_staging.py",
        "_review_materialize_staging",
    )
    expand.expand_draft(draft_path)
    for item_id in materialize.item_ids(staging_dir, set()):
        materialize.materialize_item(staging_dir / "items" / item_id, repo_root)
    return staging_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()
    try:
        output = build_review_staging(
            _load(args.observation),
            ImageAttributionBundle.model_validate(_load(args.images)),
            ReviewIssuesBundle.model_validate(_load(args.issues)),
            args.staging_dir,
            repo_root=args.repo_root,
        )
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(f"REVIEW STAGING FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"REVIEW STAGING READY (QUARANTINED): {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
