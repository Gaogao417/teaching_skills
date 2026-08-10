"""Lifecycle state discriminators for the question-ingestion workflow (architecture §3.3).

These are the only values the review/outcome lifecycle may take. They are pure
discriminators — no behaviour, no provider/adapter coupling. ``state`` /
``extract_outcome`` consume them; the graph never invents new states.
"""

from __future__ import annotations

from typing import Literal


__all__ = ["ReviewStateKind", "WorkflowOutcomeKind"]


ReviewStateKind = Literal[
    "no_review_pending",
    "waiting_for_source_review",
    "source_review_resolved",
    "waiting_for_final_review",
    "all_questions_approved",
]
"""Discriminator for the source-review / final-review lifecycle (design §5.3)."""


WorkflowOutcomeKind = Literal[
    "running",
    "waiting_for_source_review",
    "waiting_for_final_review",
    "completed",
    "failed",
]
"""The only values ``status``/``resume`` may return (architecture §10)."""
