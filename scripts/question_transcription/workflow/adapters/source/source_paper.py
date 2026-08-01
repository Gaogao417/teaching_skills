"""Authoritative source-paper builder wrapper (architecture §3.6 and §5.2).

Joins three sources into the authoritative ``paper.source.yaml``
(``math_exam_source_paper/v2``), then runs the source review gate:

- ``transcription`` (v1) — question text, answer, clue, solution_steps, evidence;
- ``images`` (v1 ImageAttributionBundle) — per-asset question_ref / role / order /
  crop / confidence (which question an image belongs to and in what reading order);
- ``manifest`` (word-source.yaml) — the ONLY carrier of vector-asset evidence
  (``ole_binding`` / ``emf_class`` / dimensions / PNG-rendition availability).

The VectorAssetGuard classifies each media asset using the manifest evidence; the
v1 image bundle then supplies the question attribution. The frozen v1
ImageAttributionBundle cannot carry ``emf_class`` / ``ole_binding`` / ``rendition``,
so the classification and the authoritative image record both live at the v2
layer. The downstream projector (``project_source_paper``) projects the resulting
v2 paper back to the v1-compatible draft the existing staging pipeline consumes.

Honest limitation (v1 -> v2 target mapping): the v1 bundle has only a flat
``role`` (prompt/solution), no part_id/step_id. ``role=prompt`` maps to
``question_stem``; ``role=solution`` maps to ``question_solution_step`` on the
question's first step when one exists (else falls back to ``question_stem``).
Precise part/step-level targets require the whole-paper transcriber to emit v2
directly (future work). Images whose asset is classified ignored (OLE formula,
tiny vector fragment) never produce an attribution; images whose asset is
classified needs_review (vector rendition missing) surface as review issues.
"""

from __future__ import annotations

from pathlib import Path

from .._common_paths import repo_root  # noqa: F401
from ...contracts import ArtifactRef, SourceBuildResult
from ...ports.source_build import SourceBuildFailure
from scripts.question_transcription.vector_asset_guard import (  # noqa: E402
    GuardDecision,
    GuardInput,
    VectorAssetGuard,
    guard_input_from_media_entry,
)


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
            # paper.
            manifest = (
                self.store.read_yaml(_as_ref(extracted_source_ref))
                if extracted_source_ref
                else None
            )
            # Build the authoritative v2 SourcePaper: text from the transcription,
            # assets/attributions from the manifest + v1 image bundle, classified
            # by the VectorAssetGuard.
            source_paper, review_items = _build_authoritative_v2(
                transcription, images, manifest
            )
            source_ref = self.store.commit_yaml(
                "structured/paper.source.yaml", source_paper, "math_exam_source_paper/v2"
            )
            # Emit REAL review issues (vector rendition missing, needs_review
            # attribution/disposition). The baseline always wrote an empty list.
            issues_ref = None
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
    """Minimal v2 SourcePaper with text only (no assets/attributions).

    Used when there is no image bundle to join (e.g. a text-only paper, or a
    non-docx source with no manifest). The authoritative path is
    :func:`_build_authoritative_v2`.
    """

    paper_id = _resolve_paper_id(transcription, manifest)
    return {
        "schema": "math_exam_source_paper/v2",
        "paper_id": paper_id,
        "questions": _build_questions(transcription),
        "assets": [],
        "attributions": [],
    }


def _resolve_paper_id(transcription: dict, manifest: dict | None) -> str:
    return (
        transcription.get("paper", {}).get("id")
        or (manifest or {}).get("paper_id")
        or "unknown"
    )


