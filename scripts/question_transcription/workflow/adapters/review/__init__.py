"""Final-review adapters (capability: review).

Canonical implementation lives in :mod:`.review.filesystem`. This package replaces
the old ``adapters/review.py`` module (M5 relocation); ``adapters.review`` still
resolves to the same public symbol so existing imports keep working.
"""

from __future__ import annotations

from .filesystem import DeterministicFinalReviewReader

__all__ = ["DeterministicFinalReviewReader"]
