#!/usr/bin/env python3
"""带重试的 observe 调度器（修正版）。

observe 脚本遇间歇性 400 (MiMo prefill 失败) 会整个进程 SystemExit。本调度器
利用 cache 断点续传：崩溃后重跑，已成功的批次命中 cache 不重发，只重发失败批次。

判断完成用 **cache 命中数**（金标准，不受 windows 残留干扰）：
  observe 主循环里 _observe_batch → provider → MimoStructuredClient 会先查 cache，
  命中直接返回不重发。所以 cache 文件数 == 已成功批次数。

每次重跑前清 windows 残留（cache 保留），避免不同批划分参数的产物重叠。

退出码：
  0 = cache 命中数 == 总批次数（全成功）
  1 = 重试耗尽仍有批次失败

用法:
  run_observe_with_retry.py --paper-id 2021-BAOSHAN-YIMO [--max-retries 4]
                            [--target-batch-pages 4] [--max-batch-pages 4]

并发模型：observe 内部 for-batch 串行，单文档同时只有 1 请求在飞。
多文档可安全并行（7 文档 ≈ 91 RPM，在 100 RPM 限额内）。
"""
from __future__ import annotations
import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts/question_transcription"
STAGING_ROOT = REPO / "artifacts/题库/2026-07-24-上海初三试卷原题库"
PY = REPO / ".venv/bin/python"

DISTRICT_CN = {
    "HUANGPU": "黄浦", "XUHUI": "徐汇", "CHANGNING": "长宁", "JINGAN": "静安",
    "PUTUO": "普陀", "HONGKOU": "虹口", "YANGPU": "杨浦", "PUDONG": "浦东新区",
    "MINHANG": "闵行", "BAOSHAN": "宝山", "JIADING": "嘉定",
    "JINSHAN": "金山", "SONGJIANG": "松江", "QINGPU": "青浦",
    "FENGXIAN": "奉贤", "CHONGMING": "崇明",
}


def resolve_sa(paper_id: str) -> Path:
    m = re.match(r"^(\d{4})-([A-Z]+)-(YIMO|ERMO)$", paper_id)
    if not m:
        raise ValueError(f"bad paper_id: {paper_id}")
    year, code, kind_en = int(m.group(1)), m.group(2), m.group(3)
    kind_cn = "一模" if kind_en == "YIMO" else "二模"
    d = DISTRICT_CN[code]
    suffix = "" if d.endswith("区") else "区"
    return REPO / "documents/初三" / f"{year}届-上海市{d}{suffix}-初三{kind_cn}数学-试卷及参考答案"


def count_batches(build: Path, target_pages: int, max_pages: int) -> int:
    """span index 按 target/max 页参数产生的批次数。"""
    sys.path.insert(0, str(SCRIPTS))
    from observe_docx_pages import build_observation_batches
    from question_span_index import QuestionSpanIndex
    si = build / "word.span-index.yaml"
    if not si.exists():
        return -1
    idx = QuestionSpanIndex.model_validate(yaml.safe_load(si.read_text(encoding="utf-8")))
    batches = build_observation_batches(
        idx, target_page_count=target_pages, hard_page_limit=max_pages,
    )
    return len(batches)


def count_cache_hits(build: Path) -> int:
    """已成功的批次数 = cache 命中数（金标准）。"""
    c = build / "cache"
    if not c.exists():
        return 0
    return len(list(c.glob("*.json")))


def run_once(sa: Path, build: Path, target_pages: int, max_pages: int, max_workers: int = 1) -> int:
    """跑一次 observe，stdout 实时透传，返回退出码。"""
    cmd = [
        str(PY), "-u", str(SCRIPTS / "observe_docx_pages.py"),
        "--word-source", str(sa / "word/word-source.yaml"),
        "--span-index", str(build / "word.span-index.yaml"),
        "--source-archive", str(sa),
        "--mimo-structured",
        "--cache-dir", str(build / "cache"),
        "--output-dir", str(build / "windows"),
        "--target-batch-pages", str(target_pages),
        "--max-batch-pages", str(max_pages),
        "--max-workers", str(max_workers),
    ]
    proc = subprocess.run(cmd, cwd=REPO)
    return proc.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper-id", required=True)
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--target-batch-pages", type=int, default=4)
    ap.add_argument("--max-batch-pages", type=int, default=4)
    ap.add_argument("--max-workers", type=int, default=16,
                    help="试卷内批次并发线程数 (默认16, 配合4页/批)")
    args = ap.parse_args()

    sa = resolve_sa(args.paper_id)
    build = STAGING_ROOT / "build" / args.paper_id
    if not (sa / "word/word-source.yaml").exists():
        print(f"[{args.paper_id}] ERROR: word-source.yaml 不存在: {sa}", flush=True)
        return 2

    total = count_batches(build, args.target_batch_pages, args.max_batch_pages)
    print(f"[{args.paper_id}] 总批次={total} target={args.target_batch_pages}页", flush=True)

    for attempt in range(1, args.max_retries + 1):
        done = count_cache_hits(build)
        print(f"[{args.paper_id}] 尝试 {attempt}/{args.max_retries}: cache命中 {done}/{total}", flush=True)
        if done >= total:
            break

        # 清 windows 残留（cache 保留续传），避免批划分变更导致产物重叠
        w = build / "windows"
        if w.exists():
            shutil.rmtree(w)
        w.mkdir(parents=True, exist_ok=True)

        t0 = time.time()
        rc = run_once(sa, build, args.target_batch_pages, args.max_batch_pages, args.max_workers)
        dt = time.time() - t0
        done_after = count_cache_hits(build)
        print(f"[{args.paper_id}] observe rc={rc} 耗时={dt:.0f}s cache {done_after}/{total}", flush=True)

        if done_after >= total:
            break

    done = count_cache_hits(build)
    if done >= total:
        print(f"[{args.paper_id}] ✅ 全部完成 ({done}/{total})", flush=True)
        return 0
    print(f"[{args.paper_id}] ❌ 仍缺 {total - done}/{total} 批", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