def _build_questions(
    transcription: dict,
    image_nodes_by_ref: dict[str, dict] | None = None,
) -> list[dict]:
    """Project v1 question text into v2 SourceQuestion dicts.

    Image nodes are inserted inline when ``image_nodes_by_ref`` supplies them, so
    the v2 contract's content-image <-> attribution binding (enforced by
    ``assert_source_review_ready``) holds. Each question's stem and first solution
    step may carry ImageNodes in reading order; the attribution ``order`` matches
    the ImageNode position within that target.

    ``image_nodes_by_ref[question_ref]`` has the shape::

        {
          "stem": [{"asset_id": "...", "order": 0}, ...],
          "solution_step": {"step_id": "1", "nodes": [{"asset_id": "...", "order": 0}, ...]},
        }
    """

    image_nodes_by_ref = image_nodes_by_ref or {}
    questions = []
    for section in transcription.get("sections", []):
        for q in section.get("questions", []):
            content = q.get("content", {})
            stem_text = content.get("stem_latex") or ""
            ref = str(q.get("question_ref"))
            nodes_spec = image_nodes_by_ref.get(ref, {})

            # Build the stem: text node first, then the image nodes in order. A
            # real stem has the text before the figure; the ImageNode order is
            # its index among ImageNodes only (matching _expected_content_bindings).
            stem: list[dict] = [{"kind": "text", "text": stem_text or "(empty stem)"}]
            for node in nodes_spec.get("stem", []):
                stem.append({"kind": "image", "asset_id": node["asset_id"]})

            solution_steps = []
            sol_nodes = nodes_spec.get("solution_step")
            for i, s in enumerate(content.get("solution_steps", [])):
                step_id = str(i + 1)
                step_content: list[dict] = [{"kind": "text", "text": s}]
                if sol_nodes and sol_nodes.get("step_id") == step_id:
                    for node in sol_nodes.get("nodes", []):
                        step_content.append({"kind": "image", "asset_id": node["asset_id"]})
                solution_steps.append({"step_id": step_id, "content": step_content})

            questions.append({
                "question_ref": q.get("question_ref"),
                "question_number": q.get("question_number"),
                "question_type": q.get("question_type"),
                "points": q.get("points", 0),
                "content": {
                    "stem": stem,
                    "answer": content.get("answer", ""),
                    "clue": content.get("clue", ""),
                    "solution_steps": solution_steps,
                    **({"choices": content.get("choices", [])}
                       if q.get("question_type") == "choice" else {}),
                },
            })
    return questions


# --------------------------------------------------------------------------- #
# Authoritative v2 join: transcription + v1 image bundle + manifest (+ guard)
# --------------------------------------------------------------------------- #


