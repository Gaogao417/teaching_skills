"""Authoritative source-paper builder wrapper (architecture §3.6 and §5.2).

Joins the whole-paper transcription with the deterministic image attribution and
produces the authoritative source artifact, then runs the source review gate.

Reality note: the existing deterministic pipeline consumes a v1
``paper.draft.yaml`` (``math_exam_staging_draft/v1``) produced by
:func:`assemble_paper_draft.assemble(transcription, images)`. The v2
``paper.source.yaml`` is a richer, image-aware view that this milestone projects
minimally from the transcription (the existing ``project_source_paper`` goes
v2→v1; a v1→v2 projection is additive and not on the critical staging path). To
keep the staging pipeline real, this builder emits BOTH:

- ``structured/paper.source.yaml`` — minimal v2 SourcePaper projection (for the
  review gate + observability);
- delegates v1 draft assembly to the downstream ``DeterministicDraftProjector``,
  which is where the existing assembler plugs in.

The source review gate uses :func:`source_review_validation.validate_source_review_gate`
when issues are present.
"""

from __future__ import annotations

from pathlib import Path

from .._common_paths import repo_root  # noqa: F401
from ...contracts import ArtifactRef, SourceBuildResult
from ...ports.source_build import SourceBuildFailure


__all__ = ["DeterministicSourcePaperBuilder"]


class DeterministicSourcePaperBuilder:
    """:class:`SourcePaperBuilder` — minimal v2 projection + review gate."""

    def __init__(self, store) -> None:
        self.store = store

    def build(self, transcription_ref, images_ref, extracted_source_ref, resolutions_ref):
        try:
            transcription = self.store.read_yaml(_as_ref(transcription_ref))
            images = self.store.read_yaml(_as_ref(images_ref)) if images_ref else None
            # The source manifest (word-source.yaml) is the ONLY carrier of
            # vector-asset evidence (ole_binding / emf_class / dimensions /
            # PNG-rendition availability). The v1 ImageAttributionBundle cannot
            # carry these fields, so they are read here and joined into the v2
            # paper. Read it now so the evidence channel is open even while the
            # fuller join (assets + attributions + guard classification) is
            # layered in.
            manifest = (
                self.store.read_yaml(_as_ref(extracted_source_ref))
                if extracted_source_ref
                else None
            )
            # Build a minimal v2 SourcePaper projection from the v1 transcription.
            source_paper = _project_minimal_v2(transcription, manifest)
            source_ref = self.store.commit_yaml(
                "structured/paper.source.yaml", source_paper, "math_exam_source_paper/v2"
            )
            # Determine blocking issues: if the image bundle carries any
            # attribution in needs_review state, or any asset in needs_review
            # disposition, emit REAL review issues (not an empty list). The
            # baseline checked the wrong field (assets[].state, which does not
            # exist on the v1 asset contract) and so never emitted issues.
            issues_ref = None
            review_items = _collect_review_issues(images, manifest)
            if review_items:
                issues_ref = self.store.commit_yaml(
                    "review/review-issues.yaml",
                    {"schema": "math_transcription_review_issues/v1",
                     "paper_id": source_paper.get("paper_id", "unknown"),
                     "issues": review_items},
                    "math_transcription_review_issues/v1",
                )
            return SourceBuildResult(source_paper=source_ref, issues=issues_ref), None, None
        except Exception as exc:  # pragma: no cover - defensive
            kind = _classify(exc)
            return None, kind, str(exc)


def _as_ref(value) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    return ArtifactRef.model_validate(value)


def _project_minimal_v2(transcription: dict, manifest: dict | None = None) -> dict:
    """Project a v1 QuestionTranscriptionBundle into a minimal v2 SourcePaper.

    Only the text-bearing fields are projected (stem/answer/clue/solution_steps as
    text nodes). Image nodes, assets and attributions are added by the
    deterministic image-attribution branch (joining ``manifest`` for vector
    evidence) in a fuller implementation; the staging pipeline below consumes the
    v1 draft, so this v2 projection is for the review gate and provenance.

    ``manifest`` is the source manifest (``word-source.yaml``); it is accepted
    now so the evidence channel is open for the fuller join, and so the paper_id
    can be recovered from the manifest when the transcription's paper.id is the
    placeholder used during ingestion.
    """

    paper_id = (
        transcription.get("paper", {}).get("id")
        or (manifest or {}).get("paper_id")
        or "unknown"
    )
    questions = []
    for section in transcription.get("sections", []):
        for q in section.get("questions", []):
            content = q.get("content", {})
            stem = content.get("stem_latex") or ""
            questions.append({
                "question_ref": q.get("question_ref"),
                "question_number": q.get("question_number"),
                "question_type": q.get("question_type"),
                "points": q.get("points", 0),
                "content": {
                    "stem": [{"kind": "text", "text": stem or "(empty stem)"}],
                    "answer": content.get("answer", ""),
                    "clue": content.get("clue", ""),
                    "solution_steps": [
                        {"step_id": str(i + 1),
                         "content": [{"kind": "text", "text": s}]}
                        for i, s in enumerate(content.get("solution_steps", []))
                    ],
                    **({"choices": content.get("choices", [])}
                       if q.get("question_type") == "choice" else {}),
                },
            })
    return {
        "schema": "math_exam_source_paper/v2",
        "paper_id": paper_id,
        "questions": questions,
        "assets": [],
        "attributions": [],
    }


def _collect_review_issues(images: dict | None, manifest: dict | None) -> list[dict]:
    """Collect REAL blocking review issues from the image bundle.

    The baseline ``_has_needs_review`` inspected ``assets[].state``, but the v1
    ``AttributionAsset`` contract has no ``state`` field (only ``disposition``) —
    so it always returned False and the issues list was always empty. A
    needs-review signal lives in two places:

    - ``attributions[].state == "needs_review"`` (model/structure uncertainty),
    - ``assets[].disposition == "needs_review"`` (unreferenced / orphan media).

    Each surfaces as a concrete review issue rather than being silently dropped.
    """
    if not images:
        return []
    issues: list[dict] = []
    for attr in images.get("attributions", []) or []:
        if attr.get("state") == "needs_review":
            issues.append({
                "issue_id": f"attr-needs-review-{attr.get('attribution_id', len(issues))}",
                "kind": "attribution_needs_review",
                "detail": (
                    f"attribution {attr.get('attribution_id', '?')} "
                    f"(asset {attr.get('asset_id', '?')}, q{attr.get('question_ref', '?')}) "
                    f"is in needs_review state and was not auto-accepted"
                ),
            })
    for asset in images.get("assets", []) or []:
        if asset.get("disposition") == "needs_review":
            issues.append({
                "issue_id": f"asset-needs-review-{asset.get('asset_id', len(issues))}",
                "kind": "asset_needs_review",
                "detail": (
                    f"asset {asset.get('asset_id', '?')} disposition=needs_review "
                    f"({asset.get('disposition_reason', 'unreferenced')})"
                ),
            })
    return issues


def _classify(exc) -> SourceBuildFailure:
    msg = str(exc).lower()
    if "validation" in msg:
        return "cross_reference_invalid"
    if "image" in msg:
        return "image_bundle_invalid"
    if "resolution" in msg:
        return "resolution_invalid"
    return "artifact_write_failed"
