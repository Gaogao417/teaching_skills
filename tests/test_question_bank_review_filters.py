"""HTTP 契约测试：题库审核 UI 的服务端筛选 + facets。

直接对真实 ``artifacts/题库``（10 formal_bank + 50 staging_exam，含 GEN-TERM、
BAOSHAN-JIADING-ERMO、-DOC-BENCHMARK 全部边界 case）跑 TestClient，不造 tmp_path
假数据。覆盖：parse_paper_id 边界、summary 字段扩展、/api/banks/facets、过滤组合、
空结果、深链向后兼容。

注：浏览器交互契约（点击/输入/debounce/重渲染）见 tests/e2e/。本文件只验 HTTP 层。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex" / "skills" / "math-topic-question-bank" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from question_bank_review_server import (  # noqa: E402
    EXAM_TYPE_TOKENS,
    create_question_bank_app,
    parse_paper_id,
)

REAL_BANK_ROOT = ROOT / "artifacts" / "题库"


# ---------------------------------------------------------------- parse_paper_id


@pytest.mark.parametrize(
    "paper_id, expected",
    [
        ("2025-JINGAN-YIMO", {"year": "2025", "exam_type": "一模", "district": "JINGAN"}),
        ("2024-YANGPU-YIMO", {"year": "2024", "exam_type": "一模", "district": "YANGPU"}),
        ("2026-PUTUO-ERMO", {"year": "2026", "exam_type": "二模", "district": "PUTUO"}),
        # 无 year/district 的通用卷。
        ("GEN-TERM", {"year": "", "exam_type": "期末", "district": ""}),
        # 多 district 合并保留。
        ("2012-BAOSHAN-JIADING-ERMO", {"year": "2012", "exam_type": "二模", "district": "BAOSHAN-JIADING"}),
        # -DOC-BENCHMARK 后缀噪声被截断。
        ("2012-YANGPU-ERMO-DOC-BENCHMARK", {"year": "2012", "exam_type": "二模", "district": "YANGPU"}),
        # 空 / 无法识别 → 全空，不抛异常。
        ("", {"year": "", "exam_type": "", "district": ""}),
        ("NOT-A-PAPER-ID", {"year": "", "exam_type": "", "district": ""}),
    ],
)
def test_parse_paper_id_handles_known_and_edge_cases(paper_id: str, expected: dict[str, str]) -> None:
    assert parse_paper_id(paper_id) == expected


def test_exam_type_token_enum_is_fine_grained_with_forward_looking_entries() -> None:
    """用户选了细分粒度：一模/二模/期中/期末/中考（后两者前瞻留位）。"""
    assert EXAM_TYPE_TOKENS == {
        "YIMO": "一模",
        "ERMO": "二模",
        "MIDTERM": "期中",
        "TERM": "期末",
        "ZHONGKAO": "中考",
    }


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def client() -> TestClient:
    """对真实 artifacts/题库 起进程内 ASGI app。"""
    return TestClient(create_question_bank_app(REAL_BANK_ROOT))


@pytest.fixture(scope="module")
def all_banks(client: TestClient) -> list[dict]:
    payload = client.get("/api/banks").json()
    assert payload["errors"] == [], f"discover() 报错: {payload['errors']}"
    return payload["banks"]


# ---------------------------------------------------------------- 字段扩展


def test_staging_summary_carries_exam_type_year_district(all_banks: list[dict]) -> None:
    staging = [b for b in all_banks if b["kind"] == "staging_exam"]
    assert staging, "真实 artifacts 里没有 staging paper，测试 fixture 失效"
    sample = next(b for b in staging if b["paper_id"] == "2025-JINGAN-YIMO")
    assert sample["exam_type"] == "一模"
    assert sample["year"] == "2025"
    assert sample["district"] == "JINGAN"


def test_formal_summary_has_empty_exam_type_year_district(all_banks: list[dict]) -> None:
    """formal_bank（课时练习）没有这些字段，统一返回空串保持 record shape 一致。"""
    formal = [b for b in all_banks if b["kind"] == "formal_bank"]
    assert formal, "真实 artifacts 里没有 formal bank"
    for bank in formal:
        assert bank["exam_type"] == ""
        assert bank["year"] == ""
        assert bank["district"] == ""


# ---------------------------------------------------------------- facets


def test_facets_returns_real_sorted_values(client: TestClient) -> None:
    facets = client.get("/api/banks/facets").json()
    assert set(facets) >= {"kinds", "grades", "years", "exam_types", "errors"}
    assert facets["errors"] == []
    assert set(facets["kinds"]) == {"formal_bank", "staging_exam"}
    assert "九年级" in facets["grades"]
    # 年份降序（最新在前）。
    years = facets["years"]
    assert years == sorted(years, reverse=True)
    assert "2025" in years
    # exam_types 必须是 EXAM_TYPE_TOKENS 声明顺序的子集（前端稳定渲染依赖此）。
    declared_order = [label for label in EXAM_TYPE_TOKENS.values() if label in set(facets["exam_types"])]
    assert facets["exam_types"] == declared_order
    assert "一模" in facets["exam_types"]
    assert "期末" in facets["exam_types"]


def test_facets_route_is_registered_before_bank_id_wildcard(client: TestClient) -> None:
    """/api/banks/facets 不能被 /api/banks/{bank_id} 吞掉。"""
    response = client.get("/api/banks/facets", params={})
    assert response.status_code == 200
    assert "kinds" in response.json()


# ---------------------------------------------------------------- 单维度过滤


def test_filter_by_kind_staging_only(client: TestClient) -> None:
    banks = client.get("/api/banks", params={"kind": "staging_exam"}).json()["banks"]
    assert banks
    assert all(b["kind"] == "staging_exam" for b in banks)


def test_filter_by_kind_formal_only(client: TestClient) -> None:
    banks = client.get("/api/banks", params={"kind": "formal_bank"}).json()["banks"]
    assert banks
    assert all(b["kind"] == "formal_bank" for b in banks)


def test_filter_by_year_2025_excludes_yearless(client: TestClient) -> None:
    banks = client.get("/api/banks", params={"year": "2025"}).json()["banks"]
    assert banks
    assert all(b["year"] == "2025" for b in banks)
    # GEN-TERM 没有 year，必须被排除。
    assert not any(b["paper_id"] == "GEN-TERM" for b in banks)


def test_filter_by_exam_type_ermo_keeps_only_ermo(client: TestClient) -> None:
    banks = client.get("/api/banks", params={"exam_type": "二模"}).json()["banks"]
    assert banks
    assert all(b["exam_type"] == "二模" for b in banks)
    paper_ids = {b["paper_id"] for b in banks}
    assert "2026-PUTUO-ERMO" in paper_ids
    # 一模不能混进来。
    assert not any(b["paper_id"].endswith("-YIMO") and "ERMO" not in b["paper_id"] for b in banks)


def test_filter_by_grade_crosses_kinds(client: TestClient) -> None:
    banks = client.get("/api/banks", params={"grade": "九年级"}).json()["banks"]
    assert banks
    assert all(b["grade"] == "九年级" for b in banks)


def test_search_query_matches_chinese_topic(client: TestClient) -> None:
    banks = client.get("/api/banks", params={"q": "静安"}).json()["banks"]
    assert banks
    assert all("静安" in b["topic"] for b in banks)


def test_search_query_matches_english_district(client: TestClient) -> None:
    """q 也应能命中 paper_id/district（拼音），不只是中文 title。"""
    banks = client.get("/api/banks", params={"q": "PUTUO"}).json()["banks"]
    assert banks
    assert all("PUTUO" in b["paper_id"] for b in banks)


# ---------------------------------------------------------------- 组合 + 边界


def test_combined_kind_year_exam_type_is_and(client: TestClient) -> None:
    banks = client.get(
        "/api/banks",
        params={"kind": "staging_exam", "year": "2025", "exam_type": "一模"},
    ).json()["banks"]
    assert banks
    for b in banks:
        assert b["kind"] == "staging_exam"
        assert b["year"] == "2025"
        assert b["exam_type"] == "一模"
    assert any(b["paper_id"] == "2025-JINGAN-YIMO" for b in banks)


def test_combined_kind_with_query(client: TestClient) -> None:
    """kind=真题 + q=杨浦：真题里命中杨浦；formal 的同名专题被排除。"""
    banks = client.get(
        "/api/banks", params={"kind": "staging_exam", "q": "杨浦"},
    ).json()["banks"]
    assert banks
    assert all(b["kind"] == "staging_exam" for b in banks)
    assert all("杨浦" in b["topic"] for b in banks)


def test_filter_no_match_returns_empty_not_error(client: TestClient) -> None:
    response = client.get("/api/banks", params={"year": "1999"})
    assert response.status_code == 200
    assert response.json()["banks"] == []


def test_default_no_params_returns_all(client: TestClient, all_banks: list[dict]) -> None:
    response = client.get("/api/banks")
    assert response.status_code == 200
    assert len(response.json()["banks"]) == len(all_banks)


# ---------------------------------------------------------------- 向后兼容


def test_bank_detail_still_works(client: TestClient) -> None:
    """深链 ?bank=<id> 走 /api/banks/{bank_id}，过滤改造不应破坏 detail。"""
    response = client.get(
        "/api/banks/staging:2026-07-24-上海初三试卷原题库:2025-JINGAN-YIMO",
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["kind"] == "staging_exam"
    assert "items" in detail


# ---------------------------------------------------------------- HTML 渲染契约


def test_page_renders_new_filter_controls(client: TestClient) -> None:
    """新控件 id 必须出现在运行时 HTML 里（浏览器 E2E 进一步验交互）。"""
    page = client.get("/")
    assert page.status_code == 200
    for element_id in (
        "filter-kind",
        "filter-grade",
        "filter-year",
        "filter-exam-type",
        "search-input",
        "bank-select",
    ):
        assert f'id="{element_id}"' in page.text, f"缺少 #{element_id}"
    # 占位 token 必须被替换干净。
    assert "__STATIC_VERSION__" not in page.text
    assert "__NUMBER_REVIEW_URL__" not in page.text
    # bank-select 改为可见 listbox，不再是 dropdown。
    assert "size=" in page.text
