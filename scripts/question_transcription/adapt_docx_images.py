#!/usr/bin/env python3
"""DOCX image-attribution Adapter (Track 2).

Converts a real ``word-source.yaml`` (produced by
``extract_docx_source.py``, schema ``math_word_source_extract/v1``) into the
standard :class:`ImageAttributionBundle`. This is the DOCX image provider --
it owns the OOXML paragraph-structure attribution that no longer needs to be
re-done by the Agent on PDF pages.

Mapping rules (see ``docs/question-transcription-architecture.md`` §8.1 and
the docx ingestion skill):
- ``media[].path`` is relative to the ``word/`` dir (e.g. ``media/image10.png``);
  the asset ``source`` becomes ``<source_archive>/word/<media path>``.
- DOCX images use the original Word media, so every attribution gets
  ``crop: full`` (the assembler expands it to ``[0,0,w,h]`` from asset dims).
- ``bucket`` -> ``role``: ``prompt`` -> ``prompt``, ``solution`` -> ``solution``,
  ``orphan`` -> asset disposition ``ignored`` (no attribution created).
- ``confidence`` -> ``state``: only ``high`` -> ``accepted``; ``medium`` and
  ``low`` -> ``needs_review``. A model/structure result that still expresses
  uncertainty must never become consumable merely by passing the Adapter.
- ``order`` is assigned per (question_ref, role) in paragraph order, which is
  the document reading order -- deterministic and stable.
- Media referenced by no attribution are emitted as ``disposition:
  needs_review`` so the assembler reports them (a real orphan the structure
  extractor could not classify), rather than silently dropped.

This adapter emits the bundle; it does not assemble a draft. The
DraftAssembler (Track 1) consumes the output.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    AttributionAsset,
    AttributionConfidence,
    ImageAttributionBundle,
)

CONFIDENCE_TO_STATE: dict[AttributionConfidence, str] = {
    "high": "accepted",
    "medium": "needs_review",
    "low": "needs_review",
}

MEDIA_TYPE_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
}


def adapt(
    word_source: dict[str, Any],
    *,
    paper_id: str,
    source_archive: str,
) -> dict[str, Any]:
    """Build a standard ImageAttributionBundle dict from word-source.yaml data."""
    attribution_status = word_source.get("image_attribution_status", "complete")
    if attribution_status == "failed":
        error = word_source.get("image_attribution_error") or {}
        detail = (
            error.get("detail")
            if isinstance(error, dict)
            else str(error)
        )
        raise ValueError(
            "word-source.yaml: image attribution failed; text transcription "
            f"may continue, but image adaptation is blocked: {detail or 'unknown error'}"
        )
    if attribution_status != "complete":
        raise ValueError(
            "word-source.yaml: unknown image_attribution_status "
            f"{attribution_status!r}"
        )
    media_entries = word_source.get("media") or []
    if not isinstance(media_entries, list) or not media_entries:
        raise ValueError("word-source.yaml: media list is required")
    image_attr = word_source.get("image_attribution") or []

    # Index media by the leaf name (image10.png) for robust matching; the
    # attribution ``media`` field and the media ``path`` both end in the same
    # leaf but the attribution drops the directory in some historical outputs.
    media_by_leaf: dict[str, dict[str, Any]] = {}
    media_by_path: dict[str, dict[str, Any]] = {}
    for entry in media_entries:
        path = str(entry.get("path") or "")
        leaf = Path(path).name
        media_by_leaf[leaf] = entry
        media_by_path[path] = entry

    assets: list[dict[str, Any]] = []
    attributions: list[dict[str, Any]] = []
    asset_ids: dict[str, str] = {}  # leaf -> asset_id
    referenced_leaves: set[str] = set()

    for entry in media_entries:
        path = str(entry.get("path") or "")
        leaf = Path(path).name
        if not leaf:
            continue
        # asset_id uses the image stem, e.g. media/image10.png -> word-image10.
        stem = Path(leaf).stem
        asset_id = f"word-{stem}"
        asset_ids[leaf] = asset_id
        suffix = Path(leaf).suffix.lower()
        media_type = MEDIA_TYPE_BY_SUFFIX.get(suffix, "image/png")
        width = int(entry.get("width_px") or 0)
        height = int(entry.get("height_px") or 0)
        if width < 1 or height < 1:
            raise ValueError(
                f"media {leaf}: width_px/height_px must be positive (got {width}x{height})"
            )
        sha = str(entry.get("sha256") or "")
        if not sha.startswith("sha256:"):
            raise ValueError(f"media {leaf}: sha256 missing or malformed")
        assets.append(
            {
                "asset_id": asset_id,
                "source": f"{source_archive}/word/{path}",
                "sha256": sha,
                "media_type": media_type,
                "width_px": width,
                "height_px": height,
                "disposition": "attributed",  # may be downgraded below
            }
        )

    # order per (question_ref, role), in document/paragraph order
    order_counts: dict[tuple[str, str], int] = defaultdict(int)
    for attr in image_attr:
        media_ref = str(attr.get("media") or "")
        leaf = Path(media_ref).name
        bucket = str(attr.get("bucket") or "")
        question_number = attr.get("question_number")
        confidence = str(attr.get("confidence") or "medium")
        paragraph_index = attr.get("paragraph_index")

        media_entry = media_by_leaf.get(leaf) or media_by_path.get(media_ref)
        if media_entry is None:
            raise ValueError(
                f"image_attribution references unknown media: {media_ref!r}"
            )
        referenced_leaves.add(leaf)
        asset_id = asset_ids[leaf]

        if bucket == "orphan":
            # Mark the asset ignored; no attribution created. Find + downgrade.
            for a in assets:
                if a["asset_id"] == asset_id:
                    a["disposition"] = "ignored"
                    a["disposition_reason"] = "orphan_in_paragraph_stream"
            continue

        if bucket not in {"prompt", "solution"}:
            raise ValueError(
                f"media {leaf}: unknown bucket {bucket!r} (expected prompt/solution/orphan)"
            )
        if question_number is None:
            raise ValueError(f"media {leaf}: question_number missing in attribution")

        role = bucket
        question_ref = str(question_number)
        state = CONFIDENCE_TO_STATE.get(confidence)  # type: ignore[arg-type]
        if state is None:
            raise ValueError(
                f"media {leaf}: unknown confidence {confidence!r}"
            )
        order = order_counts[(question_ref, role)]
        order_counts[(question_ref, role)] += 1

        attribution_id = f"attr-{asset_id}-q{question_ref}-{role}-{order}"
        attributions.append(
            {
                "attribution_id": attribution_id,
                "asset_id": asset_id,
                "question_ref": question_ref,
                "role": role,
                "crop": {"kind": "full"},
                "order": order,
                "confidence": confidence,
                "state": state,
                "provider": {
                    "kind": "docx_structure",
                    "name": "extract_docx_source",
                    "version": "v1",
                    "evidence": {"paragraph_index": paragraph_index}
                    if paragraph_index is not None
                    else {},
                },
            }
        )

    # Media referenced by no attribution: emit as needs_review (real orphan the
    # extractor could not classify), so the assembler reports rather than drops.
    leaf_by_asset_id = {v: k for k, v in asset_ids.items()}
    for a in assets:
        leaf = leaf_by_asset_id.get(a["asset_id"])
        if leaf and leaf not in referenced_leaves and a["disposition"] == "attributed":
            a["disposition"] = "needs_review"
            a["disposition_reason"] = "unreferenced_in_paragraph_stream"

    return {
        "schema": "math_image_attribution/v1",
        "paper_id": paper_id,
        "assets": assets,
        "attributions": attributions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt word-source.yaml into a standard ImageAttributionBundle.")
    parser.add_argument("--word-source", type=Path, required=True, help="path to word-source.yaml")
    parser.add_argument("--output", type=Path, required=True, help="output image-attribution bundle path")
    parser.add_argument("--paper-id", required=True, help="paper id (e.g. 2025-YANGPU-ERMO)")
    parser.add_argument(
        "--source-archive",
        required=True,
        help="repo-relative source archive dir (e.g. documents/初三/2025届-.../)",
    )
    args = parser.parse_args()

    word_source = yaml.safe_load(args.word_source.read_text(encoding="utf-8"))
    if not isinstance(word_source, dict):
        raise ValueError(f"{args.word_source}: root must be a mapping")
    if word_source.get("schema") != "math_word_source_extract/v1":
        raise ValueError(f"{args.word_source}: schema must be math_word_source_extract/v1")

    bundle_dict = adapt(
        word_source,
        paper_id=args.paper_id,
        source_archive=args.source_archive.rstrip("/"),
    )
    # Validate through the contract before writing.
    bundle = ImageAttributionBundle.model_validate(bundle_dict)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(bundle.model_dump(by_alias=True, exclude_none=True), allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    accepted = [a for a in bundle.attributions if a.state == "accepted"]
    print(
        f"DOCX IMAGES ADAPTED: {args.output} | assets={len(bundle.assets)} "
        f"attributions={len(bundle.attributions)} accepted={len(accepted)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
