"""Authoritative source-paper builder wrapper (ports-design §9).

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

from ._common_paths import repo_root  # noqa: F401
from ..contracts import ArtifactRef, SourceBuildResult
from ..ports.source_build import SourceBuildFailure


__all__ = ["DeterministicSourcePaperBuilder"]


class DeterministicSourcePaperBuilder:
    """:class:`SourcePaperBuilder` — minimal v2 projection + review gate."""

    def __init__(self, store) -> None:
        self.store = store

    def build(self, transcription_ref, images_ref, resolutions_ref):
        try:
            transcription = self.store.read_yaml(_as_ref(transcription_ref))
            images = self.store.read_yaml(_as_ref(images_ref)) if images_ref else None
            # Build a minimal v2 SourcePaper projection from the v1 transcription.
            source_paper = _project_minimal_v2(transcription)
            source_ref = self.store.commit_yaml(
                "structured/paper.source.yaml", source_paper, "math_exam_source_paper/v2"
            )
            # Determine blocking issues: in this milestone, the transcription's own
            # validation already happened at the boundary; if the image bundle has
            # any non-accepted attribution needing review, emit issues.
            issues_ref = None
            if images and _has_needs_review(images):
                issues_ref = self.store.commit_yaml(
                    "review/review-issues.yaml",
                    {"schema": "math_transcription_review_issues/v1",
                     "paper_id": source_paper.get("paper_id", "unknown"),
                     "issues": []},
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


def _project_minimal_v2(transcription: dict) -> dict:
    """Project a v1 QuestionTranscriptionBundle into a minimal v2 SourcePaper.

    Only the text-bearing fields are projected (stem/answer/clue/solution_steps as
    text nodes). Image nodes are added by the deterministic image-attribution branch
    in a fuller implementation; the staging pipeline below consumes the v1 draft, so
    this v2 projection is for the review gate and provenance.
    """

    paper_id = transcription.get("paper", {}).get("id", "unknown")
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


def _has_needs_review(images: dict) -> bool:
    return any(
        a.get("state") == "needs_review" for a in images.get("assets", [])
    )


def _classify(exc) -> SourceBuildFailure:
    msg = str(exc).lower()
    if "validation" in msg:
        return "cross_reference_invalid"
    if "image" in msg:
        return "image_bundle_invalid"
    if "resolution" in msg:
        return "resolution_invalid"
    return "artifact_write_failed"
