"""Image-attribution wrapper (architecture §3.6 and §5.2).

Wraps the existing deterministic functions (NOT the CLIs — we want exceptions, not
``SystemExit``):

- :func:`adapt_docx_images.adapt` / :func:`adapt_pdf_images.adapt` for image attribution

Bound by the composition root; the ``attribute_images`` node delegates to it.
"""

from __future__ import annotations

from ...contracts import ArtifactRef


__all__ = ["DocxOrPdfImageAttribution"]


class DocxOrPdfImageAttribution:
    """Deterministic image-attribution adapter (ports §8).

    The ``attribute`` method receives the extracted-source dict and returns
    ``(bundle_ref, structure_status, issues_ref, detail)`` matching the contract the
    ``attribute_images`` node expects.
    """

    def __init__(self, store) -> None:
        self.store = store

    def attribute(self, extracted_source):
        kind = extracted_source.get("source_kind") if isinstance(extracted_source, dict) else None
        # The node passes the ArtifactRef dict for extracted_source; we read the
        # manifest to decide DOCX vs PDF attribution.
        manifest_ref = extracted_source
        try:
            manifest = self.store.read_yaml(
                ArtifactRef.model_validate(manifest_ref)
                if not isinstance(manifest_ref, ArtifactRef)
                else manifest_ref
            ) if isinstance(manifest_ref, (dict, ArtifactRef)) else None
        except Exception:
            manifest = None
        schema = (manifest or {}).get("schema", "")
        try:
            if "word_source" in schema:
                bundle = self._adapt_docx(manifest)
            else:
                bundle = self._adapt_pdf(manifest)
            ref = self.store.commit_yaml(
                "structured/image-attribution.yaml", bundle, "math_image_attribution/v1"
            )
            return ref, "complete", None, None
        except ValueError as exc:
            return None, "failed", None, str(exc)

    def _adapt_docx(self, manifest):
        from scripts.question_transcription.adapt_docx_images import adapt  # type: ignore

        paper_id = manifest.get("paper_id", "unknown")
        source_archive = manifest.get("source", {}).get("path") or manifest.get("source_archive", "")
        return adapt(manifest, paper_id=paper_id, source_archive=source_archive)

    def _adapt_pdf(self, manifest):
        from scripts.question_transcription.adapt_pdf_images import adapt  # type: ignore

        return adapt(manifest, allow_model_accepted=False)
