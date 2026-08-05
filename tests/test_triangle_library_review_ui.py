from __future__ import annotations

import sys
from pathlib import Path

import yaml
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
DATA = ROOT / ".codex/skills/math-topic-question-bank/data"
sys.path.insert(0, str(SCRIPTS))

from question_bank_review_server import create_question_bank_app  # noqa: E402
from training_number_review_server import create_app  # noqa: E402
from triangle_candidate_review_adapter import BANK_ID  # noqa: E402


def test_material_review_ui_exposes_three_layers_and_persists_toggles(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            review_path=tmp_path / "numbers.yaml",
            history_path=tmp_path / "history.sqlite3",
            trig_review_path=tmp_path / "trig.yaml",
            triangle_review_path=tmp_path / "triangles.yaml",
        )
    )
    trig = client.get("/api/trig-ratios").json()
    triangles = client.get("/api/triangles").json()
    assert trig["total_count"] == 41
    assert triangles["total_count"] == 745

    trig_id = trig["entries"][0]["id"]
    result = client.put(f"/api/trig-ratios/{trig_id}", json={"disabled": True})
    assert result.status_code == 200
    review = yaml.safe_load((tmp_path / "trig.yaml").read_text(encoding="utf-8"))
    assert review["schema"] == "math_triangle_trig_ratio_review/v1"
    assert review["disabled_entry_ids"] == [trig_id]


def test_generated_candidates_use_existing_question_bank_review_ui(tmp_path: Path) -> None:
    review_path = tmp_path / "question-review.yaml"
    client = TestClient(
        create_question_bank_app(
            bank_root=tmp_path / "banks",
            triangle_candidates_path=DATA / "triangle-cosine-question-candidates.yaml",
            triangle_question_review_path=review_path,
        )
    )
    bootstrap = client.get("/api/bootstrap").json()
    assert any(bank["id"] == BANK_ID for bank in bootstrap["banks"])
    directory = client.get(f"/api/banks/{BANK_ID}?directory=1").json()
    assert directory["kind"] == "staging_exam"
    assert directory["item_count"] == 500

    item_id = directory["items"][0]["id"]
    item = client.get(f"/api/banks/{BANK_ID}/items/{item_id}").json()
    assert item["solution_steps"] == []
    assert item["answer"]
    decision = client.post(
        f"/api/banks/{BANK_ID}/items/{item_id}/review",
        json={"decision": "approved", "note": ""},
    )
    assert decision.status_code == 200
    persisted = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    assert persisted["entries"][0]["question_id"] == item_id
    assert persisted["entries"][0]["decision"] == "approved"