def _build_authoritative_v2(
    transcription: dict, images: dict | None, manifest: dict | None
) -> tuple[dict, list[dict]]:
    """Build the authoritative v2 SourcePaper, joining all three sources.

    Returns ``(source_paper_dict, review_issues)``. Vector assets are classified
    by the :class:`VectorAssetGuard` using manifest evidence; the v1 image bundle
    supplies question_ref / role / order / crop / confidence.

    Assets classified ``ignored`` (OLE formula, tiny fragment) never produce an
    attribution and never reach the downstream materializer. Assets classified
    ``needs_review`` (vector without rendition) produce a review issue instead of
    an attribution. Ordinary raster assets and accepted vector assets (with a
    PNG rendition) become v2 ``SourceImageAsset`` records with attributions and a
    matching inline ``ImageNode`` so the review-gate content-image binding holds.
    """

    paper_id = _resolve_paper_id(transcription, manifest)

    if not images:
        return (
            {
                "schema": "math_exam_source_paper/v2",
                "paper_id": paper_id,
                "questions": _build_questions(transcription),
                "assets": [],
                "attributions": [],
            },
            [],
        )

    # Index manifest media by leaf for the join. The v1 asset source path ends in
    # the same leaf as the manifest media path (media/image72.wmf).
    media_by_leaf: dict[str, dict] = {}
    if manifest:
        for entry in manifest.get("media") or []:
            leaf = Path(str(entry.get("path") or "")).name
            if leaf:
                media_by_leaf[leaf] = entry

    guard = VectorAssetGuard()
    v1_assets_by_id = {a.get("asset_id"): a for a in images.get("assets", []) or []}
    referenced_asset_ids = {
        a.get("asset_id") for a in images.get("attributions", []) or []
    }

    # Classify each v1 asset. ignored -> dropped; needs_review -> issue;
    # accepted -> v2 SourceImageAsset.
    accepted_asset_ids: set[str] = set()
    assets: list[dict] = []
    review_issues: list[dict] = []
    for asset_id, v1_asset in v1_assets_by_id.items():
        source_path = str(v1_asset.get("source") or "")
        leaf = Path(source_path).name
        media_entry = media_by_leaf.get(leaf, {})
        ginput = guard_input_from_media_entry(media_entry) if media_entry else None
        if ginput is None:
            # No manifest evidence (e.g. PDF region crop): treat as ordinary
            # raster — accept as-is. Such assets already exist as PNG page
            # regions and never carry vector evidence.
            ginput = GuardInput(
                media_path=leaf,
                media_type=str(v1_asset.get("media_type") or "image/png"),
                width_px=int(v1_asset.get("width_px") or 0),
                height_px=int(v1_asset.get("height_px") or 0),
                emf_class=None,
                ole_binding_embedded=None,
                has_png_rendition=True,
            )
        decision = guard.classify(ginput)
        if decision.disposition == "ignored":
            continue
        if decision.disposition == "needs_review":
            review_issues.append({
                "issue_id": f"vector-rendition-missing-{asset_id}",
                "kind": "vector_rendition_missing",
                "detail": (
                    f"asset {asset_id} ({leaf}, {ginput.width_px}x{ginput.height_px}) "
                    f"is a non-OLE vector without a PNG rendition; cannot be cropped"
                ),
            })
            continue
        assets.append(_build_v2_asset(asset_id, v1_asset, ginput, decision))
        accepted_asset_ids.add(asset_id)

    # Build v2 attributions from accepted v1 attributions whose asset survived.
    # First resolve each attribution's v2 target. A prompt image and a solution
    # image which both resolve to question_stem (e.g. a fillin question with no
    # solution_steps) must land in ONE ordered sequence; so we collect every
    # accepted attribution, then group by content position (stem / solution_step)
    # and assign a single absolute order matching the inline ImageNode position.
    step1_by_ref: dict[str, str | None] = {}
    for section in transcription.get("sections", []):
        for q in section.get("questions", []):
            ref = str(q.get("question_ref"))
            steps = (q.get("content") or {}).get("solution_steps") or []
            step1_by_ref[ref] = "1" if steps else None

    # Collect accepted attributions with their resolved target + a stable sort
    # within each (question_ref, role) so order is deterministic.
    accepted_pairs: list[tuple[str, str, str, int, dict, dict]] = []
    # role rank: prompt (0) before solution (1) so prompt images lead when both
    # map to question_stem.
    role_rank = {"prompt": 0, "solution": 1}
    role_counter: dict[tuple[str, str], int] = {}
    for attr in images.get("attributions", []) or []:
        asset_id = attr.get("asset_id")
        if asset_id not in accepted_asset_ids:
            continue
        if attr.get("state") != "accepted":
            review_issues.append({
                "issue_id": f"attribution-needs-review-{attr.get('attribution_id', len(review_issues))}",
                "kind": "attribution_needs_review",
                "detail": (
                    f"attribution {attr.get('attribution_id', '?')} "
                    f"(asset {asset_id}, q{attr.get('question_ref', '?')}) "
                    f"is in needs_review state"
                ),
            })
            continue
        question_ref = str(attr.get("question_ref"))
        role = str(attr.get("role"))
        target = _role_to_target(role, question_ref, step1_by_ref)
        within = role_counter.get((question_ref, role), 0)
        role_counter[(question_ref, role)] = within + 1
        accepted_pairs.append(
            (question_ref, role, target["target"], within, attr, target)
        )

    # Group by (question_ref, content_position) and assign absolute order.
    # content_position: "stem" for question_stem, "step:<id>" for a solution step.
    from collections import defaultdict as _dd
    by_position: dict[tuple[str, str], list[tuple[str, str, int, dict, dict]]] = _dd(list)
    for question_ref, role, target_kind, within, attr, target in accepted_pairs:
        if target_kind == "question_stem":
            position = "stem"
        else:  # question_solution_step
            position = "step:" + str(target.get("step_id"))
        by_position[(question_ref, position)].append((role, target_kind, within, attr, target))

    attributions: list[dict] = []
    image_nodes_by_ref: dict[str, dict] = {}
    for (question_ref, position), items in sorted(by_position.items()):
        # Sort within a position: role rank first (prompt before solution),
        # then the original within-role order.
        items.sort(key=lambda it: (role_rank.get(it[0], 9), it[2]))
        target = items[0][4]  # shared target for this position
        target_kind = target["target"]
        nodes_bucket: list[dict] = []
        # _build_questions emits ONE text node before the image nodes (stem text
        # / step text), so the n-th image (0-based) sits at absolute node index
        # 1+n. The review gate's _expected_content_bindings computes order as the
        # absolute enumerate position over ALL nodes (text+image).
        for image_index, (_role, _tk, _within, attr, _t) in enumerate(items):
            asset_id = str(attr.get("asset_id"))
            order = 1 + image_index
            attributions.append({
                "attribution_id": str(attr.get("attribution_id") or f"attr-{asset_id}-{question_ref}-{position}-{image_index}"),
                "asset_id": asset_id,
                "question_ref": question_ref,
                "target": target,
                "crop": _project_crop(attr.get("crop")),
                "order": order,
                "confidence": str(attr.get("confidence") or "medium"),
                "state": "accepted",
            })
            nodes_bucket.append({"asset_id": asset_id, "order": order})
        qspec = image_nodes_by_ref.setdefault(question_ref, {})
        if position == "stem":
            qspec["stem"] = nodes_bucket
        else:
            step_id = position.split(":", 1)[1]
            qspec["solution_step"] = {"step_id": step_id, "nodes": nodes_bucket}

    questions = _build_questions(transcription, image_nodes_by_ref)

    # Surface unreferenced needs_review dispositions from the v1 bundle.
    for asset_id, v1_asset in v1_assets_by_id.items():
        if asset_id in referenced_asset_ids:
            continue
        if v1_asset.get("disposition") == "needs_review":
            review_issues.append({
                "issue_id": f"asset-needs-review-{asset_id}",
                "kind": "asset_needs_review",
                "detail": (
                    f"asset {asset_id} disposition=needs_review "
                    f"({v1_asset.get('disposition_reason', 'unreferenced')})"
                ),
            })

    source_paper = {
        "schema": "math_exam_source_paper/v2",
        "paper_id": paper_id,
        "questions": questions,
        "assets": assets,
        "attributions": attributions,
    }
    return source_paper, review_issues

    # Index manifest media by leaf for the join. The v1 asset source path ends in
    # the same leaf as the manifest media path (media/image72.wmf).
    media_by_leaf: dict[str, dict] = {}
    if manifest:
        for entry in manifest.get("media") or []:
            leaf = Path(str(entry.get("path") or "")).name
            if leaf:
                media_by_leaf[leaf] = entry

    guard = VectorAssetGuard()
    assets: list[dict] = []
    attributions: list[dict] = []
    review_issues: list[dict] = []

    if not images:
        return (
            {
                "schema": "math_exam_source_paper/v2",
                "paper_id": paper_id,
                "questions": questions,
                "assets": [],
                "attributions": [],
            },
            [],
        )

    # Classify each v1 asset via the guard (using manifest evidence), then keep
    # only accepted/needs_review assets for the v2 paper. ignored assets drop.
    v1_assets_by_id = {a.get("asset_id"): a for a in images.get("assets", []) or []}
    # Build the set of asset_ids that are referenced by at least one attribution;
    # unreferenced media are not part of any question's figure set.
    referenced_asset_ids = {
        a.get("asset_id") for a in images.get("attributions", []) or []
    }

    # asset_id -> guard decision, computed once. We also remember whether a PNG
    # rendition path was declared so the v2 asset can point at it.
    accepted_asset_ids: set[str] = set()
    for asset_id, v1_asset in v1_assets_by_id.items():
        source_path = str(v1_asset.get("source") or "")
        leaf = Path(source_path).name
        media_entry = media_by_leaf.get(leaf, {})
        # Construct the guard input from the manifest evidence (the v1 asset's
        # media_type may still lie if produced by an older extractor; the
        # manifest is authoritative for classification).
        ginput = guard_input_from_media_entry(media_entry) if media_entry else None
        if ginput is None:
            # No manifest evidence (e.g. PDF region crop): treat as an ordinary
            # raster asset — accept as-is. Such assets already exist as PNG page
            # regions and never carry vector evidence.
            ginput = GuardInput(
                media_path=leaf,
                media_type=str(v1_asset.get("media_type") or "image/png"),
                width_px=int(v1_asset.get("width_px") or 0),
                height_px=int(v1_asset.get("height_px") or 0),
                emf_class=None,
                ole_binding_embedded=None,
                has_png_rendition=True,
            )
        decision = guard.classify(ginput)

        if decision.disposition == "ignored":
            # OLE formula or tiny fragment: do not emit a v2 asset or attribution.
            continue
        if decision.disposition == "needs_review":
            review_issues.append({
                "issue_id": f"vector-rendition-missing-{asset_id}",
                "kind": "vector_rendition_missing",
                "detail": (
                    f"asset {asset_id} ({leaf}, {ginput.width_px}x{ginput.height_px}) "
                    f"is a non-OLE vector without a PNG rendition; cannot be cropped"
                ),
            })
            continue

        # accepted: build the v2 SourceImageAsset. Raster originals self-rendition;
        # vector assets use their declared PNG rendition (the guard accepted only
        # because has_png_rendition was True).
        assets.append(_build_v2_asset(asset_id, v1_asset, ginput, decision))
        accepted_asset_ids.add(asset_id)

    # Build v2 attributions from accepted v1 attributions whose asset survived
    # the guard. Map role -> target conservatively (see module docstring).
    order_counts: dict[tuple[str, str], int] = {}
    for attr in images.get("attributions", []) or []:
        asset_id = attr.get("asset_id")
        if asset_id not in accepted_asset_ids:
            continue
        if attr.get("state") not in ("accepted",):
            # needs_review attribution: surface as a review issue, not a v2 attr.
            review_issues.append({
                "issue_id": f"attribution-needs-review-{attr.get('attribution_id', len(review_issues))}",
                "kind": "attribution_needs_review",
                "detail": (
                    f"attribution {attr.get('attribution_id', '?')} "
                    f"(asset {asset_id}, q{attr.get('question_ref', '?')}) "
                    f"is in needs_review state"
                ),
            })
            continue
        question_ref = str(attr.get("question_ref"))
        role = str(attr.get("role"))
        target = _role_to_target(role, question_ref, step1_by_ref)
        order = order_counts.get((question_ref, role), 0)
        order_counts[(question_ref, role)] = order + 1
        attributions.append({
            "attribution_id": str(attr.get("attribution_id") or f"attr-{asset_id}-{question_ref}-{role}-{order}"),
            "asset_id": str(asset_id),
            "question_ref": question_ref,
            "target": target,
            "crop": _project_crop(attr.get("crop")),
            "order": order,
            "confidence": str(attr.get("confidence") or "medium"),
            "state": "accepted",
        })

    # Also surface unreferenced needs_review dispositions from the v1 bundle
    # (assets the extractor could not classify to any question).
    for asset_id, v1_asset in v1_assets_by_id.items():
        if asset_id in referenced_asset_ids:
            continue
        if v1_asset.get("disposition") == "needs_review":
            review_issues.append({
                "issue_id": f"asset-needs-review-{asset_id}",
                "kind": "asset_needs_review",
                "detail": (
                    f"asset {asset_id} disposition=needs_review "
                    f"({v1_asset.get('disposition_reason', 'unreferenced')})"
                ),
            })

    source_paper = {
        "schema": "math_exam_source_paper/v2",
        "paper_id": paper_id,
        "questions": questions,
        "assets": assets,
        "attributions": attributions,
    }
    return source_paper, review_issues


