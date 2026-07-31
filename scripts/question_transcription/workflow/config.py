"""Compatibility shim — config moved to :mod:`.bootstrap.config` (M6).

Re-exports the canonical symbols so existing imports keep working until M8.
"""

from __future__ import annotations

from .bootstrap.config import *  # noqa: F401,F403
from .bootstrap.config import __all__  # noqa: F401
