#!/usr/bin/env python3
"""为待录入试卷建立独立的 source-archive 目录。

合集目录（如 documents/上海一模/2021年...（16份）/）里多个区的 .doc 平铺在一起，
DOCX ingestion 要求每卷一个独立的 source-archive 目录。本脚本把指定试卷的源文件
复制到 documents/初三/<规范目录名>/source.doc，并打印每卷的 paper_id / 源路径。

用法:
  prepare_source_archives.py --batch 2021-yimo   # 预置批次
  prepare_source_archives.py --list               # 列出可用批次
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "documents"

# 区名 -> 规范中文目录用名（单字区，不含"区"）
DISTRICT_CN = {
    "HUANGPU": "黄浦", "XUHUI": "徐汇", "CHANGNING": "长宁", "JINGAN": "静安",
    "PUTUO": "普陀", "HONGKOU": "虹口", "YANGPU": "杨浦", "PUDONG": "浦东新区",
    "MINHANG": "闵行", "BAOSHAN": "宝山", "JIADING": "嘉定",
    "JINSHAN": "金山", "SONGJIANG": "松江", "QINGPU": "青浦",
    "FENGXIAN": "奉贤", "CHONGMING": "崇明",
}
CODE_TO_CN = DISTRICT_CN


def archive_dir_name(year: int, district_code: str, kind_cn: str) -> str:
    """documents/初三 下 的 source-archive 目录名，与已录入卷一致。"""
    d = CODE_TO_CN[district_code]
    # "浦东新区"已含"区"，其余单字区名需补"区"
    suffix = "" if d.endswith("区") else "区"
    return f"{year}届-上海市{d}{suffix}-初三{kind_cn}数学-试卷及参考答案"


def find_collect_source(year: int, kind_cn: str) -> Path:
    """定位合集目录: documents/上海一模/ 或 documents/初三/上海二模/。"""
    if kind_cn == "一模":
        root = DOCS / "上海一模"
        pat = re.compile(rf"^{year}年.*一模")
    else:
        root = DOCS / "初三/上海二模"
        pat = re.compile(rf"^{year}年.*二模")
    for d in root.iterdir():
        if d.is_dir() and pat.match(d.name):
            return d
    raise FileNotFoundError(f"未找到 {year}年{kind_cn} 合集目录于 {root}")


def find_district_file(collect_dir: Path, year: int, district_code: str) -> Path:
    """在合集目录里找到该区的 .doc/.docx 文件。"""
    cn = CODE_TO_CN[district_code]
    # 匹配文件名里含该区名的 doc/docx
    cands = [f for f in collect_dir.glob("*") if f.suffix.lower() in (".doc", ".docx")
             and cn in f.name]
    if not cands:
        raise FileNotFoundError(f"在 {collect_dir} 找不到含「{cn}」的 doc/docx")
    return cands[0]


def prepare(paper_id: str, dry_run: bool = False) -> dict:
    """为单个 paper_id 建立 source-archive。返回 {paper_id, src, archive, status}。"""
    m = re.match(r"^(\d{4})-([A-Z]+)-(YIMO|ERMO)$", paper_id)
    if not m:
        return {"paper_id": paper_id, "status": "BAD_ID"}
    year, code, kind_en = int(m.group(1)), m.group(2), m.group(3)
    kind_cn = "一模" if kind_en == "YIMO" else "二模"

    collect = find_collect_source(year, kind_cn)
    src_file = find_district_file(collect, year, code)
    archive_name = archive_dir_name(year, code, kind_cn)
    archive = DOCS / "初三" / archive_name

    if archive.exists() and (archive / "source.doc").exists():
        return {"paper_id": paper_id, "status": "EXISTS",
                "archive": str(archive.relative_to(REPO)), "src": str(src_file.relative_to(REPO))}

    if not dry_run:
        archive.mkdir(parents=True, exist_ok=True)
        dest = archive / ("source.doc" if src_file.suffix.lower() == ".doc" else "source.docx")
        shutil.copy2(src_file, dest)
    return {"paper_id": paper_id, "status": "CREATED" if not dry_run else "DRY",
            "archive": str(archive.relative_to(REPO)), "src": str(src_file.relative_to(REPO))}


# 试点批次：2021 一模 15 卷（3 agent × 5）
BATCH_2021_YIMO = [
    f"2021-{c}-YIMO" for c in [
        "BAOSHAN", "CHANGNING", "CHONGMING", "FENGXIAN", "HONGKOU",  # agent1
        "HUANGPU", "JIADING", "JINGAN", "JINSHAN", "MINHANG",         # agent2
        "PUDONG", "PUTUO", "QINGPU", "SONGJIANG", "XUHUI",            # agent3
    ]
]
BATCHES = {"2021-yimo": BATCH_2021_YIMO}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", help="预置批次名")
    ap.add_argument("--list", action="store_true", help="列出可用批次")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("paper_ids", nargs="*", help="直接指定 paper_id 列表")
    args = ap.parse_args()

    if args.list:
        for name, ids in BATCHES.items():
            print(f"{name}: {len(ids)} 卷")
        return

    ids = args.paper_ids
    if args.batch:
        ids = BATCHES[args.batch]

    for pid in ids:
        try:
            r = prepare(pid, args.dry_run)
            print(f"{r['paper_id']:24} {r['status']:8} {r.get('archive','')}")
        except Exception as e:
            print(f"{pid:24} ERROR    {e}")


if __name__ == "__main__":
    main()
