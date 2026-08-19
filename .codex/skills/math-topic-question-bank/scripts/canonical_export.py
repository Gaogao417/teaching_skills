#!/usr/bin/env python3
"""Canonical authoring export & registry (Phase 2 P2-02/P2-05/P2-06/P2-07).

Bridges the reviewed staging pipeline and the cross-repo canonical contracts
(``ai_teaching_contracts``): the candidate exporter turns one audited staging
into canonical ``SourceEvidence`` + ``QuestionCandidate`` payloads (validated by
the vendored Pydantic adapter), and the registry writer promotes approved items
into immutable ``QuestionTruth`` versions under
``artifacts/canonical-authoring/``:

    artifacts/canonical-authoring/
      id-allocations.yaml        # per-source_key SEQ ledger (QC/SE/QT), never reused
      question-truth/QT-SMV-00N/{v1.json, v2.json, …, registry.yaml}
      source-evidence/SE-SMV-00N.json
      question-candidate/QC-SMV-00N.json   # archived at promotion time
      stale-events.yaml          # Question change → downstream stale ledger (P2-07)

Immutability rules implemented here (ADR-002/ADR-004):

- an Approved version file is written once; a later promotion of the same
  QuestionTruth writes ``v<N+1>`` and flips the previous version's status to
  ``Superseded`` (the only sanctioned rewrite — status/superseded_by metadata,
  never content);
- ``content_hash`` covers the CONTENT fields only (everything except
  ``content_hash``/``status``/``superseded_by``/``approval``), so a Draft→Approved
  transition or supersede does not re-hash content;
- every read of a version verifies its recorded ``content_hash`` (fail closed on
  drift, ADR-002 §3 triple ``(id, version, hash)``);
- the ``current`` pointer lives in ``registry.yaml`` (registry metadata, not
  artifact content — ADR-004 §3).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.ai_teaching_contracts import (  # noqa: E402
    validate_for_publication,
    validate_payload,
)

__all__ = [
    "CANONICAL_ROOT",
    "AllocationLedger",
    "CanonicalExportError",
    "build_candidate_export",
    "write_candidate_export",
    "promote_canonical",
    "current_truth",
    "truth_history",
    "read_truth_version",
]

CANONICAL_ROOT = _REPO_ROOT / "artifacts/canonical-authoring"

_QUESTION_TYPE_MAP = {
    "choice": "choice",
    "fillin": "fill_blank",
    "problem": "solution",
    "short_answer": "solution",
}
# content_hash covers the CONTENT fields only. ``version``/``artifact_uri``
# (registry identity — artifact_uri embeds the version), ``status``/
# ``superseded_by`` (lifecycle transitions) and ``approval`` (review metadata)
# are excluded, so a Draft→Approved promotion or a supersede never re-hashes
# content and an unchanged re-promotion stays idempotent (ADR-004 §3).
_HASH_EXCLUDED = {
    "content_hash",
    "status",
    "superseded_by",
    "approval",
    "version",
    "artifact_uri",
}
QT_NAMESPACE = "question-truth"
SE_NAMESPACE = "source-evidence"
QC_NAMESPACE = "question-candidate"
PAGE_IMAGE_NAMESPACE = "page-image"


class CanonicalExportError(Exception):
    """Canonical export/promotion failed (always fail closed)."""


_SUBQUESTION_MARKER = re.compile(r"[（(]([1-9])[）)]")


def split_subquestions(stem: str) -> list[dict[str, Any]]:
    """Derive structured subquestions from （1）（2）… stem markers.

    Display-grade derivation, same source of truth as the review UI's
    explanations panel: prompts stay verbatim, part ids are the marker digits.
    Fewer than two markers (or duplicate ids) → no structure. Per-subquestion
    answers/solutions are deliberately NOT split — per the target architecture
    (09 §data model) canonicalAnswer/reviewedSolution stay question-level and
    the per-part teaching decomposition belongs to Phase 3 TeachingSteps.
    """
    text = str(stem or "")
    matches = list(_SUBQUESTION_MARKER.finditer(text))
    if len(matches) < 2:
        return []
    parts: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        prompt = text[match.end():end].strip()
        if prompt:
            parts.append({"part_id": match.group(1), "prompt": prompt})
    ids = [part["part_id"] for part in parts]
    if len(ids) != len(set(ids)):
        return []
    return parts


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(payload: dict[str, Any]) -> str:
    content = {
        key: value
        for key, value in payload.items()
        if key not in _HASH_EXCLUDED
    }
    return "sha256:" + hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanonicalExportError(f"{path}: root must be a mapping")
    return value


def _write_yaml_atomic(path: Path, payload: dict[str, Any]) -> None:
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                payload, handle, allow_unicode=True, sort_keys=False, width=1000
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# ID allocation ledger (SEQ never reused — ADR-004 §1)
# --------------------------------------------------------------------------- #


class AllocationLedger:
    """Per-source_key canonical ID allocations for one paper's staging.

    The ledger is the durable bridge between staging identity (``source_key``)
    and canonical IDs. Golden questions are pre-seeded (QT-SMV-001..006 from the
    PRDS id-registry); every other question allocates the next free SEQ per
    type on first sight. Allocations persist in
    ``artifacts/canonical-authoring/id-allocations.yaml`` so re-exports and
    re-promotions reuse — never reassign — IDs.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = (
            _load_yaml(path) if path.is_file() else {"schema": "ai_teaching_id_allocations/v1", "allocations": {}}
        )
        if self.data.get("schema") != "ai_teaching_id_allocations/v1":
            raise CanonicalExportError(f"{path}: unexpected schema")
        self.allocations: dict[str, dict[str, Any]] = self.data.setdefault(
            "allocations", {}
        )
        if not isinstance(self.allocations, dict):
            raise CanonicalExportError(f"{path}: allocations must be a mapping")
        # Frozen golden QuestionTruth IDs (PRDS id-registry formalization):
        # the staging source_key -> canonical QT id binding is fixed here so a
        # golden question can never be re-numbered by allocation order.
        self.golden_qt_ids: dict[str, str] = dict(
            self.data.get("golden_qt_ids") or {}
        )

    def _max_seq(self, prefix: str) -> int:
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{3}})$")
        best = 0
        for entry in self.allocations.values():
            for key in ("qt_id", "qc_id"):
                match = pattern.match(str(entry.get(key) or ""))
                if match:
                    best = max(best, int(match.group(1)))
            for se_id in entry.get("se_ids") or []:
                match = pattern.match(str(se_id))
                if match:
                    best = max(best, int(match.group(1)))
        # Golden pins reserve their QT ids GLOBALLY (any pack's source key).
        # Without this, a fresh ledger hands a golden-reserved id to the first
        # non-golden question of whichever pack exports first (observed:
        # 2025-HUANGPU-YIMO-Q01 stole QT-SMV-001 pinned to a Minhang key).
        if prefix.startswith("QT-"):
            for value in self.golden_qt_ids.values():
                match = pattern.match(str(value))
                if match:
                    best = max(best, int(match.group(1)))
        return best

    def allocation_for(self, source_key: str) -> dict[str, Any]:
        return self.allocations.get(source_key)

    def _qt_id_owner(self, qt_id: str, *, excluding: str) -> str | None:
        for key, entry in self.allocations.items():
            if key != excluding and entry.get("qt_id") == qt_id:
                return key
        return None

    def allocate(
        self,
        source_key: str,
        *,
        scope: str = "SMV",
        golden_qt_id: str | None = None,
        evidence_count: int = 0,
    ) -> dict[str, Any]:
        """Return (creating if needed) the allocation for ``source_key``."""
        existing = self.allocations.get(source_key)
        if existing is not None:
            owner = self._qt_id_owner(existing.get("qt_id", ""), excluding=source_key)
            if owner is not None:
                raise CanonicalExportError(
                    f"id collision: {existing.get('qt_id')} allocated to both "
                    f"{source_key} and {owner}; rebuild the ledger"
                )
            return existing
        golden_qt_id = golden_qt_id or self.golden_qt_ids.get(source_key)
        qt_next = self._max_seq(f"QT-{scope}") + 1
        qc_next = self._max_seq(f"QC-{scope}") + 1
        se_next = self._max_seq(f"SE-{scope}") + 1
        if golden_qt_id is not None:
            qt_id = golden_qt_id
        else:
            qt_id = f"QT-{scope}-{qt_next:03d}"
        owner = self._qt_id_owner(qt_id, excluding=source_key)
        if owner is not None:
            raise CanonicalExportError(
                f"id collision: {qt_id} already allocated to {owner}, "
                f"cannot allocate for {source_key}"
            )
        qc_id = f"QC-{scope}-{qc_next:03d}"
        se_ids = [f"SE-{scope}-{se_next + i:03d}" for i in range(evidence_count)]
        entry = {
            "source_key": source_key,
            "qt_id": qt_id,
            "qc_id": qc_id,
            "se_ids": se_ids,
            "allocated_at": _now(),
        }
        self.allocations[source_key] = entry
        _write_yaml_atomic(self.path, self.data)
        return entry

    def save(self) -> None:
        _write_yaml_atomic(self.path, self.data)


