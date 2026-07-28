"""Review-server 读模型（Catalog Snapshot + AssetIndex + 批量审核）的回归测试。

覆盖设计文档 ``docs/review-server-performance-redesign.md`` §12.1/§12.2：
- snapshot 在多次读请求间被复用（不再每个请求全量 discover）。
- ``approve_all_staging`` 内 ``record()`` 只调用一次（A8 核心）。
- 并发"边审核边读"始终拿到 counts 与 items review 状态一致的快照。
- AssetIndex 在图片原地替换后用新 mtime 服务新内容（?v= 缓存破坏）。
- ``/healthz`` 不再触发全量 discover（A9）。
"""

from __future__ import annotations

import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex" / "skills" / "math-topic-question-bank" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from question_bank_review_server import create_question_bank_app  # noqa: E402


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def assignment(item_id: str, *, teacher: bool, diagram: dict | None = None) -> dict:
    block: dict = {
        "type": "problem",
        "id": item_id,
        "stem_latex": "求 $x$。",
    }
    if diagram:
        block["diagram_col"] = diagram
    if teacher:
        block.update(
            {
                "answer": "$x=4$。",
                "solution_steps": [{"title": "计算", "content": "$x=4$。"}],
            }
        )
    return {
        "meta": {"title": item_id},
        "sections": [{"id": "question", "type": "practice", "blocks": [block]}],
    }


def make_staging(root: Path, *, second_item: bool = False) -> tuple[Path, str]:
    """两题 staging 试卷：Q001 带 prompt 图，可选追加 Q002。"""
    paper_dir = root / "source-bank" / "staging" / "PAPER-A"
    item_dir = paper_dir / "items" / "Q001"
    assets = item_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("source-question.png", "prompt.png"):
        (assets / name).write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    write_yaml(
        item_dir / "source.yaml",
        {
            "schema": "math_exam_item_source/v1",
            "item_id": "Q001",
            "source_key": "PAPER-A-Q01",
            "paper_id": "PAPER-A",
            "question_number": 1,
            "question_type": "problem",
            "points": 4,
            "section_title": "一、选择题",
            "source_directory": "documents/paper-a",
            "crops": {
                "question_evidence": [{"output": "assets/source-question.png"}],
                "prompt": [{"output": "assets/prompt.png"}],
            },
            "transcription": {"prompt_status": "author_pass"},
            "content_hash": f"sha256:{'1' * 64}",
        },
    )
    write_yaml(
        item_dir / "student.resolved.assignment.yaml",
        assignment(
            "q1",
            teacher=False,
            diagram={"image_path": "assets/prompt.png", "variant": "prompt"},
        ),
    )
    teacher = assignment("q1", teacher=True)
    teacher["sections"][0]["blocks"][0]["teaching"] = {"difficulty": "foundation"}
    write_yaml(item_dir / "teacher.resolved.assignment.yaml", teacher)
    sections = [{"id": "choice", "title": "一、选择题", "item_ids": ["Q001"]}]
    if second_item:
        q2_dir = paper_dir / "items" / "Q002"
        q2_assets = q2_dir / "assets"
        q2_assets.mkdir(parents=True, exist_ok=True)
        (q2_assets / "source-question.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        write_yaml(
            q2_dir / "source.yaml",
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
        write_yaml(q2_dir / "student.resolved.assignment.yaml", assignment("q2", teacher=False))
        q2_teacher = assignment("q2", teacher=True)
        q2_teacher["sections"][0]["blocks"][0]["solution_steps"] = ["$2+2=4$。"]
        write_yaml(q2_dir / "teacher.resolved.assignment.yaml", q2_teacher)
        sections.append({"id": "fillin", "title": "二、填空题", "item_ids": ["Q002"]})
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
            "sections": sections,
        },
    )
    return paper_dir, "staging:source-bank:PAPER-A"


