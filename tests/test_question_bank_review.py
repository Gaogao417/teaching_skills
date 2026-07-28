from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".codex" / "skills" / "math-topic-question-bank"
SCRIPTS = PACKAGE / "scripts"
sys.path.insert(0, str(SCRIPTS))

from question_bank_review_server import create_question_bank_app  # noqa: E402


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def assignment(item_id: str, *, teacher: bool, diagram: dict | None = None) -> dict:
    block = {
        "type": "problem",
        "id": item_id,
        "stem_latex": "如图，求 $x$。\n保留第二行。<img src=x onerror=alert(1)>",
    }
    if diagram:
        block["diagram_col"] = diagram
    if teacher:
        block.update(
            {
                "answer": "$x=4$。",
                "explanation": "先找对应关系，再计算。",
                "solution_steps": [
                    {"title": "判断", "content": "确定对应边。"},
                    {"title": "计算", "content": "$x=8\\times\\frac12=4$。"},
                ],
            }
        )
    return {
        "meta": {"title": item_id},
        "sections": [{"id": "question", "type": "practice", "blocks": [block]}],
    }


def make_bank(root: Path, folder: str, bank_id: str, topic: str, *, count: int = 2) -> Path:
    bank_dir = root / folder
    items = []
    for index in range(1, count + 1):
        item_id = f"Q{index:03d}"
        item_dir = bank_dir / "items" / item_id
        prompt = item_dir / "prompt.png"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        solution = item_dir / "solution.svg"
        solution.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
        write_yaml(
            item_dir / "student.resolved.assignment.yaml",
            assignment(item_id, teacher=False, diagram={"image_path": "prompt.png", "variant": "prompt"}),
        )
        teacher_payload = assignment(item_id, teacher=True)
        teacher_payload["sections"][0]["blocks"][0]["answer_space"] = {
            "diagram_col": {"image_path": "solution.svg", "variant": "solution"}
        }
        write_yaml(item_dir / "teacher.resolved.assignment.yaml", teacher_payload)
        items.append(
            {
                "id": item_id,
                "title": f"题目 {index}",
                "question_type": "problem",
                "difficulty": "foundation" if index == 1 else "standard",
                "skill_tags": ["相似", "对应边"],
                "variation_dimension": "changed_numbers",
                "diagram_requirement": "prompt_and_solution",
                "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
                "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
                "weight": 1.0,
                "enabled": index == 1,
            }
        )
    write_yaml(
        bank_dir / "question-bank.yaml",
        {
            "schema": "math_topic_question_bank/v1",
            "bank": {
                "id": bank_id,
                "topic": topic,
                "grade": "八年级",
                "subject": "数学",
                "status": "ready",
                "target_count": count,
            },
            "items": items,
        },
    )
    return bank_dir


def make_staging(root: Path) -> tuple[Path, str]:
    paper_dir = root / "source-bank" / "staging" / "PAPER-A"
    item_dir = paper_dir / "items" / "Q001"
    assets = item_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in (
        "source-question.png",
        "prompt.png",
        "solution-diagram.png",
        "official-solution.png",
    ):
        (assets / name).write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    write_yaml(
        item_dir / "source.yaml",
        {
            "schema": "math_exam_item_source/v1",
            "item_id": "Q001",
            "source_key": "PAPER-A-Q01",
            "paper_id": "PAPER-A",
            "question_number": 1,
            "question_type": "choice",
            "points": 4,
            "section_title": "一、选择题",
            "source_directory": "documents/paper-a",
            "crops": {
                "question_evidence": [{"output": "assets/source-question.png"}],
                "prompt": [{"output": "assets/prompt.png"}],
                "solution": [{"output": "assets/solution-diagram.png"}],
                "official_solution": [{"output": "assets/official-solution.png"}],
            },
            "transcription": {
                "question_status": "author_pass",
                "official_solution_status": "author_pass",
                "independent_review": "pending",
                "human_review": "pending",
            },
            "content_hash": f"sha256:{'1' * 64}",
        },
    )
    student = assignment(
        "q1",
        teacher=False,
        diagram={"image_path": "assets/prompt.png", "variant": "prompt"},
    )
    student["sections"][0]["blocks"][0].update(
        {
            "type": "choice",
            "stem_latex": "下列结论正确的是（\\quad）。",
            "choices": {"A": "$1$", "B": "$2$"},
        }
    )
    teacher = assignment("q1", teacher=True)
    teacher_block = teacher["sections"][0]["blocks"][0]
    teacher_block.update(
        {
            "type": "choice",
            "stem_latex": "下列结论正确的是（\\quad）。",
            "choices": {"A": "$1$", "B": "$2$"},
            "answer": "B",
            "explanation": "公众号参考答案：B。",
            "solution_notes": [
                {"title": "严谨补充", "content_latex": "由定义可知答案为 $B$。"}
            ],
            "teaching": {"difficulty": "foundation", "skill_tags": ["定义", "判断"]},
        }
    )
    teacher_block["solution_steps"][0]["diagram_col"] = {
        "image_path": "assets/solution-diagram.png",
        "variant": "solution",
        "disclosure_policy": "teacher_only",
    }
    write_yaml(item_dir / "student.resolved.assignment.yaml", student)
    write_yaml(item_dir / "teacher.resolved.assignment.yaml", teacher)
    write_yaml(
        paper_dir / "paper.yaml",
        {
            "schema": "math_exam_paper/v1",
            "paper": {
                "id": "PAPER-A",
                "title": "A 区九年级数学",
                "grade": "九年级",
                "subject": "数学",
            },
            "question_bank": "../../question-bank.yaml",
            "sections": [{"id": "choice", "title": "一、选择题", "item_ids": ["Q001"]}],
        },
    )
    return paper_dir, "staging:source-bank:PAPER-A"


