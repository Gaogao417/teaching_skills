"""Real-DOCX regression set for SourceQuestion v2 feature selection."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.scan_docx_source_features import (  # noqa: E402
    scan_docx,
)

FIXTURE = (
    ROOT
    / "tests/question_transcription/fixtures/docx-v2-canary-set.yaml"
)


def test_real_docx_canary_feature_profiles_are_stable():
    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema"] == "math_docx_v2_canary_set/v1"
    assert len(fixture["cases"]) == 5

    for case in fixture["cases"]:
        report = scan_docx(ROOT / case["source"])
        expected = case["expected"]
        for key in (
            "media_count",
            "ole_formula_preview_count",
            "vector_count",
            "unbound_vector_count",
        ):
            assert report[key] == expected[key], f"{case['id']}: {key}"
        if "unbound_vectors" in expected:
            assert report["unbound_vectors"] == expected["unbound_vectors"]
        if "attribution_count" in expected:
            assert report["attribution_error"] is None
            assert report["attribution_count"] == expected["attribution_count"]
        if "attribution_error_contains" in expected:
            assert expected["attribution_error_contains"] in (
                report["attribution_error"] or ""
            )
