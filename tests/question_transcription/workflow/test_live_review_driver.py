from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXAM_SOURCE_SCRIPTS = (
    ROOT / ".codex/skills/math-topic-question-bank/scripts"
)
if str(EXAM_SOURCE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(EXAM_SOURCE_SCRIPTS))

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from exam_source_contracts import ExamItemReview
from scripts.question_transcription.workflow import run_live_paper
from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
    DeterministicCatalogNotifier,
)
from scripts.question_transcription.workflow.adapters.review.filesystem import (
    DeterministicFinalReviewReader,
)
from scripts.question_transcription.workflow.checkpoint import (
    make_sqlite_checkpointer,
    thread_id_for,
)
from scripts.question_transcription.workflow.bootstrap.composition import (
    build_run_layout,
)
from scripts.question_transcription.workflow.graph import build_graph
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.run_live_paper import (
    _RESUME_WAKE_ACK,
    _approve_final_review,
)


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


def test_catalog_notifier_exposes_run_staging_to_review_ui(tmp_path: Path) -> None:
    store = _store(tmp_path)
    staging = store.layout.structured_dir
    (staging / "paper.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_paper/v1",
                "paper": {"id": "p", "title": "Paper P"},
                "sections": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    notifier = DeterministicCatalogNotifier(store)
    result, failure, detail = notifier.refresh(str(staging))

    assert (result, failure, detail) == (None, None, None)
    catalog_root = store.layout.root / "review-catalog"
    alias = catalog_root / "langgraph" / "staging" / "p"
    assert alias.is_symlink()
    assert alias.resolve() == staging.resolve()
    assert (staging / ".catalog-version").is_file()
    assert list(catalog_root.glob("*/staging/*/paper.yaml")) == [
        alias / "paper.yaml"
    ]


def test_auto_approval_copies_source_identity_and_current_hash(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "PAPER-A"
    item_dir = staging / "items" / "Q001"
    item_dir.mkdir(parents=True)
    source = {
        "schema": "math_exam_item_source/v1",
        "item_id": "Q001",
        "source_key": "PAPER-A-Q01",
        "content_hash": f"sha256:{'1' * 64}",
    }
    (item_dir / "source.yaml").write_text(
        yaml.safe_dump(source, sort_keys=False), encoding="utf-8"
    )

    assert _approve_final_review(str(staging)) == 1

    review = yaml.safe_load((item_dir / "review.yaml").read_text(encoding="utf-8"))
    assert review["schema"] == "math_exam_item_review/v1"
    assert review["item_id"] == source["item_id"]
    assert review["source_key"] == source["source_key"]
    assert review["content_hash"] == source["content_hash"]
    assert review["status"] == "approved"
    assert review["reviewer"] == "live-verification-driver"
    assert review["reviewed_at"]
    assert review["notes"] == []
    ExamItemReview.model_validate(review)


def test_auto_approval_rebinds_stale_review_to_current_source_hash(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "PAPER-A"
    item_dir = staging / "items" / "Q001"
    item_dir.mkdir(parents=True)
    current_hash = f"sha256:{'2' * 64}"
    (item_dir / "source.yaml").write_text(
        yaml.safe_dump(
            {
                "item_id": "Q001",
                "source_key": "PAPER-A-Q01",
                "content_hash": current_hash,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (item_dir / "review.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_item_review/v1",
                "item_id": "Q001",
                "status": "pending",
                "content_hash": f"sha256:{'1' * 64}",
                "notes": ["keep this note"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    _approve_final_review(str(staging))

    review = yaml.safe_load((item_dir / "review.yaml").read_text(encoding="utf-8"))
    assert review["source_key"] == "PAPER-A-Q01"
    assert review["content_hash"] == current_hash
    assert review["notes"] == ["keep this note"]


def test_auto_approval_produces_zero_approved_audit_errors_for_all_items(
    tmp_path: Path,
) -> None:
    """Auto-mode (``--final-review-mode auto``) must write reviews that pass the
    approved-audit gate with zero errors across the three load-bearing categories:

    - ``source_key`` mismatch (review.source_key != source.source_key): 0
    - stale review (review.content_hash != source.content_hash): 0
    - ``ExamItemReview`` Pydantic validation: 0

    This is the offline regression for the approved-audit error counts; it does not
    impersonate a human reviewer — every review is stamped ``live-verification-driver``
    so the audit trail keeps auto and human approvals distinguishable.
    """

    staging = tmp_path / "staging" / "PAPER-MULTI"
    items = staging / "items"
    for n in range(1, 4):
        qid = f"Q00{n}"
        item_dir = items / qid
        item_dir.mkdir(parents=True)
        digest = f"sha256:{str(n) * 64}"
        (item_dir / "source.yaml").write_text(
            yaml.safe_dump(
                {
                    "item_id": qid,
                    "source_key": f"PAPER-MULTI-{qid}",
                    "content_hash": digest,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    assert _approve_final_review(str(staging)) == 3

    source_key_errors = stale_errors = validation_errors = 0
    for item_dir in sorted(items.iterdir()):
        review = yaml.safe_load((item_dir / "review.yaml").read_text(encoding="utf-8"))
        source = yaml.safe_load((item_dir / "source.yaml").read_text(encoding="utf-8"))
        # ExamItemReview validation (raises on any field/validator failure).
        model = ExamItemReview.model_validate(review)
        # Cross-field checks the approved audit performs (validate_exam_source).
        if model.item_id != source["item_id"]:
            source_key_errors += 1
        if model.source_key != source["source_key"]:
            source_key_errors += 1
        if model.content_hash != source["content_hash"]:
            stale_errors += 1
        # The auto driver must identify itself, never a human reviewer.
        assert model.reviewer == "live-verification-driver"

    assert (source_key_errors, stale_errors, validation_errors) == (0, 0, 0)


def test_cli_defaults_to_human_final_review(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "paper.docx"
    source.write_bytes(b"placeholder")
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return "run-test"

    monkeypatch.setattr(run_live_paper, "run", fake_run)

    assert (
        run_live_paper.main(
            [
                "--paper-id",
                "PAPER-A",
                "--source",
                str(source),
                "--source-kind",
                "docx",
            ]
        )
        == 0
    )
    assert captured["final_review_mode"] == "human"


def test_cli_resumes_existing_review_checkpoint_without_source(monkeypatch) -> None:
    captured = {}

    def fake_resume(**kwargs):
        captured.update(kwargs)
        return kwargs["run_id"]

    monkeypatch.setattr(run_live_paper, "resume", fake_resume)

    assert (
        run_live_paper.main(
            [
                "--paper-id",
                "PAPER-A",
                "--resume-run-id",
                "run-123",
            ]
        )
        == 0
    )
    assert captured == {
        "paper_id": "PAPER-A",
        "run_id": "run-123",
        "agent_host": "claude-code",
        "page_provider": "qwen",
    }


# --------------------------------------------------------------------------- #
# Review-UI interpreter selection
# --------------------------------------------------------------------------- #


def test_review_ui_command_uses_an_interpreter_that_imports_fastapi_and_uvicorn(
    tmp_path: Path,
) -> None:
    """The printed Review-UI command must launch under a fastapi-capable python.

    A worktree-local ``./.venv`` is provisioned for the workflow (langgraph, pydantic)
    but need not carry the Review UI's web stack, so the driver must probe candidates
    and select one that actually imports ``fastapi`` and ``uvicorn``.
    """

    layout = RunLayout(tmp_path / "build", "PAPER-A", "run-probe")
    layout.ensure()
    cmd = run_live_paper._review_ui_command(layout)
    python_bin = cmd.split()[0]
    proc = subprocess.run(
        [python_bin, "-c", "import fastapi, uvicorn"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, (
        f"Review-UI python cannot import fastapi/uvicorn: stderr={proc.stderr!r}"
    )
    # bank-root is the run-local catalog the notifier publishes.
    assert str(layout.root / "review-catalog") in cmd


# --------------------------------------------------------------------------- #
# Final-review gate: pending interrupts, only approved routes onward
# --------------------------------------------------------------------------- #


class _SimpleDeps:
    """Minimal deps exposing only ``deterministic.final_review_reader``."""

    def __init__(self, reader) -> None:
        self.reader = reader

    @property
    def deterministic(self):
        outer = self

        class _Det:
            final_review_reader = outer.reader

        return _Det()


def _write_item(staging: Path, item_id: str, *, source: bool = True, status: str | None = None) -> None:
    item = staging / "items" / item_id
    item.mkdir(parents=True, exist_ok=True)
    if source:
        (item / "source.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema": "math_exam_item_source/v1",
                    "item_id": item_id,
                    "source_key": f"PAPER-A-{item_id}",
                    "content_hash": f"sha256:{item_id[-1] * 64}",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    if status is not None:
        (item / "review.yaml").write_text(
            yaml.safe_dump(
                {"schema": "math_exam_item_review/v1", "item_id": item_id, "status": status},
                sort_keys=False,
            ),
            encoding="utf-8",
        )


def _final_review_graph(reader, *, checkpointer=None, route_to_done: bool = True):
    """Compile a graph whose only node is the real ``final_review_check``.

    When ``route_to_done`` is True, an approved check flows on to a terminal ``done``
    node so the run completes; when pending, the node interrupts and the run pauses.
    """

    from langgraph.graph import END, START, StateGraph
    from scripts.question_transcription.workflow.nodes.review import (
        make_final_review_check_node,
    )
    from scripts.question_transcription.workflow.orchestration.langgraph.state import (
        WorkflowState,
    )

    g = StateGraph(WorkflowState)
    g.add_node("final_review_check", make_final_review_check_node(_SimpleDeps(reader)))
    if route_to_done:

        def done(state):
            return {"review_state": state.get("review_state", "no_review_pending")}

        g.add_node("done", done)
        g.add_conditional_edges(
            "final_review_check",
            lambda s: "done" if s.get("review_state") == "all_questions_approved" else END,
            ["done", END],
        )
        g.add_edge("done", END)
    else:
        g.add_edge("final_review_check", END)
    g.add_edge(START, "final_review_check")
    return g.compile(checkpointer=checkpointer)


def test_final_review_check_node_interrupts_when_reviews_pending(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    _write_item(staging, "Q001", status="approved")
    _write_item(staging, "Q002", status="pending")  # not yet approved
    reader = DeterministicFinalReviewReader(_store(tmp_path))

    from langgraph.checkpoint.memory import MemorySaver

    app = _final_review_graph(reader, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}, "recursion_limit": 50}
    list(app.stream({"staging_directory": str(staging), "run_id": "run-x"}, config=cfg, stream_mode="updates"))
    state = app.get_state(cfg)
    # Pending: the node is paused mid-execution (next == final_review_check).
    assert state.next == ("final_review_check",)
    interrupts = state.tasks[0].interrupts
    payload = interrupts[0].value
    assert payload.get("kind") == "waiting_for_final_review"
    assert "Q002" in payload.get("pending", [])


def test_final_review_check_node_routes_approved_only_when_all_approved(
    tmp_path: Path,
) -> None:
    """Approved routing is decided by re-reading disk, never by the resume payload."""

    staging = tmp_path / "staging"
    _write_item(staging, "Q001", status="approved")
    _write_item(staging, "Q002", status="approved")
    reader = DeterministicFinalReviewReader(_store(tmp_path))

    from langgraph.checkpoint.memory import MemorySaver

    app = _final_review_graph(reader, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}, "recursion_limit": 50}
    list(app.stream({"staging_directory": str(staging), "run_id": "run-x"}, config=cfg, stream_mode="updates"))
    state = app.get_state(cfg)
    assert state.next == ()  # reached END
    assert state.values["review_state"] == "all_questions_approved"


# --------------------------------------------------------------------------- #
# Cross-process resume via Command(resume=...) against a persisted SqliteSaver
# --------------------------------------------------------------------------- #


class _ResumeState(dict):
    """TypedDict-ish dict used by the minimal interrupt graph below."""


def _build_minimal_interrupt_graph(checkpointer, *, is_pending):
    """A graph whose ``gate`` node mirrors the real ``final_review_check`` semantics.

    On every entry it consults ``is_pending`` (the "disk" read).  While pending it
    ``interrupt()``s; on resume the interrupt returns the wake ack (never an approval),
    so the node re-reads ``is_pending`` and either self-loops (still pending -> the next
    execution re-interrupts) or proceeds to ``done`` (approved).  This is exactly how the
    production node + ``route_after_final_review`` self-loop behave.
    """

    from typing import TypedDict

    class S(TypedDict, total=False):
        review_state: str
        log: list[str]

    def pre(state):
        return {"log": state.get("log", []) + ["pre"]}

    def gate_node(state):
        if is_pending():
            interrupt({"kind": "waiting_for_final_review"})
            # Resume reached: wake ack is not an approval — re-read and route.
            return {"review_state": "waiting_for_final_review" if is_pending() else "all_questions_approved"}
        return {"review_state": "all_questions_approved"}

    def done(state):
        return {"log": state.get("log", []) + ["approved", "done"]}

    def route(s):
        rs = s.get("review_state")
        if rs == "all_questions_approved":
            return "done"
        if rs == "waiting_for_final_review":
            return "gate"  # self-loop -> next execution re-interrupts
        return END

    g = StateGraph(S)
    g.add_node("pre", pre)
    g.add_node("gate", gate_node)
    g.add_node("done", done)
    g.add_edge(START, "pre")
    g.add_edge("pre", "gate")
    g.add_conditional_edges("gate", route, ["gate", "done", END])
    g.add_edge("done", END)
    return g.compile(checkpointer=checkpointer)


def test_resume_wakes_interrupt_only_after_disk_approval(tmp_path: Path) -> None:
    """Cross-process resume must (a) re-fire when still pending and (b) complete once
    the on-disk gate flips to approved.  Mirrors the driver's human-review flow."""

    approved = {"value": False}
    db_path = tmp_path / "resume.sqlite"
    is_pending = lambda: not approved["value"]  # noqa: E731

    # Process 1: build + run to the interrupt.
    saver1 = make_sqlite_checkpointer(db_path)
    thread_id = thread_id_for("run-crossproc")
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    app1 = _build_minimal_interrupt_graph(saver1, is_pending=is_pending)
    list(app1.stream({"log": []}, config=cfg, stream_mode="updates"))
    assert app1.get_state(cfg).next == ("gate",)

    # Confirm the OLD None-resume idiom does NOT advance past the interrupt: streaming
    # None re-fires the interrupt instead of resuming (langgraph 0.2.76 behavior).
    list(app1.stream(None, config=cfg, stream_mode="updates"))
    assert app1.get_state(cfg).next == ("gate",)

    # Process 2 (new connection to the same DB): a non-None Command resume wakes the
    # paused node; still-pending re-interrupts (the wake ack is never an approval).
    saver2 = make_sqlite_checkpointer(db_path)
    app2 = _build_minimal_interrupt_graph(saver2, is_pending=is_pending)
    list(app2.stream(Command(resume=_RESUME_WAKE_ACK), config=cfg, stream_mode="updates"))
    assert app2.get_state(cfg).next == ("gate",), "still pending must re-interrupt"

    # Approve on disk and resume again from a third process: now it completes.
    approved["value"] = True
    saver3 = make_sqlite_checkpointer(db_path)
    app3 = _build_minimal_interrupt_graph(saver3, is_pending=is_pending)
    list(app3.stream(Command(resume=_RESUME_WAKE_ACK), config=cfg, stream_mode="updates"))
    final = app3.get_state(cfg)
    assert final.next == ()
    assert final.values["review_state"] == "all_questions_approved"
    assert "done" in final.values.get("log", [])
    # The wake ack never appears as an approval decision in the log.
    assert _RESUME_WAKE_ACK not in final.values.get("log", [])


def test_command_resume_none_is_not_a_valid_resume(tmp_path: Path) -> None:
    """``Command(resume=None)`` is an empty input and must not resume an interrupt."""

    approved = {"value": False}
    db_path = tmp_path / "resume_none.sqlite"
    is_pending = lambda: not approved["value"]  # noqa: E731
    saver = make_sqlite_checkpointer(db_path)
    cfg = {"configurable": {"thread_id": thread_id_for("run-none")}, "recursion_limit": 50}
    app = _build_minimal_interrupt_graph(saver, is_pending=is_pending)
    list(app.stream({"log": []}, config=cfg, stream_mode="updates"))
    assert app.get_state(cfg).next == ("gate",)
    with pytest.raises(Exception):  # EmptyInputError in langgraph 0.2.76
        app.invoke(Command(resume=None), config=cfg)
    # Interrupt untouched.
    assert app.get_state(cfg).next == ("gate",)


def test_resume_run_id_loads_persisted_sqlite_checkpoint(tmp_path: Path, monkeypatch) -> None:
    """``resume`` rebuilds the graph against the persisted ``<run-id>.sqlite`` and
    wakes the interrupt with a non-decision Command; the resume value is the wake ack,
    not an approval."""

    run_id = "run-staged"
    layout = build_run_layout(tmp_path / "build", "PAPER-A", run_id)
    layout.ensure()
    db_path = layout.root / f"{run_id}.sqlite"
    # The driver resolves its build root via _repo_root()/build; redirect it to the
    # tmp build so resume() finds the staged checkpoint under tmp_path.
    monkeypatch.setattr(run_live_paper, "_build_root", lambda: tmp_path / "build")

    approved = {"value": False}

    def make_app(deps, *, checkpointer=None):
        return _build_minimal_interrupt_graph(checkpointer, is_pending=lambda: not approved["value"])

    # Stage the interrupt using the same builder the driver will reuse.
    saver0 = make_sqlite_checkpointer(db_path)
    cfg = {"configurable": {"thread_id": thread_id_for(run_id)}, "recursion_limit": 50}
    list(make_app(None, checkpointer=saver0).stream({"log": []}, config=cfg, stream_mode="updates"))
    assert make_app(None, checkpointer=saver0).get_state(cfg).next == ("gate",)

    captured: dict[str, Any] = {}

    real_make_saver = run_live_paper.make_sqlite_checkpointer

    def spy_make_saver(path):
        saver_obj = real_make_saver(path)
        captured.setdefault("db_paths", []).append(str(Path(path)))
        return saver_obj

    monkeypatch.setattr(run_live_paper, "make_sqlite_checkpointer", spy_make_saver)
    monkeypatch.setattr(run_live_paper, "bind", lambda config, layout, mode="live": object())
    monkeypatch.setattr(run_live_paper, "build_graph", make_app)

    persisted: list[dict] = []
    monkeypatch.setattr(
        run_live_paper,
        "_persist_state",
        lambda layout, state: persisted.append(dict(state)),
    )

    # Pending: resume re-interrupts (the wake ack is never an approval).
    run_live_paper.resume(paper_id="PAPER-A", run_id=run_id)
    assert str(db_path) in captured["db_paths"], "resume must reuse the persisted sqlite"

    # Approve on disk, then resume to completion.
    approved["value"] = True
    run_live_paper.resume(paper_id="PAPER-A", run_id=run_id)
    assert persisted, "resume must persist final state"
    assert persisted[-1]["log"][-1] == "done"
