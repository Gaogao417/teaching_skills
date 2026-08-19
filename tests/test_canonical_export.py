"""Phase 2 canonical export/registry tests (P2-02/P2-05/P2-06/P2-07).

Covers the full staging→candidate→immutable-QuestionTruth lifecycle against the
vendored ``ai_teaching_contracts`` adapter: schema validity, fail-closed
publication, idempotent re-promotion, supersede-on-change with the stale-event
ledger, and hash-verified registry reads.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".codex/skills/math-topic-question-bank/scripts"))

import canonical_export as ce  # noqa: E402

PACK_DIR_NAME = "TEST-PACK"
PACK_ID = "pack-test-similarity"
PARSER = {
    "parser_id": "test-parser",
    "parser_version": "v1",
    "harness": "test-harness",
}


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def canonical_env(tmp_path: Path, monkeypatch):
    """Redirect the module's repo/canonical roots at a temp tree."""
    repo_root = tmp_path / "repo"
    (repo_root / "documents" / PACK_DIR_NAME / "word" / "pages").mkdir(parents=True)
    for page in range(1, 4):
        (repo_root / "documents" / PACK_DIR_NAME / "word" / "pages" / f"{page:03d}.png").write_bytes(
            f"page-{page}".encode()
        )
    monkeypatch.setattr(ce, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(ce, "CANONICAL_ROOT", repo_root / "artifacts/canonical-authoring")
    return repo_root


def _make_staging(
    repo_root: Path,
    *,
    paper_id: str = "TEST-PAPER",
    stem: str = "如图，求 $BE$ 的长。",
    answer: str = "$1$",
) -> Path:
    staging = repo_root / "staging" / paper_id
    item = staging / "items" / "Q001"
    if item.exists():
        import shutil

        shutil.rmtree(item)
    item.mkdir(parents=True)
    (staging / "paper.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_paper/v1",
                "paper": {
                    "id": paper_id,
                    "title": "测试卷",
                    "grade": "初三",
                    "source_archive": f"documents/{PACK_DIR_NAME}",
                },
                "question_bank": "../../question-bank.yaml",
                "sections": [{"id": "fillin", "title": "填空", "item_ids": ["Q001"]}],
            }
        ),
        encoding="utf-8",
    )
    page_image = f"documents/{PACK_DIR_NAME}/word/pages/002.png"
    (item / "source.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_item_source/v1",
                "item_id": "Q001",
                "source_key": f"{paper_id}-Q01",
                "paper_id": paper_id,
                "question_number": 1,
                "question_type": "fillin",
                "content_hash": "sha256:" + "0" * 64,
                "word_evidence": {
                    "question": [{"page_image": page_image, "page_number": 1}],
                    "official_solution": [{"page_image": page_image, "page_number": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    (item / "teacher.resolved.assignment.yaml").write_text(
        yaml.safe_dump(
            {
                "sections": [
                    {
                        "type": "practice",
                        "blocks": [
                            {
                                "id": "Q001",
                                "type": "fillin",
                                "stem_latex": stem,
                                "answer": answer,
                                "clue": "折叠",
                                "solution_steps": [],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (item / "review.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_item_review/v1",
                "item_id": "Q001",
                "content_hash": "sha256:" + "0" * 64,
                "status": "approved",
                "reviewer": "教研-测试",
                "reviewed_at": "2026-08-19T10:00:00+00:00",
                "notes": [],
            }
        ),
        encoding="utf-8",
    )
    # Ingestion run page-plan: run page 1 -> pack word/pages/002.png.
    run_dir = (
        repo_root
        / "build/question-ingestion"
        / paper_id
        / "run-test"
        / "source"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "page-plan.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_page_plan/v1",
                "paper_id": paper_id,
                "sources": [],
                "pages": [
                    {
                        "page_number": 1,
                        "run_path": "source/pages/002.png",
                        "origin_archive": f"documents/{PACK_DIR_NAME}/source.docx",
                        "origin_path": "pages/002.png",
                        "origin_page_number": 2,
                    }
                ],
                "non_question_pages": [],
            }
        ),
        encoding="utf-8",
    )
    return staging


def _pack_map() -> dict[str, str]:
    return {PACK_DIR_NAME: PACK_ID}


def _export(staging: Path):
    return ce.build_candidate_export(
        staging, parser_provenance=PARSER, pack_map=_pack_map()
    )


def test_candidate_export_validates_against_contracts(canonical_env: Path) -> None:
    staging = _make_staging(canonical_env)
    export = _export(staging)
    assert len(export["items"]) == 1
    item = export["items"][0]
    # SE payload points at the durable original page with its real hash.
    se = item["se_payloads"][0]
    assert se["source_pack_id"] == PACK_ID
    assert se["artifact_uri"] == (
        f"artifact://page-image/{PACK_ID}@v1/word/pages/002.png"
    )
    assert se["content_hash"] == _sha256_file(
        canonical_env / "documents" / PACK_DIR_NAME / "word" / "pages" / "002.png"
    )
    assert se["locator"] == {"kind": "page", "page": 2}
    # QC references the SE and carries the parser provenance.
    qc = item["qc_payload"]
    assert qc["source_evidence_refs"][0]["evidence_id"] == se["evidence_id"]
    assert qc["question_type"] == "fill_blank"
    assert qc["review_state"]["status"] == "InReview"
    assert qc["extraction"]["parser_provenance"] == PARSER


def test_first_promotion_writes_immutable_v1(canonical_env: Path) -> None:
    staging = _make_staging(canonical_env)
    export = _export(staging)
    result = ce.promote_canonical(export)
    assert result == {"promoted": [export["items"][0]["allocation"]["qt_id"]], "skipped": [], "superseded": []}

    qt_id = export["items"][0]["allocation"]["qt_id"]
    payload = ce.read_truth_version(qt_id, "v1")
    assert payload["status"] == "Approved"
    assert payload["version"] == "v1"
    assert payload["artifact_uri"] == f"artifact://question-truth/{qt_id}@v1"
    assert payload["canonical_answer"] == {"kind": "expression", "value": "$1$"}
    assert payload["reviewed_solution"].startswith("参考答案：")
    assert payload["approval"]["reviewer_id"] == "教研-测试"
    current = ce.current_truth(qt_id)
    assert current["version"] == "v1"
    registry = ce.truth_history(qt_id)
    assert registry["current_version"] == "v1"
    # SE artifact file exists on disk.
    se_id = export["items"][0]["se_payloads"][0]["evidence_id"]
    assert (
        canonical_env / "artifacts/canonical-authoring/source-evidence" / f"{se_id}.json"
    ).is_file()


def test_re_promotion_same_content_is_idempotent(canonical_env: Path) -> None:
    staging = _make_staging(canonical_env)
    export = _export(staging)
    ce.promote_canonical(export)
    result = ce.promote_canonical(_export(staging))
    qt_id = export["items"][0]["allocation"]["qt_id"]
    assert result == {"promoted": [], "skipped": [qt_id], "superseded": []}
    assert ce.current_truth(qt_id)["version"] == "v1"


def test_changed_content_supersedes_and_records_stale_event(
    canonical_env: Path,
) -> None:
    staging = _make_staging(canonical_env)
    export = _export(staging)
    qt_id = export["items"][0]["allocation"]["qt_id"]
    ce.promote_canonical(export)

    # Human edits the answer, review re-approves → export again.
    _make_staging(canonical_env, answer="$2$")
    second = ce.promote_canonical(_export(staging))
    assert second["superseded"] == [qt_id]

    v1 = ce.read_truth_version(qt_id, "v1")
    assert v1["status"] == "Superseded"
    assert v1["superseded_by"] == {"artifact_id": qt_id, "version": "v2"}
    # Supersede is a metadata transition only: content hash unchanged.
    original_hash = export["items"][0]["qc_payload"]["content_hash"]
    assert v1["content_hash"] != original_hash  # different objects by design
    v2 = ce.current_truth(qt_id)
    assert v2["version"] == "v2"
    assert v2["canonical_answer"]["value"] == "$2$"

    stale = ce._load_yaml(
        canonical_env / "artifacts/canonical-authoring/stale-events.yaml"
    )
    assert stale["events"][0]["question"] == {
        "artifact_id": qt_id,
        "from_version": "v1",
        "to_version": "v2",
    }
    downstream = {entry["type"] for entry in stale["events"][0]["downstream"]}
    assert downstream == {"teaching-approach", "tutor-plan"}


def test_registry_read_fails_closed_on_hash_drift(
    canonical_env: Path, tmp_path: Path
) -> None:
    staging = _make_staging(canonical_env)
    export = _export(staging)
    ce.promote_canonical(export)
    qt_id = export["items"][0]["allocation"]["qt_id"]
    version_file = (
        canonical_env
        / "artifacts/canonical-authoring/question-truth"
        / qt_id
        / "v1.json"
    )
    payload = json.loads(version_file.read_text(encoding="utf-8"))
    payload["stem"] = "tampered stem"
    version_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ce.CanonicalExportError, match="content_hash drift"):
        ce.read_truth_version(qt_id, "v1")
    with pytest.raises(ce.CanonicalExportError, match="content_hash drift"):
        ce.current_truth(qt_id)


def test_unmapped_pack_fails_closed(canonical_env: Path) -> None:
    staging = _make_staging(canonical_env)
    with pytest.raises(ce.CanonicalExportError, match="no pack id mapping"):
        ce.build_candidate_export(
            staging, parser_provenance=PARSER, pack_map={"other-dir": "pack-other"}
        )


def test_golden_allocation_is_respected(canonical_env: Path) -> None:
    staging = _make_staging(canonical_env)
    ledger_path = canonical_env / "artifacts/canonical-authoring/id-allocations.yaml"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        yaml.safe_dump(
            {
                "schema": "ai_teaching_id_allocations/v1",
                "allocations": {
                    "TEST-PAPER-Q01": {
                        "source_key": "TEST-PAPER-Q01",
                        "qt_id": "QT-SMV-001",
                        "qc_id": "QC-SMV-001",
                        "se_ids": ["SE-SMV-001", "SE-SMV-002"],
                        "allocated_at": "2026-08-18T00:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    export = ce.build_candidate_export(
        staging,
        parser_provenance=PARSER,
        pack_map=_pack_map(),
        ledger_path=ledger_path,
    )
    allocation = export["items"][0]["allocation"]
    assert allocation["qt_id"] == "QT-SMV-001"
    # Two evidence units (question + official_solution) reuse the seeded SE ids.
    assert [se["evidence_id"] for se in export["items"][0]["se_payloads"]] == [
        "SE-SMV-001",
        "SE-SMV-002",
    ]
    result = ce.promote_canonical(export)
    assert result["promoted"] == ["QT-SMV-001"]


def test_split_subquestions_derives_structure_from_markers() -> None:
    stem = (
        "已知：如图，在 Rt△ABC 中．（1）求证：∠DAB=∠DCF；（2）当点 E 在边 CD 上时，"
        "求 y 关于 x 的函数关系式；（3）试求 AD 的长."
    )
    parts = ce.split_subquestions(stem)
    assert [p["part_id"] for p in parts] == ["1", "2", "3"]
    assert parts[0]["prompt"].startswith("求证：")
    assert parts[2]["prompt"].startswith("试求")
    # 单标记 / 无标记 / 重复编号 → 不产出结构
    assert ce.split_subquestions("（1）只有一小问") == []
    assert ce.split_subquestions("纯文字题干") == []
    assert ce.split_subquestions("（1）A（1）B") == []


def test_publication_prevalidation_placeholder_is_schema_legal(
    canonical_env: Path,
) -> None:
    """promote_exam_paper 的干跑预校验对每个 item 构造占位 version 的 payload
    走 _validate_publication；占位必须满足 schema 的 ^v[0-9]+$ 模式（回归：
    曾用 "v_prevalidate"，干跑恒失败，晋升永远进不去）。真实版本从 v1 起，
    "v0" 不会被写成任何 registry 文件。"""
    staging = _make_staging(canonical_env)
    export = _export(staging)
    assert export["items"]
    for item in export["items"]:
        ce._validate_publication(ce._build_truth_payload(item, version="v0"))


def test_candidate_and_truth_carry_subquestions(canonical_env: Path) -> None:
    staging = _make_staging(
        canonical_env,
        stem="如图，在 △ABC 中．（1）求证：CE⊥AB；（2）求 AF·DE=AG·B．",
    )
    export = _export(staging)
    qc = export["items"][0]["qc_payload"]
    assert [p["part_id"] for p in qc["subquestions"]] == ["1", "2"]
    ce.promote_canonical(export)
    qt_id = export["items"][0]["allocation"]["qt_id"]
    truth = ce.current_truth(qt_id)
    assert [p["part_id"] for p in truth["subquestions"]] == ["1", "2"]
    assert truth["subquestions"][1]["prompt"].startswith("求")
    # 小问级答案/解答字段不存在（架构上归属 Phase 3 TeachingStep）。
    assert all(set(p) == {"part_id", "prompt"} for p in truth["subquestions"])
