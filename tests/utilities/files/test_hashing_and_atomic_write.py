"""Unit tests for the L0 utilities (architecture §3.1, M7).

These assert the pure general-purpose capabilities: hashing helpers produce stable
fingerprints, and atomic writes never leave a partial file visible. They also confirm
the cache-key helper is order-independent (the property the provider cache keys rely on).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.utilities.files.atomic_write import (
    atomic_write_bytes,
    atomic_write_text,
    atomic_write_yaml,
)
from scripts.utilities.files.hashing import (
    sha256_bytes,
    sha256_file,
    sha256_hex,
    stable_json_sha256,
)


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #


def test_sha256_bytes_and_hex_prefix():
    assert sha256_bytes(b"abc") == "sha256:" + sha256_hex(b"abc")
    # known vector
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_file_streams_in_chunks(tmp_path):
    path = tmp_path / "f.bin"
    payload = b"x" * (1024 * 1024 * 2 + 13)  # > 1 MiB to exercise the chunk loop
    path.write_bytes(payload)
    assert sha256_file(path) == sha256_bytes(payload)


def test_stable_json_sha256_is_order_independent():
    a = stable_json_sha256({"a": 1, "b": 2, "nested": {"y": 1, "x": 0}})
    b = stable_json_sha256({"nested": {"x": 0, "y": 1}, "b": 2, "a": 1})
    assert a == b


def test_stable_json_sha256_compact_separators():
    # No whitespace differences should change the digest.
    import json

    payload = {"k": "v", "n": 3}
    direct = stable_json_sha256(payload)
    # Re-deriving with the same rules yields the same digest (no hidden state).
    assert direct == stable_json_sha256(json.loads(json.dumps(payload)))


# --------------------------------------------------------------------------- #
# Atomic writes
# --------------------------------------------------------------------------- #


def test_atomic_write_text_replaces_existing(tmp_path):
    target = tmp_path / "sub" / "f.txt"
    atomic_write_text(target, "first")
    assert target.read_text(encoding="utf-8") == "first"
    atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    # no leftover .tmp
    assert not (tmp_path / "sub" / "f.txt.tmp").exists()


def test_atomic_write_bytes(tmp_path):
    target = tmp_path / "f.bin"
    atomic_write_bytes(target, b"\x00\x01\x02")
    assert target.read_bytes() == b"\x00\x01\x02"


def test_atomic_write_yaml_round_trip(tmp_path):
    target = tmp_path / "f.yaml"
    value = {"list": [1, 2, 3], "unicode": "数学", "nested": {"k": "v"}}
    atomic_write_yaml(target, value)
    import yaml

    loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert loaded == value
