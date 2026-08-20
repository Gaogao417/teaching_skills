"""Phase 3 TeachingApproach authoring：sidecar、append-only 证据、canonical 冻结与 stale。

覆盖 10 号计划 §8 的测试清单：audio/transcript/polished/manual edit 共存、重录重润色
新手编形成新 revision、Approved 修改回 Draft 且旧版可取回、多 Approach 并行批准、
Question version mismatch 禁止批准/发布、静态答案一致性 fail closed、legacy 兼容路径。
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

import canonical_export as ce  # noqa: E402
import explanations_ai  # noqa: E402
import teaching_approach as ta  # noqa: E402
from question_bank_review_server import create_question_bank_app  # noqa: E402
from integrations.ai_teaching_contracts import validate_payload  # noqa: E402


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


STEM_Q1 = "如图。（1）求证：$\\triangle ABE\\sim\\triangle EFC$；（2）求 $CE$ 的长。"


def assignment(item_id: str, *, teacher: bool, stem: str) -> dict:
    block: dict = {"type": "problem", "id": item_id, "stem_latex": stem}
    if teacher:
        block.update(
            {
                "answer": "（1）见解答；（2）$CE=2$。",
                "clue": "先由平行得等角，AA 判定相似，再列比例求 $CE=2$。",
                "solution_steps": [
                    "（1）由 $BE \\parallel CF$ 得角相等，AA 判定 $\\triangle ABE\\sim\\triangle EFC$。",
                    "（2）由对应边成比例列式，解得 $CE=2$。",
                ],
            }
        )
    return {
        "meta": {"title": item_id},
        "sections": [{"id": "question", "type": "practice", "blocks": [block]}],
    }


def write_truth(
    canonical_root: Path,
    qt_id: str,
    *,
    stem: str = STEM_Q1,
    answer_kind: str = "expression",
    answer_value: str = "$CE=2$",
    version: str = "v1",
    current: str | None = None,
) -> dict:
    payload = {
        "schema": "ai_teaching_question_truth/v1",
        "artifact_id": qt_id,
        "version": version,
        "status": "Approved",
        "question_type": "solution",
        "stem": stem,
        "canonical_answer": {"kind": answer_kind, "value": answer_value},
        "reviewed_solution": "参考答案（测试）",
        "source_evidence_refs": [
            {"evidence_id": "SE-TEST-001", "artifact_uri": "artifact://source-evidence/SE-TEST-001"}
        ],
        "approval": {"reviewer_id": "fixture", "approved_at": "2026-08-19T00:00:00+00:00"},
        "content_hash": "",
        "artifact_uri": f"artifact://question-truth/{qt_id}@{version}",
    }
    payload["content_hash"] = ce._content_hash(payload)
    base = canonical_root / "question-truth" / qt_id
    ce._write_json_atomic(base / f"{version}.json", payload)
    registry_path = base / "registry.yaml"
    if registry_path.is_file():
        registry = ce._load_yaml(registry_path)
        for entry in registry["versions"]:
            if entry["version"] == version:
                break
        else:
            registry["versions"].append(
                {
                    "version": version,
                    "status": "Approved",
                    "content_hash": payload["content_hash"],
                    "approved_at": payload["approval"]["approved_at"],
                }
            )
        registry["current_version"] = current or version
    else:
        registry = {
            "artifact_id": qt_id,
            "current_version": current or version,
            "versions": [
                {
                    "version": version,
                    "status": "Approved",
                    "content_hash": payload["content_hash"],
                    "approved_at": payload["approval"]["approved_at"],
                }
            ],
        }
    ce._write_yaml_atomic(registry_path, registry)
    return payload


@pytest.fixture
def bank_root(tmp_path: Path) -> Path:
    root = tmp_path / "题库"
    bank_dir = root / "2026-01-A"
    items = []
    for index in range(1, 3):
        item_id = f"Q{index:03d}"
        stem = STEM_Q1 if index == 1 else "如图，直接求 $x$。"
        item_dir = bank_dir / "items" / item_id
        write_yaml(item_dir / "teacher.resolved.assignment.yaml", assignment(item_id, teacher=True, stem=stem))
        write_yaml(item_dir / "student.resolved.assignment.yaml", assignment(item_id, teacher=False, stem=stem))
        # Q001 有 canonical 绑定；Q002 无（source_key 不在账本）。
        if index == 1:
            write_yaml(
                item_dir / "source.yaml",
                {"schema": "math_exam_item_source/v1", "item_id": item_id, "source_key": "TEST-SOURCE-Q1"},
            )
        else:
            write_yaml(
                item_dir / "source.yaml",
                {"schema": "math_exam_item_source/v1", "item_id": item_id, "source_key": "TEST-SOURCE-UNBOUND"},
            )
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
def canonical_root(tmp_path: Path) -> Path:
    root = tmp_path / "canonical-authoring"
    write_truth(root, "QT-SMV-001")
    write_yaml(
        root / "id-allocations.yaml",
        {
            "schema": "ai_teaching_id_allocations/v1",
            "golden_qt_ids": {},
            "allocations": {
                "TEST-SOURCE-Q1": {
                    "source_key": "TEST-SOURCE-Q1",
                    "qt_id": "QT-SMV-001",
                    "qc_id": "QC-SMV-001",
                    "se_ids": ["SE-TEST-001"],
                }
            },
            "ta_next_seq": 1,
            "ta_allocations": {},
        },
    )
    return root


@pytest.fixture
def client(
    bank_root: Path,
    canonical_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setattr(explanations_ai, "api_key", lambda: "fake-key")
    monkeypatch.setattr(
        explanations_ai, "transcribe_audio", lambda data, ct: "口述转写：先证相似，再列比例，解得 $CE=2$。"
    )
    monkeypatch.setattr(
        explanations_ai, "polish_explanation_text", lambda ctx: "润色稿：由平行得等角，AA 判定相似，列比例得 $CE=2$。"
    )
    tools_root = tmp_path / "teaching-tools"
    tools_root.mkdir()
    app = create_question_bank_app(
        bank_root, teaching_tools_root=tools_root, canonical_root=canonical_root
    )
    return TestClient(app)


APPROACH_URL = "/api/banks/bank-a/items/Q001/teaching-approach"


def valid_steps(*, with_answer: bool = True) -> list[dict]:
    narration_extra = " 得 $CE=2$。" if with_answer else " 得解。"
    prove = "证 $\\triangle ABE\\sim\\triangle EFC$"
    return [
        {
            "intent": "模型识别",
            "narration": "先看 8 字结构" + (f"，{prove}" if with_answer else "") + "。",
            "expected_student_reasoning": "学生能指出平行导等角，AA 判定。",
            "accepted_alternatives": ["先标角再配边"],
            "common_errors": ["按图上位置顺排顶点"],
            "skill_ids": ["SKILL-SMV-008"],
        },
        {
            "intent": "对应边配对",
            "narration": "按对应顶点配边，写出比例式。",
            "expected_student_reasoning": "学生能写出对应边比例。",
            "common_errors": ["对应边错配"],
            "skill_ids": ["SKILL-SMV-002"],
        },
        {
            "intent": "设元列式",
            "narration": "代入已知长度列方程求解" + narration_extra,
            "expected_student_reasoning": "学生能解出 CE。",
            "skill_ids": ["SKILL-SMV-007"],
        },
    ]


def create_approach(client: TestClient, title: str = "从公共角正推") -> str:
    response = client.post(
        f"{APPROACH_URL}/approaches",
        json={"title": title, "author": "teacher-a"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["question"]["artifact_id"] == "QT-SMV-001"
    return payload["approaches"][-1]["id"]


# --------------------------------------------------------------------------- #
# P3-01：legacy title-only 更新落盘
# --------------------------------------------------------------------------- #


def test_title_only_update_persists(client: TestClient, bank_root: Path) -> None:
    created = client.post(
        "/api/banks/bank-a/items/Q001/explanations/approaches",
        json={"subquestion_id": "sq1"},
    )
    assert created.status_code == 200
    approach_id = created.json()["subquestions"][0]["approaches"][-1]["id"]
    updated = client.put(
        f"/api/banks/bank-a/items/Q001/explanations/approaches/{approach_id}",
        json={"title": "新标题"},
    )
    assert updated.status_code == 200
    reloaded = client.get("/api/banks/bank-a/items/Q001/explanations").json()
    stored = [
        approach
        for sq in reloaded["subquestions"]
        for approach in sq["approaches"]
        if approach["id"] == approach_id
    ][0]
    assert stored["title"] == "新标题"
    sidecar = yaml.safe_load(
        (bank_root / "2026-01-A" / "items" / "Q001" / "explanations.yaml").read_text(encoding="utf-8")
    )
    assert sidecar["subquestions"][0]["approaches"][0]["title"] == "新标题"


# --------------------------------------------------------------------------- #
# 工作区 sidecar：创建、绑定、编辑、manual_edit_notes（P3-04/P3-06）
# --------------------------------------------------------------------------- #


def test_create_requires_canonical_binding(client: TestClient) -> None:
    response = client.post(
        "/api/banks/bank-a/items/Q002/teaching-approach/approaches",
        json={"title": "无绑定", "author": "teacher-a"},
    )
    assert response.status_code == 400
    assert "QuestionTruth" in response.json()["detail"]


def test_working_sidecar_crud_and_edit_notes(
    client: TestClient, bank_root: Path
) -> None:
    approach_id = create_approach(client)
    updated = client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "学会从平行条件找 AA 判定", "entry_signal": "BE∥CF", "editor": "teacher-a"},
    )
    assert updated.status_code == 200
    approach = [a for a in updated.json()["approaches"] if a["id"] == approach_id][0]
    assert approach["goal"] == "学会从平行条件找 AA 判定"
    assert approach["entry_signal"] == "BE∥CF"
    assert approach["status"] == "draft"
    notes = approach["evidence"]["manual_edit_notes"]
    assert notes and "teacher-a" in notes[-1] and "goal" in notes[-1]

    sidecar = yaml.safe_load(
        (bank_root / "2026-01-A" / "items" / "Q001" / "teaching-approach.yaml").read_text(encoding="utf-8")
    )
    assert sidecar["schema"] == ta.APPROACH_SCHEMA
    assert sidecar["question"]["artifact_id"] == "QT-SMV-001"
    assert sidecar["approaches"][0]["author"] == "teacher-a"


# --------------------------------------------------------------------------- #
# P3-02/P3-03：录音 append-only 修订 + 受限回放
# --------------------------------------------------------------------------- #


def upload_audio(client: TestClient, approach_id: str, marker: bytes) -> dict:
    response = client.post(
        f"{APPROACH_URL}/approaches/{approach_id}/audio",
        content=marker,
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_recording_append_only_revisions(
    client: TestClient, bank_root: Path
) -> None:
    approach_id = create_approach(client)
    first = upload_audio(client, approach_id, b"RIFF-first-recording")
    recordings = first["approaches"][-1]["evidence"]["recordings"]
    assert len(recordings) == 1
    assert recordings[0]["revision"] == 1
    first_path = recordings[0]["audio_path"]
    first_transcript_path = recordings[0]["transcript_path"]

    second = upload_audio(client, approach_id, b"RIFF-second-recording")
    approach = [a for a in second["approaches"] if a["id"] == approach_id][0]
    recordings = approach["evidence"]["recordings"]
    assert len(recordings) == 2
    assert recordings[0]["revision"] == 1
    assert recordings[1]["revision"] == 2
    # 旧修订的 ref 不被覆盖（append-only），两个音频文件都还在盘上。
    assert recordings[0]["audio_path"] == first_path
    assert recordings[0]["transcript_path"] == first_transcript_path
    item_dir = bank_root / "2026-01-A" / "items" / "Q001"
    assert (item_dir / first_path).read_bytes() == b"RIFF-first-recording"
    assert (item_dir / recordings[1]["audio_path"]).read_bytes() == b"RIFF-second-recording"


def test_audio_playback_restricted(client: TestClient) -> None:
    approach_id = create_approach(client)
    upload_audio(client, approach_id, b"RIFF-audio-bytes")
    ok = client.get(f"{APPROACH_URL}/approaches/{approach_id}/audio/1")
    assert ok.status_code == 200
    assert ok.content == b"RIFF-audio-bytes"
    assert ok.headers["content-type"] in {"audio/wav", "audio/x-wav"}
    missing = client.get(f"{APPROACH_URL}/approaches/{approach_id}/audio/9")
    assert missing.status_code == 400
    # 路径穿越被路由/端点层拒绝（revision 必须是证据链登记过的修订号）。
    wrong = client.get(f"{APPROACH_URL}/approaches/{approach_id}/audio/../../source.yaml")
    assert wrong.status_code in {400, 404, 405, 422}
    assert client.get(f"{APPROACH_URL}/approaches/{approach_id}/audio/0").status_code == 400
    assert client.get(f"{APPROACH_URL}/approaches/{approach_id}/audio/abc").status_code == 422


def test_polish_appends_revision_and_keeps_transcript(client: TestClient) -> None:
    approach_id = create_approach(client)
    uploaded = upload_audio(client, approach_id, b"RIFF-audio-bytes")
    polished = client.post(f"{APPROACH_URL}/approaches/{approach_id}/polish")
    assert polished.status_code == 200
    approach = [a for a in polished.json()["approaches"] if a["id"] == approach_id][0]
    recordings = approach["evidence"]["recordings"]
    polishes = approach["evidence"]["polishes"]
    assert len(polishes) == 1
    assert polishes[0]["based_on_recording"] == 1
    assert approach["polished_text"].startswith("润色稿")
    assert recordings[0]["transcript"] == uploaded["approaches"][-1]["evidence"]["recordings"][0]["transcript"]
    assert recordings[0]["transcript_path"]  # 转写稿文件保留


# --------------------------------------------------------------------------- #
# P3-05：从 assignment solution_steps 初始化 TeachingStep 草稿
# --------------------------------------------------------------------------- #


def test_steps_init_assignment_scaffold_without_ai(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explanations_ai, "api_key", lambda: None)
    approach_id = create_approach(client)
    response = client.post(f"{APPROACH_URL}/approaches/{approach_id}/steps/init", json={})
    assert response.status_code == 200
    approach = [a for a in response.json()["approaches"] if a["id"] == approach_id][0]
    assert approach["steps_origin"] == "assignment"
    assert [s["step_id"] for s in approach["steps"]] == ["S1", "S2"]
    assert "AA 判定" in approach["steps"][0]["narration"]
    assert approach["steps"][0]["skill_ids"] == []  # 教师必须补齐


def test_steps_init_ai_draft_only_suggests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_draft(ctx):
        assert ctx["allowed_skill_ids"] == ta.TOPIC_SKILL_IDS
        return [
            {
                "intent": "识别模型",
                "narration": "看 8 字。",
                "expected_student_reasoning": "…",
                "accepted_alternatives": [],
                "common_errors": ["顶点顺排"],
                "skill_ids": ["SKILL-SMV-008"],
                "origin": "ai_draft",
            }
        ] * 3

    monkeypatch.setattr(explanations_ai, "draft_teaching_steps", fake_draft)
    approach_id = create_approach(client)
    response = client.post(
        f"{APPROACH_URL}/approaches/{approach_id}/steps/init",
        json={"use_ai": True},
    )
    assert response.status_code == 200
    approach = [a for a in response.json()["approaches"] if a["id"] == approach_id][0]
    assert approach["steps_origin"] == "ai_draft"
    assert approach["steps"][0]["origin"] == "ai_draft"
    # 再次初始化不传 replace 被拒绝（不静默覆盖教师草稿）。
    again = client.post(f"{APPROACH_URL}/approaches/{approach_id}/steps/init", json={})
    assert again.status_code == 400


# --------------------------------------------------------------------------- #
# P3-07：批准冻结 canonical ApprovedTeachingApproach.v1
# --------------------------------------------------------------------------- #


def approve(client: TestClient, approach_id: str, **overrides):
    body = {"reviewer_id": "reviewer-r", "review_note": "教学审核通过"}
    body.update(overrides)
    return client.post(f"{APPROACH_URL}/approaches/{approach_id}/approve", json=body)


def test_manual_approach_freezes_canonical_v1(
    client: TestClient, canonical_root: Path, bank_root: Path
) -> None:
    approach_id = create_approach(client)
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "AA 判定 + 比例求解", "entry_signal": "BE∥CF", "steps": valid_steps(), "editor": "teacher-a"},
    )
    response = approve(client, approach_id)
    assert response.status_code == 200, response.text
    canonical = response.json()["canonical"]
    assert canonical["artifact_id"] == "TA-SMV-001"
    assert canonical["version"] == "v1"

    frozen = ta.read_approach_version("TA-SMV-001", "v1", root=canonical_root)
    ok, errors = validate_payload(frozen)
    assert ok, errors
    assert frozen["status"] == "Approved"
    assert frozen["question_ref"] == {
        "artifact_id": "QT-SMV-001",
        "version": "v1",
        "content_hash": ce.current_truth("QT-SMV-001", root=canonical_root)["content_hash"],
    }
    assert [s["step_id"] for s in frozen["steps"]] == ["S1", "S2", "S3"]
    assert frozen["evidence"]["manual_edit_notes"]  # 编辑痕迹进 canonical 证据链

    registry = ta.approach_history("TA-SMV-001", root=canonical_root)
    assert registry["current_version"] == "v1"
    ledger = ce._load_yaml(canonical_root / "id-allocations.yaml")
    assert ledger["ta_allocations"]["QT-SMV-001"][0]["ta_id"] == "TA-SMV-001"


def test_freeze_copies_evidence_files_to_canonical(
    client: TestClient, canonical_root: Path
) -> None:
    approach_id = create_approach(client)
    upload_audio(client, approach_id, b"RIFF-evidence-audio")
    client.post(f"{APPROACH_URL}/approaches/{approach_id}/polish")
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "AA 判定 + 比例求解", "steps": valid_steps(), "editor": "teacher-a"},
    )
    response = approve(client, approach_id)
    assert response.status_code == 200, response.text
    frozen = ta.read_approach_version("TA-SMV-001", "v1", root=canonical_root)
    assert frozen["evidence"]["audio"], "audio evidence 应进入 canonical"
    assert frozen["evidence"]["transcripts"], "transcript evidence 应进入 canonical"
    assert frozen["evidence"]["polished"], "polished evidence 应进入 canonical"
    audio_uri = frozen["evidence"]["audio"][0]["artifact_uri"]
    assert audio_uri.startswith("artifact://audio/TA-SMV-001@v1/")
    audio_name = audio_uri.rsplit("/", 1)[-1]
    copied = canonical_root / "audio" / "TA-SMV-001" / "v1" / audio_name
    assert copied.read_bytes() == b"RIFF-evidence-audio"


def test_approve_gates_fail_closed(client: TestClient) -> None:
    approach_id = create_approach(client)
    # 缺 goal
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"steps": valid_steps(), "editor": "teacher-a"},
    )
    assert "goal" in approve(client, approach_id).json()["detail"]
    # 步骤不足 3
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g", "steps": valid_steps()[:2], "editor": "teacher-a"},
    )
    assert "3" in approve(client, approach_id).json()["detail"]
    # 步骤缺 skill_ids（normalize 后为空）
    steps = valid_steps()
    steps[1]["skill_ids"] = []
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g", "steps": steps, "editor": "teacher-a"},
    )
    assert "skill_ids" in approve(client, approach_id).json()["detail"]
    # 静态答案一致性：步骤从不陈述答案/求证目标（fail closed）
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g", "steps": valid_steps(with_answer=False), "editor": "teacher-a"},
    )
    detail = approve(client, approach_id).json()["detail"]
    assert "一致性" in detail
    # 缺 reviewer_id（schema 层拒绝）
    response = client.post(
        f"{APPROACH_URL}/approaches/{approach_id}/approve", json={"reviewer_id": ""}
    )
    assert response.status_code == 422


def test_static_answer_consistency_unit() -> None:
    truth = {
        "stem": "（1）求证：$CE \\perp AB$；（2）求 $AF \\cdot DE = AG \\cdot BC$。",
        "canonical_answer": {"kind": "solution", "value": "（1）（2）得证"},
    }
    good = [{"narration": "推出 $CE \\perp AB$，且 $AF \\cdot DE = AG \\cdot BC$。", "expected_student_reasoning": ""}]
    assert ta.static_answer_consistency(truth, good) == []
    bad = [{"narration": "只写了一半结论。", "expected_student_reasoning": ""}]
    problems = ta.static_answer_consistency(truth, bad)
    assert problems and "求证目标" in problems[0]

    choice = {
        "stem": "选择题。",
        "canonical_answer": {"kind": "choice_option", "options": [{"id": "B", "value": "4"}]},
    }
    assert ta.static_answer_consistency(choice, [{"narration": "选 B：$4$", "expected_student_reasoning": ""}]) == []
    assert ta.static_answer_consistency(choice, [{"narration": "选 C", "expected_student_reasoning": ""}])

    unextractable = {"stem": "无目标题。", "canonical_answer": {"kind": "solution", "value": ""}}
    assert ta.static_answer_consistency(unextractable, good)  # fail closed


def test_ledger_allocation_stable_and_collision_guard(
    canonical_root: Path,
) -> None:
    ledger_path = canonical_root / "id-allocations.yaml"
    first = ta.allocate_ta_id(ledger_path, qt_id="QT-SMV-001", local_id="t1", title="A")
    again = ta.allocate_ta_id(ledger_path, qt_id="QT-SMV-001", local_id="t1", title="A2")
    assert first == again == "TA-SMV-001"
    second = ta.allocate_ta_id(ledger_path, qt_id="QT-SMV-001", local_id="t2", title="B")
    assert second == "TA-SMV-002"
    ledger = ce._load_yaml(ledger_path)
    ledger["ta_next_seq"] = 2  # 人为把计数器拨回已占用值
    ce._write_yaml_atomic(ledger_path, ledger)
    third = ta.allocate_ta_id(ledger_path, qt_id="QT-SMV-001", local_id="t3", title="C")
    assert third == "TA-SMV-003"


# --------------------------------------------------------------------------- #
# FR-4 / AC-5：编辑回 Draft + 旧版可取回；多 Approach 并行批准
# --------------------------------------------------------------------------- #


def test_edit_after_approval_creates_v2_and_supersedes(
    client: TestClient, canonical_root: Path
) -> None:
    approach_id = create_approach(client)
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g1", "steps": valid_steps(), "editor": "teacher-a"},
    )
    approve(client, approach_id)
    # 批准后编辑 → 回 Draft，canonical v1 仍可读。
    edited = client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g2（修订）", "editor": "teacher-a"},
    )
    approach = [a for a in edited.json()["approaches"] if a["id"] == approach_id][0]
    assert approach["status"] == "draft"
    assert approach["approval"] is None
    assert approach["canonical"]["version"] == "v1"
    v1 = ta.read_approach_version("TA-SMV-001", "v1", root=canonical_root)
    assert v1["status"] == "Approved"
    assert v1["goal"] == "g1"
    # 再次批准 → v2，v1 Superseded，两个版本都完整可读。
    response = approve(client, approach_id, review_note="二次审核")
    assert response.status_code == 200
    assert response.json()["canonical"]["version"] == "v2"
    registry = ta.approach_history("TA-SMV-001", root=canonical_root)
    assert registry["current_version"] == "v2"
    statuses = {e["version"]: e["status"] for e in registry["versions"]}
    assert statuses == {"v1": "Superseded", "v2": "Approved"}
    old = ta.read_approach_version("TA-SMV-001", "v1", root=canonical_root)
    assert old["status"] == "Superseded"
    assert old["superseded_by"] == {"artifact_id": "TA-SMV-001", "version": "v2"}


def test_parallel_approaches_both_approved(
    client: TestClient, canonical_root: Path
) -> None:
    first_id = create_approach(client, title="思路 A：正推")
    second_id = create_approach(client, title="思路 B：反推")
    for approach_id in (first_id, second_id):
        client.put(
            f"{APPROACH_URL}/approaches/{approach_id}",
            json={"goal": "g", "steps": valid_steps(), "editor": "teacher-a"},
        )
        assert approve(client, approach_id).status_code == 200
    current = ta.approaches_for_question(
        "QT-SMV-001",
        ledger_path=canonical_root / "id-allocations.yaml",
        root=canonical_root,
    )
    assert sorted(a["artifact_id"] for a in current) == ["TA-SMV-001", "TA-SMV-002"]
    # 有 canonical 冻结的工作副本不可删除。
    blocked = client.delete(f"{APPROACH_URL}/approaches/{first_id}")
    assert blocked.status_code == 400


# --------------------------------------------------------------------------- #
# P3-08：Question version 漂移 → Approach stale（可读不可发布）
# --------------------------------------------------------------------------- #


def test_question_change_propagates_stale(
    client: TestClient, canonical_root: Path
) -> None:
    approach_id = create_approach(client)
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g", "steps": valid_steps(), "editor": "teacher-a"},
    )
    approve(client, approach_id)
    # 模拟 Phase 2 的 question change：QT 晋升 v2 + stale 事件。
    write_truth(canonical_root, "QT-SMV-001", answer_value="$CE=3$", version="v2")
    ce._write_yaml_atomic(
        canonical_root / "stale-events.yaml",
        {
            "schema": "ai_teaching_stale_events/v1",
            "events": [
                {
                    "occurred_at": "2026-08-19T00:00:00+00:00",
                    "kind": "question_change",
                    "question": {"artifact_id": "QT-SMV-001", "from_version": "v1", "to_version": "v2"},
                    "downstream": [{"type": "teaching-approach", "action": "stale"}],
                }
            ],
        },
    )
    result = ta.apply_question_change_stale(root=canonical_root)
    assert result["stale_versions"] == ["TA-SMV-001@v1"]
    registry = ta.approach_history("TA-SMV-001", root=canonical_root)
    assert registry["versions"][0]["status"] == "Stale"
    stale_file = ta.read_approach_version("TA-SMV-001", "v1", root=canonical_root)
    assert stale_file["status"] == "Stale"  # 旧版可读，但不再是 Approved
    # approaches_for_question 只返回绑定 v2 的当前 Approved（旧版不可再发布）。
    assert ta.approaches_for_question(
        "QT-SMV-001", ledger_path=canonical_root / "id-allocations.yaml", root=canonical_root
    ) == []
    # 教师按新 Truth 修订步骤后重批 → v2 绑定 QT v2。
    steps = valid_steps()
    steps[2]["narration"] = steps[2]["narration"].replace("$CE=2$", "$CE=3$")
    client.put(
        f"{APPROACH_URL}/approaches/{approach_id}",
        json={"goal": "g", "steps": steps, "editor": "teacher-a"},
    )
    response = approve(client, approach_id)
    assert response.status_code == 200
    frozen = ta.read_approach_version("TA-SMV-001", "v2", root=canonical_root)
    assert frozen["question_ref"]["version"] == "v2"
    current = ta.approaches_for_question(
        "QT-SMV-001", ledger_path=canonical_root / "id-allocations.yaml", root=canonical_root
    )
    assert [a["version"] for a in current] == ["v2"]


# --------------------------------------------------------------------------- #
# Phase 4：question change 同轮传播 tutor-plan stale（stale-events downstream 声明）
# --------------------------------------------------------------------------- #


def _write_tutor_plan(
    canonical_root: Path,
    tp_id: str,
    qt_id: str,
    *,
    qt_version: str = "v1",
    qt_hash: str = "sha256:" + "a" * 64,
    version: str = "v1",
) -> dict:
    """写入最小 Approved TutorPlanBundle v2 注册表（结构与 tools 仓 materializer 产物一致）。"""
    payload = {
        "schema": "ai_teaching_tutor_plan_bundle/v2",
        "artifact_id": tp_id,
        "version": version,
        "status": "Approved",
        "question_ref": {"artifact_id": qt_id, "version": qt_version, "content_hash": qt_hash},
        "approach_refs": [
            {
                "artifact_id": "TA-SMV-001",
                "version": "v1",
                "content_hash": "sha256:" + "b" * 64,
                "part_id": "1",
            }
        ],
        "recommended_routes": [
            {
                "route_id": "R1",
                "role": "primary",
                "checkpoint_ids": ["CP1"],
                "completion_condition": "fixture",
            }
        ],
        "checkpoints": [
            {"checkpoint_id": "CP1", "part_id": "1", "expected_reasoning": "fixture", "resource_ids": ["RES1"]}
        ],
        "resources": [
            {"resource_id": "RES1", "kind": "explanation", "source": "authored", "content": "fixture"}
        ],
        "policy_constraints": {
            "allowed_move_types": ["explain"],
            "allowed_capabilities": [],
            "forbidden_content_kinds": ["canonical_answer"],
            "maximum_assistance_level": 2,
            "assessment_enabled": False,
        },
        "build_provenance": {
            "provider": "deterministic-rules",
            "model_id": "plan-build-rules/v1",
            "workflow_version": "tutor-plan-build/v1",
            "run_id": "run-fixture",
            "built_at": "2026-08-21T00:00:00Z",
            "runtime_registry_version": "action-runtime-registry/v5@fixture",
        },
        "runtime_projection": {
            "materializer_version": "tutor-plan-materializer/0.1.0",
            "runtime_registry_version": "action-runtime-registry/v5@fixture",
            "projection_hash": "sha256:" + "c" * 64,
            "validation_status": "passed",
        },
        "approval": {"reviewer_id": "fixture", "approved_at": "2026-08-21T00:00:00Z"},
        "content_hash": "",
        "artifact_uri": f"artifact://tutor-plan/{tp_id}@{version}",
    }
    payload["content_hash"] = ce._content_hash(payload, extra_excluded=("runtime_projection",))
    base = canonical_root / "tutor-plan" / tp_id
    ce._write_json_atomic(base / f"{version}.json", payload)
    ce._write_yaml_atomic(
        base / "registry.yaml",
        {
            "artifact_id": tp_id,
            "current_version": version,
            "versions": [
                {
                    "version": version,
                    "status": "Approved",
                    "content_hash": payload["content_hash"],
                    "approved_at": "2026-08-21T00:00:00Z",
                    "question_ref": {
                        "artifact_id": qt_id,
                        "version": qt_version,
                        "content_hash": qt_hash,
                    },
                }
            ],
        },
    )
    return payload


def test_question_change_propagates_stale_to_tutor_plan(
    canonical_root: Path,
) -> None:
    plan = _write_tutor_plan(canonical_root, "TP-SMV-001", "QT-SMV-001")
    write_truth(canonical_root, "QT-SMV-001", answer_value="$CE=3$", version="v2")
    ce._write_yaml_atomic(
        canonical_root / "stale-events.yaml",
        {
            "schema": "ai_teaching_stale_events/v1",
            "events": [
                {
                    "occurred_at": "2026-08-21T00:00:00+00:00",
                    "kind": "question_change",
                    "question": {"artifact_id": "QT-SMV-001", "from_version": "v1", "to_version": "v2"},
                    "downstream": [
                        {"type": "teaching-approach", "action": "stale"},
                        {"type": "tutor-plan", "action": "stale"},
                    ],
                }
            ],
        },
    )
    result = ta.apply_question_change_stale(root=canonical_root)
    assert "TP-SMV-001@v1" in result["stale_versions"]
    registry = ce._load_yaml(canonical_root / "tutor-plan" / "TP-SMV-001" / "registry.yaml")
    assert registry["versions"][0]["status"] == "Stale"
    stale_plan = json.loads(
        (canonical_root / "tutor-plan" / "TP-SMV-001" / "v1.json").read_text(encoding="utf-8")
    )
    assert stale_plan["status"] == "Stale"  # 可读不可发布
    # 绑定新版本的 plan 不受影响。
    fresh = _write_tutor_plan(
        canonical_root,
        "TP-SMV-002",
        "QT-SMV-001",
        qt_version="v2",
    )
    assert fresh["status"] == "Approved"
    ce._write_yaml_atomic(canonical_root / "stale-events.yaml", {
        "schema": "ai_teaching_stale_events/v1",
        "events": [],
    })
    again = ta.apply_question_change_stale(root=canonical_root)
    assert "TP-SMV-002@v1" not in again["stale_versions"]


# --------------------------------------------------------------------------- #
# 兼容路径：legacy explanations blueprint 导出仍可运行（退出门禁 5）
# --------------------------------------------------------------------------- #


def test_legacy_explanations_blueprint_still_works(
    client: TestClient, tmp_path: Path
) -> None:
    created = client.post(
        "/api/banks/bank-a/items/Q001/explanations/approaches",
        json={"subquestion_id": "sq1"},
    )
    approach_id = created.json()["subquestions"][0]["approaches"][-1]["id"]
    client.put(
        f"/api/banks/bank-a/items/Q001/explanations/approaches/{approach_id}",
        json={"explanation_text": "讲解 $CE=2$。", "solution_text": "解：$CE=2$。"},
    )
    approved = client.post(
        f"/api/banks/bank-a/items/Q001/explanations/approaches/{approach_id}/approve"
    )
    assert approved.status_code == 200
    export = approved.json()["export"]
    assert export["candidate_count"] == 1
    assert Path(export["batch_path"]).is_file()


# --------------------------------------------------------------------------- #
# 前端静态接线（与 legacy 面板同标准：无 innerHTML、端点模板、函数存在）
# --------------------------------------------------------------------------- #


def test_teaching_approach_ui_static_wiring() -> None:
    html = (PACKAGE / "templates" / "question-bank-review.html").read_text(encoding="utf-8")
    for node_id in (
        "approach-card",
        "approach-body",
        "approach-message",
        "approach-binding",
        "approach-create",
        "approach-reviewer-input",
        "approach-author-input",
        "approach-part-select",  # ADR-005：part 选择（旧粒度解法补绑；模板保留隐藏占位）
        "part-overview-section",  # 小问栏：该问真值切片（题面/答案/解答）
        "part-tabs",  # 小问栏切换（箭头 + 圆点，默认第一小问）
        "whole-approach-details",  # ADR-005 前整题粒度旧解法折叠区
    ):
        assert f'id="{node_id}"' in html, node_id

    js = (PACKAGE / "static" / "question-bank-review.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js
    for name in (
        "loadApproaches",
        "renderApproachItem",
        "renderSubquestionPreview",
        "toggleApproachRecording",
        "uploadApproachRecording",
        "initApproachStepsAction",
        "approveApproachFreezeAction",
        "saveApproachStepsAction",
    ):
        assert f"function {name}" in js, name
    assert "/teaching-approach" in js
    assert 'createElement("audio")' in js  # <audio> 回放（P3-02）
    assert "audio.controls = true" in js
    css = (PACKAGE / "static" / "question-bank-review.css").read_text(encoding="utf-8")
    for klass in (".approach-item", ".approach-steps", ".approach-recording audio"):
        assert klass in css, klass


# --------------------------------------------------------------------------- #
# ADR-005：小问粒度 part 绑定（v2）
# --------------------------------------------------------------------------- #


def write_truth_v2_multipart(canonical_root: Path, qt_id: str = "QT-SMV-003") -> dict:
    payload = {
        "schema": "ai_teaching_question_truth/v2",
        "artifact_id": qt_id,
        "version": "v1",
        "status": "Approved",
        "question_type": "solution",
        "stem": "已知：如图，$BE \\parallel CF$。",
        "subquestions": [
            {
                "part_id": "1",
                "prompt": "求证：$\\triangle ABE\\sim\\triangle EFC$",
                "canonical_answer": {"kind": "proof", "value": "相似得证"},
                "reviewed_solution": "AA 判定得相似。",
            },
            {
                "part_id": "2",
                "prompt": "求 $CE$ 的长。",
                "canonical_answer": {"kind": "expression", "value": "$CE=2$"},
                "reviewed_solution": "对应边成比例求解。",
            },
        ],
        "source_evidence_refs": [
            {"evidence_id": "SE-TEST-001", "artifact_uri": "artifact://source-evidence/SE-TEST-001"}
        ],
        "approval": {"reviewer_id": "fixture", "approved_at": "2026-08-20T00:00:00+00:00"},
        "content_hash": "",
        "artifact_uri": f"artifact://question-truth/{qt_id}@v1",
    }
    payload["content_hash"] = ce._content_hash(payload)
    base = canonical_root / "question-truth" / qt_id
    ce._write_json_atomic(base / "v1.json", payload)
    ce._write_yaml_atomic(
        base / "registry.yaml",
        {
            "artifact_id": qt_id,
            "current_version": "v1",
            "versions": [
                {
                    "version": "v1",
                    "status": "Approved",
                    "content_hash": payload["content_hash"],
                    "approved_at": payload["approval"]["approved_at"],
                }
            ],
        },
    )
    return payload


def _draft_part_approach(*, with_answer: bool = True) -> dict:
    conclusion = "解得 $CE=2$" if with_answer else "解得结论"
    return {
        "id": "t1",
        "title": "第(2)问：比例式求 CE",
        "author": "teacher-a",
        "status": "draft",
        "part_id": "2",
        "goal": "由对应边成比例求 CE",
        "entry_signal": "已证相似",
        "steps": [
            {
                "step_id": "S1",
                "intent": "识别对应边",
                "narration": "读出对应边。",
                "expected_student_reasoning": "BE/EF",
                "skill_ids": ["SKILL-SMV-002"],
            },
            {
                "step_id": "S2",
                "intent": "列比例式",
                "narration": "由相似列比例。",
                "expected_student_reasoning": "比例式",
                "skill_ids": ["SKILL-SMV-007"],
            },
            {
                "step_id": "S3",
                "intent": "求解收尾",
                "narration": conclusion,
                "expected_student_reasoning": "CE 的长",
                "skill_ids": ["SKILL-SMV-003"],
            },
        ],
        "steps_origin": "manual",
        "polished_text": "",
        "evidence": {"recordings": [], "polishes": [], "manual_edit_notes": ["part 重切"]},
        "approval": None,
        "canonical": None,
        "created_at": "2026-08-20T00:00:00+00:00",
    }


def _ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "id-allocations.yaml"
    write_yaml(
        ledger,
        {"schema": "ai_teaching_id_allocations/v1", "allocations": {}, "ta_next_seq": 1},
    )
    return ledger


def test_part_binding_freeze_gates(tmp_path: Path) -> None:
    canonical_root = tmp_path / "canonical-authoring"
    truth = write_truth_v2_multipart(canonical_root)
    ledger = _ledger(tmp_path)
    approach = _draft_part_approach()

    # 多小问 QT：缺 part_id / part_id 不在列表 → fail closed
    with pytest.raises(ta.TeachingApproachError, match="必须绑定具体小问"):
        ta.freeze_approved_approach(
            approach, tmp_path, reviewer_id="r", review_note="n",
            qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root,
        )
    with pytest.raises(ta.TeachingApproachError, match="不在小问列表"):
        ta.freeze_approved_approach(
            approach, tmp_path, reviewer_id="r", review_note="n",
            qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="9",
        )
    # 合法 part 绑定 → v2 冻结，question_ref 携带 part_id
    frozen = ta.freeze_approved_approach(
        approach, tmp_path, reviewer_id="r", review_note="n",
        qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="2",
    )
    assert frozen["schema"] == "ai_teaching_teaching_approach/v2"
    assert frozen["question_ref"]["part_id"] == "2"
    assert frozen["question_ref"]["content_hash"] == truth["content_hash"]
    ok, errors = validate_payload(frozen)
    assert ok, errors

    # part 感知读取入口：只命中绑定 part 的 TA
    all_current = ta.approaches_for_question(
        "QT-SMV-003", ledger_path=ledger, root=canonical_root
    )
    part2 = ta.approaches_for_question(
        "QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="2"
    )
    part1 = ta.approaches_for_question(
        "QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="1"
    )
    assert [p["artifact_id"] for p in all_current] == [frozen["artifact_id"]]
    assert [p["artifact_id"] for p in part2] == [frozen["artifact_id"]]
    assert part1 == []


def test_part_scoped_static_consistency(tmp_path: Path) -> None:
    canonical_root = tmp_path / "canonical-authoring"
    write_truth_v2_multipart(canonical_root)
    ledger = _ledger(tmp_path)

    # part 2 的步骤不陈述该问答案 → 一致性 fail closed
    approach = _draft_part_approach(with_answer=False)
    with pytest.raises(ta.TeachingApproachError, match="一致性"):
        ta.freeze_approved_approach(
            approach, tmp_path, reviewer_id="r", review_note="n",
            qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="2",
        )
    # 同样步骤对 part 1 求证目标也不满足（目标按 part 提取，互不串门）
    with pytest.raises(ta.TeachingApproachError, match="一致性"):
        ta.freeze_approved_approach(
            approach, tmp_path, reviewer_id="r", review_note="n",
            qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="1",
        )


def test_part_id_forbidden_without_subquestions(tmp_path: Path) -> None:
    canonical_root = tmp_path / "canonical-authoring"
    write_truth(canonical_root, "QT-SMV-001")  # v1 风格：无 subquestions
    ledger = _ledger(tmp_path)
    with pytest.raises(ta.TeachingApproachError, match="不得携带 part_id"):
        ta.freeze_approved_approach(
            _draft_part_approach(), tmp_path, reviewer_id="r", review_note="n",
            qt_id="QT-SMV-001", ledger_path=ledger, root=canonical_root, part_id="1",
        )


def test_approach_set_freeze_gates(tmp_path: Path) -> None:
    canonical_root = tmp_path / "canonical-authoring"
    write_truth_v2_multipart(canonical_root)
    ledger = _ledger(tmp_path)

    frozen2 = ta.freeze_approved_approach(
        _draft_part_approach(), tmp_path, reviewer_id="r", review_note="n",
        qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="2",
    )
    part1 = _draft_part_approach()
    part1["id"] = "t2"
    part1["part_id"] = "1"
    part1["title"] = "第(1)问：AA 判定证相似"
    part1["steps"][2]["narration"] = "两组对应角相等，AA 判定证得 $\\triangle ABE\\sim\\triangle EFC$。"
    frozen1 = ta.freeze_approved_approach(
        part1, tmp_path, reviewer_id="r", review_note="n",
        qt_id="QT-SMV-003", ledger_path=ledger, root=canonical_root, part_id="1",
    )
    set_payload = ta.freeze_approach_set(
        "QT-SMV-003",
        [
            {
                "part_id": "1",
                "approach": {
                    "artifact_id": frozen1["artifact_id"],
                    "version": frozen1["version"],
                    "content_hash": frozen1["content_hash"],
                },
            },
            {
                "part_id": "2",
                "approach": {
                    "artifact_id": frozen2["artifact_id"],
                    "version": frozen2["version"],
                    "content_hash": frozen2["content_hash"],
                },
            },
        ],
        reviewer_id="r",
        review_note="golden 选法",
        ledger_path=ledger,
        root=canonical_root,
        cross_part_rhythm="第(1)问的相似是第(2)问比例求解的台阶",
    )
    assert set_payload["artifact_id"] == "AS-SMV-001"
    assert set_payload["schema"] == "ai_teaching_approach_set/v1"
    ok, errors = validate_payload(set_payload)
    assert ok, errors
    # parts 与小问不一一对应 → fail closed（缺 part 1）
    with pytest.raises(ta.TeachingApproachError, match="不一一对应"):
        ta.freeze_approach_set(
            "QT-SMV-003", [{"part_id": "1", "approach": {}}, {"part_id": "3", "approach": {}}],
            reviewer_id="r", review_note="n", ledger_path=ledger, root=canonical_root,
        )
    # 引用不存在/非 current Approved 版本 → fail closed
    with pytest.raises(ta.TeachingApproachError, match="TA-SMV-999"):
        ta.freeze_approach_set(
            "QT-SMV-003",
            [
                {"part_id": "1", "approach": {"artifact_id": "TA-SMV-999", "version": "v1", "content_hash": frozen1["content_hash"]}},
                {"part_id": "2", "approach": {"artifact_id": frozen2["artifact_id"], "version": frozen2["version"], "content_hash": frozen2["content_hash"]}},
            ],
            reviewer_id="r", review_note="n", ledger_path=ledger, root=canonical_root,
        )
