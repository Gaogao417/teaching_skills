"""Tests for the frozen v1 contracts (P0).

These validate that the contract types load the golden fixtures, reject the
error classes the architecture promises (duplicate refs, unknown asset,
missing solution_steps, bad crop box, etc.), and that JSON Schema dumps.
They are provider-agnostic: Track 1/2/3 all rely on these.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    AssemblyReport,
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)
from scripts.question_transcription import schema_dump  # noqa: E402

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Golden fixtures load
# --------------------------------------------------------------------------- #


def test_yangpu_transcription_bundle_loads():
    bundle = QuestionTranscriptionBundle.model_validate(_load(FIX / "yangpu-q18.transcription.yaml"))
    assert bundle.paper.id == "2025-YANGPU-ERMO"
    assert bundle.refs() == ["18"]
    q = bundle.sections[0].questions[0]
    assert q.question_type == "short_answer"
    # The six steps are preserved verbatim (§12 test 5/8 at contract level).
    assert len(q.content.solution_steps) == 6
    assert q.content.solution_steps[0].startswith("取$AC$的中点$F$")
    assert q.content.solution_steps[-1] == "所以$4\\leqslant BE\\leqslant 6$。"


def test_yangpu_attribution_bundle_loads():
    bundle = ImageAttributionBundle.model_validate(_load(FIX / "yangpu-q18.attribution.yaml"))
    assert bundle.paper_id == "2025-YANGPU-ERMO"
    accepted = [a for a in bundle.attributions if a.state == "accepted"]
    assert len(accepted) == 2
    ignored = [a for a in bundle.assets if a.disposition == "ignored"]
    assert len(ignored) == 1


def test_pdf_region_transcription_bundle_loads():
    bundle = QuestionTranscriptionBundle.model_validate(
        _load(FIX / "pdf-region-q24.transcription.yaml")
    )
    q = bundle.sections[0].questions[0]
    assert q.question_type == "problem"
    assert q.evidence.question[0].kind == "region"
    assert q.evidence.question[0].box_px == [80, 210, 1010, 860]


def test_pdf_region_attribution_bundle_loads():
    bundle = ImageAttributionBundle.model_validate(
        _load(FIX / "pdf-region-q24.attribution.yaml")
    )
    states = {a.state for a in bundle.attributions}
    assert states == {"accepted", "needs_review"}
    # needs_review asset is allowed to have an attribution (it has one).
    unresolved = [a for a in bundle.assets if a.disposition == "needs_review"]
    assert len(unresolved) == 1


# --------------------------------------------------------------------------- #
# Contract rejections
# --------------------------------------------------------------------------- #


def _base_transcription() -> dict:
    return {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": "X",
            "title": "t",
            "grade": "九年级",
            "source_archive": "documents/x",
        },
        "sections": [
            {
                "section_ref": "fillin",
                "title": "二、填空题",
                "questions": [
                    {
                        "question_ref": "18",
                        "question_number": 18,
                        "question_type": "short_answer",
                        "points": 4,
                        "content": {
                            "stem_latex": "$x$",
                            "answer": "$1$",
                            "clue": "c",
                            "solution_steps": ["step1"],
                        },
                        "evidence": {
                            "question": [{"kind": "page", "source": "p1", "page_number": 1}],
                            "solution": [{"kind": "page", "source": "p2", "page_number": 2}],
                            "solution_start_anchor": "a",
                            "solution_end_anchor": "b",
                        },
                    }
                ],
            }
        ],
        "provider": {"kind": "agent", "name": "codex", "version": "v1"},
    }


def test_duplicate_question_ref_rejected():
    payload = _base_transcription()
    # add a second section referencing the same question_ref "18"
    payload["sections"][0]["questions"].append(
        {**payload["sections"][0]["questions"][0], "question_ref": "18", "question_number": 19}
    )
    with pytest.raises(Exception):
        QuestionTranscriptionBundle.model_validate(payload)


def test_choice_requires_four_choices_and_letter_answer():
    payload = _base_transcription()
    q = payload["sections"][0]["questions"][0]
    q["question_type"] = "choice"
    q["content"]["choices"] = ["$1$", "$2$"]  # too few
    q["content"]["answer"] = "B"
    with pytest.raises(Exception):
        QuestionTranscriptionBundle.model_validate(payload)
    # four choices but bad answer still fails
    payload2 = _base_transcription()
    q2 = payload2["sections"][0]["questions"][0]
    q2["question_type"] = "choice"
    q2["content"]["choices"] = ["$1$", "$2$", "$3$", "$4$"]
    q2["content"]["answer"] = "E"
    with pytest.raises(Exception):
        QuestionTranscriptionBundle.model_validate(payload2)


def test_problem_requires_solution_steps():
    payload = _base_transcription()
    q = payload["sections"][0]["questions"][0]
    q["question_type"] = "problem"
    q["content"]["solution_steps"] = []
    with pytest.raises(Exception):
        QuestionTranscriptionBundle.model_validate(payload)


def test_region_crop_bad_box_rejected():
    payload = _load(FIX / "pdf-region-q24.attribution.yaml")
    payload["attributions"][0]["crop"]["box_px"] = [100, 100, 50, 200]  # left >= right
    with pytest.raises(Exception):
        ImageAttributionBundle.model_validate(payload)


def test_attribution_unknown_asset_rejected():
    payload = _load(FIX / "yangpu-q18.attribution.yaml")
    payload["attributions"][0]["asset_id"] = "does-not-exist"
    with pytest.raises(Exception):
        ImageAttributionBundle.model_validate(payload)


def test_attributed_asset_without_attribution_rejected():
    payload = _load(FIX / "yangpu-q18.attribution.yaml")
    # remove both attributions; the attributed assets now have none.
    payload["attributions"] = []
    with pytest.raises(Exception):
        ImageAttributionBundle.model_validate(payload)


def test_extra_key_rejected():
    payload = _load(FIX / "yangpu-q18.transcription.yaml")
    payload["paper"]["unexpected"] = "x"
    with pytest.raises(Exception):
        QuestionTranscriptionBundle.model_validate(payload)


# --------------------------------------------------------------------------- #
# JSON Schema dump
# --------------------------------------------------------------------------- #


def test_json_schema_dump_writes_three_contracts(tmp_path):
    written = schema_dump.dump_all(tmp_path)
    assert set(written) == {"question_transcription", "image_attribution", "draft_assembly_report"}
    names = {p.name for p in tmp_path.iterdir()}
    for expected in (
        "question_transcription.schema.json",
        "image_attribution.schema.yaml",
        "draft_assembly_report.schema.json",
    ):
        assert expected in names
    # report schema has the v1 discriminator
    report = yaml.safe_load((tmp_path / "draft_assembly_report.schema.yaml").read_text("utf-8"))
    assert "math_draft_assembly_report/v1" in str(report)


def test_assembly_report_roundtrip():
    report = AssemblyReport(
        schema="math_draft_assembly_report/v1",
        paper_id="X",
        question_count=1,
        accepted_attributions=1,
        consumed_attributions=1,
        ignored_assets=0,
        unresolved_assets=0,
    )
    dumped = report.model_dump(by_alias=True, exclude_none=True)
    assert dumped["schema"] == "math_draft_assembly_report/v1"
