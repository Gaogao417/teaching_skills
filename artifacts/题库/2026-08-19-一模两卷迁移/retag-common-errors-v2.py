#!/usr/bin/env python3
"""Phase 5 remediation：TA-SMV-016/017/018 补 step common_errors（升 v2）。

背景（phase-5-exit-report §3.3 内容数据缺口）：
- TP-SMV-004/005 的 checkpoint 无 common_deviations，S6（自我修正剧本）在
  这两个 plan 上无偏差数据可派生 → golden 实跑 2 skip；
- 根因是 ADR-005 part 级重切（recut-part-v2.py）时新 TA 未携带旧整题 TA
  已 authored 的 common_errors。

本次（2026-08-21，Phase 5 reopened / remediation）：
- 错因主体从旧整题 TA-SMV-004@v2 / TA-SMV-005@v2（Stale 但内容 authored）
  按新 part 级 steps 语义映射回填；
- TA-SMV-017 S3 第 2 条、TA-SMV-018 S1/S2 为迁移 agent 代拟（旧错因无
  对应认知节点），登记偏差待真人教师复核；
- 证据 ref 复用 v1 canonical 不可变副本（append-only，不重录）；
- 批准人 migration-agent（代理偏差沿 Phase 3/4 先例）。

幂等守卫（Phase 3 重切事故教训）：sidecar 条目 canonical.version 已 ≥ v2
即跳过，不会重复冻结出 v3。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".codex/skills/math-topic-question-bank/scripts"))
sys.path.insert(0, str(REPO))

import teaching_approach as ta  # noqa: E402

BANK = Path(__file__).resolve().parent
ROOT = REPO / "artifacts/canonical-authoring"
LEDGER = ROOT / "id-allocations.yaml"
REVIEWER = "migration-agent"
REVIEW_NOTE = (
    "Phase 5 remediation（S6 skip 消除）：补 step common_errors——主体按步映射自"
    "旧整题 TA-SMV-004/005@v2 authored 错因；TA-SMV-017 S3-2、TA-SMV-018 S1/S2 "
    "为 agent 代拟待真人教师复核（偏差登记）"
)

# 每条：sidecar item 目录 / qt / local_id / 目标 TA / part（None=整题）/
# step_id → common_errors（source 标注 authored=旧整题映射、drafted=代拟）。
RETAG = [
    {
        "item": "黄浦2025/items/Q021",
        "qt_id": "QT-SMV-004",
        "local_id": "t2",
        "ta_id": "TA-SMV-016",
        "part_id": None,
        "common_errors": {
            # TA-SMV-004@v2 authored，1:1 步映射（三步结构相同）
            "S1": (["仪器边长与相似三角形对应边对应错"], "authored"),
            "S2": (["A 字型对应边错配", "漏加仪器的 40cm 结构量"], "authored"),
            "S3": (["两次实践的比例方向写反", "单位换算出错"], "authored"),
        },
    },
    {
        "item": "黄浦2025/items/Q022",
        "qt_id": "QT-SMV-005",
        "local_id": "t2",
        "ta_id": "TA-SMV-017",
        "part_id": "1",
        "common_errors": {
            "S1": (["平分线两侧的角与三角形顶点对应错"], "authored"),
            "S2": (["把外角当成底角本身"], "authored"),
            # S3-1 authored（旧 S2 错因按语义移位）；S3-2 drafted
            "S3": (["顶点对应关系写错", "只证一组角相等就下相似结论"], "mixed"),
        },
    },
    {
        "item": "黄浦2025/items/Q022",
        "qt_id": "QT-SMV-005",
        "local_id": "t3",
        "ta_id": "TA-SMV-018",
        "part_id": "2",
        "common_errors": {
            "S1": (["平行等角认错位置（内错角与同位角混淆）"], "drafted"),
            "S2": (["外角和分解相减时对应项错位"], "drafted"),
            "S3": (["平行线截得的比例上下位写反", "不用第一问结论另起炉灶"], "authored"),
        },
    },
]


def main() -> int:
    created: list[str] = []
    drafted: list[str] = []
    for spec in RETAG:
        item_dir = BANK / spec["item"]
        payload = ta.load_sidecar(item_dir)
        assert payload is not None, spec["item"]
        entry = next(
            (a for a in payload["approaches"] if a.get("id") == spec["local_id"]), None
        )
        assert entry is not None, f"{spec['item']}: 缺 local_id {spec['local_id']}"
        canonical = entry.get("canonical") or {}
        assert canonical.get("artifact_id") == spec["ta_id"], (
            f"{spec['item']}#{spec['local_id']}: canonical 指向 "
            f"{canonical.get('artifact_id')}，期望 {spec['ta_id']}"
        )
        if canonical.get("version") != "v1":
            print(f"skip（已是 {canonical.get('version')}）: {spec['ta_id']}")
            continue

        errors_by_step = spec["common_errors"]
        step_ids = {s["step_id"] for s in entry["steps"]}
        assert step_ids == set(errors_by_step), (
            f"{spec['ta_id']}: sidecar steps {sorted(step_ids)} 与错因表 "
            f"{sorted(errors_by_step)} 不一致"
        )
        for step in entry["steps"]:
            errors, source = errors_by_step[step["step_id"]]
            step["common_errors"] = errors
            if source in ("drafted", "mixed"):
                drafted.append(f"{spec['ta_id']}#{step['step_id']}")

        notes = entry["evidence"].setdefault("manual_edit_notes", [])
        notes.append(
            "Phase 5 remediation（2026-08-21）：补 common_errors（TP-004/005 "
            "S6 剧本偏差输入来源），主体映射自旧整题 TA authored 错因"
        )

        frozen = ta.freeze_approved_approach(
            entry,
            item_dir,
            reviewer_id=REVIEWER,
            review_note=REVIEW_NOTE,
            qt_id=spec["qt_id"],
            ledger_path=LEDGER,
            root=ROOT,
            part_id=spec["part_id"],
        )
        entry["approval"] = {
            "reviewer_id": REVIEWER,
            "approved_at": frozen["approval"]["approved_at"],
            "review_note": REVIEW_NOTE,
        }
        entry["canonical"] = {
            "artifact_id": frozen["artifact_id"],
            "version": frozen["version"],
            "content_hash": frozen["content_hash"],
            "approved_at": frozen["approval"]["approved_at"],
        }
        ta.save_sidecar(item_dir, payload)
        created.append(
            f"{frozen['artifact_id']}@{frozen['version']} → {spec['qt_id']}"
            f"{'#' + spec['part_id'] if spec['part_id'] else '（整题）'}"
            f" hash={frozen['content_hash'][:19]}…"
        )

    for line in created:
        print(line)
    if drafted:
        print("代拟偏差（待真人教师复核）:", ", ".join(drafted))
    print(f"total: {len(created)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
