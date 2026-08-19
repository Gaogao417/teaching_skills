#!/usr/bin/env python3
"""ADR-005 T2.1：dogfood 8 题 QuestionTruth v2 重迁移（小问级真值）。

对两份迁移卷各构造一个合成 staging 视图（bank items 以符号链接挂入），
只导出 8 个目标 source_key，经 canonical_export v2 组装（per-part 答案/
解答、stem 去内联、range_constraint 修复）后 promote：
- 8 题 v1 → Superseded，v2 = current Approved；
- 每题写一条 question_change stale 事件（Phase 2 台账），旧绑定 TA 随后
  在批准流程中 Stale（先 QT 后 TA 的顺序不可逆反）。

切分为确定性建议（与审题面板同一套函数）；本驱动为迁移 agent 代理执行，
人工核对记录于 PRDS phase-3 报告 v2 重闭环章节。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".codex/skills/math-topic-question-bank/scripts"))

import yaml  # noqa: E402

import canonical_export as ce  # noqa: E402

BANK = Path(__file__).resolve().parent
PAPERS = {
    "闵行2020": {
        "paper_id": "2020-MINHANG-YIMO",
        "source_keys": {
            "2020-MINHANG-YIMO-Q07",  # QT-SMV-013
            "2020-MINHANG-YIMO-Q18",  # QT-SMV-001
            "2020-MINHANG-YIMO-Q23",  # QT-SMV-002
            "2020-MINHANG-YIMO-Q25",  # QT-SMV-003
        },
    },
    "黄浦2025": {
        "paper_id": "2025-HUANGPU-YIMO",
        "source_keys": {
            "2025-HUANGPU-YIMO-Q21",  # QT-SMV-048
            "2025-HUANGPU-YIMO-Q22",  # QT-SMV-004
            "2025-HUANGPU-YIMO-Q23",  # QT-SMV-005
            "2025-HUANGPU-YIMO-Q25",  # QT-SMV-006
        },
    },
}
PARSER = {
    "parser_id": "phase3-repromote_v2",
    "parser_version": "adr-005-subquestion-truth",
    "harness": "migration-agent",
}


def main() -> int:
    pack_map = yaml.safe_load(
        (ce.CANONICAL_ROOT / "pack-map.yaml").read_text(encoding="utf-8")
    )
    promoted_all: list[str] = []
    for bank_dir_name, spec in PAPERS.items():
        bank_dir = BANK / bank_dir_name
        paper_dir = bank_dir / "papers" / spec["paper_id"]
        with tempfile.TemporaryDirectory(prefix="repromote-v2-") as tmp:
            staging = Path(tmp) / "staging"
            (staging / "items").mkdir(parents=True)
            (staging / "paper.yaml").write_text(
                (paper_dir / "paper.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            for item_dir in sorted((bank_dir / "items").iterdir()):
                if not item_dir.is_dir():
                    continue
                (staging / "items" / item_dir.name).symlink_to(item_dir)
            export = ce.build_candidate_export(
                staging,
                parser_provenance=PARSER,
                pack_map=pack_map,
                only_source_keys=spec["source_keys"],
            )
            found = {item["source_key"] for item in export["items"]}
            missing = spec["source_keys"] - found
            if missing:
                raise SystemExit(f"{spec['paper_id']}: missing items {sorted(missing)}")
            result = ce.promote_canonical(export)
            print(spec["paper_id"], result)
            promoted_all.extend(result["promoted"] + result["superseded"])
    print("touched:", sorted(promoted_all))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
