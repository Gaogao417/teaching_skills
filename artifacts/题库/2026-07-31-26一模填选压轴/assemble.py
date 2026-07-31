#!/usr/bin/env python3
"""组装 2026 届一模（2025 学年第一学期期末）填选压轴学生版 assignment。

从 ``上海初三试卷原题库`` 的 15 份 ``2026-<区>-TERM`` / ``GEN-TERM`` staging 中
各取选择题压轴 Q006 与填空题压轴 Q018，合并成一份单 section 学生版 YAML：
题干 LaTeX 与配图直接复用，``image_path`` 重定位到本目录，block id 重编为
H001–H030。不生成 teacher 版，不显示答案。

用法::

    ./.venv/bin/python artifacts/题库/2026-07-31-26一模填选压轴/assemble.py
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
STAGING = REPO / "artifacts/题库/2026-07-24-上海初三试卷原题库/staging"
OUTPUT_DIR = Path(__file__).resolve().parent

# 区 staging 目录名 -> 中文短名，顺序即成卷顺序（按区拼音 + 期末练习卷收尾）。
DISTRICTS: list[tuple[str, str]] = [
    ("2026-JIADING-TERM", "嘉定"),
    ("2026-JINSHAN-TERM", "金山"),
    ("2026-PUTUO-TERM", "普陀"),
    ("2026-MINHANG-TERM", "闵行"),
    ("2026-SONGJIANG-TERM", "松江"),
    ("2026-JINGAN-TERM", "静安"),
    ("2026-CHONGMING-TERM", "崇明"),
    ("2026-QINGPU-TERM", "青浦"),
    ("2026-HONGKOU-TERM", "虹口"),
    ("2026-YANGPU-TERM", "杨浦"),
    ("2026-HUANGPU-TERM", "黄浦"),
    ("2026-XUHUI-TERM", "徐汇"),
    ("2026-BAOSHAN-TERM", "宝山"),
    ("2026-FENGXIAN-TERM", "奉贤"),
    ("GEN-TERM", "期末练习卷"),
]

# 每份卷子真正的"填选最后一题"。大多数卷子是 选择Q006 + 填空Q018，但金山选择
# 只有 5 题、黄浦填空只有 10 题，末题不同（依据各卷 paper.yaml，不可假设 6/18）。
DEFAULT_PICKS: list[tuple[str, str]] = [
    ("Q006", "选择6"),
    ("Q018", "填空18"),
]
PICKS_OVERRIDE: dict[str, list[tuple[str, str]]] = {
    "2026-JINSHAN-TERM": [("Q005", "选择5"), ("Q015", "填空15")],
    "2026-HUANGPU-TERM": [("Q006", "选择6"), ("Q016", "填空16")],
    # 闵行/杨浦额外补入填空倒数第二题（Q017），插在填空末题 Q018 之前。
    "2026-MINHANG-TERM": [("Q006", "选择6"), ("Q017", "填空17"), ("Q018", "填空18")],
    "2026-YANGPU-TERM": [("Q006", "选择6"), ("Q017", "填空17"), ("Q018", "填空18")],
}


def picks_for(dir_name: str) -> list[tuple[str, str]]:
    return PICKS_OVERRIDE.get(dir_name, DEFAULT_PICKS)

QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}

# 渲染模板（exam-zh-practice）用 `block.choices|dictsort` 遍历，要求 choices 是
# dict；题库 staging YAML 是历史遗留的 list 形态，这里把前 4 项映射为 A/B/C/D。
CHOICE_KEYS = ["A", "B", "C", "D", "E", "F", "G"]


def coerce_choices(block: dict[str, Any]) -> None:
    """把 list 形态的 choices 原地转成 {A: .., B: .., ..} dict。"""
    choices = block.get("choices")
    if isinstance(choices, list):
        block["choices"] = {
            CHOICE_KEYS[i]: text for i, text in enumerate(choices[: len(CHOICE_KEYS)])
        }


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def rebase_assets(value: Any, source_dir: Path, output_dir: Path) -> Any:
    """把 image_path/tikz_path 改写成相对 output_dir 的相对路径。"""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"image_path", "tikz_path"} and isinstance(child, str):
                source = Path(child)
                if not source.is_absolute():
                    source = (source_dir / child).resolve()
                result[key] = Path(os.path.relpath(source, output_dir)).as_posix()
            else:
                result[key] = rebase_assets(child, source_dir, output_dir)
        return result
    if isinstance(value, list):
        return [rebase_assets(child, source_dir, output_dir) for child in value]
    return copy.deepcopy(value)


def practice_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for section in payload.get("sections", [])
        if isinstance(section, dict) and section.get("type") == "practice"
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") in QUESTION_TYPES
    ]


def _choices_items(block: dict[str, Any]) -> list[str]:
    """统一 choices 为有序文本列表。"""
    ch = block.get("choices")
    if isinstance(ch, dict):
        return [f"{k}. {v}" for k, v in sorted(ch.items())]
    if isinstance(ch, list):
        return [f"{chr(65 + i)}. {v}" for i, v in enumerate(ch)]
    return []


def generate_student_tex(blocks: list[dict[str, Any]], out_path: Path) -> None:
    """直接生成 student.tex：每题留演算空间，每两题一页，题首带来源标注。

    不走公共渲染模板，因为模板的 choice/fillin 题块不渲染答题区；这里参考
    artifacts/题库/2026-07-27-26一模相似三角形证明题/generate_tex.py 的做法，
    对每道压轴题用 \\answerarea 留演算空白。
    """
    lines = [
        r"\documentclass{exam-zh}",
        r"\usepackage{edu-practice}",
        "",
        r"\examsetup{",
        r"  question/show-answer = false,",
        r"  fillin/show-answer = false,",
        r"  solution/show-solution = hide,",
        r"}",
        "",
        r"\begin{document}",
        "",
        r"\section*{2026 届一模选择填空压轴精选}",
        "",
    ]

    for i, block in enumerate(blocks, 1):
        label = block.get("source_label", "")
        btype = block.get("type")
        stem = (block.get("stem_latex") or block.get("stem") or "").strip()
        diagram = block.get("diagram_col") or {}
        img_path = diagram.get("image_path", "")
        width = diagram.get("width", "58mm")
        # 演算空白：填空压轴比选择压轴给更多空间。
        # 首页因有 \section* 标题占位，前两题压缩答题区以保证 1、2 题同面。
        if i <= 2:
            answer_h = "30mm" if btype == "fillin" else "24mm"
        else:
            answer_h = "48mm" if btype == "fillin" else "40mm"

        lines.append(f"% ---------- 第 {i} 题 ({label}) ----------")
        lines.append(r"\needspace{10\baselineskip}")
        lines.append("")

        if img_path:
            lines.append(r"\begin{question}[points=4]")
            lines.append(r"\noindent")
            lines.append(
                r"  \begin{minipage}[t]{\dimexpr\linewidth-" + width + r"-6mm\relax}"
            )
            lines.append(r"    \vspace{0pt}")
            lines.append(rf"    \hfill{{\color{{edu-blue!60}}\small\textit{{{label}}}}}\par")
            lines.append(f"    {stem}")
            if btype == "choice":
                lines.append(r"    \par")
                lines.append(r"    \begin{choices}[columns=1]")
                for item in _choices_items(block):
                    lines.append(r"      \item " + item.split(". ", 1)[-1])
                lines.append(r"    \end{choices}")
            lines.append(r"  \end{minipage}\hfill")
            lines.append(rf"  \begin{{diagramcoltikz}}{{{width}}}{{}}")
            lines.append(rf"  \includegraphics[width=\linewidth]{{\detokenize{{{img_path}}}}}")
            lines.append(r"  \end{diagramcoltikz}")
            lines.append(r"  \par\medskip")
            lines.append(rf"  \answerarea[{answer_h}]")
            lines.append(r"\end{question}")
        else:
            lines.append(r"\begin{question}[points=4]")
            lines.append(rf"    \hfill{{\color{{edu-blue!60}}\small\textit{{{label}}}}}\par")
            lines.append(f"    {stem}")
            if btype == "choice":
                lines.append(r"    \par")
                lines.append(r"    \begin{choices}[columns=1]")
                for item in _choices_items(block):
                    lines.append(r"      \item " + item.split(". ", 1)[-1])
                lines.append(r"    \end{choices}")
            lines.append(r"  \par\medskip")
            lines.append(rf"  \answerarea[{answer_h}]")
            lines.append(r"\end{question}")

        lines.append("")
        # 每两题一页（最后一题后不强制分页）
        if i % 2 == 0 and i < len(blocks):
            lines.append(r"\newpage")
            lines.append("")

    lines.append(r"\end{document}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    combined_blocks: list[dict[str, Any]] = []
    source_records: list[str] = []
    next_number = 1
    missing: list[str] = []

    for dir_name, district_cn in DISTRICTS:
        paper_dir = STAGING / dir_name
        for qid, kind_cn in picks_for(dir_name):
            yaml_path = paper_dir / "items" / qid / "student.resolved.assignment.yaml"
            if not yaml_path.exists():
                missing.append(f"{dir_name}/{qid}")
                continue
            payload = load_yaml(yaml_path)
            blocks = practice_blocks(payload)
            if not blocks:
                missing.append(f"{dir_name}/{qid} (no practice block)")
                continue
            block = rebase_assets(blocks[0], yaml_path.parent, OUTPUT_DIR)
            coerce_choices(block)
            block["id"] = f"H{next_number:03d}"
            source_label = f"{district_cn}·{kind_cn}"
            block["source_label"] = source_label
            combined_blocks.append(block)
            source_records.append(
                f"{dir_name}/{qid} -> H{next_number:03d} ({source_label})"
            )
            next_number += 1

    if missing:
        print("WARNING: missing items (skipped):", file=sys.stderr)
        for entry in missing:
            print(f"  - {entry}", file=sys.stderr)

    combined = {
        "meta": {
            "title": "2026 届一模选择填空压轴精选 · 学生版",
            "grade": "九年级",
            "subject": "数学",
            "total_points": sum(int(block.get("points") or 0) for block in combined_blocks),
            "version": "student",
            "show_answers": False,
            "source_artifacts": {
                "question_bank": "../2026-07-24-上海初三试卷原题库",
                "assignment_parts": source_records,
            },
        },
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "inline",
        },
        "sections": [
            {
                "id": "choice-fillin-final",
                "type": "practice",
                "visibility": "student",
                "blocks": combined_blocks,
            }
        ],
    }

    out_path = OUTPUT_DIR / "combined.student.assignment.yaml"
    out_path.write_text(
        yaml.safe_dump(combined, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    tex_path = OUTPUT_DIR / "student.tex"
    generate_student_tex(combined_blocks, tex_path)
    print(f"wrote {out_path}")
    print(f"wrote {tex_path}")
    print(f"collected {len(combined_blocks)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
