#!/usr/bin/env python3
"""扫描上海一模/二模源文档，对照 staging，列出未处理清单。

判断主键：paper_id = f"{year}-{DISTRICT_CODE}-{YIMO|ERMO}"
- staging 的 paper_id 直接从目录名取（地面真值）。
- 源文档解析出 paper_id 后，不在 staging 集合里 -> MISSING。
- staging 有 authoring-remaining.yaml -> INCOMPLETE。
一份源文档可能产生多个 paper_id（如"宝山区、嘉定区"联合卷）。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAGING_ROOT = REPO / "artifacts/题库/2026-07-24-上海初三试卷原题库/staging"
DOCS = REPO / "documents"

# 区名 -> paper_id 拼写（与 staging 命名一致）。长名优先，避免"浦东"误吞"浦东新区"。
DISTRICT_MAP = {
    "黄浦": "HUANGPU", "徐汇": "XUHUI", "长宁": "CHANGNING", "静安": "JINGAN",
    "普陀": "PUTUO", "虹口": "HONGKOU", "杨浦": "YANGPU",
    "浦东新区": "PUDONG", "浦东": "PUDONG",
    "闵行": "MINHANG", "宝山": "BAOSHAN", "嘉定": "JIADING",
    "金山": "JINSHAN", "松江": "SONGJIANG", "青浦": "QINGPU",
    "奉贤": "FENGXIAN", "崇明": "CHONGMING", "崇明县": "CHONGMING",
    "闸北": "ZHABEI",
}


def parse_districts(text: str) -> list[str]:
    """从文本中提取所有区码。返回如 ['BAOSHAN','JIADING']。"""
    codes: list[str] = []
    for cn, code in DISTRICT_MAP.items():
        if cn in text:
            codes.append(code)
    seen = set()
    out = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ---------- 收集已录入 staging ----------
def load_staging() -> tuple[set[str], dict[str, str]]:
    """返回 (paper_id 集合, {paper_id: 'INCOMPLETE'|'COMPLETE'})。"""
    ids: set[str] = set()
    status: dict[str, str] = {}
    if not STAGING_ROOT.exists():
        return ids, status
    for d in STAGING_ROOT.iterdir():
        if not d.is_dir() or not re.match(r"^\d{4}-", d.name):
            continue
        pid = d.name
        ids.add(pid)
        status[pid] = "INCOMPLETE" if (d / "authoring-remaining.yaml").exists() else "COMPLETE"
    return ids, status


# ---------- 收集源文档 ----------
def collect_sources() -> list[dict]:
    items: list[dict] = []

    # 1. documents/初三/下 届-一模/二模 目录（2022-2026 主来源）
    chusan = DOCS / "初三"
    if chusan.exists():
        for entry in chusan.iterdir():
            if not entry.is_dir():
                continue
            m = re.match(r"^(\d{4})届-上海市(.+?)-初三(一模|二模)数学", entry.name)
            if m:
                year, dist_text, kind = int(m.group(1)), m.group(2), m.group(3)
                kind_en = "YIMO" if kind == "一模" else "ERMO"
                items += _from_source(entry, year, dist_text, kind_en, kind, "dir")

    # 2. documents/初三/上海二模/ 下 YYYY年合集 .doc（2012-2014）
    ermo_dir = DOCS / "初三/上海二模"
    if ermo_dir.exists():
        for year_dir in sorted(ermo_dir.iterdir()):
            m = re.match(r"^(\d{4})年", year_dir.name)
            if not m or not year_dir.is_dir():
                continue
            year = int(m.group(1))
            for f in sorted(year_dir.glob("*二模*.doc*")):
                dist_text = _extract_dist_from_filename(f.name)
                if dist_text:
                    items += _from_source(f, year, dist_text, "ERMO", "二模", "doc-collect")

    # 3. documents/上海一模/ 下 YYYY年合集 .doc/.docx（2014-2023）
    yimo_root = DOCS / "上海一模"
    if yimo_root.exists():
        for year_dir in sorted(yimo_root.iterdir()):
            m = re.match(r"^(\d{4})年", year_dir.name)
            if not m or not year_dir.is_dir():
                continue
            year = int(m.group(1))
            for f in sorted(year_dir.glob("*一模*.doc*")):
                dist_text = _extract_dist_from_filename(f.name)
                if dist_text:
                    items += _from_source(f, year, dist_text, "YIMO", "一模", "doc-collect")

    return items


def _extract_dist_from_filename(name: str) -> str:
    """从如 '2019年上海市普陀区中考数学一模试卷（含解析版）.doc' 提取区段。"""
    m = re.search(r"上海市(.+?区(?:县)?)", name)
    return m.group(1) if m else ""


def _from_source(path: Path, year: int, dist_text: str, kind_en: str, kind_cn: str, origin: str) -> list[dict]:
    codes = parse_districts(dist_text)
    if not codes:
        return []
    ext = path.suffix.lower()
    fmt = "pdf" if ext == ".pdf" else "docx" if ext == ".docx" else "doc"
    out = []
    for code in codes:
        out.append({
            "source_rel": str(path.relative_to(REPO)),
            "year": year,
            "district_cn": dist_text,
            "district_code": code,
            "kind_en": kind_en,
            "kind_cn": kind_cn,
            "paper_id": f"{year}-{code}-{kind_en}",
            "format": fmt,
            "origin": origin,
        })
    return out


# ---------- 对照 ----------
def cross_reference(sources, staging_ids, staging_status):
    """每个 paper_id 取最佳来源（dir > doc-collect），判断状态。"""
    by_pid: dict[str, list[dict]] = {}
    for s in sources:
        by_pid.setdefault(s["paper_id"], []).append(s)

    rows = []
    for pid, srcs in sorted(by_pid.items()):
        srcs.sort(key=lambda x: 0 if x["origin"] == "dir" else 1)
        best = dict(srcs[0])
        best["all_sources"] = [s["source_rel"] for s in srcs]
        if pid in staging_ids:
            best["status"] = staging_status[pid]
        else:
            best["status"] = "MISSING"
        rows.append(best)
    return rows


def _summary(rows):
    s = {"COMPLETE": 0, "INCOMPLETE": 0, "MISSING": 0}
    for r in rows:
        s[r["status"]] = s.get(r["status"], 0) + 1
    missing_by = {}
    for r in rows:
        if r["status"] == "MISSING":
            key = f"{r['year']}-{r['kind_en']}"
            missing_by[key] = missing_by.get(key, 0) + 1
    s["missing_breakdown"] = dict(sorted(missing_by.items()))
    return s


def main():
    staging_ids, staging_status = load_staging()
    sources = collect_sources()
    rows = cross_reference(sources, staging_ids, staging_status)

    pending = [r for r in rows if r["status"] != "COMPLETE"]
    pending.sort(key=lambda x: (x["year"], x["kind_en"], x["district_code"]))

    out = {
        "generated_at": "2026-07-29",
        "staging_root": str(STAGING_ROOT.relative_to(REPO)),
        "staging_count": len(staging_ids),
        "source_paper_ids": len(rows),
        "summary": _summary(rows),
        "pending_count": len(pending),
        "pending": pending,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