# --------------------------------------------------------------------------- #
# Candidate export (P2-02)
# --------------------------------------------------------------------------- #


def _page_plan_for_staging(staging_dir: Path) -> dict[str, Any] | None:
    """Locate the ingestion run's page-plan for this staging (best effort).

    The review-catalog symlink layout links ``review-catalog/langgraph/staging/
    <paper_id>`` at the run root; page-plan.yaml sits in the run's ``source/``
    directory. Search the known run layout, then fall back to walking
    ``build/question-ingestion/<paper_id>/*/source/page-plan.yaml``.
    """
    paper_id = _load_yaml(staging_dir / "paper.yaml").get("paper", {}).get("id")
    if not paper_id:
        return None
    run_root = _REPO_ROOT / "build/question-ingestion" / str(paper_id)
    if run_root.is_dir():
        plans = list(run_root.glob("*/source/page-plan.yaml"))
        if plans:
            # Multiple runs of one paper may exist (retries); the staging under
            # review belongs to the most recent run, so pick by mtime — run-id
            # ordering is a random uuid, not chronological.
            latest = max(plans, key=lambda path: path.stat().st_mtime)
            return _load_yaml(latest)
    return None


def _pack_id_for(source_directory: str, pack_map: dict[str, str]) -> str:
    normalized = str(source_directory).rstrip("/")
    for directory, pack_id in pack_map.items():
        key = directory.rstrip("/")
        # Accept the pack directory itself, any suffix path ending at it, and
        # entry FILES inside it (docx runs record source.docx as the archive).
        if (
            normalized == key
            or normalized.endswith(f"/{key}")
            or normalized.endswith(f"/{key}/{Path(normalized).name}")
        ):
            return pack_id
    raise CanonicalExportError(
        f"no pack id mapping for source_directory {source_directory!r}; "
        "pass --pack-map entries for every source pack"
    )


