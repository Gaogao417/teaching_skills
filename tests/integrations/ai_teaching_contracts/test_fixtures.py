"""P1-06 / 退出门禁 1：Python 侧对全部 canonical fixture 的正反例校验。

期望结果表来自 fixtures-manifest.json（PRD 仓 contracts/fixtures 的
vendored 副本）。TypeScript 侧（teaching-tools）用同一批文件与同一张表
断言，两侧布尔结果一致即门禁通过。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ai_teaching_contracts.validation import validate_payload  # noqa: E402

FIXTURES_DIR = ROOT / "integrations" / "ai_teaching_contracts" / "fixtures"
MANIFEST = json.loads((FIXTURES_DIR / "fixtures-manifest.json").read_text(encoding="utf-8"))


def test_manifest_fixture_count_matches_directory():
    files = {p.name for p in FIXTURES_DIR.glob("*.json")} - {"fixtures-manifest.json"}
    registered = {entry["file"] for entry in MANIFEST["fixtures"]}
    assert files == registered, f"fixture drift: {files ^ registered}"


def test_vendored_fixtures_match_manifest_hashes():
    for entry in MANIFEST["fixtures"]:
        digest = hashlib.sha256((FIXTURES_DIR / entry["file"]).read_bytes()).hexdigest()
        assert digest == entry["sha256"][len("sha256:") :], f"sha256 drift: {entry['file']}"


def test_every_schema_has_positive_and_negative():
    by_schema: dict[str, set[str]] = {}
    for entry in MANIFEST["fixtures"]:
        by_schema.setdefault(entry["object_schema"], set()).add(entry["expect_schema"])
    # fixture 覆盖必须与 validation 分派表一一对应（新 schema 常量即新正反例义务）。
    from integrations.ai_teaching_contracts.validation import _SCHEMA_CONST_TO_MODEL

    assert set(by_schema) == set(_SCHEMA_CONST_TO_MODEL), by_schema.keys() ^ _SCHEMA_CONST_TO_MODEL.keys()
    for schema_const, outcomes in by_schema.items():
        assert "valid" in outcomes, f"{schema_const}: no positive fixture"
        assert "invalid" in outcomes, f"{schema_const}: no negative fixture"


def test_python_validates_all_fixtures_per_manifest():
    mismatches = []
    for entry in MANIFEST["fixtures"]:
        payload = json.loads((FIXTURES_DIR / entry["file"]).read_text(encoding="utf-8"))
        ok, errors = validate_payload(payload)
        expected = entry["expect_schema"] == "valid"
        assert isinstance(ok, bool)
        if ok != expected:
            mismatches.append((entry["file"], ok, expected, errors[:2]))
    assert not mismatches, mismatches


def test_error_messages_are_nonempty_for_invalid():
    for entry in MANIFEST["fixtures"]:
        if entry["expect_schema"] != "invalid":
            continue
        payload = json.loads((FIXTURES_DIR / entry["file"]).read_text(encoding="utf-8"))
        ok, errors = validate_payload(payload)
        assert not ok
        assert errors, entry["file"]
        assert all(isinstance(e, str) and e for e in errors), entry["file"]
