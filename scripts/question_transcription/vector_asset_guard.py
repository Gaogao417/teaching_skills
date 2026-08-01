"""Vector asset guard — pure classification of DOCX vector media.

Sits between the source manifest (``word-source.yaml``, which already carries
``ole_binding`` / ``emf_class`` / dimensions for vector media) and the
authoritative ``SourcePaper v2`` builder. The guard decides, per media asset:

- OLE-embedded Equation WMF/EMF           -> ``ignored`` / ``ole_formula``
- non-OLE WMF/EMF, both dims <= 16 px     -> ``ignored`` / ``tiny_vector_fragment``
- non-OLE WMF/EMF, over the size gate,
  WITH a raster PNG rendition available   -> ``accepted`` (consume the rendition)
- non-OLE WMF/EMF, over the size gate,
  NO raster rendition                     -> ``needs_review`` / ``vector_rendition_missing``
- ordinary raster (png/jpg/...)           -> ``accepted`` (self-rendition)

The guard is pure logic: it never reads files and never converts anything. The
absence of a WMF->PNG converter in this repository means a vector asset without
a pre-existing PNG rendition is always routed to human review.

Rationale (architecture decision A): ``SourcePaper v2`` is the authoritative
image record. The v1 ``ImageAttributionBundle`` is a frozen compatibility
contract that cannot carry ``emf_class`` / ``ole_binding`` / ``rendition``, so
the classification MUST happen at the v2 layer — not inside ``adapt_docx_images``
(which would then be unable to forward the evidence downstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


__all__ = [
    "TINY_VECTOR_MAX_PX",
    "VectorAssetGuard",
    "GuardInput",
    "GuardDecision",
    "GuardReason",
]


# A vector fragment whose width AND height are both at or below this threshold is
# treated as a stray glyph fragment (a leftover drawing/canvas element, not a
# real figure). Both dims must be small: a 5x800px sliver is still a real image.
TINY_VECTOR_MAX_PX = 16

GuardReason = Literal[
    "ole_formula",
    "tiny_vector_fragment",
    "vector_rendition_missing",
]

_Disposition = Literal["ignored", "needs_review", "accepted"]

_VECTOR_SUFFIXES = {".wmf", ".emf"}
_VECTOR_MEDIA_TYPES = {
    "image/wmf",
    "image/emf",
    "image/x-wmf",
    "image/x-emf",
}


@dataclass(frozen=True)
class GuardInput:
    """One media entry from ``word-source.yaml`` projected to the guard's view.

    ``media_path`` is the leaf path (``media/image72.wmf``). ``width_px`` /
    ``height_px`` are the rendered dims. ``emf_class`` / ``ole_binding`` are
    present only on vector media (PNG entries carry ``None``).
    ``has_png_rendition`` is True when a separate PNG rendition exists for this
    asset; ordinary raster media is its own rendition (True).
    """

    media_path: str
    media_type: str
    width_px: int
    height_px: int
    emf_class: str | None
    ole_binding_embedded: bool | None
    has_png_rendition: bool


@dataclass(frozen=True)
class GuardDecision:
    """The guard's per-asset verdict.

    ``uses_rendition`` is True only for an ``accepted`` vector asset that must be
    consumed via its PNG rendition (never via the raw WMF bytes). Raster assets
    carry ``uses_rendition=False`` because the original IS the display image.
    """

    disposition: _Disposition
    reason: GuardReason | None
    uses_rendition: bool


class VectorAssetGuard:
    """Classify a media asset for the authoritative v2 source paper."""

    def classify(self, media: GuardInput) -> GuardDecision:
        suffix = Path(media.media_path).suffix.lower()
        is_vector = (
            suffix in _VECTOR_SUFFIXES
            or media.media_type.lower() in _VECTOR_MEDIA_TYPES
        )

        # Ordinary raster: accept as-is (it is its own rendition).
        if not is_vector:
            return GuardDecision(
                disposition="accepted", reason=None, uses_rendition=False
            )

        # Vector path. OLE-embedded Equation objects are always formula media —
        # they are equation glyphs, never content figures.
        if media.emf_class == "formula" or media.ole_binding_embedded is True:
            return GuardDecision(
                disposition="ignored", reason="ole_formula", uses_rendition=False
            )

        # Tiny non-OLE fragment: a stray glyph / canvas leftover, not a figure.
        if media.width_px <= TINY_VECTOR_MAX_PX and media.height_px <= TINY_VECTOR_MAX_PX:
            return GuardDecision(
                disposition="ignored",
                reason="tiny_vector_fragment",
                uses_rendition=False,
            )

        # Larger non-OLE vector: needs a raster rendition to be usable. The
        # repository has no WMF->PNG converter, so without a pre-existing PNG we
        # route to human review rather than letting raw WMF bytes reach the
        # materializer (which would raise Pillow's "cannot find loader").
        if media.has_png_rendition:
            return GuardDecision(
                disposition="accepted", reason=None, uses_rendition=True
            )
        return GuardDecision(
            disposition="needs_review",
            reason="vector_rendition_missing",
            uses_rendition=False,
        )


def guard_input_from_media_entry(entry: dict[str, Any]) -> GuardInput:
    """Build a :class:`GuardInput` from a ``word-source.yaml`` media entry.

    The extractor emits ``ole_binding`` / ``emf_class`` only on vector media; a
    PNG entry has neither. ``has_png_rendition`` defaults to False here — the v2
    builder is responsible for joining any PNG-rendition evidence it knows about
    before constructing the asset (the guard only sees whether one was declared).
    """

    path = str(entry.get("path") or "")
    media_type = _media_type_for_path(path)
    ole = entry.get("ole_binding") or {}
    embedded = ole.get("embedded") if isinstance(ole, dict) else None
    declared_rendition = entry.get("rendition")
    return GuardInput(
        media_path=path,
        media_type=media_type,
        width_px=int(entry.get("width_px") or 0),
        height_px=int(entry.get("height_px") or 0),
        emf_class=entry.get("emf_class"),
        ole_binding_embedded=embedded,
        has_png_rendition=bool(declared_rendition) or not _is_vector(path, media_type),
    )


def _is_vector(path: str, media_type: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in _VECTOR_SUFFIXES or media_type.lower() in _VECTOR_MEDIA_TYPES


def _media_type_for_path(path: str) -> str:
    """Return the honest media type for a path (WMF must NOT be reported as PNG)."""

    suffix = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".webp": "image/webp",
        ".wmf": "image/wmf",
        ".emf": "image/emf",
    }.get(suffix, "application/octet-stream")
