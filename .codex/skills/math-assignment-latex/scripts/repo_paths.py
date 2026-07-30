"""Repository path discovery for scripts bundled inside this skill."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Return the repository root without depending on the skill nesting depth."""
    cursor = (start or Path(__file__)).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for candidate in (cursor, *cursor.parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError(f"repository root not found above {cursor}")
