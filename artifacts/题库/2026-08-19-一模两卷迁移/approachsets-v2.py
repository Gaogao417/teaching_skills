#!/usr/bin/env python3
"""ADR-005 T2.3：golden 6 题 ApproachSet 冻结（AS-SMV-001..006）。

每题一份：小问顺序 + 每问主选 part 级 TA（ADR-005 重切产物）+ 跨问节奏。
选法说明由迁移 agent 撰写（与讲解稿同源偏差，登记待教师复核）。
必须在 recut-part-v2.py 之后运行。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".codex/skills/math-topic-question-bank/scripts"))

import teaching_approach as ta  # noqa: E402

ROOT = REPO / "artifacts/canonical-authoring"
LEDGER = ROOT / "id-allocations.yaml"


def _ref(ta_id: str) -> dict:
    payload = ta.current_approach(ta_id, root=ROOT)
    assert payload["status"] == "Approved", ta_id
    return {
        "artifact_id": payload["artifact_id"],
        "version": payload["version"],
        "content_hash": payload["content_hash"],
    }


SETS = {
    "QT-SMV-001": {
        "parts": [{"part_id": "", "approach": _ref("TA-SMV-009"),
                   "note": "整题单问：翻折不变量主线路"}],
        "cross_part_rhythm": None,
    },
    "QT-SMV-002": {
        "parts": [
            {"part_id": "1", "approach": _ref("TA-SMV-010"), "note": "正推：等积变形直抵垂直"},
            {"part_id": "2", "approach": _ref("TA-SMV-011")},
        ],
        "cross_part_rhythm": "第(1)问的垂直结论是第(2)问比例式的台阶：Teach 模式先固定 CE⊥AB 再迁移到等积式目标。",
    },
    "QT-SMV-003": {
        "parts": [
            {"part_id": "1", "approach": _ref("TA-SMV-012")},
            {"part_id": "2", "approach": _ref("TA-SMV-013")},
            {"part_id": "3", "approach": _ref("TA-SMV-014")},
        ],
        "cross_part_rhythm": "压轴三问递进：第(1)问等角是第(2)问设元建函数的工具，第(2)问的函数关系式与范围是第(3)问分类取舍的判据。",
    },
    "QT-SMV-004": {
        "parts": [{"part_id": "", "approach": _ref("TA-SMV-016"),
                   "note": "整题单问：两次实践互证的建模主线"}],
        "cross_part_rhythm": None,
    },
    "QT-SMV-005": {
        "parts": [
            {"part_id": "1", "approach": _ref("TA-SMV-017")},
            {"part_id": "2", "approach": _ref("TA-SMV-018")},
        ],
        "cross_part_rhythm": "第(1)问的相似比是第(2)问比例转移的起点：先固定 △CEA∽△CDB 再做平行等角传递。",
    },
    "QT-SMV-006": {
        "parts": [
            {"part_id": "1", "approach": _ref("TA-SMV-019")},
            {"part_id": "2", "approach": _ref("TA-SMV-020")},
            {"part_id": "3", "approach": _ref("TA-SMV-021")},
        ],
        "cross_part_rhythm": "动点压轴三段节奏：第(1)问等角为第(2)问锁相似提供条件，第(2)问的 BP/GP 位置量是第(3)问分类列式的坐标系。",
    },
}


def main() -> int:
    for qt_id, spec in SETS.items():
        payload = ta.freeze_approach_set(
            qt_id,
            spec["parts"],
            reviewer_id="migration-agent",
            review_note="golden 选法冻结（ADR-005 §5），跨问节奏为迁移 agent 撰写，待教师复核",
            ledger_path=LEDGER,
            root=ROOT,
            cross_part_rhythm=spec["cross_part_rhythm"],
        )
        print(f"{payload['artifact_id']}@{payload['version']} → {qt_id} "
              f"parts={len(payload['parts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