def _artifact_subpath(origin: dict[str, Any], source_kind_hint: str) -> str:
    """Map one page-plan origin to its durable path under the pack directory."""
    archive = str(origin.get("origin_archive") or "")
    path = str(origin.get("origin_path") or "")
    if archive.endswith(".docx") or archive.endswith(".doc"):
        # exam docx renders live under word/; the supplementary official-answer
        # docx under word-answer/ (both pre-extracted into the pack directory).
        marker = Path(archive).parent
        sub = "word-answer" if "word-answer" in str(marker) or _is_answer_archive(archive) else "word"
        return f"{sub}/{path}"
    return path


def _is_answer_archive(archive: str) -> bool:
    return "答案" in Path(archive).stem or "answer" in Path(archive).stem.lower()


def _run_page_origins(page_plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(entry["page_number"]): entry
        for entry in page_plan.get("pages") or []
    }


def _evidence_units(
    item_source: dict[str, Any],
    pack_id: str,
    origins: dict[int, dict[str, Any]],
    pack_root: Path,
) -> list[dict[str, Any]]:
    """Build SourceEvidence payload units from one item's word_evidence spans.

    Each contiguous page span per role becomes one evidence unit; page numbers
    map back to the ORIGINAL archive/page via the run page plan so the
    ``artifact_uri`` always points at a durable original file.
    """
    units: list[dict[str, Any]] = []
    word_evidence = item_source.get("word_evidence") or {}
    for role, locator_role in (
        ("question", "question"),
        ("official_solution", "official_solution"),
    ):
        entries = word_evidence.get(role) or []
        for entry in entries:
            page_number = int(entry["page_number"])
            origin = origins.get(page_number)
            if origin is None:
                raise CanonicalExportError(
                    f"{item_source.get('item_id')}: word_evidence page "
                    f"{page_number} has no page-plan origin"
                )
            subpath = _artifact_subpath(origin, "")
            original_file = pack_root / subpath
            if not original_file.is_file():
                raise CanonicalExportError(
                    f"durable page image missing: {original_file} "
                    f"(origin {origin})"
                )
            digest = hashlib.sha256(original_file.read_bytes()).hexdigest()
            units.append(
                {
                    "role": locator_role,
                    "payload": {
                        "schema": "ai_teaching_source_evidence/v1",
                        "evidence_id": None,  # assigned by the ledger
                        "source_pack_id": pack_id,
                        "artifact_uri": (
                            f"artifact://{PAGE_IMAGE_NAMESPACE}/{pack_id}@v1/{subpath}"
                        ),
                        "content_hash": f"sha256:{digest}",
                        "locator": {
                            "kind": "page",
                            "page": int(origin.get("origin_page_number") or page_number),
                        },
                        "parser_provenance": None,  # filled by caller
                        "extracted_at": None,
                        "notes": (
                            f"role={locator_role}; run page {page_number}; "
                            f"origin={Path(str(origin.get('origin_archive'))).name}"
                        ),
                    },
                }
            )
    return units


