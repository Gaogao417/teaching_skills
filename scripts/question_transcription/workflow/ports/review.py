"""Final review port (architecture §5.3).

Reads the per-question review state from the staging directory and decides whether
to interrupt for final review, stop for rejected items, or run the approved audit.

``RunApprovedAudit`` must call ``audit_staging.py --require-approved-review``; only
its success gates ``End`` (design §16.10). Resume only wakes the graph — it does
not equal approval (design §16.8).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..ports.staging import StageFailure


__all__ = ["FinalReviewStatus", "FinalReviewReader"]


FinalReviewStatus = Literal["approved", "rejected", "pending"]
"""
Coarse projection of the per-question review state:

- ``approved``  -> all questions approved -> run approved audit -> End
- ``rejected``  -> at least one rejected -> Failed (design §11)
- ``pending``   -> still waiting -> interrupt for final review
"""


@runtime_checkable
class FinalReviewReader(Protocol):
    """Read the final-review status from the staging directory."""

    def read_status(
        self, staging_directory: str
    ) -> "tuple[FinalReviewStatus | None, StageFailure | None, str | None, list[str] | None]":
        """Returns ``(status, None, None, item_ids)`` on success.

        ``item_ids`` carries pending ids (for ``pending``) or rejected ids (for
        ``rejected``); empty/unused for ``approved``.
        """
