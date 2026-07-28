#!/usr/bin/env python3
"""PDF / scan image-attribution Adapter (Track 3).

PDF and scan sources have no OOXML paragraph structure, so figure attribution
comes from a vision detection provider (Agent or detection model). This adapter
wraps that provider's raw output and emits the standard
:class:`ImageAttributionBundle`. Per ``docs/question-transcription-architecture.md``
§8.2, the text and image bundles may come from the same vision call but must be
split into the two standard bundles; this owns the image side.

Provider input format (``pdf-detection.yaml``) is intentionally minimal and is
defined here (no prior PDF detection format exists in the repo):

```yaml
schema: math_pdf_detection/v1            # this adapter's input
source_archive: documents/初三/...        # repo-relative
pages:                                    # one entry per immutable page image
  - path: pages-pages/001.png             # relative to source_archive
    sha256: sha256:...
    width_px: 1240
    height_px: 1754
detections:                               # figure/region detections
  - page_path: pages-pages/004.png
    question_number: 24
    role: prompt                          # prompt | solution
    box_px: [650, 315, 1000, 690]         # [left, top, right, bottom]
    whiteout_px: []                       # optional
    confidence: medium                    # high | medium | low
    note: parabola figure
```

Mapping:
- Each page becomes an asset. ``source`` = ``<source_archive>/<page_path>``.
- Each detection becomes a ``crop: region`` attribution on that page's asset.
- ``confidence`` -> ``state`` mirrors the DOCX adapter: high/medium -> accepted,
  low -> needs_review.
- Pages with zero detections are emitted as ``disposition: needs_review`` so the
  assembler reports (never silently drops) a page that the provider scanned but
  could not attribute.

The assembler validates region boxes against asset dims and consumes only
accepted attributions, exactly once.
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
    ImageAttributionBundle,
)
from scripts.question_transcription.pdf_observation_contracts import (  # noqa: E402
    MergedPdfObservation,
)

CONFIDENCE_TO_STATE: dict[str, str] = {
    "high": "accepted",
    "medium": "accepted",
    "low": "needs_review",
}


def adapt(
    detection: dict[str, Any] | MergedPdfObservation,
    *,
    allow_model_accepted: bool = False,
) -> dict[str, Any]:
    """Adapt either the new merged observation or the legacy detection payload."""
    if isinstance(detection, MergedPdfObservation):
        return adapt_observation(
            detection, allow_model_accepted=allow_model_accepted
        )
    if detection.get("schema") == "math_pdf_merged_observation/v1":
        return adapt_observation(
            MergedPdfObservation.model_validate(detection),
            allow_model_accepted=allow_model_accepted,
        )
    return _adapt_legacy_detection(detection)


def adapt_observation(
    observation: MergedPdfObservation,
    *,
    allow_model_accepted: bool = False,
) -> dict[str, Any]:
    """Split image attributions from a validated joint PDF observation."""
    figures_by_page: dict[int, list[tuple[str, Any]]] = defaultdict(list)
    for question in observation.questions:
        for figure in question.figures:
            figures_by_page[figure.page_number].append(
                (question.question_ref, figure)
            )

    assets: list[dict[str, Any]] = []
    asset_ids: dict[int, str] = {}
    for page in observation.pages:
        asset_id = f"page-{page.page_number:03d}"
        asset_ids[page.page_number] = asset_id
        active = [
            figure
            for _, figure in figures_by_page.get(page.page_number, [])
            if figure.state != "rejected"
        ]
        assets.append(
            {
                "asset_id": asset_id,
                "source": _source(
                    observation.paper.source_archive, page.source
                ),
                "sha256": page.sha256,
                "media_type": (
                    "image/jpeg"
                    if Path(page.source).suffix.lower() in {".jpg", ".jpeg"}
                    else "image/png"
                ),
                "width_px": page.width_px,
                "height_px": page.height_px,
                "disposition": "attributed" if active else "ignored",
                **(
                    {}
                    if active
                    else {"disposition_reason": "no_independent_figure"}
                ),
            }
        )

    attributions = []
    for page_number in sorted(figures_by_page):
        for question_ref, figure in sorted(
            figures_by_page[page_number],
            key=lambda item: (int(item[0].split("-", 1)[0]), item[1].role, item[1].order),
        ):
            crop: dict[str, Any] = {
                "kind": "region",
                "box_px": figure.box_px,
            }
            if figure.whiteout_px:
                crop["whiteout_px"] = figure.whiteout_px
            evidence: dict[str, object] = {
                "local_id": figure.local_id,
                "page_number": page_number,
            }
            if figure.note:
                evidence["note"] = figure.note
            if figure.needs_human_crop:
                evidence["needs_human_crop"] = True
            state = figure.state
            if state == "accepted" and not allow_model_accepted:
                state = "needs_review"
                evidence["model_acceptance_downgraded"] = True
            attributions.append(
                {
                    "attribution_id": (
                        f"attr-page-{page_number:03d}-q{question_ref}-"
                        f"{figure.role}-{figure.order}"
                    ),
                    "asset_id": asset_ids[page_number],
                    "question_ref": question_ref,
                    "role": figure.role,
                    "crop": crop,
                    "order": figure.order,
                    "confidence": figure.confidence,
                    "state": state,
                    "provider": {
                        **observation.provider.model_dump(),
                        "evidence": evidence,
                    },
                }
            )
    result = {
        "schema": "math_image_attribution/v1",
        "paper_id": observation.paper.id,
        "assets": assets,
        "attributions": attributions,
    }
    return ImageAttributionBundle.model_validate(result).model_dump(
        by_alias=True, exclude_none=True
    )


def _source(archive: str, source: str) -> str:
    if Path(source).is_absolute() or source.startswith(f"{archive.rstrip('/')}/"):
        return source
    return f"{archive.rstrip('/')}/{source.lstrip('/')}"


def _adapt_legacy_detection(
    detection: dict[str, Any],
) -> dict[str, Any]:
    """Build a standard ImageAttributionBundle from the legacy detection input."""
    if detection.get("schema") != "math_pdf_detection/v1":
        raise ValueError("detection schema must be math_pdf_detection/v1")
    source_archive = (detection.get("source_archive") or "").rstrip("/")
    if not source_archive:
        raise ValueError("detection.source_archive is required")
    paper_id = detection.get("paper_id")
    if not paper_id:
        raise ValueError("detection.paper_id is required")

    pages = detection.get("pages") or []
    if not isinstance(pages, list) or not pages:
        raise ValueError("detection.pages must be a non-empty list")

    # Index pages by path and by leaf for robust matching.
    page_by_path: dict[str, dict[str, Any]] = {}
    for page in pages:
        path = str(page.get("path") or "")
        if not path:
            raise ValueError("a page entry is missing path")
        page_by_path[path] = page

    assets: list[dict[str, Any]] = []
    asset_ids: dict[str, str] = {}
    for index, page in enumerate(pages, start=1):
        path = str(page.get("path") or "")
        asset_id = f"page-{Path(path).stem}"  # pages-pages/004.png -> page-004
        if asset_id in asset_ids.values():
            asset_id = f"page-{index:03d}"
        asset_ids[path] = asset_id
        width = int(page.get("width_px") or 0)
        height = int(page.get("height_px") or 0)
        if width < 1 or height < 1:
            raise ValueError(f"page {path}: width_px/height_px must be positive")
        sha = str(page.get("sha256") or "")
        if not sha.startswith("sha256:"):
            raise ValueError(f"page {path}: sha256 missing or malformed")
        assets.append(
            {
                "asset_id": asset_id,
                "source": f"{source_archive}/{path}",
                "sha256": sha,
                "media_type": "image/png",
                "width_px": width,
                "height_px": height,
                "disposition": "attributed",  # downgraded later if no detection
            }
        )

    detections = detection.get("detections") or []
    order_counts: dict[tuple[str, str], int] = defaultdict(int)
    referenced_pages: set[str] = set()
    attributions: list[dict[str, Any]] = []

    for det in detections:
        page_path = str(det.get("page_path") or "")
        page = page_by_path.get(page_path)
        if page is None:
            raise ValueError(
                f"detection references unknown page: {page_path!r}"
            )
        referenced_pages.add(page_path)
        asset_id = asset_ids[page_path]

        role = str(det.get("role") or "")
        if role not in {"prompt", "solution"}:
            raise ValueError(f"detection on {page_path}: role must be prompt/solution")
        question_number = det.get("question_number")
        if question_number is None:
            raise ValueError(f"detection on {page_path}: question_number missing")
        question_ref = str(question_number)
        box = det.get("box_px")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError(
                f"detection on {page_path}: box_px must be four ints"
            )
        confidence = str(det.get("confidence") or "medium")
        state = CONFIDENCE_TO_STATE.get(confidence)
        if state is None:
            raise ValueError(f"detection on {page_path}: unknown confidence {confidence!r}")

        order = order_counts[(question_ref, role)]
        order_counts[(question_ref, role)] += 1

        attribution_id = f"attr-{asset_id}-q{question_ref}-{role}-{order}"
        crop: dict[str, Any] = {"kind": "region", "box_px": [int(v) for v in box]}
        whiteout = det.get("whiteout_px") or []
        if whiteout:
            crop["whiteout_px"] = [[int(v) for v in w] for w in whiteout]

        attributions.append(
            {
                "attribution_id": attribution_id,
                "asset_id": asset_id,
                "question_ref": question_ref,
                "role": role,
                "crop": crop,
                "order": order,
                "confidence": confidence,
                "state": state,
                "provider": {
                    "kind": str(det.get("provider_kind") or "agent"),
                    "name": str(det.get("provider_name") or "visual-attributor"),
                    "version": str(det.get("provider_version") or "v1"),
                    "evidence": {"note": det["note"]} if det.get("note") else {},
                },
            }
        )

    # Pages the provider scanned but found nothing on -> needs_review, reported
    # by the assembler rather than silently dropped.
    for path, asset_id in asset_ids.items():
        if path not in referenced_pages:
            for a in assets:
                if a["asset_id"] == asset_id:
                    a["disposition"] = "needs_review"
                    a["disposition_reason"] = "no_detection_on_page"

    return {
        "schema": "math_image_attribution/v1",
        "paper_id": paper_id,
        "assets": assets,
        "attributions": attributions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt a PDF detection payload into a standard ImageAttributionBundle.")
    parser.add_argument("--detection", type=Path, required=True, help="path to pdf-detection.yaml")
    parser.add_argument("--output", type=Path, required=True, help="output image-attribution bundle path")
    parser.add_argument(
        "--allow-model-accepted",
        action="store_true",
        help=(
            "preserve accepted states from a merged observation after explicit "
            "human crop confirmation; legacy detection behavior is unchanged"
        ),
    )
    args = parser.parse_args()

    detection = yaml.safe_load(args.detection.read_text(encoding="utf-8"))
    if not isinstance(detection, dict):
        raise ValueError(f"{args.detection}: root must be a mapping")

    bundle_dict = adapt(
        detection, allow_model_accepted=args.allow_model_accepted
    )
    bundle = ImageAttributionBundle.model_validate(bundle_dict)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(bundle.model_dump(by_alias=True, exclude_none=True), allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    accepted = [a for a in bundle.attributions if a.state == "accepted"]
    print(
        f"PDF IMAGES ADAPTED: {args.output} | pages={len(bundle.assets)} "
        f"detections={len(bundle.attributions)} accepted={len(accepted)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