@pytest.fixture
def bank_root(tmp_path: Path) -> Path:
    root = tmp_path / "题库"
    make_bank(root, "2026-01-A", "bank-a", "A 专题")
    make_bank(root, "2026-02-B", "bank-b", "B 专题", count=1)
    write_yaml(root / "ignored" / "question-bank.yaml", {"schema": "wrong/v1", "bank": {"id": "ignored"}})
    return root


@pytest.fixture
def staging_root(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "题库"
    paper_dir, staging_id = make_staging(root)
    return root, paper_dir, staging_id


def test_discovers_valid_banks_in_stable_order_without_absolute_paths(bank_root: Path) -> None:
    client = TestClient(create_question_bank_app(bank_root, number_review_url="http://127.0.0.1:8876/"))
    response = client.get("/api/banks")

    assert response.status_code == 200
    payload = response.json()
    assert [bank["id"] for bank in payload["banks"]] == ["bank-a", "bank-b"]
    assert payload["banks"][0] == {
        "id": "bank-a",
        "kind": "formal_bank",
        "topic": "A 专题",
        "grade": "八年级",
        "subject": "数学",
        "status": "ready",
        "target_count": 2,
        "item_count": 2,
        "enabled_count": 1,
        "exam_type": "",
        "year": "",
        "district": "",
    }
    assert payload["number_review_url"] == "http://127.0.0.1:8876/"
    assert str(bank_root) not in response.text


def test_bank_detail_extracts_stem_answer_steps_and_preview_urls(bank_root: Path) -> None:
    client = TestClient(create_question_bank_app(bank_root))
    response = client.get("/api/banks/bank-a")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["Q001", "Q002"]
    item = payload["items"][0]
    assert item["stem_latex"].startswith("如图，求 $x$。\n保留第二行。")
    assert "<img src=x" in item["stem_latex"]
    assert item["answer"] == "$x=4$。"
    # explanation 是 legacy 字段，服务器按"待重转写"策略不回传（见 explanation→clue 重命名）。
    assert "explanation" not in item
    assert [step["title"] for step in item["solution_steps"]] == ["判断", "计算"]
    assert [step["content"] for step in item["solution_steps"]] == ["确定对应边。", "$x=8\\times\\frac12=4$。"]
    assert item["prompt_preview_url"].startswith("/api/assets/bank-a/Q001/prompt?v=")
    assert item["solution_preview_url"].startswith("/api/assets/bank-a/Q001/solution?v=")


def test_broken_item_is_local_and_unknown_bank_is_404(bank_root: Path) -> None:
    (bank_root / "2026-01-A/items/Q002/teacher.resolved.assignment.yaml").unlink()
    client = TestClient(create_question_bank_app(bank_root))

    payload = client.get("/api/banks/bank-a").json()
    assert "load_error" not in payload["items"][0]
    assert payload["items"][1]["load_error"]
    assert client.get("/api/banks/no-such-bank").status_code == 404


def test_asset_endpoint_serves_only_mapped_preview_files(bank_root: Path) -> None:
    client = TestClient(create_question_bank_app(bank_root))
    prompt = client.get("/api/assets/bank-a/Q001/prompt")
    solution = client.get("/api/assets/bank-a/Q001/solution")

    assert prompt.status_code == 200
    assert prompt.headers["content-type"] == "image/png"
    assert solution.status_code == 200
    assert solution.headers["content-type"] == "image/svg+xml"
    assert client.get("/api/assets/bank-a/Q001/../../question-bank.yaml").status_code in {400, 404}
    assert client.get("/api/assets/bank-a/Q001/other").status_code in {400, 404, 422}


def test_asset_endpoint_rejects_symlink_escape(bank_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    prompt = bank_root / "2026-01-A/items/Q001/prompt.png"
    prompt.unlink()
    prompt.symlink_to(outside)
    client = TestClient(create_question_bank_app(bank_root))

    assert client.get("/api/assets/bank-a/Q001/prompt").status_code in {400, 404}


def test_discovers_staging_exam_and_exposes_source_teacher_and_review_fields(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    listing = client.get("/api/banks").json()
    staging = next(bank for bank in listing["banks"] if bank["id"] == staging_id)
    assert staging["kind"] == "staging_exam"
    assert staging["topic"] == "A 区九年级数学"
    assert staging["item_count"] == 1
    assert staging["approved_count"] == 0

    detail = client.get(f"/api/banks/{staging_id}").json()
    item = detail["items"][0]
    assert item["stem_latex"] == "下列结论正确的是（\\quad）。"
    assert item["choices"] == {"A": "$1$", "B": "$2$"}
    assert item["answer"] == "B"
    # explanation 是 legacy 字段，服务器不回传（explanation→clue 重命名后旧卷待重转写）。
    assert "explanation" not in item
    assert item["difficulty"] == "foundation"
    assert item["skill_tags"] == ["定义", "判断"]
    assert item["solution_notes"][0]["title"] == "严谨补充"
    assert item["prompt_status"] == "author_pass"
    assert item["prompt_review_notes"] == []
    assert item["review"]["status"] == "pending"
    assert item["source_question_previews"][0]["url"].startswith(
        f"/api/assets/{staging_id}/Q001/source-question-0?v="
    )
    assert item["source_question_previews"][0]["title"] == "原题截图 1"
    assert item["prompt_previews"][0]["url"].startswith(
        f"/api/assets/{staging_id}/Q001/prompt-0?v="
    )
    assert item["prompt_previews"][0]["title"] == "题图 1"
    assert item["official_solution_previews"][0]["url"].startswith(
        f"/api/assets/{staging_id}/Q001/official-solution-0?v="
    )
    assert item["official_solution_previews"][0]["title"] == "官方解答原图 1"
    assert item["solution_steps"][0]["preview_url"].startswith(
        f"/api/assets/{staging_id}/Q001/solution-step-1?v="
    )
    assert client.get(item["source_question_previews"][0]["url"]).status_code == 200
    assert client.get(item["solution_steps"][0]["preview_url"]).status_code == 200
    assert str(root) not in client.get(f"/api/banks/{staging_id}").text


def test_staging_review_approve_reject_note_and_stale_detection(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    endpoint = f"/api/banks/{staging_id}/items/Q001/review"
    blank_revision = client.post(endpoint, json={"decision": "rejected", "note": "   "})
    assert blank_revision.status_code == 400
    assert "必须填写修改意见" in blank_revision.text
    assert not (paper_dir / "items/Q001/review.yaml").exists()

    approved = client.post(endpoint, json={"decision": "approved", "note": ""})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    review_path = paper_dir / "items/Q001/review.yaml"
    review = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    assert review == {
        "schema": "math_exam_item_review/v1",
        "item_id": "Q001",
        "source_key": "PAPER-A-Q01",
        "content_hash": f"sha256:{'1' * 64}",
        "status": "approved",
        "reviewer": "question-bank-review-ui",
        "reviewed_at": review["reviewed_at"],
        "notes": [],
    }
    assert datetime.fromisoformat(review["reviewed_at"]).tzinfo is not None

    source_path = paper_dir / "items/Q001/source.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source["content_hash"] = f"sha256:{'2' * 64}"
    write_yaml(source_path, source)
    stale = client.get(f"/api/banks/{staging_id}").json()["items"][0]["review"]
    assert stale["status"] == "approved"
    assert stale["stale"] is True

    rejected = client.post(endpoint, json={"decision": "rejected", "note": "公式需复核。"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["stale"] is False
    rewritten = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    assert rewritten["content_hash"] == f"sha256:{'2' * 64}"
    assert rewritten["notes"] == ["公式需复核。"]


def test_staging_detail_renders_string_format_solution_steps(
    staging_root: tuple[Path, Path, str],
) -> None:
    """旧卷 solution_steps 常是字符串数组（逐条复刻原解答），后端归一成 {content} 渲染。"""
    root, paper_dir, staging_id = staging_root
    teacher_path = paper_dir / "items/Q001/teacher.resolved.assignment.yaml"
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    teacher["sections"][0]["blocks"][0]["solution_steps"] = [
        "两个含有根式的代数式相乘，若积不含根式则互为有理化因式。",
        "$\\sqrt{a-4}\\cdot\\sqrt{a-4}=a-4$，结果不含根号，符合定义。",
    ]
    write_yaml(teacher_path, teacher)
    client = TestClient(create_question_bank_app(root))

    item = client.get(f"/api/banks/{staging_id}").json()["items"][0]
    assert [step["title"] for step in item["solution_steps"]] == ["", ""]
    assert item["solution_steps"][0]["content"].startswith("两个含有根式")
    assert item["solution_steps"][1]["content"].startswith("$\\sqrt{a-4}")
    # edit_target/edit_index 仍按位保留，前端解析图槽位不受格式影响。
    assert item["solution_steps"][0]["edit_target"] == "solution_step"
    assert item["solution_steps"][0]["edit_index"] == 0


def test_formal_detail_renders_string_format_solution_steps(bank_root: Path) -> None:
    """formal 题库路径同样要把字符串 solution_steps 归一成 {content}。"""
    teacher_path = bank_root / "2026-01-A/items/Q001/teacher.resolved.assignment.yaml"
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    teacher["sections"][0]["blocks"][0]["solution_steps"] = ["纯文字步骤。", "$x=4$。"]
    write_yaml(teacher_path, teacher)
    client = TestClient(create_question_bank_app(bank_root))

    item = client.get("/api/banks/bank-a").json()["items"][0]
    assert [step["content"] for step in item["solution_steps"]] == ["纯文字步骤。", "$x=4$。"]
    assert [step["title"] for step in item["solution_steps"]] == ["", ""]


def _add_second_staging_item(paper_dir: Path) -> None:
    """给 PAPER-A staging 卷追加 Q002，供 review-all 多题场景使用。"""
    item_dir = paper_dir / "items/Q002"
    assets = item_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "source-question.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    write_yaml(
        item_dir / "source.yaml",
        {
            "schema": "math_exam_item_source/v1",
            "item_id": "Q002",
            "source_key": "PAPER-A-Q02",
            "paper_id": "PAPER-A",
            "question_number": 2,
            "question_type": "fillin",
            "points": 4,
            "section_title": "二、填空题",
            "source_directory": "documents/paper-a",
            "crops": {"question_evidence": [{"output": "assets/source-question.png"}]},
            "transcription": {"human_review": "pending"},
            "content_hash": f"sha256:{'3' * 64}",
        },
    )
    student = assignment("q2", teacher=False)
    student["sections"][0]["blocks"][0].update(
        {"type": "fillin", "stem_latex": "计算 $2+2=$ \\underline{\\quad}。"}
    )
    teacher = assignment("q2", teacher=True)
    teacher["sections"][0]["blocks"][0].update(
        {
            "type": "fillin",
            "stem_latex": "计算 $2+2=$ \\underline{\\quad}。",
            "answer": "$4$",
            "solution_steps": ["$2+2=4$。"],
        }
    )
    write_yaml(item_dir / "student.resolved.assignment.yaml", student)
    write_yaml(item_dir / "teacher.resolved.assignment.yaml", teacher)
    paper_path = paper_dir / "paper.yaml"
    paper = yaml.safe_load(paper_path.read_text(encoding="utf-8"))
    paper["sections"].append({"id": "fillin", "title": "二、填空题", "item_ids": ["Q002"]})
    write_yaml(paper_path, paper)


def test_review_all_staging_approves_every_item_and_returns_summary(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    _add_second_staging_item(paper_dir)
    client = TestClient(create_question_bank_app(root))

    response = client.post(f"/api/banks/{staging_id}/review-all")
    assert response.status_code == 200
    payload = response.json()
    assert payload["errors"] == []
    # §9.2 推荐方案：bulk approve 返回 {counts, updated_reviews, errors}，
    # 不再重拉整卷 items；counts.approved 反映全卷通过结果。
    assert payload["counts"]["approved"] == 2
    assert set(payload["updated_reviews"]) == {"Q001", "Q002"}
    assert all(
        payload["updated_reviews"][item_id]["status"] == "approved"
        for item_id in ("Q001", "Q002")
    )
    # 两题 review.yaml 都写成 approved。
    for item_id in ("Q001", "Q002"):
        review = yaml.safe_load(
            (paper_dir / f"items/{item_id}/review.yaml").read_text(encoding="utf-8")
        )
        assert review["status"] == "approved"
        assert review["reviewer"] == "question-bank-review-ui"


def test_review_all_staging_collects_per_item_errors_without_aborting(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    _add_second_staging_item(paper_dir)
    # 删掉 Q002 的 source.yaml，让该题审核失败但 Q001 仍应成功。
    (paper_dir / "items/Q002/source.yaml").unlink()
    client = TestClient(create_question_bank_app(root))

    response = client.post(f"/api/banks/{staging_id}/review-all")
    assert response.status_code == 200
    payload = response.json()
    assert [error["item_id"] for error in payload["errors"]] == ["Q002"]
    # Q001 仍被通过；updated_reviews 只含成功的 Q001，Q002 缺席。
    assert set(payload["updated_reviews"]) == {"Q001"}
    q001_review = yaml.safe_load(
        (paper_dir / "items/Q001/review.yaml").read_text(encoding="utf-8")
    )
    assert q001_review["status"] == "approved"
    assert payload["counts"]["approved"] == 1


def test_review_all_rejects_formal_bank_with_404(bank_root: Path) -> None:
    client = TestClient(create_question_bank_app(bank_root))
    # formal 题库不是 staging，review-all 应 404。
    assert client.post("/api/banks/bank-a/review-all").status_code == 404


def test_staging_review_and_assets_reject_path_or_symlink_escape(
    staging_root: tuple[Path, Path, str], tmp_path: Path
) -> None:
    root, paper_dir, staging_id = staging_root
    item_dir = paper_dir / "items/Q001"
    outside = tmp_path / "outside.yaml"
    outside.write_text("safe: true\n", encoding="utf-8")
    (item_dir / "review.yaml").symlink_to(outside)
    client = TestClient(create_question_bank_app(root))

    response = client.post(
        f"/api/banks/{staging_id}/items/Q001/review",
        json={"decision": "approved", "note": ""},
    )
    assert response.status_code == 400
    assert outside.read_text(encoding="utf-8") == "safe: true\n"
    assert client.post(
        f"/api/banks/{staging_id}/items/../../review",
        json={"decision": "approved", "note": ""},
    ).status_code in {400, 404, 405}
    assert client.get(
        f"/api/assets/{staging_id}/Q001/../../source.yaml"
    ).status_code in {400, 404}


def pasted_png(size: tuple[int, int] = (96, 64), color: str = "navy") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def test_staging_prompt_image_can_be_replaced_from_clipboard_and_stales_review(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    review_endpoint = f"/api/banks/{staging_id}/items/Q001/review"
    assert client.post(
        review_endpoint, json={"decision": "approved", "note": ""}
    ).status_code == 200

    response = client.post(
        f"/api/banks/{staging_id}/items/Q001/images/prompt/0",
        content=pasted_png(),
        headers={"Content-Type": "image/png"},
    )

    assert response.status_code == 200
    item = response.json()
    assert item["review"]["status"] == "approved"
    assert item["review"]["stale"] is True
    assert item["prompt_status"] == "review_pass"
    assert item["prompt_review_notes"] == []
    assert item["prompt_previews"][0]["edit_target"] == "prompt"
    assert item["prompt_previews"][0]["edit_index"] == 0

    item_dir = paper_dir / "items/Q001"
    source = yaml.safe_load((item_dir / "source.yaml").read_text(encoding="utf-8"))
    crop = source["crops"]["prompt"][0]
    assert crop["box_px"] == [0, 0, 96, 64]
    assert crop["source_sha256"] == crop["output_sha256"]
    assert crop["output"].startswith("assets/manual-prompt-1-")
    manual_image = item_dir / crop["output"]
    assert manual_image.is_file()
    with Image.open(manual_image) as image:
        assert image.size == (96, 64)

    teacher = yaml.safe_load(
        (item_dir / "teacher.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    student = yaml.safe_load(
        (item_dir / "student.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    assert teacher["sections"][0]["blocks"][0]["diagram_col"]["image_path"] == crop["output"]
    assert student["sections"][0]["blocks"][0]["diagram_col"]["image_path"] == crop["output"]
    assert source["content_hash"] != f"sha256:{'1' * 64}"
    assert client.get(item["prompt_previews"][0]["url"]).status_code == 200


def test_staging_missing_solution_step_image_can_be_pasted_teacher_only(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    item_dir = paper_dir / "items/Q001"
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    teacher["sections"][0]["blocks"][0]["solution_steps"][0].pop("diagram_col")
    write_yaml(teacher_path, teacher)
    source_path = item_dir / "source.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source["crops"]["solution"] = []
    write_yaml(source_path, source)
    client = TestClient(create_question_bank_app(root))

    response = client.post(
        f"/api/banks/{staging_id}/items/Q001/images/solution_step/0",
        content=pasted_png((80, 120), "white"),
        headers={"Content-Type": "image/png"},
    )

    assert response.status_code == 200
    item = response.json()
    assert item["solution_steps"][0]["preview_url"]
    assert item["solution_steps"][0]["edit_target"] == "solution_step"
    rewritten_teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    diagram = rewritten_teacher["sections"][0]["blocks"][0]["solution_steps"][0]["diagram_col"]
    assert diagram["variant"] == "solution"
    rewritten_student = yaml.safe_load(
        (item_dir / "student.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    assert "solution_steps" not in rewritten_student["sections"][0]["blocks"][0]


def test_staging_prompt_replacement_preserves_stem_image_layout(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    item_dir = paper_dir / "items/Q001"
    for name in ("teacher.resolved.assignment.yaml", "student.resolved.assignment.yaml"):
        path = item_dir / name
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        block = payload["sections"][0]["blocks"][0]
        block.pop("diagram_col", None)
        block["stem_image"] = {
            "image_path": "assets/prompt.png",
            "width": "0.82\\linewidth",
            "variant": "prompt",
            "disclosure_policy": "clean",
        }
        write_yaml(path, payload)
    client = TestClient(create_question_bank_app(root))

    response = client.post(
        f"/api/banks/{staging_id}/items/Q001/images/prompt/0",
        content=pasted_png(),
        headers={"Content-Type": "image/png"},
    )

    assert response.status_code == 200
    teacher = yaml.safe_load(
        (item_dir / "teacher.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    block = teacher["sections"][0]["blocks"][0]
    assert "diagram_col" not in block
    assert block["stem_image"]["image_path"].startswith("assets/manual-prompt-")
    assert block["stem_image"]["width"] == "0.82\\linewidth"


def test_staging_prompt_image_can_be_removed_from_slot_without_deleting_asset(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    item_dir = paper_dir / "items/Q001"
    original_asset = item_dir / "assets/prompt.png"
    client = TestClient(create_question_bank_app(root))
    assert client.post(
        f"/api/banks/{staging_id}/items/Q001/review",
        json={"decision": "approved", "note": ""},
    ).status_code == 200

    response = client.delete(
        f"/api/banks/{staging_id}/items/Q001/images/prompt/0"
    )

    assert response.status_code == 200
    item = response.json()
    assert item["prompt_previews"] == []
    assert item["prompt_status"] == "needs_human_crop"
    assert item["prompt_review_notes"]
    assert item["review"]["stale"] is True
    assert original_asset.is_file()
    source = yaml.safe_load((item_dir / "source.yaml").read_text(encoding="utf-8"))
    assert source["crops"]["prompt"] == []
    for name in ("teacher.resolved.assignment.yaml", "student.resolved.assignment.yaml"):
        payload = yaml.safe_load((item_dir / name).read_text(encoding="utf-8"))
        block = payload["sections"][0]["blocks"][0]
        assert "diagram_col" not in block
        assert "stem_image" not in block


def test_staging_solution_step_image_can_be_removed_teacher_only(
    staging_root: tuple[Path, Path, str],
) -> None:
    root, paper_dir, staging_id = staging_root
    item_dir = paper_dir / "items/Q001"
    client = TestClient(create_question_bank_app(root))

    response = client.delete(
        f"/api/banks/{staging_id}/items/Q001/images/solution_step/0"
    )

    assert response.status_code == 200
    assert response.json()["solution_steps"][0]["preview_url"] is None
    source = yaml.safe_load((item_dir / "source.yaml").read_text(encoding="utf-8"))
    assert source["crops"]["solution"] == []
    teacher = yaml.safe_load(
        (item_dir / "teacher.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    assert "diagram_col" not in teacher["sections"][0]["blocks"][0]["solution_steps"][0]


def test_staging_official_solution_gallery_supports_add_append_replace_remove(
    staging_root: tuple[Path, Path, str],
) -> None:
    """解答图按题目管理：official_solution 支持替换、连续追加、按位删除，
    并同步 source_solution_images；学生版派生时移除解答图。"""
    root, paper_dir, staging_id = staging_root
    item_dir = paper_dir / "items/Q001"
    source_path = item_dir / "source.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    # 起点为空解答图（保留原 question/prompt/solution 裁切）。
    source["crops"]["official_solution"] = []
    write_yaml(source_path, source)
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    teacher["sections"][0]["blocks"][0].pop("source_solution_images", None)
    write_yaml(teacher_path, teacher)
    client = TestClient(create_question_bank_app(root))

    base = f"/api/banks/{staging_id}/items/Q001/images/official_solution"

    # 1) 空图库追加第一张。
    first = client.post(
        f"{base}/0",
        content=pasted_png((100, 50), "white"),
        headers={"Content-Type": "image/png"},
    )
    assert first.status_code == 200
    item = first.json()
    assert [p["edit_target"] for p in item["official_solution_previews"]] == ["official_solution"]
    assert [p["edit_index"] for p in item["official_solution_previews"]] == [0]
    # 写图后 content_hash 必须被刷新（图片变化会让此前审核决定过期）。
    assert item["content_hash"] != f"sha256:{'1' * 64}"
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    images = teacher["sections"][0]["blocks"][0]["source_solution_images"]
    assert len(images) == 1
    assert images[0]["variant"] == "source_solution"
    assert images[0]["disclosure_policy"] == "teacher_only"

    # 2) 连续追加第二张（index == 现有数量）。
    second = client.post(
        f"{base}/1",
        content=pasted_png((80, 80), "black"),
        headers={"Content-Type": "image/png"},
    )
    assert second.status_code == 200
    assert len(second.json()["official_solution_previews"]) == 2
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    assert len(teacher["sections"][0]["blocks"][0]["source_solution_images"]) == 2

    # 3) 替换第 0 张（index 0 已存在）。
    replaced = client.post(
        f"{base}/0",
        content=pasted_png((64, 64), "navy"),
        headers={"Content-Type": "image/png"},
    )
    assert replaced.status_code == 200
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    assert len(teacher["sections"][0]["blocks"][0]["source_solution_images"]) == 2

    # 4) 学生版不含解答图。
    student = yaml.safe_load(
        (item_dir / "student.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    assert "source_solution_images" not in student["sections"][0]["blocks"][0]

    # 5) 删除第 1 张，剩余 1 张。
    deleted = client.delete(f"{base}/1")
    assert deleted.status_code == 200
    assert len(deleted.json()["official_solution_previews"]) == 1
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    assert len(teacher["sections"][0]["blocks"][0]["source_solution_images"]) == 1

    # 6) 越界追加被拒。
    assert client.post(
        f"{base}/5",
        content=pasted_png(),
        headers={"Content-Type": "image/png"},
    ).status_code == 400

    # 7) 解答步图编辑入口（solution_step）在 staging 仍可用，且与解答图分区。
    step_post = client.post(
        f"/api/banks/{staging_id}/items/Q001/images/solution_step/0",
        content=pasted_png((70, 70), "white"),
        headers={"Content-Type": "image/png"},
    )
    assert step_post.status_code == 200
    assert step_post.json()["solution_steps"][0]["edit_target"] == "solution_step"


def test_image_replacement_rejects_non_images_formal_banks_and_bad_indexes(
    staging_root: tuple[Path, Path, str],
    bank_root: Path,
) -> None:
    root, _, staging_id = staging_root
    staging_client = TestClient(create_question_bank_app(root))
    endpoint = f"/api/banks/{staging_id}/items/Q001/images/prompt/0"
    assert staging_client.post(
        endpoint, content=b"not an image", headers={"Content-Type": "text/plain"}
    ).status_code == 415
    assert staging_client.post(
        endpoint, content=b"not an image", headers={"Content-Type": "image/png"}
    ).status_code == 400
    assert staging_client.post(
        f"/api/banks/{staging_id}/items/Q001/images/prompt/2",
        content=pasted_png(),
        headers={"Content-Type": "image/png"},
    ).status_code == 400

    formal_client = TestClient(create_question_bank_app(bank_root))
    assert formal_client.post(
        "/api/banks/bank-a/items/Q001/images/prompt/0",
        content=pasted_png(),
        headers={"Content-Type": "image/png"},
    ).status_code == 404
    assert formal_client.delete(
        "/api/banks/bank-a/items/Q001/images/prompt/0"
    ).status_code == 404


def test_page_uses_review_assets_and_reciprocal_navigation(bank_root: Path) -> None:
    client = TestClient(create_question_bank_app(bank_root, number_review_url="http://localhost:9991/"))
    page = client.get("/")

    assert page.status_code == 200
    assert "专题题库审核" in page.text
    assert 'id="bank-select"' in page.text
    assert 'id="question-list"' in page.text
    assert "/static/question-bank-review.css" in page.text
    assert "/static/question-bank-review.js" in page.text
    assert "/static/question-bank-review.css?v=" in page.text
    assert "/static/question-bank-review.js?v=" in page.text
    assert "__STATIC_VERSION__" not in page.text
    assert page.headers["cache-control"] == "no-store"
    assert "http://localhost:9991/" in page.text


def test_static_ui_preserves_inert_text_responsive_layout_and_native_controls() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")
    css = (PACKAGE / "static/question-bank-review.css").read_text(encoding="utf-8")

    assert '<select id="bank-select"' in template
    assert '<ul id="choices" class="choice-list"></ul>' in template
    assert 'id="prompt-review-alert"' in template
    assert 'id="prompt-review-notes"' in template
    assert 'id="previous-item"' in template and 'id="next-item"' in template
    assert "textContent" in script
    assert "choiceLabel(key, index)" in script
    assert "stripEmbeddedChoiceLabel(value)" in script
    assert 'item.prompt_status === "needs_human_crop"' in script
    assert "item.stem_latex" not in "".join(
        line for line in script.splitlines() if "innerHTML" in line
    )
    assert ".choice-list { margin: 0; padding: 0; list-style: none; }" in css
    assert "white-space: pre-wrap" in css
    assert "object-fit: contain" in css
    assert "@media (max-width: 760px)" in css
    assert "min-height: 42px" in css


def test_staging_image_slots_support_select_paste_delete_and_add() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")
    css = (PACKAGE / "static/question-bank-review.css").read_text(encoding="utf-8")

    assert 'id="image-dialog"' not in template
    assert "function selectImageSlot" in script
    assert "selectedImageSlot" in script
    assert 'addEventListener("paste"' in script
    assert "imageItem.getAsFile()" in script
    assert "function uploadPastedImage" in script
    assert "function deleteImageSlot" in script
    assert "/images/${encodeURIComponent(target.target)}/${target.index}" in script
    assert '{ method: "DELETE" }' in script
    assert "image-delete-button" in script
    # source-lightbox 重构后，新增图片改为点击 .image-section 空白区（wireImageSections
    # + emptyAddHint），不再用独立的 image-add-slot 控件。
    assert "function wireImageSections" in script
    assert "function emptyAddHint" in script
    assert "点击选中 · ⌘V 替换" in script
    assert 'editTarget: "prompt"' in script
    assert 'editTarget: "question_evidence"' not in script
    # 解答图改为按题目管理：official_solution 作为可编辑 image-section，不再绑定解题步骤。
    assert 'editTarget: "official_solution"' in script
    assert ".image-delete-button" in css
    assert ".empty-add-hint" in css
    assert ".is-selected" in css


def test_staging_solution_image_gallery_is_topic_level_and_steps_readonly() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")

    # 独立的题目级“解答图”图库 section，编辑目标为 official_solution。
    assert 'data-image-target="official_solution"' in template
    assert 'id="official-solution-preview"' in template
    assert 'official_solution: { label: "解答图"' in script
    # 解题步骤不再作为图片编辑入口：旧 step.preview_url 只读显示。
    assert "if (step.preview_url)" in script
    assert 'figure.className = "step-preview"' in script
    # 解题步骤不再生成可编辑空槽 / 选中替换提示。
    assert "wireImageSlot(figure, step.edit_target" not in script
    assert 'figure.className = "step-preview is-empty"' not in script
    # 解答图保存成功提示原审核过期。
    assert "该题此前的人工审核已自动过期" in script
    # 正式题库不显示解答图编辑入口（section 默认 hidden，仅 staging 取消隐藏）。
    assert '.closest(".image-section")' in script


def test_review_shortcuts_revision_dialog_and_audio_feedback_are_wired() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")

    assert 'id="revision-dialog"' in template
    assert 'id="revision-note"' in template
    assert 'id="revision-form"' in template
    assert "要求修改 <kbd>R</kbd>" in template
    assert "通过 <kbd>A</kbd>" in template
    assert "<kbd>←</kbd> 上一题" in template
    assert "下一题 <kbd>→</kbd>" in template
    assert 'document.addEventListener("keydown"' in script
    assert 'key === "a"' in script and 'key === "r"' in script
    assert 'event.key === "ArrowLeft"' in script
    assert 'event.key === "ArrowRight"' in script
    assert "event.repeat" in script
    assert "isEditableTarget" in script
    assert "requestSubmit" in script
    assert 'event.key === "Escape"' in script
    assert "AudioContext" in script
    assert "playApprovalSound" in script
    assert "playPageTurnSound" in script
    assert "function reviewNeedsAttention(item)" in script
    assert "function findNextReviewIndex(currentIndex)" in script
    assert "(currentIndex + offset) % items.length" in script
    assert "updateStagingProgress()" in script
    assert "本卷已经没有待审核题目" in script


def test_question_bank_review_loads_and_retypesets_mathjax_safely() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")

    assert "window.MathJax" in template
    assert "https://cdn.jsdelivr.net/npm/mathjax@4/tex-mml-chtml.js" in template
    assert "inlineMath" in template and "displayMath" in template
    assert "typesetClear" in script
    assert "typesetPromise" in script
    assert "#reader" not in template.split("window.MathJax", 1)[0]
    assert "math-render-status" not in template
    assignment_inner_html = [
        line for line in script.splitlines()
        if "innerHTML" in line and any(field in line for field in ("stem", "answer", "explanation", "step"))
    ]
    assert assignment_inner_html == []


def test_question_bank_review_formats_latex_enumerate_for_mathjax() -> None:
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")

    assert "function formatReviewText(value)" in script
    assert r"\\begin\{enumerate\}" in script
    assert r"\\end\{enumerate\}" in script
    assert r"\\item" in script
    assert 'setText("stem", formatReviewText(' in script
    assert "content.textContent = formatReviewText(step.content)" in script


def test_question_bank_review_formats_fillin_as_visible_blank() -> None:
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")

    assert r"\\fillin(?:\[[^\]]*\])?(?:\{[^}]*\})?" in script
    assert '"＿＿＿＿＿＿"' in script
    assert "const withFillinBlanks" in script
    assert '.replace(/\\\\because/g, "∵")' in script
    assert '.replace(/\\\\therefore/g, "∴")' in script


def test_question_bank_review_renders_solution_step_diagrams() -> None:
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")
    css = (PACKAGE / "static/question-bank-review.css").read_text(encoding="utf-8")

    assert "if (step.preview_url)" in script
    assert 'figure.className = "step-preview"' in script
    assert "step.preview_title" in script
    assert ".step-preview img" in css


def test_question_list_is_compact_and_previews_on_hover_or_focus() -> None:
    template = (PACKAGE / "templates/question-bank-review.html").read_text(encoding="utf-8")
    script = (PACKAGE / "static/question-bank-review.js").read_text(encoding="utf-8")
    render_list = script.split("function renderList()", 1)[1].split("function applyItem", 1)[0]

    assert "math-render-status" not in template
    assert "detail.status" not in script
    assert "item.difficulty" not in render_list
    assert 'addEventListener("mouseenter"' in render_list
    assert 'addEventListener("focus"' in render_list


def test_number_review_has_question_bank_link() -> None:
    template = (PACKAGE / "templates/training-number-review.html").read_text(encoding="utf-8")
    assert "题库" in template
    assert "__QUESTION_BANK_REVIEW_URL__" in template
