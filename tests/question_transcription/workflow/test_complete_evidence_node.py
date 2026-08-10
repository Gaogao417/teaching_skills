from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.staging import existing_pipeline
from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
    DeterministicAssetMaterializer,
    DeterministicEvidenceCompleter,
    DeterministicStagingAuditor,
    DeterministicStagingExpander,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.contracts import ArtifactRef
from scripts.question_transcription.workflow.nodes.downstream import (
    make_complete_evidence_node,
)


def _page(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 96), "white").save(path)


def _draft(repo: Path) -> dict:
    pages = repo / "documents" / "PAPER-EVIDENCE" / "word" / "pages"
    for page in range(1, 6):
        _page(pages / f"{page:03d}.png")

    def evidence(page: int) -> list[dict]:
        return [
            {
                "page_image": str(pages / f"{page:03d}.png"),
                "page_number": page,
            }
        ]

    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {
            "id": "PAPER-EVIDENCE",
            "title": "Word evidence regression",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": str(repo / "documents" / "PAPER-EVIDENCE"),
        },
        "question_bank": "../../question-bank.yaml",
        "sections": [
            {
                "id": "choice",
                "title": "一、选择题",
                "items": [
                    {
                        "item_id": "Q001",
                        "question_number": 1,
                        "question_type": "choice",
                        "points": 3,
                        "question_word_evidence": evidence(1),
                        "prompt": [],
                        "official_solution": {
                            "start_anchor": "1.",
                            "end_anchor": "2.",
                            "word_evidence": evidence(2),
                            "crops": [],
                        },
                        "block": {
                            "stem_latex": "第一题",
                            "choices": ["甲", "乙", "丙", "丁"],
                            "answer": "A",
                            "clue": "逐项判断。",
                        },
                    },
                    {
                        "item_id": "Q002",
                        "question_number": 2,
                        "question_type": "choice",
                        "points": 3,
                        "question_word_evidence": evidence(3),
                        "prompt": [],
                        "official_solution": {
                            "start_anchor": "2.",
                            "end_anchor": "<END_OF_SOURCE>",
                            "word_evidence": evidence(4),
                            "crops": [],
                        },
                        "block": {
                            "stem_latex": "第二题",
                            "choices": ["甲", "乙", "丙", "丁"],
                            "answer": "B",
                            "clue": "逐项判断。",
                        },
                    },
                ],
            }
        ],
    }