def _build_v2_asset(
    asset_id: str,
    v1_asset: dict,
    ginput: "GuardInput",
    decision: "GuardDecision",
) -> dict:
    """Build one v2 SourceImageAsset dict from the guard decision + v1 asset."""

    media_type = ginput.media_type
    is_vector = media_type.lower() in {
        "image/wmf", "image/emf", "image/x-wmf", "image/x-emf",
    } or Path(ginput.media_path).suffix.lower() in {".wmf", ".emf"}
    # ole_binding: required by the v2 contract for vector assets. Reconstruct it
    # from the guard input; for raster it stays None.
    ole_binding = None
    if is_vector:
        ole_binding = {"embedded": bool(ginput.ole_binding_embedded)}

    # rendition: raster originals self-rendition (the source IS the display
    # image). Vector assets accepted by the guard must have a declared PNG
    # rendition; we point at the same source path (the extractor is expected to
    # have produced the PNG alongside the WMF).
    source = str(v1_asset.get("source") or ginput.media_path)
    sha = str(v1_asset.get("sha256") or "sha256:" + "0" * 64)
    rendition = {
        "path": source,
        "sha256": sha,
        "media_type": "image/png",
        "width_px": int(v1_asset.get("width_px") or ginput.width_px),
        "height_px": int(v1_asset.get("height_px") or ginput.height_px),
    }
    return {
        "asset_id": str(asset_id),
        "original_path": ginput.media_path,
        "original_sha256": sha,
        "original_media_type": media_type,
        "emf_class": ginput.emf_class or "diagram",
        "ole_binding": ole_binding,
        "rendition": rendition,
    }


def _role_to_target(
    role: str, question_ref: str, step1_by_ref: dict[str, str | None]
) -> dict:
    """Map a v1 attribution role to a v2 target dict.

    Conservative (see module docstring): prompt -> question_stem; solution ->
    question_solution_step on the first step if one exists, else question_stem.
    The downstream projector inverts this (step targets -> role=solution).
    """

    if role == "solution":
        step_id = step1_by_ref.get(question_ref)
        if step_id is not None:
            return {"target": "question_solution_step", "step_id": step_id}
    return {"target": "question_stem"}


def _project_crop(crop: dict | None) -> dict:
    """Project a v1 crop spec ({kind: full} or {kind: region, box_px, ...})."""

    crop = crop or {}
    kind = crop.get("kind", "full")
    if kind == "full":
        return {"kind": "full"}
    return {
        "kind": "region",
        "box_px": list(crop.get("box_px", [])),
        "whiteout_px": [list(w) for w in crop.get("whiteout_px", [])],
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
