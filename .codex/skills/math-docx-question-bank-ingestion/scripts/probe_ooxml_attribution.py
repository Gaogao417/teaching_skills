#!/usr/bin/env python3
"""Probe: 从 OOXML 还原"图片 → 题号"归属，对照 draft 里 agent 填的归属。

不是正式生产脚本，是一次性量化探针，验证 OOXML 路径能否替代模型认图。

输入：
  <paper-id>  artifacts/题库/.../staging/<paper-id> 下的 paper.draft.yaml
              对应的 word 源目录靠 draft 里的 question_word_evidence.page_image
              路径反推（取 word/ 前缀）。

输出：每张 agent 已归属的 prompt/solution 图，打印
  - OOXML 推断的归属题号、章节、答案/解析区分
  - draft 里 agent 填的题号
  - 是否一致 / 差异类型
最后汇总命中率与差异分布。
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import yaml

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# 文档流 token：文字 / 图片锚。
# 图片锚支持两种形式：
#   - DrawingML: <a:blip r:embed="rIdNN"/>
#   - VML/OLE  : <v:imagedata r:id="rIdNN"/>  （旧式 MathType/OLE 公式与部分图）
# 用元素名限定，避免误匹配其它 r:id 关系引用。
TOKEN_RE = re.compile(
    r'<w:t[^>]*>([^<]*)</w:t>'
    r'|<a:blip[^>]*\sr:embed="(rId\d+)"'
    r'|<v:imagedata[^>]*\sr:id="(rId\d+)"'
)

# 题号识别：大题号 N. / N． / N、，N 在 1..30。
# 前置断言用"非数字"边界，覆盖中文标点（．）和全角括号 ） 等场景。
# 半角点在字符类里转义；后接空白或中文。
QNUM_RE = re.compile(r'(?:(?<=[^0-9])|(?<=^))(\d{1,2})[\.．、](?=\s)')

# 章节关键词
SECTION_KEYWORDS = [
    ("一、选择题", "选择题"),
    ("二、填空题", "填空题"),
    ("三、解答题", "解答题"),
]

# 答案/解析区标记
SOLUTION_MARKERS = ["【答案】", "【解析】", "【分析】", "【详解】", "【小问"]


def build_timeline(document_xml: str) -> list[tuple[str, str]]:
    """拍平文档为 (TXT|IMG, value) 时间线，合并连续文字。"""
    raw = []
    for m in TOKEN_RE.finditer(document_xml):
        txt, embed_rid, imagedata_rid = m.group(1), m.group(2), m.group(3)
        if embed_rid or imagedata_rid:
            raw.append(("IMG", embed_rid or imagedata_rid))
        elif txt is not None:
            raw.append(("TXT", txt))
    merged = []
    for kind, val in raw:
        if merged and merged[-1][0] == "TXT" and kind == "TXT":
            merged[-1] = ("TXT", merged[-1][1] + val)
        else:
            merged.append([kind, val])
    return [(k, v) for k, v in merged]


def load_rels(rels_xml: str) -> dict[str, str]:
    """rId -> media/imageNN.ext。只保留真正的位图（png/jpg/jpeg），
    丢弃 wmf/emf——后者是公式对象，不是题图。

    按 <Relationship> 元素逐个抽取属性，对 Id/Target 的属性顺序鲁棒
    （不同 Word 生成器顺序不同：有的 Id 在前，有的 Target 在前）。
    """
    rels = {}
    for m in re.finditer(r"<Relationship\b([^>]*)/>", rels_xml):
        attrs = m.group(1)
        rid_m = re.search(r'Id="(rId\d+)"', attrs)
        tgt_m = re.search(r'Target="([^"]+)"', attrs)
        if not (rid_m and tgt_m):
            continue
        rid, tgt = rid_m.group(1), tgt_m.group(1)
        if "media/image" not in tgt:
            continue
        ext = tgt.rsplit(".", 1)[-1].lower()
        if ext in {"png", "jpg", "jpeg"}:
            rels[rid] = tgt
    return rels


def nearest_text(timeline: list[tuple[str, str]], idx: int, direction: str, limit: int = 120) -> str:
    """从 idx 往前/往后找最近的非空文字段，取末尾/开头 limit 字。"""
    step = -1 if direction == "prev" else 1
    for j in range(idx + step, -1 if step < 0 else len(timeline), step):
        if timeline[j][0] == "TXT" and timeline[j][1].strip():
            v = timeline[j][1]
            return v[-limit:] if direction == "prev" else v[:limit]
        # 只跨过最近的那个文字段即可
        if timeline[j][0] == "TXT":
            continue
    return ""


def extract_qnums_from_text(text: str) -> list[int]:
    """抽取文字段里所有题号（按出现顺序）。用于扫描整段文档流。"""
    if not text:
        return []
    nums = []
    for s in QNUM_RE.findall(text):
        try:
            n = int(s)
        except ValueError:
            continue
        if 1 <= n <= 30:
            nums.append(n)
    return nums


def classify_position(prev_text: str, next_text: str) -> str:
    """判断这张图属于题干区还是解答区。"""
    # 解答/解析标记出现在 prev 末尾或 next 开头，视为解答图
    for marker in SOLUTION_MARKERS:
        if marker in prev_text or marker in next_text:
            return "solution"
    # next 里有选项标签 A./B./C./D. 通常是选择题题图
    if re.search(r'[ABCD][\.．]', next_text[:30]):
        return "prompt"
    # prev 末尾是"如图"/"图N所示"/"（　）"通常是题干图
    if re.search(r'如图|图\d|所示|（\s*）|\(\s*\)', prev_text[-40:]):
        return "prompt"
    return "unknown"


def ooxml_attribution(document_xml: str, rels: dict[str, str]) -> list[dict]:
    """对每个图片锚，推断归属题号、章节、区域。返回列表。"""
    timeline = build_timeline(document_xml)
    current_section = "未知"
    current_qnum: int | None = None
    in_solution_block = False
    results = []
    for i, (kind, val) in enumerate(timeline):
        if kind == "TXT":
            # 更新章节
            for kw, name in SECTION_KEYWORDS:
                if kw in val:
                    current_section = name
                    break
            # 游标法：文字段里每出现一个题号就推进当前题号游标。
            # 题号是文档流的硬锚点，最后一个题号即图片插入时所属的题。
            qns = extract_qnums_from_text(val)
            for qn in qns:
                current_qnum = qn
            # 是否进入解答区：解答标记出现即标记
            if any(m in val for m in SOLUTION_MARKERS):
                in_solution_block = True
            # 新题号且其后没有紧跟解答标记 → 题干区（重置）
            if qns and not any(m in val for m in SOLUTION_MARKERS):
                # 题号出现在文字里、但这段文字不含【答案】【解析】等，按题干处理
                pass  # 不重置 in_solution_block，因为【解析】可能跨段
        else:  # IMG
            # 只保留位图（png/jpg）。rels 已过滤掉 wmf/emf；非位图的 rId
            # 这里直接跳过，不进入结果，避免公式对象污染归属表。
            target = rels.get(val)
            if not target:
                continue
            prev_text = nearest_text(timeline, i, "prev")
            next_text = nearest_text(timeline, i, "next")
            area = classify_position(prev_text, next_text)
            # 归属题号：游标值（图片插入点时最近的题号）
            qnum = current_qnum
            image_name = target.split("/")[-1]
            results.append({
                "rid": val,
                "image": image_name,
                "qnum": qnum,
                "section": current_section,
                "area": area,
                "prev_tail": prev_text[-60:].replace("\n", " "),
                "next_head": next_text[:60].replace("\n", " "),
            })
    return results


def draft_attribution(draft_path: Path) -> list[dict]:
    """从 paper.draft.yaml 提取 agent 已填的图片归属。"""
    d = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
    out = []
    for sec in d.get("sections", []):
        sec_title = sec.get("title", "")
        for item in sec.get("items", []):
            qnum = item.get("question_number")
            item_id = item.get("item_id")
            for role in ("prompt", "solution"):
                for crop in item.get(role, []) or []:
                    src = crop.get("source", "")
                    m = re.search(r"media/(image\d+\.\w+)", src)
                    if not m:
                        continue
                    out.append({
                        "item_id": item_id,
                        "qnum": qnum,
                        "role": role,
                        "image": m.group(1),
                        "section": sec_title,
                    })
    return out


def compare(ooxml: list[dict], draft: list[dict]) -> None:
    """对照并打印。"""
    # 以 draft 里的图为基准（这些是 agent 已归属的）
    ooxml_by_img = defaultdict(list)
    for o in ooxml:
        ooxml_by_img[o["image"]].append(o)

    print("=" * 78)
    print(f"OOXML 推断图片锚总数: {len(ooxml)}")
    print(f"draft 已归属图片数: {len(draft)}")
    print("=" * 78)

    match = partial = miss_draft = miss_ooxml = 0
    mismatches = []

    for d in draft:
        img = d["image"]
        qnum_d = d["qnum"]
        role_d = d["role"]
        candidates = ooxml_by_img.get(img, [])
        if not candidates:
            print(f"[draft-only] {img:18s} Q{qnum_d:<3} role={role_d:<8} → OOXML 中未找到（可能 image 编号不一致/裁剪副本）")
            miss_ooxml += 1
            continue
        # 取第一个候选（一张图理论上出现一次；若重复出现取最贴近的）
        o = candidates[0]
        qnum_o = o["qnum"]
        if qnum_o is None:
            print(f"[no-qnum]    {img:18s} draft=Q{qnum_d:<3} role={role_d:<8} | OOXML 无法定题号 | prev=...{o['prev_tail'][-30:]!r}")
            miss_draft += 1
            continue
        if qnum_o == qnum_d:
            match += 1
            print(f"[OK]         {img:18s} Q{qnum_d} {role_d:<8} ↔ OOXML Q{qnum_o} {o['area']}")
        else:
            partial += 1
            mismatches.append((img, qnum_d, role_d, qnum_o, o))
            print(f"[MISMATCH]   {img:18s} draft=Q{qnum_d:<3} role={role_d:<8} | OOXML=Q{qnum_o} {o['area']}")
            print(f"             prev=...{o['prev_tail']!r}")
            print(f"             next={o['next_head']!r}")

    total = len(draft)
    print()
    print("=" * 78)
    print(f"对照结果（以 draft 已归属图为基准，共 {total} 张）:")
    print(f"  完全一致     : {match:4d}  ({match/total*100:5.1f}%)" if total else "  无")
    print(f"  题号不符     : {partial:4d}  ({partial/total*100:5.1f}%)" if total else "")
    print(f"  OOXML 无题号 : {miss_draft:4d}")
    print(f"  draft 图在 OOXML 找不到: {miss_ooxml:4d}")
    print("=" * 78)
    if mismatches:
        print("\n差异详情（按 draft 题号排序）：")
        for img, qd, rd, qo, o in sorted(mismatches, key=lambda x: x[1] or 0):
            print(f"  {img:14s} draft Q{qd}({rd}) vs OOXML Q{qo}({o['area']})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paper_id", help="staging 目录名，如 2026-XUHUI-ERMO")
    ap.add_argument("--staging-root", default="artifacts/题库/2026-07-24-上海初三试卷原题库/staging")
    args = ap.parse_args()

    draft_path = Path(args.staging_root) / args.paper_id / "paper.draft.yaml"
    if not draft_path.exists():
        print(f"找不到 draft: {draft_path}", file=sys.stderr)
        return 1

    # 从 draft 反推 word 源目录：优先 question_word_evidence.page_image，
    # 其次任意 media/ 引用路径（兼容只用 question_word_evidence 的卷和
    # 只用 media 引用但没有整页图证据的卷）。
    d = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
    word_dir = None
    for sec in d.get("sections", []):
        for item in sec.get("items", []):
            for ev in item.get("question_word_evidence", []) or []:
                pi = ev.get("page_image")
                if pi:
                    word_dir = Path(pi).resolve().parent.parent  # .../word/pages/N.png -> .../word
                    break
            if word_dir:
                break
            for role in ("prompt", "solution"):
                for crop in item.get(role, []) or []:
                    src = crop.get("source", "")
                    m = re.search(r"(.*/word)/media/", src)
                    if m:
                        word_dir = Path(m.group(1)).resolve()
                        break
                if word_dir:
                    break
        if word_dir:
            break
    if not word_dir:
        print("draft 里没有 word 路径线索（既无 question_word_evidence 也无 media 引用）", file=sys.stderr)
        return 1
    doc_xml = word_dir / "ooxml" / "document.xml"
    rels_xml = word_dir / "ooxml" / "document.xml.rels"
    if not doc_xml.exists() or not rels_xml.exists():
        print(f"OOXML 文件缺失: {doc_xml}", file=sys.stderr)
        return 1

    print(f"# {args.paper_id}")
    print(f"# word 源: {word_dir}")
    print()
    document_xml = doc_xml.read_text(encoding="utf-8")
    rels = load_rels(rels_xml.read_text(encoding="utf-8"))
    ooxml = ooxml_attribution(document_xml, rels)
    draft = draft_attribution(draft_path)
    compare(ooxml, draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
