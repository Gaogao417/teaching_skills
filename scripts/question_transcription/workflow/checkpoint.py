"""Checkpointer factories (design §8.4).

- Local development / SQLite recovery tests: :func:`make_sqlite_checkpointer`.
- Automated unit tests: :func:`make_inmemory_checkpointer`.
- ``thread_id == run_id`` (design §8.4); the checkpoint never stores page-image
  bytes, PDF bytes, or API keys because ``WorkflowState`` only holds ``ArtifactRef``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver


__all__ = [
    "make_inmemory_checkpointer",
    "make_sqlite_checkpointer",
    "thread_id_for",
]


def make_inmemory_checkpointer() -> BaseCheckpointSaver:
    """Return a volatile ``MemorySaver`` for unit tests / fake graph runs."""

    return MemorySaver()


def make_sqlite_checkpointer(db_path: Path | str) -> BaseCheckpointSaver:
    """Return a persistent ``SqliteSaver`` keyed on ``db_path``.

    Creates parent directories. Use one SQLite DB per run (``<run-id>.sqlite``) so
    recovery is scoped; a shared DB is also fine since ``thread_id`` separates runs.
    """

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # SqliteSaver.from_conn_string is a @contextmanager (it yields the saver and owns
    # the sqlite connection lifetime). Returning it directly breaks callers that need
    # a ready instance (langgraph reads ``checkpointer.get_next_version`` eagerly at
    # stream time). Construct the saver from our own sqlite3 connection so the
    # returned object IS the saver; ``setup()`` initializes the schema idempotently.
    import sqlite3

    conn = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def thread_id_for(run_id: str) -> str:
    """The LangGraph ``thread_id`` is the run id (design §8.4)."""

    return run_id
