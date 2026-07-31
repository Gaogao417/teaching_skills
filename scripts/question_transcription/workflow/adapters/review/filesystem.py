"""Final-review reader wrapper (architecture §3.6 and §5.3).

Reads each item's ``review.yaml`` in the staging directory and projects the set into
a coarse :data:`FinalReviewStatus`:

- ``approved``  — every item has ``status == "approved"``;
- ``rejected``  — at least one item has ``status == "rejected"``;
- ``pending``   — otherwise (some items lack an approved review).

The reader only inspects files; it never approves anything. Resume only wakes the
graph; approval must already be on disk (design §16.8).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ...ports.review import FinalReviewStatus


__all__ = ["DeterministicFinalReviewReader"]


class DeterministicFinalReviewReader:
    """:class:`FinalReviewReader` backed by per-item ``review.yaml`` files."""

    def __init__(self, store) -> None:
        self.store = store

    def read_status(self, staging_directory):
        try:
            staging = Path(staging_directory)
            items_dir = staging / "items"
            statuses: list[tuple[str, str]] = []
            if items_dir.is_dir():
                for item_dir in sorted(items_dir.iterdir()):
                    if not item_dir.is_dir():
                        continue
                    review = item_dir / "review.yaml"
                    if not review.exists():
                        statuses.append((item_dir.name, "missing"))
                        continue
                    data = yaml.safe_load(review.read_text(encoding="utf-8")) or {}
                    statuses.append((item_dir.name, str(data.get("status", "missing"))))
            if not statuses:
                # No items yet: treat as pending so the graph interrupts rather than
                # silently completing (design §16.10).
                return "pending", None, None, []
            rejected = [name for name, s in statuses if s == "rejected"]
            if rejected:
                return "rejected", None, None, rejected
            pending = [name for name, s in statuses if s != "approved"]
            if pending:
                return "pending", None, None, pending
            return "approved", None, None, []
        except Exception as exc:
            return None, "validation_failed", f"{type(exc).__name__}: {exc}", None
