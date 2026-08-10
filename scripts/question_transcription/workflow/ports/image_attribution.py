"""Image attribution port (architecture §3.4, §5.2, M3.4).

Formalises the previously untyped ``image_attribution: object`` dependency as a
``Protocol``. Image attribution is a *deterministic* branch (it reads the source
manifest and runs the existing adapt scripts); it is not an LLM call. Its result feeds
the source-paper join (ports §8).

``structure_status == "failed"`` is not "no images on this paper": it means attribution
could not produce a usable bundle. The source join may then save the text transcription
but must emit a blocking issue (ports §8).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..contracts import ArtifactRef, ExtractedSource


__all__ = ["ImageAttributionStatus", "ImageAttributor"]


ImageAttributionStatus = Literal["complete", "failed"]
"""Outcome of the deterministic image-attribution branch."""


@runtime_checkable
class ImageAttributor(Protocol):
    """Attribute source images to questions deterministically.

    Returns ``(bundle_ref, structure_status, issues_ref, detail)``:
    - ``bundle_ref`` — :class:`ArtifactRef` to ``math_image_attribution/v1`` (None on
      failure);
    - ``structure_status`` — ``"complete"`` or ``"failed"``;
    - ``issues_ref`` — optional issues artifact;
    - ``detail`` — None on success, a detail string on failure.
    """

    def attribute(
        self, extracted_source: ExtractedSource | ArtifactRef
    ) -> "tuple[ArtifactRef | None, ImageAttributionStatus, ArtifactRef | None, str | None]": ...