def pasted_png(size: tuple[int, int] = (96, 64), color: str = "navy") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def staging_root(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "题库"
    paper_dir, staging_id = make_staging(root, second_item=True)
    return root, paper_dir, staging_id


# ---------------------------------------------------------------- snapshot 复用


def test_snapshot_caches_across_read_requests(staging_root: tuple[Path, Path, str]) -> None:
    """两次 /api/banks 之间只 discover 一次（A1/A4：snapshot 命中后不再全量扫描）。"""
    root, _, _ = staging_root
    client = TestClient(create_question_bank_app(root))
    before = client.app.state.catalog.discover_count
    client.get("/api/banks")
    after_first = client.app.state.catalog.discover_count
    client.get("/api/banks")
    client.get("/api/banks/facets")
    after_repeated = client.app.state.catalog.discover_count

    assert after_first == before + 1, "首次请求应触发一次全量构建"
    assert after_repeated == after_first, "后续读请求应命中 snapshot，不再 discover"


def test_healthz_does_not_trigger_full_discover(staging_root: tuple[Path, Path, str]) -> None:
    """/healthz 不应是放大器（A9）：只读 snapshot，不额外 discover。"""
    root, _, _ = staging_root
    client = TestClient(create_question_bank_app(root))
    client.get("/api/banks")  # 预热 snapshot
    warmed = client.app.state.catalog.discover_count
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ready"] is True
    assert body["banks"] == 1
    assert client.app.state.catalog.discover_count == warmed


# ---------------------------------------------------------------- 批量审核（A8）


def test_approve_all_staging_records_bank_once(staging_root: tuple[Path, Path, str]) -> None:
    """A8 核心：25 题也不应 25 次 discover。bulk approve 内 record() 只调用 1 次。"""
    root, paper_dir, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    catalog = client.app.state.catalog

    record_calls = {"count": 0}
    original_record = catalog.record

    def counting_record(bank_id: str):
        record_calls["count"] += 1
        return original_record(bank_id)

    catalog.record = counting_record  # type: ignore[assignment]
    try:
        response = client.post(f"/api/banks/{staging_id}/review-all")
    finally:
        catalog.record = original_record  # type: ignore[assignment]

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["approved"] == 2
    # bulk approve 在循环外只 discover 一次；循环内走 _write_staging_review_with_record。
    assert record_calls["count"] == 1, (
        f"bulk approve 应只 record() 一次，实际 {record_calls['count']} 次（A8 回归）"
    )


# ---------------------------------------------------------------- 并发一致性（§12.2）


def test_concurrent_read_during_bulk_approve_sees_consistent_snapshot(
    staging_root: tuple[Path, Path, str],
) -> None:
    """边审核边搜索：读线程始终拿到 counts 与 items review 状态一致的完整快照。

    不应出现"counts.approved==2 但 items 里仍有 pending"这种半更新视图。
    """
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    client.get("/api/banks")  # 预热

    inconsistencies: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            detail = client.get(f"/api/banks/{staging_id}").json()
            items = detail.get("items", [])
            approved_items = sum(
                1
                for item in items
                if (item.get("review") or {}).get("status") == "approved"
                and not (item.get("review") or {}).get("stale")
            )
            declared = detail.get("approved_count", 0)
            # 允许审核进行中 approved_items < declared（读快照先于写完成），
            # 但不允许 declared 全通过(==item_count)却仍有 pending item（半更新）。
            if declared == len(items) and approved_items != len(items):
                inconsistencies.append(
                    f"counts.approved={declared}==item_count 但只 {approved_items} 题 approved"
                )
            time.sleep(0.001)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for _ in range(3):
            pool.submit(reader)
        # 主线程驱动多次 bulk approve（每次重建 snapshot），制造并发窗口。
        for _ in range(5):
            client.post(f"/api/banks/{staging_id}/review-all")
            # 审核之间重置一题让 bulk approve 有实际工作（reject 后再 bulk approve）。
            client.post(
                f"/api/banks/{staging_id}/items/Q001/review",
                json={"decision": "rejected", "note": "复核"},
            )
        stop.set()

    assert not inconsistencies, (
        "并发期间观察到 counts/items 不一致的半更新快照：\n" + "\n".join(inconsistencies)
    )


# ---------------------------------------------------------------- AssetIndex ?v=（§12.1）


def test_asset_index_serves_replaced_image_with_new_version(
    staging_root: tuple[Path, Path, str],
) -> None:
    """图片原地替换后，/api/assets 的 ?v= 必须变化且返回新内容（?v= 缓存破坏）。"""
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))

    detail = client.get(f"/api/banks/{staging_id}").json()
    original_url = detail["items"][0]["prompt_previews"][0]["url"]
    original_bytes = client.get(original_url).content
    warmed_discover_count = client.app.state.catalog.discover_count

    # 替换 prompt 图：不同尺寸/颜色的 PNG，确保字节不同。
    response = client.post(
        f"/api/banks/{staging_id}/items/Q001/images/prompt/0",
        content=pasted_png((48, 48), "maroon"),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 200
    # UI 内部写只刷新当前 bank，不能重新 discover / 全量重建所有题库。
    assert client.app.state.catalog.discover_count == warmed_discover_count
    assert response.json()["prompt_previews"][0]["url"] != original_url

    refreshed = client.get(f"/api/banks/{staging_id}").json()
    new_url = refreshed["items"][0]["prompt_previews"][0]["url"]
    # URL 的 ?v= 必须随新 mtime 变化，否则浏览器会显示旧图。
    assert new_url != original_url, "换图后 ?v= 未更新，浏览器会命中旧缓存"
    assert new_url.split("/api/assets/", 1)[1].startswith("staging:source-bank:PAPER-A/Q001/prompt-0")
    new_bytes = client.get(new_url).content
    assert new_bytes != original_bytes, "换图后服务端仍返回旧文件内容"
    with Image.open(io.BytesIO(new_bytes)) as image:
        assert image.size == (48, 48)


# ---------------------------------------------------------------- 阶段 4/5：bootstrap + 目录 + 单题


def test_bootstrap_returns_summaries_facets_errors_in_one_call(
    staging_root: tuple[Path, Path, str],
) -> None:
    """§8.1：bootstrap 一次返回 banks + facets + errors + number_review_url，且读 snapshot O(1)。"""
    root, _, _ = staging_root
    client = TestClient(create_question_bank_app(root))
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) >= {"banks", "facets", "errors", "number_review_url"}
    # 与单独接口语义一致：banks 等于 /api/banks，facets 等于 /api/banks/facets。
    banks_payload = client.get("/api/banks").json()
    facets_payload = client.get("/api/banks/facets").json()
    assert payload["banks"] == banks_payload["banks"]
    assert payload["facets"] == {
        key: facets_payload[key] for key in ("kinds", "grades", "years", "exam_types")
    }
    assert payload["errors"] == banks_payload["errors"]


