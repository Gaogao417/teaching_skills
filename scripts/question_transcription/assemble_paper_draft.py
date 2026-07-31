#!/usr/bin/env python3
"""Deterministic DraftAssembler.

Joins a :class:`QuestionTranscriptionBundle` and an
:class:`ImageAttributionBundle` on ``question_ref`` and renders a byte-stable
``paper.draft.yaml`` (``math_exam_staging_draft/v1``) plus an
:class:`AssemblyReport`. The assembler does no OCR, no math, and no image
recognition; it only validates, joins, orders, and renders.

See ``docs/question-transcription-architecture.md`` §7.

Design rules (§7.1-7.5):
- ``sections/questions`` order is the final paper order; ``Q001``/``Q002`` are
  assigned in that order, never from a provider file name.
- Transcription text (stem, choices, answer, clue, steps, notes) is copied
  verbatim -- no summarizing, no re-splitting of ``solution_steps``.
- Evidence mapping depends only on the ``EvidenceRef`` variant:
    page    -> question_word_evidence / official_solution.word_evidence
    region  -> question_evidence       / official_solution.crops
- Image mapping:
    role=prompt   -> draft prompt[]
    role=solution -> draft official_solution.crops[]  (per §7.3 / §13.4)
  Only ``state == "accepted"`` attributions are consumed; each exactly once.
  crop: full    -> box_px = [0, 0, width, height]  (asset dims)
  crop: region  -> box_px / whiteout_px copied verbatim.
- Hard errors (don't write the draft): paper_id mismatch, unknown question_ref,
  duplicate order within (question, role), unconsumed accepted attribution,
  out-of-bounds region crop, missing required text fields.
- Warnings (don't block): ``needs_review`` attributions, ``needs_review``
  assets.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    AssemblyError,
    AssemblyReport,
    AssemblyWarning,
    Attribution,
    AttributionAsset,
    AttributionState,
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
    TranscriptionQuestion,
)

SCHEMA = "math_exam_staging_draft/v1"


# --------------------------------------------------------------------------- #
# YAML I/O (matches expand_staging_draft.py's writer for byte stability)
# --------------------------------------------------------------------------- #


def _dump_yaml(value: dict[str, Any]) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return data


# --------------------------------------------------------------------------- #
# Path safety
# --------------------------------------------------------------------------- #


def _check_inside_archive(source: str, archive: str, label: str, errors: list[AssemblyError]) -> None:
    """Forbid ``..`` escape and require the path to live under the source archive.

    Two source shapes are accepted:

    - **Archive-relative** (PDF flow): a repo-relative path that equals or starts
      with the source archive name (e.g. ``2023-X.pdf`` slices).
    - **Absolute rendered page path** (DOCX/whole-paper flow): the source-extraction
      branch back-fills evidence with the absolute path of a rendered page image.
      These are already ``resolve()``-d (no ``..``), and the downstream materialize
      step enforces they stay under the repo root via its own ``inside()`` check, so
      we accept them without the archive-prefix constraint.
    """
    if ".." in Path(source).parts:
        errors.append(
            AssemblyError(
                code="path_escape",
                detail=f"{label}: source path must not contain '..': {source}",
            )
        )
        return
    if Path(source).is_absolute():
        # Rendered page-image path from the whole-paper evidence back-fill; safety
        # is enforced by materialize_staging's inside(repo_root) check downstream.
        return
    # Relative path: must live under the source archive (PDF-slice convention).
    norm_archive = archive.rstrip("/") + "/"
    if not (source == archive or source.startswith(norm_archive)):
        errors.append(
            AssemblyError(
                code="path_outside_archive",
                detail=f"{label}: source path must be inside {archive}: {source}",
            )
        )


# --------------------------------------------------------------------------- #
# Evidence -> draft fields
# --------------------------------------------------------------------------- #


def _question_evidence_field(question: TranscriptionQuestion) -> tuple[list[dict], list[dict]]:
    """Return (question_evidence crops, question_word_evidence spans) for one question."""
    crops: list[dict] = []
    spans: list[dict] = []
    for ref in question.evidence.question:
        if ref.kind == "region":
            crops.append(
                {"source": ref.source, "box_px": list(ref.box_px)}
            )
        else:  # page
            spans.append({"page_image": ref.source, "page_number": ref.page_number})
    return crops, spans


def _solution_evidence_field(question: TranscriptionQuestion) -> tuple[list[dict], list[dict]]:
    """Return (official_solution.crops, official_solution.word_evidence) for one question."""
    crops: list[dict] = []
    spans: list[dict] = []
    for ref in question.evidence.solution:
        if ref.kind == "region":
            crops.append(
                {"source": ref.source, "box_px": list(ref.box_px)}
            )
        else:  # page
            spans.append({"page_image": ref.source, "page_number": ref.page_number})
    return crops, spans


# --------------------------------------------------------------------------- #
# Image attribution -> draft fields
# --------------------------------------------------------------------------- #


def _resolve_crop(
    attr: Attribution, asset: AttributionAsset, errors: list[AssemblyError]
) -> dict[str, Any] | None:
    """Expand a CropSpec against the asset into a draft crop dict."""
    crop = attr.crop
    if crop.kind == "full":
        return {"source": asset.source, "box_px": [0, 0, asset.width_px, asset.height_px]}
    # region
    left, top, right, bottom = crop.box_px
    if left < 0 or top < 0 or right > asset.width_px or bottom > asset.height_px:
        errors.append(
            AssemblyError(
                code="crop_out_of_bounds",
                detail=(
                    f"attribution {attr.attribution_id}: region box_px "
                    f"{list(crop.box_px)} exceeds asset {asset.asset_id} dims "
                    f"{asset.width_px}x{asset.height_px}"
                ),
                attribution_id=attr.attribution_id,
                asset_id=asset.asset_id,
            )
        )
        return None
    out: dict[str, Any] = {"source": asset.source, "box_px": list(crop.box_px)}
    if crop.whiteout_px:
        out["whiteout_px"] = [list(w) for w in crop.whiteout_px]
    return out


# --------------------------------------------------------------------------- #
# Core assembly
# --------------------------------------------------------------------------- #


def assemble(
    transcription: QuestionTranscriptionBundle,
    images: ImageAttributionBundle,
) -> tuple[dict[str, Any] | None, AssemblyReport]:
    """Join the two bundles into a draft payload and a report.

    Returns ``(draft, report)``. ``draft`` is ``None`` if ``report.errors`` is
    non-empty (the assembler refuses to emit a partial draft).
    """
    errors: list[AssemblyError] = []
    warnings: list[AssemblyWarning] = []

    # Image attribution is an independent, optional branch (architecture §25/§414):
    # a paper with no figures, or one whose attribution failed, must still assemble
    # a text-only draft. Treat a missing bundle as an empty one keyed to this paper
    # rather than crashing on ``images.paper_id``.
    if images is None:
        images = ImageAttributionBundle(
            schema="math_image_attribution/v1",
            paper_id=transcription.paper.id,
            assets=[],
            attributions=[],
        )

    if transcription.paper.id != images.paper_id:
        errors.append(
            AssemblyError(
                code="paper_id_mismatch",
                detail=(
                    f"transcription paper.id {transcription.paper.id!r} != "
                    f"image paper_id {images.paper_id!r}"
                ),
            )
        )

    # Index questions by ref for join + unknown-ref detection.
    questions_by_ref: dict[str, TranscriptionQuestion] = {}
    for section in transcription.sections:
        for q in section.questions:
            questions_by_ref[q.question_ref] = q

    assets_by_id = {a.asset_id: a for a in images.assets}

    # Group accepted attributions by (question_ref, role) and validate ordering.
    grouped: dict[tuple[str, str], list[Attribution]] = defaultdict(list)
    accepted_ids: set[str] = set()
    for attr in images.attributions:
        if attr.state == "accepted":
            grouped[(attr.question_ref, attr.role)].append(attr)
            accepted_ids.add(attr.attribution_id)
        elif attr.state == "needs_review":
            warnings.append(
                AssemblyWarning(
                    code="image_needs_review",
                    attribution_id=attr.attribution_id,
                    asset_id=attr.asset_id,
                    detail=f"attribution {attr.attribution_id} not accepted; omitted from draft",
                )
            )
        # rejected: neither consumed nor warned (explicitly discarded)

    # Unknown question_ref among accepted attributions.
    for (qref, _role), attrs in grouped.items():
        if qref not in questions_by_ref:
            for attr in attrs:
                errors.append(
                    AssemblyError(
                        code="unknown_question_ref",
                        detail=(
                            f"attribution {attr.attribution_id}: question_ref {qref!r} "
                            "not present in transcription bundle"
                        ),
                        attribution_id=attr.attribution_id,
                        question_ref=qref,
                    )
                )

    # Duplicate order within (question_ref, role) -> hard error.
    for (qref, role), attrs in grouped.items():
        counter = Counter(a.order for a in attrs)
        for order, count in counter.items():
            if count > 1:
                dup_ids = [a.attribution_id for a in attrs if a.order == order]
                errors.append(
                    AssemblyError(
                        code="duplicate_order",
                        detail=(
                            f"question {qref} role {role}: order {order} used by "
                            f"{count} attributions {dup_ids}"
                        ),
                        question_ref=qref,
                    )
                )

    # Build per-question image lists. Track consumed attribution ids.
    consumed: set[str] = set()
    prompt_by_ref: dict[str, list[tuple[Attribution, AttributionAsset]]] = defaultdict(list)
    solution_by_ref: dict[str, list[tuple[Attribution, AttributionAsset]]] = defaultdict(list)
    if not errors:
        for (qref, role), attrs in grouped.items():
            if qref not in questions_by_ref:
                continue  # already an error
            bucket = prompt_by_ref if role == "prompt" else solution_by_ref
            for attr in sorted(attrs, key=lambda a: (a.order, a.attribution_id)):
                asset = assets_by_id[attr.asset_id]
                bucket[qref].append((attr, asset))
                consumed.add(attr.attribution_id)

    # Unconsumed accepted attribution -> hard error (§3.1: never silently drop).
    for attr_id in sorted(accepted_ids - consumed):
        errors.append(
            AssemblyError(
                code="unconsumed_accepted_attribution",
                detail=(
                    f"attribution {attr_id} is accepted but was not consumed "
                    "(likely a duplicate-order or unknown-ref failure)"
                ),
                attribution_id=attr_id,
            )
        )

    # Path safety for every referenced source.
    archive = transcription.paper.source_archive
    for section in transcription.sections:
        for q in section.questions:
            for ref in (*q.evidence.question, *q.evidence.solution):
                _check_inside_archive(ref.source, archive, f"question {q.question_ref} evidence", errors)
    for attr in images.attributions:
        if attr.state != "accepted":
            continue
        asset = assets_by_id[attr.asset_id]
        _check_inside_archive(asset.source, archive, f"attribution {attr.attribution_id} asset", errors)

    if errors:
        report = _build_report(
            transcription, images, consumed, draft_path=None, errors=errors, warnings=warnings
        )
        return None, report

    # ---- Build the draft payload (deterministic order) ---------------------
    draft_sections: list[dict[str, Any]] = []
    question_index = 0
    for section in transcription.sections:
        items: list[dict[str, Any]] = []
        for q in section.questions:
            question_index += 1
            item_id = f"Q{question_index:03d}"
            item = _build_item(
                item_id=item_id,
                question=q,
                archive=archive,
                prompt_pairs=prompt_by_ref.get(q.question_ref, []),
                solution_pairs=solution_by_ref.get(q.question_ref, []),
                errors=errors,
            )
            items.append(item)
        draft_sections.append({"id": section.section_ref, "title": section.title, "items": items})

    paper = {
        "id": transcription.paper.id,
        "title": transcription.paper.title,
        "grade": transcription.paper.grade,
        "subject": transcription.paper.subject,
        "source_archive": transcription.paper.source_archive,
    }
    if transcription.paper.duration:
        paper["duration"] = transcription.paper.duration

    draft = {
        "schema": SCHEMA,
        "paper": paper,
        "question_bank": transcription.paper.question_bank,
        "sections": draft_sections,
    }

    if errors:
        report = _build_report(
            transcription, images, consumed, draft_path=None, errors=errors, warnings=warnings
        )
        return None, report

    report = _build_report(
        transcription, images, consumed, draft_path=None, errors=[], warnings=warnings
    )
    return draft, report


def _build_item(
    *,
    item_id: str,
    question: TranscriptionQuestion,
    archive: str,
    prompt_pairs: list[tuple[Attribution, AttributionAsset]],
    solution_pairs: list[tuple[Attribution, AttributionAsset]],
    errors: list[AssemblyError],
) -> dict[str, Any]:
    """Assemble one draft item. Appends to ``errors`` on per-item failure."""
    q_crops, q_spans = _question_evidence_field(question)
    s_crops, s_spans = _solution_evidence_field(question)

    item: dict[str, Any] = {
        "item_id": item_id,
        "question_number": question.question_number,
        "question_type": question.question_type,
        "points": question.points,
    }
    if q_crops:
        item["question_evidence"] = q_crops
    if q_spans:
        item["question_word_evidence"] = q_spans

    # prompt images (role=prompt)
    item["prompt"] = []
    for attr, asset in prompt_pairs:
        crop = _resolve_crop(attr, asset, errors)
        if crop is not None:
            item["prompt"].append(crop)

    # official_solution: anchors + crops(region evidence) + word_evidence(page evidence)
    official: dict[str, Any] = {
        "start_anchor": question.evidence.solution_start_anchor,
        "end_anchor": question.evidence.solution_end_anchor,
    }
    # solution images (role=solution) live in official_solution.crops per §7.3
    sol_image_crops: list[dict[str, Any]] = []
    for attr, asset in solution_pairs:
        crop = _resolve_crop(attr, asset, errors)
        if crop is not None:
            sol_image_crops.append(crop)
    # Merge: solution image crops + region-evidence solution crops. Image crops
    # first (they are the attributed figures), then the region-evidence crops
    # (the official-answer page regions). Both are legitimate crops on the same
    # list; the expander treats them identically.
    merged_crops = sol_image_crops + s_crops
    if merged_crops:
        official["crops"] = merged_crops
    if s_spans:
        official["word_evidence"] = s_spans
    item["official_solution"] = official

    # block: copy transcription content verbatim
    block: dict[str, Any] = {"stem_latex": question.content.stem_latex}
    if question.content.choices:
        block["choices"] = list(question.content.choices)
    block["answer"] = question.content.answer
    block["clue"] = question.content.clue
    if question.content.solution_steps:
        block["solution_steps"] = list(question.content.solution_steps)
    if question.content.solution_notes:
        block["solution_notes"] = list(question.content.solution_notes)
    item["block"] = block
    return item


def _build_report(
    transcription: QuestionTranscriptionBundle,
    images: ImageAttributionBundle,
    consumed: set[str],
    *,
    draft_path: str | None,
    errors: list[AssemblyError],
    warnings: list[AssemblyWarning],
) -> AssemblyReport:
    accepted = [a for a in images.attributions if a.state == "accepted"]
    ignored = [a for a in images.assets if a.disposition == "ignored"]
    unresolved = [a for a in images.assets if a.disposition == "needs_review"]
    question_count = sum(len(s.questions) for s in transcription.sections)
    return AssemblyReport(
        schema="math_draft_assembly_report/v1",
        paper_id=transcription.paper.id,
        draft_path=draft_path,
        question_count=question_count,
        accepted_attributions=len(accepted),
        consumed_attributions=len(consumed),
        ignored_assets=len(ignored),
        unresolved_assets=len(unresolved),
        errors=errors,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic paper-draft assembler.")
    parser.add_argument("--transcription", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="draft output path (skipped under --check)")
    parser.add_argument("--report", type=Path, help="optional assembly-report output path")
    parser.add_argument("--check", action="store_true", help="validate only; do not write draft")
    args = parser.parse_args()

    transcription = QuestionTranscriptionBundle.model_validate(
        _load_yaml(args.transcription)
    )
    images = ImageAttributionBundle.model_validate(_load_yaml(args.images))

    draft, report = assemble(transcription, images)

    report_text = _dump_yaml(
        report.model_dump(by_alias=True, exclude_none=True)
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report_text, encoding="utf-8")

    if report.errors:
        print("ASSEMBLY FAILED:")
        for err in report.errors:
            print(f"  - [{err.code}] {err.detail}")
        if args.report:
            print(f"(report written to {args.report})")
        return 1

    if args.check:
        print(f"ASSEMBLY OK (check only): questions={report.question_count} "
              f"consumed={report.consumed_attributions}/{report.accepted_attributions} "
              f"warnings={len(report.warnings)}")
        if args.report:
            print(f"(report written to {args.report})")
        return 0

    if not args.output:
        print("ASSEMBLY OK but --output not given and --check not set; nothing written.")
        if args.report:
            print(f"(report written to {args.report})")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_dump_yaml(draft), encoding="utf-8")
    report = report.model_copy(update={"draft_path": str(args.output)})
    if args.report:
        args.report.write_text(
            _dump_yaml(report.model_dump(by_alias=True, exclude_none=True)),
            encoding="utf-8",
        )
    print(f"ASSEMBLED: {args.output} | questions={report.question_count} "
          f"consumed={report.consumed_attributions}/{report.accepted_attributions} "
          f"warnings={len(report.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
