"""退出门禁 5：Assessment 类 fixture 不含答案真值与 Tutor tool capability（扫描测试）。

规则来自 fixtures-manifest.json 的 assessment_scan 段（PRDS 仓维护），
TypeScript 侧用同一规则扫描同一批文件。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES_DIR = ROOT / "integrations" / "ai_teaching_contracts" / "fixtures"
MANIFEST = json.loads((FIXTURES_DIR / "fixtures-manifest.json").read_text(encoding="utf-8"))
RULES = MANIFEST["assessment_scan"]


def _walk(node, path="$"):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def test_assessment_fixtures_exist():
    assert RULES["assessment_files"], "至少要有一个 assessment fixture 供扫描"


def test_assessment_fixtures_have_no_answer_truth_keys():
    for name in RULES["assessment_files"]:
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        offenders = [
            where
            for where, key, _ in _walk(payload)
            if key in RULES["forbidden_keys"]
        ]
        assert not offenders, f"{name}: 答案真值字段泄漏 {offenders}"


def test_assessment_fixtures_have_no_tutor_tool_capabilities():
    for name in RULES["assessment_files"]:
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        for where, key, value in _walk(payload):
            if key in RULES["empty_only_keys"]:
                assert value == [], f"{name}: {where} 必须为空（Assessment 禁止 Tutor tools）"


def test_assessment_fixtures_do_not_embed_answer_values():
    for name in RULES["assessment_files"]:
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        strings = [v for _, _, v in _walk(payload) if isinstance(v, str)]
        for forbidden in RULES["forbidden_answer_values"]:
            for s in strings:
                assert forbidden not in s, f"{name}: 字符串含答案真值 {forbidden!r}"
