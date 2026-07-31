"""Atomic file-replacement helpers (architecture §3.1, M7).

Write to a sibling ``.tmp`` then ``os.replace`` onto the final path, so a reader never
observes a partial file. The text and YAML writers are the canonical implementations;
provider cache files and artifact commits share them.

Pure and domain-free: no artifact schema, no ingestion paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


__all__ = ["atomic_write_text", "atomic_write_yaml", "atomic_write_bytes"]


def _tmp_sibling(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".tmp")


def atomic_write_text(path: Path | str, text: str) -> None:
    """Atomically write UTF-8 ``text`` to ``path`` via a sibling ``.tmp`` + replace."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_sibling(target)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Atomically write raw ``data`` to ``path`` via a sibling ``.tmp`` + replace."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_sibling(target)
    tmp.write_bytes(data)
    os.replace(tmp, target)


def atomic_write_yaml(path: Path | str, value: Any) -> None:
    """Atomically dump ``value`` as YAML (stable, unicode, no sort)."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_sibling(target)
    with tmp.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(
            value,
            fp,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        )
    os.replace(tmp, target)
