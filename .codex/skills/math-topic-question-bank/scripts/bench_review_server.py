#!/usr/bin/env python3
"""Review-server 接口基准（§11 阶段 0 / §12.3）。

用 TestClient 对每个读接口在「冷态」「热态」下各跑 N 次，输出 p50/p95 与 stats 计数器，
对照设计文档 §12.3 的目标表。读快照改造后，热态应远低于冷态。

用法::

    ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/bench_review_server.py
    ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/bench_review_server.py --bank-root artifacts/题库 --rounds 20

不启动真实 uvicorn：TestClient 在进程内跑，避免端口/网络抖动，专注测服务端处理成本。
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from question_bank_review_server import (  # noqa: E402
    DEFAULT_BANK_ROOT,
    create_question_bank_app,
)


def percentiles(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    ordered = sorted(samples_ms)
    index_p50 = max(0, int(len(ordered) * 0.5) - 1)
    index_p95 = max(0, int(len(ordered) * 0.95) - 1)
    return {
        "p50": ordered[index_p50],
        "p95": ordered[index_p95],
        "min": ordered[0],
        "max": ordered[-1],
    }


def time_call(client: TestClient, method: str, path: str) -> float:
    """单次调用耗时（毫秒）。不读 body，只测服务端处理 + 序列化。"""
    started = time.perf_counter()
    response = getattr(client, method)(path)
    response.content  # 触发完整读取，计入耗时
    elapsed = (time.perf_counter() - started) * 1000.0
    if response.status_code >= 400:
        raise RuntimeError(f"{method.upper()} {path} → {response.status_code}: {response.text[:200]}")
    return elapsed


def percentile_row(label: str, cold_ms: float, hot_samples: list[float]) -> str:
    pct = percentiles(hot_samples)
    return (
        f"{label:<38} cold={cold_ms:>8.2f}ms  "
        f"hot p50={pct['p50']:>7.2f}  p95={pct['p95']:>7.2f}  "
        f"min={pct['min']:>7.2f}  max={pct['max']:>7.2f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-root", type=Path, default=DEFAULT_BANK_ROOT)
    parser.add_argument("--rounds", type=int, default=15, help="每个接口热态重复次数")
    parser.add_argument("--warmup", type=int, default=3, help="热态测量前预热次数")
    args = parser.parse_args(argv)

    print(f"# bank_root={args.bank_root}  rounds={args.rounds}  warmup={args.warmup}")
    print("# 冷态 = 新 app 实例首次调用；热态 = snapshot 已构建后重复调用。")
    print()

    app = create_question_bank_app(args.bank_root)
    client = TestClient(app)
    catalog = app.state.catalog

    snapshot_response = client.get("/healthz")
    if snapshot_response.status_code != 200:
        print(f"/healthz 预检失败：{snapshot_response.status_code}", file=sys.stderr)
        return 1
    bank_count = snapshot_response.json().get("banks", 0)
    if bank_count == 0:
        print(f"bank_root 下未发现题库：{args.bank_root}", file=sys.stderr)
        return 1

    bootstrap_payload = client.get("/api/bootstrap").json()
    banks = bootstrap_payload.get("banks", [])
    if not banks:
        print("bootstrap 返回空题库列表，无法继续测卷级接口", file=sys.stderr)
        return 1
    first_bank_id = banks[0]["id"]
    # 找一个有 items 的 staging 卷做单题 / 资产基准。
    detail_target = None
    asset_target = None
    source_page_target = None
    for bank in banks:
        detail = client.get(f"/api/banks/{bank['id']}").json()
        items = detail.get("items") or []
        if items and detail_target is None:
            detail_target = (bank["id"], items[0]["id"])
        # 找一个带 prompt 图的 staging item。
        if asset_target is None and bank["kind"] == "staging_exam":
            for item in items:
                previews = item.get("prompt_previews") or []
                if previews:
                    asset_target = (bank["id"], item["id"], previews[0]["url"])
                    break
        if source_page_target is None and bank["kind"] == "staging_exam":
            for item in items:
                pages = item.get("source_question_pages") or []
                if pages:
                    source_page_target = (bank["id"], item["id"], pages[0]["url"])
                    break
        if detail_target and asset_target and source_page_target:
            break

    # 冷态：用全新的 app 实例测每个接口一次，反映「首请求 = snapshot 首建」成本。
    print("## 冷态（新 app 实例首次调用，snapshot 首次构建）")
    cold_app = create_question_bank_app(args.bank_root)
    cold_client = TestClient(cold_app)
    cold = {
        "/api/bootstrap": time_call(cold_client, "get", "/api/bootstrap"),
        "/api/banks": time_call(cold_client, "get", "/api/banks"),
        "/api/banks/facets": time_call(cold_client, "get", "/api/banks/facets"),
        f"/api/banks/{first_bank_id}": time_call(cold_client, "get", f"/api/banks/{first_bank_id}"),
    }
    if detail_target:
        cold[f"/api/banks/{detail_target[0]}/items/{{item}}"] = time_call(
            cold_client, "get", f"/api/banks/{detail_target[0]}/items/{detail_target[1]}"
        )
    if asset_target:
        cold[asset_target[2]] = time_call(cold_client, "get", asset_target[2])
    if source_page_target:
        cold[source_page_target[2]] = time_call(cold_client, "get", source_page_target[2])
    for path, ms in cold.items():
        print(f"  {path:<48} {ms:>9.2f} ms")
    print()

    # 热态：在已预热的 client 上重复测。
    for _ in range(max(args.warmup, 1)):
        client.get("/api/bootstrap")
    print(f"## 热态（snapshot 已构建，重复 {args.rounds} 次）")

    def hot(label: str, method: str, path: str) -> None:
        samples = [time_call(client, method, path) for _ in range(args.rounds)]
        pct = percentiles(samples)
        print(
            f"  {label:<48} "
            f"p50={pct['p50']:>7.2f}  p95={pct['p95']:>7.2f}  "
            f"min={pct['min']:>7.2f}  max={pct['max']:>7.2f} ms"
        )

    hot("/api/bootstrap", "get", "/api/bootstrap")
    hot("/api/banks", "get", "/api/banks")
    hot("/api/banks?q=模", "get", "/api/banks?q=" + "模")
    hot("/api/banks/facets", "get", "/api/banks/facets")
    hot(f"/api/banks/{first_bank_id}", "get", f"/api/banks/{first_bank_id}")
    if detail_target:
        hot(
            f"/api/banks/{detail_target[0]}/items/{{item}}",
            "get",
            f"/api/banks/{detail_target[0]}/items/{detail_target[1]}",
        )
    if asset_target:
        hot(asset_target[2], "get", asset_target[2])
    if source_page_target:
        hot(source_page_target[2], "get", source_page_target[2])
    print()

    print("## stats（本轮累计）")
    for key, value in catalog.stats().items():
        print(f"  {key:<26} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
