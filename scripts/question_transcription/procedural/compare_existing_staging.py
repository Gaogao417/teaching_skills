#!/usr/bin/env python3
"""Compare a frozen observation with an existing staging without trusting it.

The comparator runs *after* observation/merge output has been frozen. It can
only append review issues; it never changes the provisional candidate selected
by merge.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    EvidenceRef,
    PageEvidence,
    RegionEvidence,
)
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
from scripts.question_transcription.procedural.review_issue_engine import (  # noqa: E402
    FieldCandidate,
    build_issue,
    raw_value,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def find_existing_staging(
    repo_root: Path,
    paper_id: str,
    *,
    exclude: Path | None = None,
) -> Path | None:
    matches = sorted(
        path.resolve()
        for path in (repo_root / "artifacts" / "题库").glob(
            f"*/staging/{paper_id}"
        )
        if (path / "paper.yaml").is_file()
    )
    if exclude is not None:
        matches = [path for path in matches if path != exclude.resolve()]
    if len(matches) > 1:
        raise ValueError(
            f"multiple existing staging directories for {paper_id}: "
            + ", ".join(str(path) for path in matches)
        )
    return matches[0] if matches else None


def _first_block(path: Path) -> dict[str, Any]:
    assignment = _load_yaml(path)
    for section in assignment.get("sections", []):
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks", []):
            if isinstance(block, dict):
                return block
    raise ValueError(f"{path}: no assignment block")


def _source_evidence(source: dict[str, Any], role: str) -> tuple[EvidenceRef, ...]:
    values: list[EvidenceRef] = []
    word = source.get("word_evidence") or {}
    word_role = "question" if role == "question" else "official_solution"
    for entry in word.get(word_role, []) if isinstance(word, dict) else []:
        if not isinstance(entry, dict):
            continue
        values.append(
            PageEvidence(
                kind="page",
                source=str(entry["page_image"]),
                page_number=int(entry["page_number"]),
            )
        )
    crops = source.get("crops") or {}
    crop_role = "question_evidence" if role == "question" else "official_solution"
    for entry in crops.get(crop_role, []) if isinstance(crops, dict) else []:
        if not isinstance(entry, dict):
            continue
        values.append(
            RegionEvidence(
                kind="region",
                source=str(entry["source"]),
                page_number=int(entry.get("page_number") or 1),
                box_px=list(entry["box_px"]),
            )
        )
    return tuple(values)


def _observation_parts(
    observation: DocxObservationBundle | MergedPdfObservation,
) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(observation, DocxObservationBundle):
        return observation.paper.id, [
            {
                "question_ref": question.question_ref,
                "question_number": question.question_number,
                "content": question.content.model_dump(mode="json"),
                "question_evidence": tuple(question.evidence.question),
                "solution_evidence": tuple(question.evidence.solution),
                "confidence": {
                    "stem": question.transcription_confidence.stem,
                    "formula": question.transcription_confidence.formula,
                    "solution": question.transcription_confidence.solution_steps,
                },
            }
            for question in observation.questions
        ]

    pages = {page.page_number: page for page in observation.pages}

    def evidence(entries: Any) -> tuple[EvidenceRef, ...]:
        return tuple(
            RegionEvidence(
                kind="region",
                source=(
                    page.source
                    if Path(page.source).is_absolute()
                    or page.source.startswith(
                        f"{observation.paper.source_archive.rstrip('/')}/"
                    )
                    else (
                        f"{observation.paper.source_archive.rstrip('/')}/"
                        f"{page.source.lstrip('/')}"
                    )
                ),
                page_number=entry.page_number,
                box_px=entry.box_px,
            )
            for entry in entries
            for page in [pages[entry.page_number]]
        )

    return observation.paper.id, [
        {
            "question_ref": question.question_ref,
            "question_number": question.question_number,
            "content": (
                question.content.model_dump(mode="json")
                if question.content is not None
                else {}
            ),
            "question_evidence": evidence(question.question_evidence),
            "solution_evidence": evidence(question.solution_evidence),
            "confidence": {
                "stem": question.confidence.get("stem", "medium"),
                "formula": question.confidence.get("formula", "medium"),
                "solution": question.confidence.get("formula", "medium"),
            },
        }
        for question in observation.questions
    ]


def compare_existing(
    observation: DocxObservationBundle | MergedPdfObservation,
    baseline_staging: Path,
    *,
    existing: ReviewIssuesBundle | None = None,
) -> ReviewIssuesBundle | None:
    paper_id, questions = _observation_parts(observation)
    baseline_paper = _load_yaml(baseline_staging / "paper.yaml")
    baseline_id = str((baseline_paper.get("paper") or {}).get("id") or "")
    if baseline_id != paper_id:
        raise ValueError(
            f"baseline paper id {baseline_id!r} does not match {paper_id!r}"
        )

    baseline_by_number: dict[int, tuple[str, dict[str, Any], dict[str, Any]]] = {}
    for source_path in sorted((baseline_staging / "items").glob("Q*/source.yaml")):
        source = _load_yaml(source_path)
        number = int(source.get("question_number"))
        item_dir = source_path.parent
        block = _first_block(item_dir / "teacher.resolved.assignment.yaml")
        baseline_by_number[number] = (item_dir.name, source, block)

    issues: list[ReviewIssue] = list(existing.issues if existing else [])
    known_ids = {issue.issue_id for issue in issues}
    for question in questions:
        number = int(question["question_number"])
        baseline = baseline_by_number.get(number)
        if baseline is None:
            continue
        item_id, source, block = baseline
        for field, confidence_key, evidence_role in (
            ("stem_latex", "stem", "question"),
            ("choices", "formula", "question"),
            ("answer", "solution", "solution"),
            ("solution_steps", "solution", "solution"),
        ):
            new_value = question["content"].get(field)
            old_value = block.get(field)
            if new_value is None or old_value is None:
                continue
            new_evidence = question[f"{evidence_role}_evidence"]
            old_evidence = _source_evidence(source, evidence_role)
            if not new_evidence or not old_evidence:
                continue
            field_path = f"content.{field}"
            issue_id = f"Q{number:03d}-baseline-{field.replace('_', '-')}"
            issue = build_issue(
                issue_id=issue_id,
                question_ref=str(question["question_ref"]),
                question_number=number,
                field_path=field_path,
                candidates=[
                    FieldCandidate(
                        window_id="frozen-observation",
                        value=new_value,
                        confidence=question["confidence"][confidence_key],
                        evidence=tuple(new_evidence),
                    ),
                    FieldCandidate(
                        window_id=f"baseline:{baseline_id}",
                        value=old_value,
                        confidence="medium",
                        evidence=old_evidence,
                    ),
                ],
                selected_value=new_value,
                origin="baseline_compare",
                baseline_paper_id=baseline_id,
                baseline_value=raw_value(old_value),
                code_override=(
                    "existing_staging_stem_mismatch"
                    if field == "stem_latex"
                    else None
                ),
                severity_override="blocking",
                detail=(
                    f"{item_id} differs from the frozen observation; "
                    "the baseline is comparison-only and is not automatically trusted."
                ),
            )
            if issue is not None and issue.issue_id not in known_ids:
                issues.append(issue)
                known_ids.add(issue.issue_id)

    if not issues:
        return None
    return ReviewIssuesBundle(
        schema="math_transcription_review_issues/v1",
        paper_id=paper_id,
        generated_at=(
            existing.generated_at if existing else datetime.now(timezone.utc)
        ),
        issues=issues,
    )


def _load_observation(path: Path) -> DocxObservationBundle | MergedPdfObservation:
    raw = _load_yaml(path)
    schema = raw.get("schema")
    if schema == "math_docx_observation/v1":
        return DocxObservationBundle.model_validate(raw)
    if schema == "math_pdf_merged_observation/v1":
        return MergedPdfObservation.model_validate(raw)
    raise ValueError(f"unsupported observation schema: {schema}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--baseline-staging", type=Path)
    parser.add_argument("--issues", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--no-compare-existing", action="store_true")
    args = parser.parse_args()

    observation = _load_observation(args.observation)
    paper_id = observation.paper.id
    if args.no_compare_existing:
        print("BASELINE COMPARISON SKIPPED")
        return 0
    baseline = args.baseline_staging or find_existing_staging(
        args.repo_root.resolve(),
        paper_id,
    )
    if baseline is None:
        print(f"NO EXISTING STAGING: {paper_id}")
        return 0
    existing = (
        ReviewIssuesBundle.model_validate(_load_yaml(args.issues))
        if args.issues and args.issues.is_file()
        else None
    )
    result = compare_existing(observation, baseline, existing=existing)
    if result is None:
        print(f"BASELINE MATCHED: {paper_id}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(
            result.model_dump(by_alias=True, exclude_none=True, mode="json"),
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    added = len(result.issues) - (len(existing.issues) if existing else 0)
    print(
        f"BASELINE REVIEW ISSUES: paper={paper_id} added={added} output={args.output}"
    )
    return 2 if added else 0


if __name__ == "__main__":
    raise SystemExit(main())
