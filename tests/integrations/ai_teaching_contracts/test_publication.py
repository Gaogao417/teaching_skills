"""退出门禁 3：未批准对象、含绝对本地路径的对象无法通过 publication 校验（fail closed）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ai_teaching_contracts.publication import (  # noqa: E402
    validate_for_publication,
)

FIXTURES_DIR = ROOT / "integrations" / "ai_teaching_contracts" / "fixtures"
MANIFEST = json.loads((FIXTURES_DIR / "fixtures-manifest.json").read_text(encoding="utf-8"))


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_publicable_fixtures_pass():
    for entry in MANIFEST["fixtures"]:
        if entry["expect_publication"] == "valid":
            errors = validate_for_publication(_load(entry["file"]))
            assert errors == [], (entry["file"], [str(e) for e in errors])


def test_unapproved_object_is_rejected():
    payload = _load("question-truth.pubfail.draft-status.json")
    errors = validate_for_publication(payload)
    codes = {e.code for e in errors}
    assert "not_approved" in codes


def test_absolute_local_path_is_rejected():
    for name in (
        "question-truth.pubfail.absolute-path.json",
        "teaching-approach.pubfail.absolute-path.json",
    ):
        payload = _load(name)
        errors = validate_for_publication(payload)
        codes = {e.code for e in errors}
        assert "absolute_local_path" in codes, name


def test_every_publishable_status_gate():
    truth = _load("question-truth.positive.json")
    for status in ("Draft", "InReview", "Stale", "Disabled", "Superseded"):
        mutated = dict(truth, status=status)
        assert any(e.code == "not_approved" for e in validate_for_publication(mutated)), status


def test_file_scheme_and_windows_paths_rejected():
    truth = _load("question-truth.positive.json")
    for bad in (
        "file:///Users/gaochong/audio.wav",
        "C:\\Users\\gaochong\\audio.wav",
        "录音见 /var/tmp/rec.wav",
    ):
        mutated = json.loads(json.dumps(truth))
        mutated["approval"]["review_note"] = f"备注 {bad}"
        assert any(
            e.code == "absolute_local_path" for e in validate_for_publication(mutated)
        ), bad


def test_non_publishable_types_are_rejected_outright():
    for name in ("tutor-session-event.positive.json", "skill-hypothesis.positive.json"):
        errors = validate_for_publication(_load(name))
        assert errors and errors[0].code == "not_publishable_type", name


def test_garbage_inputs_fail_closed():
    assert validate_for_publication(None)[0].code == "not_a_canonical_object"
    assert validate_for_publication({})[0].code == "not_publishable_type"