def test_bootstrap_does_not_extra_discover(staging_root: tuple[Path, Path, str]) -> None:
    """bootstrap 走 snapshot，热态不额外 discover（与 /api/banks 同纪律）。"""
    root, _, _ = staging_root
    client = TestClient(create_question_bank_app(root))
    client.get("/api/banks")  # 预热
    warmed = client.app.state.catalog.discover_count
    client.get("/api/bootstrap")
    assert client.app.state.catalog.discover_count == warmed


def test_paper_directory_is_lightweight(staging_root: tuple[Path, Path, str]) -> None:
    """§8.3：?directory=1 返回轻量目录，items 只有 id/title/review_status/stale，无 solution_steps。"""
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    directory = client.get(f"/api/banks/{staging_id}?directory=1").json()
    assert directory["id"] == staging_id
    assert directory["kind"] == "staging_exam"
    assert set(directory["counts"].keys()) == {"approved", "rejected", "stale"}
    assert directory["item_count"] == 2
    assert len(directory["items"]) == 2
    item = directory["items"][0]
    assert set(item.keys()) == {"id", "title", "review_status", "stale"}
    assert item["review_status"] == "pending"
    assert item["stale"] is False
    # 默认（不带 directory）仍返回整卷完整 detail（§14 兼容）。
    full = client.get(f"/api/banks/{staging_id}").json()
    assert "solution_steps" in full["items"][0]
    assert "counts" not in full  # 整卷形态用 approved_count 顶层字段，不是 counts 子对象


def test_single_item_endpoint_matches_full_detail_item(
    staging_root: tuple[Path, Path, str],
) -> None:
    """§8.3：GET /api/banks/{id}/items/{item_id} 返回的单题与整卷 items[0] 完全一致（snapshot O(1) 命中）。"""
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    full = client.get(f"/api/banks/{staging_id}").json()
    first_id = full["items"][0]["id"]
    single = client.get(f"/api/banks/{staging_id}/items/{first_id}").json()
    assert single == full["items"][0], "单题接口应直接回 snapshot.items_by_bank_item 的引用"


def test_single_item_and_directory_404s(staging_root: tuple[Path, Path, str]) -> None:
    """单题/目录接口对不存在的 bank/item 返回 404。"""
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    assert client.get(f"/api/banks/{staging_id}/items/ZZZ").status_code == 404
    assert client.get("/api/banks/nope?directory=1").status_code == 404
    # 不存在的 bank 取单题也 404（不抛 500）。
    assert client.get("/api/banks/nope/items/Q001").status_code == 404


