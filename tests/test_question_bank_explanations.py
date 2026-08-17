"""小题讲解/解答（explanations sidecar）的 API 行为与 UI 静态断言。

覆盖：小题派生、讲解-解答对 CRUD、录音上传+转写、润色、一键补齐、批准后
导出 teaching-tools blueprint candidate batch、以及前端面板的静态接线。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".codex" / "skills" / "math-topic-question-bank"
SCRIPTS = PACKAGE / "scripts"
sys.path.insert(0, str(SCRIPTS))

import explanations_ai  # noqa: E402
from explanations_ai import AiAssistError  # noqa: E402
from question_bank_review_server import create_question_bank_app  # noqa: E402


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def assignment(item_id: str, *, teacher: bool, stem: str) -> dict:
    block: dict = {"type": "problem", "id": item_id, "stem_latex": stem}
    if teacher:
        block.update(
            {
                "answer": "（1）见解答；（2）$CE=2$。",
                "solution_steps": [
                    {"title": "第（1）问", "content": "由平行得角相等，AA 判定。"},
                    {"title": "第（2）问", "content": "由相似得比例，$CE=2$。"},
                ],
            }
        )
    return {
        "meta": {"title": item_id},
        "sections": [{"id": "question", "type": "practice", "blocks": [block]}],
    }


@pytest.fixture
def bank_root(tmp_path: Path) -> Path:
    root = tmp_path / "题库"
    bank_dir = root / "2026-01-A"
    items = []
    for index in range(1, 3):
        item_id = f"Q{index:03d}"
        stem = (
            "如图。（1）求证：$\\triangle ABE\\sim\\triangle EFC$；（2）求 $CE$ 的长。"
            if index == 1
            else "如图，直接求 $x$。"
        )
        item_dir = bank_dir / "items" / item_id
        write_yaml(item_dir / "teacher.resolved.assignment.yaml", assignment(item_id, teacher=True, stem=stem))
        write_yaml(item_dir / "student.resolved.assignment.yaml", assignment(item_id, teacher=False, stem=stem))
        items.append(
            {
                "id": item_id,
                "title": f"题目 {index}",
                "question_type": "problem",
                "difficulty": "foundation",
                "skill_tags": ["相似"],
                "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
                "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
                "weight": 1.0,
                "enabled": True,
            }
        )
    write_yaml(
        bank_dir / "question-bank.yaml",
        {
            "schema": "math_topic_question_bank/v1",
            "bank": {
                "id": "bank-a",
                "topic": "A 专题",
                "grade": "八年级",
                "subject": "数学",
                "status": "ready",
                "target_count": 2,
            },
            "items": items,
        },
    )
    return root


@pytest.fixture
def tools_root(tmp_path: Path) -> Path:
    root = tmp_path / "teaching-tools"
    root.mkdir()
    return root


@pytest.fixture
def client(bank_root: Path, tools_root: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(explanations_ai, "api_key", lambda: "fake-key")
    app = create_question_bank_app(bank_root, teaching_tools_root=tools_root)
    return TestClient(app)


def first_approach(payload: dict, approach_id: str) -> dict:
    for subquestion in payload["subquestions"]:
        for approach in subquestion["approaches"]:
            if approach["id"] == approach_id:
                return approach
    raise AssertionError(f"approach not found: {approach_id}")


def test_view_derives_subquestions_and_flag(monkeypatch: pytest.MonkeyPatch, bank_root: Path, tools_root: Path) -> None:
    monkeypatch.setattr(explanations_ai, "api_key", lambda: None)
    no_key = TestClient(create_question_bank_app(bank_root, teaching_tools_root=tools_root))
    payload = no_key.get("/api/banks/bank-a/items/Q001/explanations").json()
    assert [(sq["id"], sq["label"]) for sq in payload["subquestions"]] == [
        ("sq1", "（1）"),
        ("sq2", "（2）"),
    ]
    assert payload["subquestions"][0]["stem_latex"].startswith("（1）求证")
    assert payload["recording_supported"] is False
    assert payload["subquestions"][0]["approaches"] == []

    single = no_key.get("/api/banks/bank-a/items/Q002/explanations").json()
    assert [(sq["id"], sq["label"]) for sq in single["subquestions"]] == [("sq1", "")]
    assert single["subquestions"][0]["stem_latex"].startswith("如图，直接求")


def test_create_update_delete_approach_persists_sidecar(client: TestClient, bank_root: Path) -> None:
    base = "/api/banks/bank-a/items/Q001/explanations"
    created = client.post(f"{base}/approaches", json={"subquestion_id": "sq1", "title": "公共角思路"})
    assert created.status_code == 200
    approach = created.json()["subquestions"][0]["approaches"][0]
    assert approach["id"] == "a1"
    assert approach["title"] == "公共角思路"

    updated = client.put(
        f"{base}/approaches/a1",
        json={"explanation_text": "先找公共角，再配等角。", "solution_text": "解：……"},
    )
    assert updated.status_code == 200
    persisted = yaml.safe_load(
        (bank_root / "2026-01-A/items/Q001/explanations.yaml").read_text(encoding="utf-8")
    )
    assert persisted["schema"] == "math_item_explanations/v1"
    assert persisted["item_id"] == "Q001"
    stored = persisted["subquestions"][0]["approaches"][0]
    assert stored["explanation"]["text"] == "先找公共角，再配等角。"
    assert stored["solution"]["text"] == "解：……"

    deleted = client.delete(f"{base}/approaches/a1")
    assert deleted.status_code == 200
    assert deleted.json()["subquestions"][0]["approaches"] == []

    assert client.post(f"{base}/approaches", json={"subquestion_id": "sq9"}).status_code == 400
    assert client.put(f"{base}/approaches/nope", json={"explanation_text": "x"}).status_code == 400


def test_recording_upload_saves_audio_and_transcript(
    client: TestClient, bank_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explanations_ai, "transcribe_audio", lambda data, ct: "先看公共角")
    monkeypatch.setattr(
        explanations_ai,
        "polish_explanation_text",
        lambda ctx: f"润色稿（{ctx['subquestion_label']}）",
    )
    base = "/api/banks/bank-a/items/Q001/explanations"
    approach = client.post(f"{base}/approaches", json={"subquestion_id": "sq1"}).json()["subquestions"][0]["approaches"][0]
    upload = client.post(
        f"{base}/approaches/{approach['id']}/audio",
        content=b"FAKE-AUDIO-BYTES",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )
    assert upload.status_code == 200
    assert upload.json()["transcript"] == "先看公共角"
    item_dir = bank_root / "2026-01-A/items/Q001"
    audio_files = sorted((item_dir / "assets/explanations").glob(f"{approach['id']}-*.webm"))
    assert len(audio_files) == 1
    assert audio_files[0].read_bytes() == b"FAKE-AUDIO-BYTES"

    polished = client.post(f"{base}/approaches/{approach['id']}/polish")
    assert polished.status_code == 200
    stored = first_approach(polished.json(), approach["id"])
    assert stored["explanation"]["text"] == "润色稿（（1））"
    assert stored["explanation"]["source"] == "polished"

    assert client.post(
        f"{base}/approaches/{approach['id']}/audio",
        content=b"x",
        headers={"Content-Type": "video/x-matroska"},
    ).status_code == 415


def test_polish_without_recording_is_rejected(client: TestClient) -> None:
    base = "/api/banks/bank-a/items/Q001/explanations"
    approach = client.post(f"{base}/approaches", json={"subquestion_id": "sq1"}).json()["subquestions"][0]["approaches"][0]
    response = client.post(f"{base}/approaches/{approach['id']}/polish")
    assert response.status_code == 400
    assert "录音" in response.json()["detail"]


def test_generate_missing_explanation_and_solution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        explanations_ai,
        "generate_explanation_text",
        lambda ctx: f"讲解（{ctx['subquestion_label']}）",
    )
    monkeypatch.setattr(
        explanations_ai,
        "generate_solution_text",
        lambda ctx: "解：配套解答。",
    )
    base = "/api/banks/bank-a/items/Q001/explanations"
    generated = client.post(f"{base}/generate", json={"kind": "explanation"}).json()
    assert generated["generated"] == 2
    approaches = [
        approach
        for subquestion in generated["explanations"]["subquestions"]
        for approach in subquestion["approaches"]
    ]
    assert [approach["explanation"]["text"] for approach in approaches] == ["讲解（（1））", "讲解（（2））"]
    assert all(approach["explanation"]["source"] == "generated" for approach in approaches)

    solutions = client.post(f"{base}/generate", json={"kind": "solution"}).json()
    assert solutions["generated"] == 2
    assert all(
        approach["solution"]["text"] == "解：配套解答。"
        for subquestion in solutions["explanations"]["subquestions"]
        for approach in subquestion["approaches"]
    )
    assert client.post(f"{base}/generate", json={"kind": "other"}).status_code == 422


def test_generate_failure_maps_to_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(ctx: dict) -> str:
        raise AiAssistError("provider_failed", "模型服务失败")

    monkeypatch.setattr(explanations_ai, "generate_explanation_text", fail)
    response = client.post(
        "/api/banks/bank-a/items/Q001/explanations/generate",
        json={"kind": "explanation"},
    )
    assert response.status_code == 502
    assert "模型服务失败" in response.json()["detail"]


def test_approve_requires_pair_and_exports_blueprint(client: TestClient, tools_root: Path) -> None:
    base = "/api/banks/bank-a/items/Q001/explanations"
    created = client.post(f"{base}/approaches", json={"subquestion_id": "sq1"}).json()
    approach_id = created["subquestions"][0]["approaches"][0]["id"]

    blocked = client.post(f"{base}/approaches/{approach_id}/approve")
    assert blocked.status_code == 400
    assert "讲解与解答" in blocked.json()["detail"]

    client.put(
        f"{base}/approaches/{approach_id}",
        json={"explanation_text": "讲解：找公共角。", "solution_text": "解：AA 判定。"},
    )
    approved = client.post(f"{base}/approaches/{approach_id}/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["blueprint"]["candidate_id"] == f"bank-a:Q001:sq1:{approach_id}"
    assert body["export"]["candidate_count"] == 1

    batch_path = Path(body["export"]["batch_path"])
    assert batch_path.is_file()
    assert batch_path.parent == tools_root / "authoring/tmp/reviewed-bank-import"
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    assert batch["taskId"] == "bank-a"
    assert batch["source"] == "reviewed-bank-import"
    assert batch["candidates"][0]["id"] == f"bank-a:Q001:sq1:{approach_id}"
    assert batch["candidates"][0]["promptData"]["explanationLatex"] == "讲解：找公共角。"
    assert batch["candidates"][0]["promptData"]["promptLatex"].startswith("（1）求证")
    assert batch["candidates"][0]["answerKey"]["solutionSteps"][0]["title"] == "第（1）问"
    assert batch["candidates"][0]["metadata"]["assignments"] == [
        str((tools_root.parent / "题库/2026-01-A/items/Q001/teacher.resolved.assignment.yaml").resolve())
    ]

    # 批准后编辑 → 回到草稿，blueprint 标记过期。
    edited = client.put(
        f"{base}/approaches/{approach_id}",
        json={"solution_text": "解：改写。"},
    ).json()
    stored = first_approach(edited, approach_id)
    assert stored["explanation"]["status"] == "draft"
    assert stored["approved_at"] is None
    assert stored["blueprint"]["stale"] is True


def test_explanations_summary_in_bank_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = client.get("/api/banks/bank-a").json()
    assert detail["items"][0]["explanations_summary"] == {
        "has_sidecar": False,
        "approach_count": 0,
        "approved_count": 0,
        "missing_explanation": True,
        "missing_solution_count": 0,
    }
    monkeypatch.setattr(explanations_ai, "generate_explanation_text", lambda ctx: "讲解")
    base = "/api/banks/bank-a/items/Q001/explanations"
    client.post(f"{base}/generate", json={"kind": "explanation"})
    detail = client.get("/api/banks/bank-a").json()
    assert detail["items"][0]["explanations_summary"]["missing_explanation"] is False


def test_staging_item_supports_approaches(bank_root: Path, tools_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper_dir = bank_root / "source-bank" / "staging" / "PAPER-A"
    item_dir = paper_dir / "items" / "Q001"
    write_yaml(
        item_dir / "teacher.resolved.assignment.yaml",
        assignment("q1", teacher=True, stem="（1）求 $a$；（2）求 $b$。"),
    )
    write_yaml(
        item_dir / "student.resolved.assignment.yaml",
        assignment("q1", teacher=False, stem="（1）求 $a$；（2）求 $b$。"),
    )
    write_yaml(
        item_dir / "source.yaml",
        {
            "schema": "math_exam_item_source/v1",
            "item_id": "Q001",
            "source_key": "PAPER-A-Q01",
            "paper_id": "PAPER-A",
            "question_number": 1,
            "question_type": "problem",
            "points": 12,
            "section_title": "解答题",
            "source_directory": "documents/paper-a",
            "crops": {},
            "transcription": {"human_review": "pending"},
            "content_hash": f"sha256:{'1' * 64}",
        },
    )
    write_yaml(
        paper_dir / "paper.yaml",
        {
            "schema": "math_exam_paper/v1",
            "paper": {"id": "PAPER-A", "title": "A 卷", "grade": "九年级", "subject": "数学"},
            "question_bank": "../../question-bank.yaml",
            "sections": [{"id": "s", "title": "解答题", "item_ids": ["Q001"]}],
        },
    )
    monkeypatch.setattr(explanations_ai, "api_key", lambda: "fake-key")
    app = create_question_bank_app(bank_root, teaching_tools_root=tools_root)
    client = TestClient(app)
    staging_id = "staging:source-bank:PAPER-A"
    base = f"/api/banks/{staging_id}/items/Q001/explanations"
    view = client.get(base)
    assert view.status_code == 200
    assert [sq["label"] for sq in view.json()["subquestions"]] == ["（1）", "（2）"]
    created = client.post(f"{base}/approaches", json={"subquestion_id": "sq2"})
    assert created.status_code == 200
    assert (item_dir / "explanations.yaml").is_file()
    assert client.get("/api/banks/bank-a/items/Q009/explanations").status_code == 404


def test_extract_body_text_accepts_plain_and_broken_json() -> None:
    """正文直出；LaTeX 反斜杠破坏 JSON 转义时兜底返回原文。"""
    assert explanations_ai._extract_body_text("直接输出的讲解正文。", "explanation") == "直接输出的讲解正文。"
    assert (
        explanations_ai._extract_body_text('```json\n{"explanation": "讲解"}\n```', "explanation") == "讲解"
    )
    # \angle 中的 \a 不是合法 JSON 转义 → 解析失败时原样返回。
    broken = '{"explanation": "找 $\\angle A$ 的公共角"}'
    assert explanations_ai._extract_body_text(broken, "explanation") == broken


def test_explanations_ui_static_wiring() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")
    css = (PACKAGE / "static/question-bank-review.css").read_text(encoding="utf-8")

    assert 'id="explanations-card"' in template
    assert 'id="explanations-body"' in template
    assert 'id="explanations-generate-missing"' in template
    assert 'id="explanations-generate-solutions"' in template
    assert 'id="explanations-export-blueprint"' in template
    assert 'id="explanations-message"' in template
    assert "讲解 / 解答（小题）" in template

    assert "function loadExplanations" in script
    assert "function renderExplanationSubquestion" in script
    assert "function renderExplanationApproach" in script
    assert "function toggleExplanationRecording" in script
    assert "function uploadExplanationRecording" in script
    assert "new MediaRecorder(stream" in script
    assert "getUserMedia({ audio: true })" in script
    assert "explanation-record-button" in script
    assert "function generateMissingAction" in script
    assert "function approveApproachAction" in script
    assert "function saveApproachText" in script
    assert "`${explanationsEndpoint(bankId, itemId)}/approaches`" in script
    assert "`${base}/approaches/${encodeURIComponent(meta.approachId)}/audio`" in script
    assert "`${explanationsEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}/polish`" in script
    assert "`${explanationsEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}/approve`" in script
    assert "`${explanationsEndpoint(bankId, itemId)}/generate`" in script
    assert "void loadExplanations(item.id)" in script
    assert "missing_explanation" in script and "缺讲解" in script
    # MathJax 安全纪律：讲解渲染同样不允许 innerHTML 赋值。
    assert "innerHTML" not in script
    assert ".explanations-card" in css or ".explanation-approach" in css
    assert ".explanation-record-button" in css
