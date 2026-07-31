"""Source-extraction and join nodes (ports-design §3, §8).

- :func:`make_extract_source_node` calls the bound :class:`SourceExtractor`, freezes
  page images + manifest, and builds the per-page :class:`PageTextJob` list.
- :func:`make_attribute_images_node` runs the deterministic image-attribution branch.
- :func:`make_build_source_paper_node` joins transcription + image attribution into
  the authoritative ``paper.source.yaml`` and runs the source review gate.
- :func:`decide_source_ready` is the pure gate decision (ports §9).
"""

from __future__ import annotations

from typing import Any

from ..artifact_store import sha256_file
from ..contracts import ArtifactRef, PageTextJob
from ..state import WorkflowState
from ..tracing import trace_event


__all__ = [
    "SourceReadyDecision",
    "decide_source_ready",
    "make_extract_source_node",
    "make_attribute_images_node",
    "make_build_source_paper_node",
]


def make_extract_source_node(deps):
    """Extract + freeze the source; build the per-page job list (design §3.1)."""

    extractor = deps.deterministic.source_extractor
    store = deps.artifact_store
    layout = deps.run_layout

    def extract_source(state: WorkflowState) -> dict[str, Any]:
        from ..contracts import ExtractedSource, SourceInput

        source = SourceInput(
            paper_id=state["paper_id"],
            source_kind=state["source_kind"],
            source_path=state["source_archive"],
            source_archive=state["source_archive"],
        )
        with trace_event("extract_source", source_kind=state["source_kind"]):
            extracted, error_kind, detail = extractor.extract(source)
        if error_kind is not None:
            return {"terminal_errors": [f"extract_source: {error_kind}: {detail}"]}
        assert extracted is not None
        # Build per-page jobs from the frozen page refs (ports §6.2).
        jobs = [
            PageTextJob(
                run_id=state["run_id"],
                paper_id=state["paper_id"],
                page_number=i + 1,
                image=page_ref,
                input_fingerprint=page_ref.sha256,
            )
            for i, page_ref in enumerate(extracted.pages)
        ]
        return {
            "extracted_source": extracted.model_dump(mode="json"),
            "page_text_jobs": [j.model_dump(mode="json") for j in jobs],
        }

    return extract_source


def make_attribute_images_node(deps):
    """Run the deterministic image-attribution branch in parallel with page text."""

    image_attr = deps.deterministic.image_attribution
    store = deps.artifact_store

    def attribute_images(state: WorkflowState) -> dict[str, Any]:
        extracted_ref = state.get("extracted_source")
        if extracted_ref is None:
            return {"terminal_errors": ["attribute_images: source not extracted"]}
        with trace_event("attribute_images"):
            # The adapter contract: attribute(extracted_source_dict) -> (bundle_ref|None,
            # structure_status, issues_ref|None, detail|None). Implementation lives in
            # adapters/image_attribution (wraps adapt_docx_images / adapt_pdf_images).
            result = image_attr.attribute(extracted_ref)
        bundle_ref, structure_status, issues_ref, detail = result
        if structure_status == "failed" and bundle_ref is None:
            # ports §8: attribution failure is not fatal to text transcription, but
            # must become a blocking issue at the join. We still record None bundle.
            return {"image_attribution": None}
        if bundle_ref is None:
            return {"terminal_errors": [f"attribute_images: {detail or 'no bundle'}"]}
        return {"image_attribution": bundle_ref.model_dump(mode="json") if hasattr(bundle_ref, 'model_dump') else bundle_ref}

    return attribute_images


class SourceReadyDecision:
    CONTINUE = "continue_to_draft"
    WAIT_REVIEW = "wait_for_source_review"
    STOP = "stop_source_build"


def decide_source_ready(build_result, issues_ref):
    """Pure source-ready gate decision (ports §9)."""

    if build_result is None:
        return SourceReadyDecision.STOP, None
    if issues_ref is not None:
        return SourceReadyDecision.WAIT_REVIEW, issues_ref
    return SourceReadyDecision.CONTINUE, None


def make_build_source_paper_node(deps):
    """Join transcription + image attribution into paper.source.yaml; run the gate."""

    builder = deps.deterministic.source_paper_builder
    store = deps.artifact_store

    def build_source_paper(state: WorkflowState) -> dict[str, Any]:
        transcription_ref = state.get("whole_paper_transcription")
        image_ref = state.get("image_attribution")
        if transcription_ref is None:
            return {"terminal_errors": ["build_source_paper: transcription missing"]}
        trans_ref = (
            ArtifactRef.model_validate(transcription_ref)
            if isinstance(transcription_ref, dict)
            else transcription_ref
        )
        img_ref = None
        if image_ref is not None:
            img_ref = (
                ArtifactRef.model_validate(image_ref)
                if isinstance(image_ref, dict)
                else image_ref
            )
        # resolutions may exist after a source-review resume.
        resolutions_path = deps.run_layout.review_resolutions_path.relative_to(
            deps.run_layout.root
        )
        resolutions_ref = None
        abs_res = deps.run_layout.review_resolutions_path
        if abs_res.exists():
            resolutions_ref = ArtifactRef(
                path=str(resolutions_path),
                sha256=sha256_file(abs_res),
                schema="math_transcription_review_resolutions/v1",
            )
        with trace_event("build_authoritative_source"):
            result, failure, detail = builder.build(trans_ref, img_ref, resolutions_ref)
        if failure is not None:
            return {"terminal_errors": [f"build_source_paper: {failure}: {detail}"]}
        assert result is not None
        next_state: dict[str, Any] = {
            "source_paper": result.source_paper.model_dump(mode="json")
            if hasattr(result.source_paper, "model_dump")
            else result.source_paper
        }
        if result.issues is not None:
            next_state["review_state"] = "waiting_for_source_review"
            next_state["terminal_errors"] = []  # not terminal; it's an interrupt
        else:
            next_state["review_state"] = "no_review_pending"
        return next_state

    return build_source_paper