def build_candidate_export(
    staging_dir: Path,
    *,
    parser_provenance: dict[str, Any],
    pack_map: dict[str, str],
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Build the canonical SourceEvidence + QuestionCandidate payloads.

    Returns ``{paper_id, items: [{source_key, se_payloads, qc_payload}]}``.
    Every payload is validated with the vendored ``ai_teaching_contracts``
    adapter before it is returned; a staging that cannot produce schema-valid
    canonical payloads fails closed.
    """
    staging_dir = Path(staging_dir).resolve()
    paper_payload = _load_yaml(staging_dir / "paper.yaml")
    paper = paper_payload.get("paper") or {}
    paper_id = str(paper.get("id"))
    source_directory = str(paper.get("source_archive") or "")
    pack_id = _pack_id_for(source_directory, pack_map)
    pack_root = (_REPO_ROOT / source_directory).resolve() if source_directory else _REPO_ROOT
    # The exam archive is the source.docx FILE for docx runs; the pack root is
    # its directory (word/, word-answer/ renderings live beside it).
    if pack_root.is_file():
        pack_root = pack_root.parent

    page_plan = _page_plan_for_staging(staging_dir) or {"pages": []}
    origins = _run_page_origins(page_plan)

    ledger = AllocationLedger(ledger_path or (CANONICAL_ROOT / "id-allocations.yaml"))
    items: list[dict[str, Any]] = []
    for item_dir in sorted((staging_dir / "items").iterdir()):
        if not item_dir.is_dir():
            continue
        item_source = _load_yaml(item_dir / "source.yaml")
        source_key = str(item_source.get("source_key"))
        teacher = _load_yaml(item_dir / "teacher.resolved.assignment.yaml")
        block = _practice_block(teacher)
        allocation = ledger.allocation_for(source_key) or ledger.allocate(
            source_key, evidence_count=0
        )

        units = _evidence_units(item_source, pack_id, origins, pack_root)
        # Evidence IDs allocate lazily on first need and are reused afterwards.
        needed = len(units)
        while len(allocation.get("se_ids") or []) < needed:
            next_seq = ledger._max_seq("SE-SMV") + 1
            allocation.setdefault("se_ids", []).append(f"SE-SMV-{next_seq:03d}")
        ledger.save()

        extracted_at = str(
            item_source.get("transcription", {}).get("reviewed_at") or _now()
        )
        se_payloads = []
        # Re-exports may produce fewer evidence units than a previous export
        # allocated (resolver ranges differ per run); bind the first N in role
        # order so evidence IDs stay stable across re-exports, and never
        # reassign the spares to other items (SEQ 永不复用).
        for unit, se_id in zip(units, allocation["se_ids"][:needed], strict=True):
            payload = dict(unit["payload"])
            payload["evidence_id"] = se_id
            payload["parser_provenance"] = parser_provenance
            payload["extracted_at"] = extracted_at
            ok, errors = validate_payload(payload)
            if not ok:
                raise CanonicalExportError(
                    f"{source_key}: source evidence {se_id} invalid: {errors}"
                )
            se_payloads.append(payload)

        stem = str(block.get("stem_latex") or block.get("stem") or "")
        answer = str(block.get("answer") or "")
        solution_steps = [
            _step_text(step) for step in (block.get("solution_steps") or [])
        ]
        question_type = _QUESTION_TYPE_MAP[str(item_source["question_type"])]
        review_path = item_dir / "review.yaml"
        review = _load_yaml(review_path) if review_path.is_file() else {}
        edited = (item_dir / "text-edits.yaml").is_file()
        qc_payload = {
            "schema": "ai_teaching_question_candidate/v1",
            "candidate_id": allocation["qc_id"],
            "source_evidence_refs": [
                {
                    "evidence_id": payload["evidence_id"],
                    "artifact_uri": (
                        f"artifact://{SE_NAMESPACE}/{payload['evidence_id']}"
                    ),
                }
                for payload in se_payloads
            ],
            "question_type": question_type,
            "stem": stem,
            **({"subquestions": split_subquestions(stem)}),
            "figure_refs": [],
            "review_state": {
                "status": "InReview",
                "note": "canonical export from audited staging; awaiting approval",
                "edited_by_reviewer": edited,
            },
            "extraction": {
                "extracted_at": extracted_at,
                "parser_provenance": parser_provenance,
            },
            "content_hash": "",
        }
        qc_payload["content_hash"] = _content_hash(qc_payload)
        ok, errors = validate_payload(qc_payload)
        if not ok:
            raise CanonicalExportError(
                f"{source_key}: question candidate invalid: {errors}"
            )
        items.append(
            {
                "source_key": source_key,
                "item_id": item_source.get("item_id"),
                "allocation": allocation,
                "se_payloads": se_payloads,
                "qc_payload": qc_payload,
                "_block": block,
                "_source": item_source,
                "_review": review,
                "_edited": edited,
            }
        )
    return {"paper_id": paper_id, "pack_id": pack_id, "items": items}


def write_candidate_export(
    staging_dir: Path,
    export: dict[str, Any],
) -> Path:
    """Persist the candidate export under ``staging/canonical/candidates.json``."""
    out_dir = Path(staging_dir).resolve() / "canonical"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ai_teaching_candidate_export/v1",
        "paper_id": export["paper_id"],
        "pack_id": export["pack_id"],
        "items": [
            {
                "source_key": item["source_key"],
                "source_evidence": item["se_payloads"],
                "question_candidate": item["qc_payload"],
            }
            for item in export["items"]
        ],
    }
    path = out_dir / "candidates.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# Registry promotion (P2-05) + stale events (P2-07)
# --------------------------------------------------------------------------- #


def _truth_registry_path(artifact_id: str) -> Path:
    return CANONICAL_ROOT / QT_NAMESPACE / artifact_id / "registry.yaml"


def _truth_version_path(artifact_id: str, version: str) -> Path:
    return CANONICAL_ROOT / QT_NAMESPACE / artifact_id / f"{version}.json"


def _build_truth_payload(
    item: dict[str, Any], *, version: str, superseded_by: dict | None = None
) -> dict[str, Any]:
    block = item["_block"]
    source = item["_source"]
    review = item["_review"]
    allocation = item["allocation"]
    staging_type = str(source["question_type"])
    answer = str(block.get("answer") or "")
    steps = [_step_text(step) for step in (block.get("solution_steps") or [])]
    if steps:
        reviewed_solution = "\n".join(steps)
    else:
        pages = sorted(
            {
                entry["page_number"]
                for entry in (source.get("word_evidence") or {}).get(
                    "official_solution", []
                )
            }
        )
        reviewed_solution = (
            f"参考答案：{answer}（官方解答页 {pages or '见证据'}，人工核对）"
        )
    if staging_type == "choice":
        canonical_answer = {"kind": "choice_option", "value": answer.strip().upper()}
    else:
        canonical_answer = {"kind": "expression", "value": answer}
        if "<" in answer or "≤" in answer or ">" in answer or "≥" in answer:
            canonical_answer["range_constraint"] = answer

    truth_stem = str(block.get("stem_latex") or block.get("stem") or "")
    payload: dict[str, Any] = {
        "schema": "ai_teaching_question_truth/v1",
        "artifact_id": allocation["qt_id"],
        "version": version,
        "status": "Approved",
        "question_type": _QUESTION_TYPE_MAP[staging_type],
        "stem": truth_stem,
        **(
            {"subquestions": subquestions}
            if (subquestions := split_subquestions(truth_stem))
            else {}
        ),
        "canonical_answer": canonical_answer,
        "reviewed_solution": reviewed_solution,
        "source_evidence_refs": item["qc_payload"]["source_evidence_refs"],
        "origin_candidate_id": allocation["qc_id"],
        "approval": {
            "reviewer_id": str(review.get("reviewer") or "unknown-reviewer"),
            "approved_at": str(review.get("reviewed_at") or _now()),
            "review_note": "; ".join(str(n) for n in review.get("notes") or []) or None,
            "edits_applied": bool(item["_edited"]),
        },
        "content_hash": "",
        "artifact_uri": f"artifact://{QT_NAMESPACE}/{allocation['qt_id']}@{version}",
    }
    if superseded_by is not None:
        payload["status"] = "Superseded"
        payload["superseded_by"] = superseded_by
    payload["content_hash"] = _content_hash(payload)
    return payload


def _validate_publication(payload: dict[str, Any]) -> None:
    ok, errors = validate_payload(payload)
    if not ok:
        raise CanonicalExportError(
            f"{payload.get('artifact_id')}: question truth schema invalid: {errors}"
        )
    publication_errors = validate_for_publication(payload)
    if publication_errors:
        raise CanonicalExportError(
            f"{payload.get('artifact_id')}: publication validation failed "
            f"(fail closed): {[str(e) for e in publication_errors]}"
        )


def _append_stale_event(artifact_id: str, from_version: str, to_version: str) -> None:
    """P2-07: Question change → Approach/Plan stale ledger (manifest/event).

    Phase 3/4 consumers read this ledger to refuse new publications bound to a
    superseded QuestionTruth version (ADR-002 §3); the event store integration
    itself is Phase 5.
    """
    path = CANONICAL_ROOT / "stale-events.yaml"
    data: dict[str, Any] = (
        _load_yaml(path) if path.is_file() else {"schema": "ai_teaching_stale_events/v1", "events": []}
    )
    events = data.setdefault("events", [])
    events.append(
        {
            "occurred_at": _now(),
            "kind": "question_change",
            "question": {
                "artifact_id": artifact_id,
                "from_version": from_version,
                "to_version": to_version,
            },
            "downstream": [
                {"type": "teaching-approach", "action": "stale"},
                {"type": "tutor-plan", "action": "stale"},
            ],
        }
    )
    _write_yaml_atomic(path, data)


def promote_canonical(export: dict[str, Any]) -> dict[str, Any]:
    """Write immutable QuestionTruth versions + SE artifacts for one export.

    Idempotent for unchanged content (same ``content_hash`` as the current
    Approved version → skipped); changed content promotes ``v<N+1>`` and
    supersedes the previous version. Publication validation is fail closed and
    happens BEFORE any file is written.
    """
    promoted, skipped, superseded = [], [], []
    for item in export["items"]:
        allocation = item["allocation"]
        artifact_id = allocation["qt_id"]
        registry_path = _truth_registry_path(artifact_id)
        registry = (
            _load_yaml(registry_path)
            if registry_path.is_file()
            else {"artifact_id": artifact_id, "current_version": None, "versions": []}
        )
        if registry.get("artifact_id") != artifact_id:
            raise CanonicalExportError(f"{registry_path}: artifact_id mismatch")

        current_version = registry.get("current_version")
        versions: list[dict[str, Any]] = list(registry.get("versions") or [])

        candidate_payload = _build_truth_payload(item, version="v_next")
        candidate_hash = candidate_payload["content_hash"]

        if current_version is not None:
            current_file = _truth_version_path(artifact_id, current_version)
            current_payload = json.loads(current_file.read_text(encoding="utf-8"))
            if current_payload.get("content_hash") == candidate_hash:
                skipped.append(artifact_id)
                _archive_candidate(item)
                continue
            next_version = f"v{int(current_version[1:]) + 1}"
            old_payload = dict(current_payload)
            old_payload["status"] = "Superseded"
            old_payload["superseded_by"] = {"artifact_id": artifact_id, "version": next_version}
        else:
            next_version = "v1"

        payload = _build_truth_payload(item, version=next_version)
        # Publication validation happens before ANY write (fail closed).
        _validate_publication(payload)

        for se_payload in item["se_payloads"]:
            ok, errors = validate_payload(se_payload)
            if not ok:
                raise CanonicalExportError(
                    f"{se_payload.get('evidence_id')}: source evidence invalid: {errors}"
                )
            _write_json_atomic(
                CANONICAL_ROOT / SE_NAMESPACE / f"{se_payload['evidence_id']}.json",
                se_payload,
            )
        _write_json_atomic(_truth_version_path(artifact_id, next_version), payload)
        _archive_candidate(item)
        if current_version is not None:
            _write_json_atomic(_truth_version_path(artifact_id, current_version), old_payload)
            versions = [
                dict(
                    entry,
                    status="Superseded",
                    superseded_by={"artifact_id": artifact_id, "version": next_version},
                )
                if entry["version"] == current_version
                else entry
                for entry in versions
            ]
            superseded.append(artifact_id)
            _append_stale_event(artifact_id, current_version, next_version)
        versions.append(
            {
                "version": next_version,
                "status": "Approved",
                "content_hash": payload["content_hash"],
                "approved_at": payload["approval"]["approved_at"],
            }
        )
        registry["current_version"] = next_version
        registry["versions"] = versions
        _write_yaml_atomic(registry_path, registry)
        promoted.append(artifact_id)
    return {"promoted": promoted, "skipped": skipped, "superseded": superseded}


def _archive_candidate(item: dict[str, Any]) -> None:
    _write_json_atomic(
        CANONICAL_ROOT / QC_NAMESPACE / f"{item['allocation']['qc_id']}.json",
        item["qc_payload"],
    )


# --------------------------------------------------------------------------- #
# Registry reads (P2-06)
# --------------------------------------------------------------------------- #


def read_truth_version(
    artifact_id: str, version: str, *, root: Path | None = None
) -> dict[str, Any]:
    """Read one QuestionTruth version, verifying its content_hash (fail closed)."""
    base = (root or CANONICAL_ROOT) / QT_NAMESPACE / artifact_id
    path = base / f"{version}.json"
    if not path.is_file():
        raise CanonicalExportError(f"unknown question truth version: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.get("content_hash")
    actual = _content_hash(payload)
    if expected != actual:
        raise CanonicalExportError(
            f"{artifact_id}@{version}: content_hash drift "
            f"(recorded {expected}, recomputed {actual}) — refusing to serve"
        )
    return payload


def truth_history(artifact_id: str, *, root: Path | None = None) -> dict[str, Any]:
    base = (root or CANONICAL_ROOT) / QT_NAMESPACE / artifact_id
    registry_path = base / "registry.yaml"
    if not registry_path.is_file():
        raise CanonicalExportError(f"unknown question truth: {artifact_id}")
    registry = _load_yaml(registry_path)
    # Every listed version must still verify; a corrupted history fails closed.
    for entry in registry.get("versions") or []:
        read_truth_version(artifact_id, entry["version"], root=root)
    return registry


def current_truth(artifact_id: str, *, root: Path | None = None) -> dict[str, Any]:
    registry = truth_history(artifact_id, root=root)
    current = registry.get("current_version")
    if not current:
        raise CanonicalExportError(f"{artifact_id}: no current version")
    return read_truth_version(artifact_id, current, root=root)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _practice_block(assignment: dict[str, Any]) -> dict[str, Any]:
    for section in assignment.get("sections") or []:
        if section.get("type") != "practice":
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict):
                return block
    raise CanonicalExportError("assignment contains no practice block")


def _step_text(step: Any) -> str:
    if isinstance(step, dict):
        return str(step.get("text") or step.get("latex") or "")
    return str(step or "")


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="canonical-export",
        description="Export canonical candidates from staging / promote / inspect registry",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser("export", help="write staging/canonical/candidates.json")
    export_parser.add_argument("staging", type=Path)
    export_parser.add_argument("--pack-map", type=Path, required=True)

    promote_parser = sub.add_parser(
        "promote", help="promote staging into immutable QuestionTruth versions"
    )
    promote_parser.add_argument("staging", type=Path)
    promote_parser.add_argument("--pack-map", type=Path, required=True)

    status_parser = sub.add_parser("status", help="read current QuestionTruth version")
    status_parser.add_argument("artifact_id")

    for sub_parser in (export_parser, promote_parser):
        sub_parser.add_argument(
            "--parser-id", default="math-topic-question-bank/ingestion"
        )
        sub_parser.add_argument(
            "--parser-version",
            default="langgraph-question-ingestion/v0+whole-paper-v2",
        )
        sub_parser.add_argument(
            "--harness", default="langgraph+claude-code-glm-5.2+qwen3.5-ocr"
        )

    args = parser.parse_args(argv)

    def provenance() -> dict[str, Any]:
        return {
            "parser_id": args.parser_id,
            "parser_version": args.parser_version,
            "harness": args.harness,
        }

    try:
        if args.command == "export":
            pack_map = yaml.safe_load(args.pack_map.read_text(encoding="utf-8"))
            export = build_candidate_export(
                args.staging,
                parser_provenance=provenance(),
                pack_map=pack_map,
            )
            path = write_candidate_export(args.staging, export)
            print(
                f"CANDIDATES EXPORTED: {path} | items={len(export['items'])} "
                f"| pack={export['pack_id']}"
            )
            return 0
        if args.command == "promote":
            pack_map = yaml.safe_load(args.pack_map.read_text(encoding="utf-8"))
            export = build_candidate_export(
                args.staging,
                parser_provenance=provenance(),
                pack_map=pack_map,
            )
            result = promote_canonical(export)
            print(
                "CANONICAL PROMOTED: "
                + ",".join(result["promoted"])
                + f" | skipped={result['skipped']} superseded={result['superseded']}"
            )
            return 0
        if args.command == "status":
            payload = current_truth(args.artifact_id)
            print(
                f"{payload['artifact_id']}@{payload['version']} status={payload['status']} "
                f"hash={payload['content_hash'][:19]}…"
            )
            registry = truth_history(args.artifact_id)
            for entry in registry.get("versions") or []:
                print(
                    f"  {entry['version']}: {entry['status']} "
                    f"({entry['approved_at']})"
                )
            return 0
    except CanonicalExportError as exc:
        raise SystemExit(str(exc)) from exc
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