def test_healthz_stats_field_is_present_and_non_breaking(
    staging_root: tuple[Path, Path, str],
) -> None:
    """§11 阶段 0：/healthz 追加 stats 字段，原有 ok/ready/banks/errors 契约不变。"""
    root, _, _ = staging_root
    client = TestClient(create_question_bank_app(root))
    body = client.get("/healthz").json()
    for key in ("ok", "ready", "banks", "errors", "stats"):
        assert key in body
    stats = body["stats"]
    for key in (
        "discover_count", "yaml_parse_count", "snapshot_hits", "snapshot_misses",
        "asset_index_hits", "asset_index_misses", "snapshot_generation",
    ):
        assert key in stats
    assert stats["discover_count"] == 1
    assert stats["snapshot_generation"] == 1


# ---------------------------------------------------------------- 阶段 6：reindex + catalog-version + 外部写


def test_reindex_bank_and_all(staging_root: tuple[Path, Path, str]) -> None:
    """§8.5：POST /api/admin/reindex 精准/全量两种形态都返回新 generation，未知的 bank 404。"""
    root, _, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    before = client.app.state.catalog.snapshot().generation

    precise = client.post(f"/api/admin/reindex?bank={staging_id}").json()
    assert precise["ok"] is True
    assert precise["banks"] == 1
    assert precise["generation"] > before

    full = client.post("/api/admin/reindex").json()
    assert full["ok"] is True
    assert full["generation"] > precise["generation"]

    assert client.post("/api/admin/reindex?bank=nope").status_code == 404


def test_catalog_version_bump_triggers_rebuild(
    staging_root: tuple[Path, Path, str],
) -> None:
    """§5.3：bump .catalog-version 后，读路由返回新内容（不受约束外部写的快速路径）。"""
    root, paper_dir, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    # 先预热，让 snapshot 记下当前 .catalog-version（若有）/指纹。
    before = client.get(f"/api/banks/{staging_id}").json()
    gen_before = client.app.state.catalog.snapshot().generation

    # bump .catalog-version 文件（模拟受控 writer）。
    bumped = client.app.state.catalog.bump_catalog_version(staging_id)
    assert bumped is True
    version_file = paper_dir / ".catalog-version"
    assert version_file.is_file()

    # 下一次读该 bank 应重建（ensure_bank_fresh 的 .catalog-version 快速路径）。
    after = client.get(f"/api/banks/{staging_id}").json()
    gen_after = client.app.state.catalog.snapshot().generation
    assert gen_after > gen_before, "bump 后读路由应触发重建"
    # 内容结构仍完整（重建没丢字段）。
    assert after["items"] == before["items"]
    # snapshot 现在缓存了新版本号。
    assert staging_id in client.app.state.catalog.snapshot().catalog_versions


def test_external_yaml_edit_detected_by_fingerprint(
    staging_root: tuple[Path, Path, str],
) -> None:
    """§5.4：不 bump、不调 reindex 的外部写（直接改 YAML）也要被指纹层 catch。"""
    root, paper_dir, staging_id = staging_root
    client = TestClient(create_question_bank_app(root))
    before = client.get(f"/api/banks/{staging_id}").json()
    gen_before = client.app.state.catalog.snapshot().generation

    # 直接改 source.yaml（模拟手工编辑，不通知）。
    source_path = paper_dir / "items" / "Q001" / "source.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source["question_number"] = 999
    write_yaml(source_path, source)
    # 触摸一下让 mtime 真正变化（write_yaml 用 yaml.safe_dump，内容变了 mtime 会变）。

    after = client.get(f"/api/banks/{staging_id}").json()
    gen_after = client.app.state.catalog.snapshot().generation
    assert gen_after > gen_before, "外部写后指纹层应触发重建，generation 递增"


def test_ttl_watcher_eventually_rebuilds(staging_root: tuple[Path, Path, str]) -> None:
    """§5.2 兜底：启动短间隔 TTL watcher 后，外部写（不触发任何读）也会被后台重建。"""
    root, paper_dir, staging_id = staging_root
    client = TestClient(create_question_bank_app(root, external_write_ttl=0.05))
    gen_before = client.app.state.catalog.snapshot().generation

    # 外部写，不读该 bank（绕过 ensure_bank_fresh），只靠 watcher。
    source_path = paper_dir / "items" / "Q001" / "source.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source["question_number"] = 4242
    write_yaml(source_path, source)

    # 轮询最多 2 秒等 watcher 重建。
    deadline = time.monotonic() + 2.0
    rebuilt = False
    while time.monotonic() < deadline:
        if client.app.state.catalog.snapshot().generation > gen_before:
            rebuilt = True
            break
        time.sleep(0.02)
    assert rebuilt, "TTL watcher 应在间隔内检测到外部写并重建 snapshot"