def _store(tmp_path: Path) -> ArtifactStore:
    (tmp_path / ".codex").symlink_to(ROOT / ".codex", target_is_directory=True)
    (tmp_path / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    layout = RunLayout(tmp_path / "build", "PAPER-EVIDENCE", "run-regression")
    layout.ensure()
    return ArtifactStore(layout)


def test_complete_evidence_node_fills_last_page_and_real_audit_passes(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression for the 155 runs that stopped at Word coverage audit.

    This exercises the actual ``complete_evidence`` graph node, then the real
    expand/materialize/audit adapters.  A direct unit test of
    ``word_evidence_pages`` alone would not catch the missing workflow wiring.
    """

    monkeypatch.setattr(existing_pipeline, "repo_root", lambda: tmp_path)
    store = _store(tmp_path)
    draft_ref = store.commit_yaml(
        "structured/paper.draft.yaml",
        _draft(tmp_path),
        "math_exam_staging_draft/v1",
    )
    deps = type(
        "Deps",
        (),
        {
            "deterministic": type(
                "Ports",
                (),
                {"evidence_completer": DeterministicEvidenceCompleter(store)},
            )()
        },
    )()

    result = make_complete_evidence_node(deps)(
        {
            "draft": draft_ref.model_dump(mode="json"),
            "source_kind": "docx",
        }
    )

    assert "terminal_errors" not in result
    completed_ref = ArtifactRef.model_validate(result["draft"])
    completed = store.read_yaml(completed_ref)
    q2 = completed["sections"][0]["items"][1]
    assert [
        entry["page_number"]
        for entry in q2["official_solution"]["word_evidence"]
    ] == [4, 5]
    report = yaml.safe_load(
        (store.layout.reports_dir / "word-evidence-report.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert report["last_page"] == 5
    assert report["changes"]

    staging, failure, detail = DeterministicStagingExpander(store).expand(
        completed_ref
    )
    assert (failure, detail) == (None, None)
    _, failure, detail = DeterministicAssetMaterializer(store).materialize(staging)
    assert (failure, detail) == (None, None)
    _, failure, detail = DeterministicStagingAuditor(store).audit(
        staging, require_approved_review=False
    )
    assert (failure, detail) == (None, None)


def test_complete_evidence_node_reports_its_own_stage_on_invalid_seed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(existing_pipeline, "repo_root", lambda: tmp_path)
    store = _store(tmp_path)
    draft = _draft(tmp_path)
    draft["sections"][0]["items"][1]["official_solution"]["word_evidence"] = []
    draft_ref = store.commit_yaml(
        "structured/paper.draft.yaml",
        draft,
        "math_exam_staging_draft/v1",
    )
    deps = type(
        "Deps",
        (),
        {
            "deterministic": type(
                "Ports",
                (),
                {"evidence_completer": DeterministicEvidenceCompleter(store)},
            )()
        },
    )()

    result = make_complete_evidence_node(deps)(
        {
            "draft": draft_ref.model_dump(mode="json"),
            "source_kind": "doc",
        }
    )

    assert result["terminal_errors"][0].startswith(
        "complete_evidence: evidence_failed:"
    )
    assert "word_evidence.official_solution must not be empty" in result[
        "terminal_errors"
    ][0]


def _separated_layout_draft(repo: Path) -> dict:
    """A separated-layout draft whose trailing question seed is an outlier.

    Mirrors the real 2014-JINSHAN-ERMO failure: questions sit on pages 1-2,
    solutions start on page 4, but Q003's recorded ``question_word_evidence``
    first page is 8 (an answer-block page) instead of its real question page.
    That seed violates the separated-layout invariant and must be repaired
    before expansion, otherwise Q002 would silently balloon across pages 2-7.
    """
    pages = repo / "documents" / "PAPER-SEP" / "word" / "pages"
    for page in range(1, 9):
        _page(pages / f"{page:03d}.png")

    def evidence(page: int) -> list[dict]:
        return [{"page_image": str(pages / f"{page:03d}.png"), "page_number": page}]

    def item(item_id: str, q_page: int, s_page: int) -> dict:
        return {
            "item_id": item_id,
            "question_number": int(item_id[1:]),
            "question_type": "choice",
            "points": 3,
            "question_word_evidence": evidence(q_page),
            "prompt": [],
            "official_solution": {
                "start_anchor": f"{item_id}.",
                "end_anchor": "<END_OF_SOURCE>",
                "word_evidence": evidence(s_page),
                "crops": [],
            },
            "block": {
                "stem_latex": item_id,
                "choices": ["甲", "乙", "丙", "丁"],
                "answer": "A",
                "clue": "逐项判断。",
            },
        }

    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {
            "id": "PAPER-SEP",
            "title": "Separated layout outlier",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": str(repo / "documents" / "PAPER-SEP"),
        },
        "question_bank": "../../question-bank.yaml",
        "sections": [
            {
                "id": "choice",
                "title": "一、选择题",
                "items": [
                    item("Q001", 1, 4),
                    item("Q002", 2, 5),
                    # Q003's real question page is 2, but the transcriber recorded
                    # page 8 (its solution page) as the question evidence seed.
                    item("Q003", 8, 7),
                ],
            }
        ],
    }


def _evidence_pages(item: dict, role: str) -> list[int]:
    if role == "question":
        entries = item["question_word_evidence"]
    else:
        entries = item["official_solution"]["word_evidence"]
    return [entry["page_number"] for entry in entries]


def test_layout_override_seeds_repairs_outlier_question_seed(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression for the 16 'question page seeds must be ascending' runs.

    With a human-confirmed ``separated`` layout and ``layout_override_seeds``,
    the answer-block outlier (Q003->p8) is clamped back into the question
    region so expansion produces reasonable ranges and the real audit passes.
    """
    monkeypatch.setattr(existing_pipeline, "repo_root", lambda: tmp_path)
    store = _store(tmp_path)
    draft_ref = store.commit_yaml(
        "structured/paper.draft.yaml",
        _separated_layout_draft(tmp_path),
        "math_exam_staging_draft/v1",
    )
    completer = DeterministicEvidenceCompleter(store)

    completed_ref, failure, detail = completer.complete(
        draft_ref,
        "docx",
        layout="separated",
        layout_override_seeds=True,
    )

    assert (failure, detail) == (None, None)
    completed = store.read_yaml(completed_ref)
    # No single item may balloon across the solution region: each question's
    # evidence must stay within the question block (pages 1-3 here).
    for item_node in completed["sections"][0]["items"]:
        question_pages = _evidence_pages(item_node, "question")
        assert max(question_pages) <= 3, (
            f"{item_node['item_id']} question pages {question_pages} leaked "
            "into the solution region"
        )
    report = yaml.safe_load(
        (store.layout.reports_dir / "word-evidence-report.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert report["layout"] == "separated"
    assert report["seed_corrections"], "expected at least one seed correction"
    # The Q003 outlier (index 2, original page 8) must be recorded.
    q3 = next(c for c in report["seed_corrections"] if c["index"] == 2)
    assert q3["original"] == 8
    assert q3["coerced"] <= 3
    # The repaired draft must pass the real downstream audit.
    staging, failure, detail = DeterministicStagingExpander(store).expand(completed_ref)
    assert (failure, detail) == (None, None)
    _, failure, detail = DeterministicAssetMaterializer(store).materialize(staging)
    assert (failure, detail) == (None, None)
    _, failure, detail = DeterministicStagingAuditor(store).audit(
        staging, require_approved_review=False
    )
    assert (failure, detail) == (None, None)


def test_explicit_layout_without_override_still_blocks_on_outlier_seed(
    tmp_path: Path, monkeypatch
) -> None:
    """A bare ``--layout`` must not silently mask an answer-block seed.

    Without ``layout_override_seeds``, the separated-layout invariant violation
    (Q003->p8 reaching into the solution region) must surface as a
    ``complete_evidence`` terminal error rather than silently producing wrong
    ranges that pass the audit.
    """
    monkeypatch.setattr(existing_pipeline, "repo_root", lambda: tmp_path)
    store = _store(tmp_path)
    draft_ref = store.commit_yaml(
        "structured/paper.draft.yaml",
        _separated_layout_draft(tmp_path),
        "math_exam_staging_draft/v1",
    )
    completer = DeterministicEvidenceCompleter(store)

    completed_ref, failure, detail = completer.complete(
        draft_ref,
        "docx",
        layout="separated",
        layout_override_seeds=False,
    )

    assert completed_ref is None
    assert failure == "evidence_failed"
    assert "violate the confirmed layout" in detail
    assert "--layout-override-seeds" in detail


def test_interleaved_override_clamps_each_seed_independently() -> None:
    """An interleaved outlier must not chain across later items.

    Regression for a real corpus run (2018-YANGPU): item Q006's question seed
    (p12) sat in the answer block, but every later question seed was legitimate
    (p3..p7). The interleaved repair must clamp only the offending item to its
    own solution page, never propagate the outlier via a running maximum -- a
    chain reaction would have rewritten 16 valid seeds and dropped their
    evidence at the expand step.
    """
    import sys as _sys

    skill_scripts = str(
        ROOT / ".codex" / "skills" / "math-docx-question-bank-ingestion" / "scripts"
    )
    if skill_scripts not in _sys.path:
        _sys.path.insert(0, skill_scripts)
    from word_evidence_pages import coerce_question_seeds  # type: ignore

    # Five items: item 2 (index 1) has q=12 > s=4 -- an answer-block seed. The
    # others are clean (q[i] <= s[i]).
    question = [1, 12, 2, 3, 4]
    solution = [3, 4, 5, 6, 7]

    coerced, corrections = coerce_question_seeds(
        question, solution, layout="interleaved"
    )

    # Only the offending item is corrected, to its own solution page.
    assert corrections == [{"index": 1, "original": 12, "coerced": 4}]
    # The clean items are untouched -- no running-maximum chain reaction.
    assert coerced == [1, 4, 2, 3, 4]
