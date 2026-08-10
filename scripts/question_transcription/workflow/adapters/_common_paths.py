"""Repo-root resolution for adapters (architecture §3.6, M5 cleanup).

Adapters need the repo root to locate deterministic skill scripts under
``.codex/skills/<skill>/scripts``. This module provides :func:`repo_root` for that
path resolution.

Historically this module also inserted the repo root onto ``sys.path`` at import time
so ``import scripts.question_transcription.*`` worked regardless of how the process
started. That import-time side effect is no longer needed now that the workflow
package is imported as a normal package (the parent package import already places the
repo root on ``sys.path``). Callers that genuinely need the bootstrap can invoke
:func:`ensure_repo_root_on_path` explicitly; nothing does so by default.
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    """The repository root (parents[4] of this file)."""

    return Path(__file__).resolve().parents[4]


def ensure_repo_root_on_path() -> None:
    """Explicitly add the repo root to ``sys.path`` if absent.

    Only call this when a process imports an adapter WITHOUT first importing the
    ``scripts`` package (rare). Normal package imports and the test harness already
    place the repo root on ``sys.path``.
    """

    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
