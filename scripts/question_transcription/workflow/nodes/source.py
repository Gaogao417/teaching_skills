"""Source-extraction and join nodes (architecture §5.2).

- :func:`make_extract_source_node` calls the bound :class:`SourceExtractor`, freezes
  page images + manifest, and builds the per-page :class:`PageTextJob` list.
- :func:`make_attribute_images_node` runs the deterministic image-attribution branch.
- :func:`make_build_source_paper_node` joins transcription + image attribution into
  the authoritative ``paper.source.yaml`` and runs the source review gate.
- :func:`decide_source_ready` is the pure gate decision (ports §9).
"""

from __future__ import annotations

from typing import Any

from ..application.stages.source import SourceReadyDecision, decide_source_ready
from ..infrastructure.artifact_store import sha256_file
from ..contracts import ArtifactRef, PageTextJob
from ..orchestration.langgraph.state import WorkflowState
from ..tracing import trace_event


__all__ = [
    "SourceReadyDecision",
    "decide_source_ready",
    "make_extract_source_node",
    "make_attribute_images_node",
    "make_build_source_paper_node",
]


def _backfill_evidence_page_paths(store, transcription_ref, extracted_source, layout):
    """Resolve whole-paper evidence ``source: "transcription"`` to real page paths.

    The transcriber emits page-NUMBER evidence refs because it only sees OCR text,
    not the rendered page images. The staging pipeline (materialize_staging) opens
    ``evidence.source``/``page_image`` as a file and hashes it, so it must be a path
    that resolves under the repo root. This maps each ``page_number`` to the absolute
    path of the corresponding rendered page (from ``extracted_source.pages``) and
    re-commits the transcription with the resolved paths.

    Operates on the typed contracts (ExtractedSource / QuestionTranscriptionBundle /
    PageEvidence) rather than raw dicts, so a malformed field fails loudly here
    instead of silently producing an invalid artifact.

    Returns the (possibly new) transcription ArtifactRef; on any failure it returns
    the original ref unchanged so the run is not blocked by a backfill error.
    """

    from ..contracts import ExtractedSource  # typed contract for the source bundle
    from ...contracts import QuestionTranscriptionBundle  # typed transcription

    try:
        extracted = ExtractedSource.model_validate(extracted_source)
        page_path_by_number: dict[int, str] = {}
        for i, pref in enumerate(extracted.pages):
            page_path_by_number[i + 1] = str((layout.root / pref.path).resolve())
        if not page_path_by_number:
            return transcription_ref

        bundle = QuestionTranscriptionBundle.model_validate(
            store.read_yaml(transcription_ref)
        )
        changed = False
        for section in bundle.sections:
            for q in section.questions:
                if q.evidence is None:
                    continue
                for role_refs in (q.evidence.question, q.evidence.solution):
                    for ref in role_refs:
                        if ref.source != "transcription":
                            continue
                        resolved = page_path_by_number.get(ref.page_number)
                        if resolved is None:
                            continue
                        ref.source = resolved
                        changed = True
        if not changed:
            return transcription_ref
        # by_alias=True so the dumped yaml uses ``schema`` (the input alias the
        # downstream projector re-validates with), not the python field name
        # ``schema_`` (which model_validate rejects as extra).
        return store.commit_yaml(
            "structured/transcription.yaml",
            bundle.model_dump(mode="json", by_alias=True),
            bundle.schema_,
        )
    except Exception:
        # Backfill must never block the pipeline; surface original ref on failure.
        return transcription_ref


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
        extracted = state.get("extracted_source")
        if extracted is None:
            return {"terminal_errors": ["attribute_images: source not extracted"]}
        # state["extracted_source"] is the serialized ExtractedSource (manifest +
        # pages + media_directory). The attribution adapter consumes the source
        # MANIFEST (the word-source / pdf-source yaml), which is the ``manifest``
        # ArtifactRef field — not the whole ExtractedSource object.
        manifest_ref = extracted.get("manifest") if isinstance(extracted, dict) else None
        if manifest_ref is None:
            return {"terminal_errors": ["attribute_images: extracted source has no manifest"]}
        with trace_event("attribute_images"):
            # The adapter contract: attribute(manifest_ref) -> (bundle_ref|None,
            # structure_status, issues_ref|None, detail|None). Implementation lives in
            # adapters/image_attribution (wraps adapt_docx_images / adapt_pdf_images).
            result = image_attr.attribute(manifest_ref)
        bundle_ref, structure_status, issues_ref, detail = result
        if structure_status == "failed" and bundle_ref is None:
            # ports §8: attribution failure is not fatal to text transcription, but
            # must become a blocking issue at the join. We still record None bundle.
            return {"image_attribution": None}
        if bundle_ref is None:
            return {"terminal_errors": [f"attribute_images: {detail or 'no bundle'}"]}
        return {"image_attribution": bundle_ref.model_dump(mode="json") if hasattr(bundle_ref, 'model_dump') else bundle_ref}

    return attribute_images


def make_build_source_paper_node(deps):
    """Join transcription + image attribution into paper.source.yaml; run the gate."""

    builder = deps.deterministic.source_paper_builder
    store = deps.artifact_store
    layout = deps.run_layout

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
        # Backfill evidence.source: the whole-paper transcriber knows only the page
        # NUMBER each question/solution spans; it cannot know the rendered page-image
        # file path (that is owned by the source-extraction branch). The downstream
        # staging pipeline (materialize_staging) treats evidence.source/page_image as a
        # real file path it opens and hashes. So before the builder reads the
        # transcription, resolve every page-number evidence ref against
        # extracted_source.pages into an absolute page-image path.
        extracted = state.get("extracted_source")
        if isinstance(extracted, dict):
            trans_ref = _backfill_evidence_page_paths(
                store, trans_ref, extracted, layout
            )
        # The source manifest (word-source.yaml) is the ONLY carrier of
        # vector-asset evidence; pass its ArtifactRef to the builder so the v2
        # paper can carry ole_binding / emf_class / rendition. Mirrors the
        # attribute_images node's manifest extraction.
        manifest_ref = None
        if isinstance(extracted, dict):
            manifest_raw = extracted.get("manifest")
            if manifest_raw is not None:
                manifest_ref = (
                    ArtifactRef.model_validate(manifest_raw)
                    if isinstance(manifest_raw, dict)
                    else manifest_raw
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
            result, failure, detail = builder.build(
                trans_ref, img_ref, manifest_ref, resolutions_ref
            )
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
