"""sys.path bootstrap for adapters that import sibling ``scripts.question_transcription``
clients (BailianOcrClient / MimoClient / source_contracts …).

The workflow package lives at ``<repo-root>/scripts/question_transcription/workflow``.
Importing ``scripts.question_transcription.*`` requires ``<repo-root>`` on sys.path.
Tests bootstrap this themselves; adapters do it here so live binding works regardless
of how the process was started (CLI / direct import).
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


_ROOT = repo_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
