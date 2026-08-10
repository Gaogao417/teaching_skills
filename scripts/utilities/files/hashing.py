"""Content-addressed SHA-256 helpers (architecture §3.1, M7).

Pure, domain-free hashing. The canonical ``sha256:<hex>`` fingerprint form is shared
by the artifact store, the source extractor and the provider cache-key computations.
These helpers know nothing about artifacts, ingestion, or any business schema.

Multiple stable callers triggered the extraction (architecture §3.1 M7 threshold):
the workflow artifact store, the source-extraction adapter, and the whole-paper /
page-text cache-key computations.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


__all__ = ["sha256_bytes", "sha256_file", "sha256_hex", "stable_json_sha256"]


def sha256_hex(data: bytes) -> str:
    """Return the bare hex digest of ``data`` (no ``sha256:`` prefix)."""

    return hashlib.sha256(data).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the ``sha256:<hex>`` fingerprint of ``data``."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    """Stream-hash a file in 1 MiB chunks, returning ``sha256:<hex>``."""

    h = hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def stable_json_sha256(payload) -> str:
    """Hash a JSON-serialisable ``payload`` with sorted keys / compact separators.

    Used for content-addressed cache keys where the key must be deterministic across
    dict insertion order. Returns the bare hex digest (cache keys are opaque ids, not
    artifact fingerprints, so no ``sha256:`` prefix).
    """

    import json

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
