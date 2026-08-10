# C 类明细: word_evidence 空 / page_number 缺失诊断

只读复核（2026-08-11）。对 `C-empty.md` 列出的 15 卷，每卷只读取
representative `paper.draft.yaml` 与其引用的 `documents/初三/...` 源目录
（仅检查存在性），统计每题 `question_word_evidence` /
`official_solution.word_evidence` 的空缺情况与每条 entry 的 `page_number`
有效性。复核同时直接调用 resolver
(`.codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py
--check`) 对每卷 draft 跑 `resolve_draft_payload(layout="auto")` 验证最终的
PASS/FAIL 与报错原文。**未修改任何 draft / source.yaml。**

字段说明：
- `question_word_evidence`：draft 里题干证据列表（resolver 期望每条含
  `page_image` + `page_number`）。
- `official_solution.word_evidence`：同上，解答证据。
- resolver 的两条硬错误：role 列表为空 → `must not be empty`；
  entry 的 `page_number` 非正整数 → `must be a positive integer`。
- resolver 校验逻辑见 `word_evidence_pages.py` 的 `evidence_page_numbers`
  / `_page_number`（draft=True 时 question role =
  `item.question_word_evidence`，solution role =
  `item.official_solution.word_evidence`）。

分类代号：
- **whole-volume-empty**(全空)：所有题两个 role 都缺 → 转录没产出 evidence。
- **page_number-only**(仅页号缺)：evidence entry 存在但缺/坏 page_number。
- **partial-empty**(部分空)：只有部分题空。
- **no-items**：draft 本身无 item。
- **ok**（本类新增，复核结果）：draft 已能通过 resolver，不再属于 C 类。

## 复核方法（可复现）

```bash
# 单卷复核（只读）：
./.venv/bin/python \
  .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py \
  <draft-path> --check
# 输出含 "WORD EVIDENCE: ..." = PASS；抛 ValueError = FAIL
```

判定优先级：先看 resolver 终态（PASS/FAIL），再看字段统计定位根因。

---

## 2012-YANGPU-ERMO-DOC-BENCHMARK

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2012-YANGPU-ERMO-DOC-BENCHMARK/paper.draft.yaml`
- draft 存在: True（25974 字节）
- resolver 终态: **FAIL** — `ValueError: Q001.question[0]: page_number must be a positive integer`
- 题数: **25**
- question_word_evidence 空/缺的题数: **0 / 25**
- official_solution.word_evidence 空/缺的题数: **0 / 25**
- page_number 缺失的 entry 数 (question | solution): **25 | 25**（共 50 条 entry 全部缺 `page_number` 字段）
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **0 / 25**
- 分类: **page_number-only**
- 根因：draft 的 word evidence 使用 **paragraph-index schema**
  (`{manifest, paragraph_start, paragraph_end}`)，resolver 期望
  page-image schema (`{page_image, page_number}`)，所以 25 题每条 entry
  都缺 `page_number` 字段（不是值为 0/负，而是 key 根本不存在）。
- question_word_evidence entry 形态:
    - `entry keys: {manifest, paragraph_end, paragraph_start}` × 25
- official_solution.word_evidence entry 形态:
    - `entry keys: {manifest, paragraph_end, paragraph_start}` × 25
- 示例 entry (item[0]):
  ```yaml
  question_word_evidence:
  - manifest: documents/初三/2012届-上海市杨浦区-初三二模数学-纯DOC测速/word/word-source.yaml
    paragraph_start: 2
    paragraph_end: 3
  official_solution.word_evidence:
  - manifest: documents/初三/2012届-上海市杨浦区-初三二模数学-纯DOC测速/word/word-source.yaml
    paragraph_start: 89
    paragraph_end: 100
  ```
- documents 源目录: `documents/初三/2012届-上海市杨浦区-初三二模数学-纯DOC测速`
    - 存在: True
    - 顶层 *.png = 0 | word/ = True | word/word-source.yaml = True | word/pages/ = **False** | word/media/ = True (152 图)
    - `word-source.yaml` schema = `math_word_source_extract/v1`，含
      `paragraphs[472]`（每条 `{index, text, images, previous_text, next_text}`），
      **没有** `pages` 维度——paragraph 与渲染页面的映射尚未生成。
    - word/ 下另有 `derived/`(5 q*.png)、`ooxml/`、`normalized.docx`、`source.doc`、`rendered.pdf` 缺失。
- **建议动作:** word 源已具备（docx + paragraph 索引），但 **`word/pages/` 尚未渲染**。
  需要先把 `normalized.docx` 渲染成 `word/pages/NNN.png`（参考
  `documents/初三/2014届-上海市徐汇区-初三一模数学-试卷及参考答案/word/pages/`
  共 45 页的 NNN.png 命名），再重跑转录让 writer 把 paragraph range
  映射成 `{page_image, page_number}`。或扩展 resolver 接受 paragraph-index
  schema 并在内部做 paragraph→page 映射。前者更符合现有 page-image 契约。

---

## 2014-XUHUI-YIMO (worktree)

- draft 路径: `.codex/worktrees/langgraph-question-ingestion/teaching_skills/build/question-ingestion/2014-XUHUI-YIMO/run-17440144d50c/structured/paper.draft.yaml`
- draft 存在: True（117473 字节，mtime 2026-08-03 10:23:57）
- resolver 终态: **PASS** — `WORD EVIDENCE: layout=separated last_page=45 changed_items=0 seed_corrections=0`
- 题数: **25**
- question_word_evidence 空/缺的题数: **0 / 25**（共 29 条 entry，4 题有 2 条）
- official_solution.word_evidence 空/缺的题数: **0 / 25**（共 58 条 entry）
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **ok（已修复，不再属于 C 类）**
- 与原 `C-empty.md` 的差异（重要）：预检扫描 (10:13) 当时该 draft 是
  <400 字节的空 fixture（`sections: []`），被归为 no-items；扫描后约 10
  分钟（10:23）该卷被重新转录，当前 draft 已是完整的 25 题、page-image
  schema、25×2 role 全部带正整数 page_number。resolver 已 PASS。
- 残留问题（非 word_evidence 维度，记录供下游处理）：
    1. draft 位于 `.codex/worktrees/` 下，被 `.gitignore:14` (` .codex/worktrees/`)
       忽略，**未入库**；`artifacts/题库/2026-07-24-上海初三试卷原题库/staging/`
       下**没有** `2014-XUHUI-YIMO` 目录，需先落盘到 staging。
    2. 所有 87 处 `page_image` 用的是**绝对 worktree 路径**
       (`/Users/gaochong/develop/teaching_skills/.codex/worktrees/.../source/docx/pages/001.png`)，
       不可移植；`source_archive` 同样指向绝对 worktree 路径。重跑时需写成
       相对 `documents/初三/2014届-上海市徐汇区-初三一模数学-试卷及参考答案/word/pages/NNN.png`。
    3. 可移植源已就绪：`documents/初三/2014届-上海市徐汇区-初三一模数学-试卷及参考答案/word/pages/`
       已有 45 个 NNN.png，与 draft 里的 last_page=45 一致。
- documents 源目录: `documents/初三/2014届-上海市徐汇区-初三一模数学-试卷及参考答案`
    - 存在: True
    - word/ = True | word/word-source.yaml = True | word/pages/ = True (45 png) | word/media/ = True | word/rendered.pdf = True
- **建议动作:** word_evidence 维度无需修复；需把该 draft 以相对路径
  重新落盘到 staging（`math-docx-question-bank-ingestion` 重跑或手工迁移），
  然后从 C 类名单移除。

---

## 2024-HUANGPU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-HUANGPU-YIMO/paper.draft.yaml`
- draft 存在: True（29924 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**（无 entry 可查）
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- 根因：源是 PDF（页面 PNG），转录走了 `question_evidence` +
  `box_px` 裁剪路径，**从未生成** word evidence。25 题两个 role 全空。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- 示例 item[0]:
  ```yaml
  question_evidence:
  - {source: documents/初三/2024届-上海市黄浦区-初三一模数学-试卷及参考答案/002.png, box_px: [110, 520, 970, 790]}
  # question_word_evidence: 无
  # official_solution.word_evidence: 无
  ```
- documents 源目录: `documents/初三/2024届-上海市黄浦区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 9 (002~010) + 001.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 `extraction-report.md`、`manifest.json`、`page.html`（PDF 提取产物，无 docx）
- **建议动作:** 源是纯 PDF，**没有 word/docx 源**。两条路线：
  (a) 若必须用 word evidence 契约 → 先获取该卷 docx（或用 OCR/PDF→docx
  转换）做 docx 提取，渲染 `word/pages/` 后重跑转录；
  (b) 更务实 → 保持 PDF region evidence，扩展 resolver 接受
  `question_evidence`(box_px) 作为合法 evidence 形态（PDF 源卷天然如此）。
  当前 13 卷 whole-volume-empty 都是 (b) 的情况，统一决策即可。

---

## 2024-JINGAN-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-JINGAN-YIMO/paper.draft.yaml`
- draft 存在: True（28357 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2024届-上海市静安区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 8 (002~009) + 001.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-CHANGNING-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-CHANGNING-YIMO/paper.draft.yaml`
- draft 存在: True（26406 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市长宁区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 9 (002~010) + 001.jpg + 011.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-HONGKOU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-HONGKOU-YIMO/paper.draft.yaml`
- draft 存在: True（31021 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市虹口区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 8 (002~009) + 001.jpg + 010.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-HUANGPU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-HUANGPU-YIMO/paper.draft.yaml`
- draft 存在: True（26217 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市黄浦区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 (002~011) + 001.jpg + 012.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-JINGAN-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-JINGAN-YIMO/paper.draft.yaml`
- draft 存在: True（28682 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市静安区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 (002~011) + 001.jpg + 012.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-JINSHAN-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-JINSHAN-YIMO/paper.draft.yaml`
- draft 存在: True（32443 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市金山区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 (002~011) + 001.jpg + 012.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-MINHANG-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-MINHANG-YIMO/paper.draft.yaml`
- draft 存在: True（27164 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市闵行区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 (002~011) + 001.jpg + 012.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-PUDONG-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-PUDONG-YIMO/paper.draft.yaml`
- draft 存在: True（30957 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市浦东新区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 (002~011) + 001.jpg + 012.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2025-QINGPU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-QINGPU-YIMO/paper.draft.yaml`
- draft 存在: True（28531 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市青浦区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 8 (002~009) + 001.jpg + 010.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2026-HUANGPU-TERM

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-HUANGPU-TERM/paper.draft.yaml`
- draft 存在: True（28654 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **23**（注意：本卷 23 题，非 25）
- question_word_evidence 空/缺的题数: **23 / 23**
- official_solution.word_evidence 空/缺的题数: **23 / 23**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **23 / 23**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 23
- official_solution.word_evidence entry 形态: `missing/None` × 23
- documents 源目录: `documents/初三/黄浦区-2025学年第一学期九年级期终考试-数学试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 (002~011) + 001.jpg + 012.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2026-JINGAN-TERM

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-JINGAN-TERM/paper.draft.yaml`
- draft 存在: True（27685 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/静安区-2025学年第一学期期末课程实施调研-九年级数学试卷`
    - 存在: True
    - 顶层 *.png = 11 (002~012) + 001.jpg + 013.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 2026-QINGPU-TERM

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-QINGPU-TERM/paper.draft.yaml`
- draft 存在: True（29126 字节）
- resolver 终态: **FAIL** — `ValueError: Q001: word_evidence.question must not be empty`
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失/非正整数 entry 数 (q | s): **0 | 0** | **0 | 0**
- 仍带 PDF 裁剪字段 `question_evidence`(box_px) 的题数: **25 / 25**
- 分类: **whole-volume-empty**
- question_word_evidence entry 形态: `missing/None` × 25
- official_solution.word_evidence entry 形态: `missing/None` × 25
- documents 源目录: `documents/初三/青浦区-2025学年第一学期九年级期终学业质量调研-数学试卷`
    - 存在: True
    - 顶层 *.png = 8 (002~009) + 001.jpg + 010.jpg | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
    - 另含 extraction-report.md / manifest.json / page.html（纯 PDF 源）
- **建议动作:** 同 2024-HUANGPU-YIMO（无 docx 源；保持 PDF region evidence 或先做 docx 提取）。

---

## 汇总表 (summary)

列说明：n=题数；qE/sE=question/solution role 空缺题数；qpn/spn=question/solution
缺 page_number 的 entry 数；qePDF=带 PDF `question_evidence`(box_px) 的题数；
resolver=直接跑 `word_evidence_pages.py --check` 的终态。

| 卷 | n | qE | sE | qpn | spn | qePDF | 分类 | 源在 | 源类型 | resolver | 建议动作 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2012-YANGPU-ERMO-DOC-BENCHMARK | 25 | 0 | 0 | 25 | 25 | 0 | page_number-only | yes | docx(无 pages) | FAIL | 渲染 word/pages 后重跑转录 |
| 2014-XUHUI-YIMO (worktree) | 25 | 0 | 0 | 0 | 0 | 0 | **ok（已修复）** | yes | docx(完整) | **PASS** | 落盘到 staging（路径相对化）后移出 C 类 |
| 2024-HUANGPU-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 保持 PDF region evidence 或先做 docx 提取 |
| 2024-JINGAN-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-CHANGNING-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-HONGKOU-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-HUANGPU-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-JINGAN-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-JINSHAN-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-MINHANG-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-PUDONG-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2025-QINGPU-YIMO | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2026-HUANGPU-TERM | 23 | 23 | 23 | 0 | 0 | 23 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2026-JINGAN-TERM | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |
| 2026-QINGPU-TERM | 25 | 25 | 25 | 0 | 0 | 25 | whole-volume-empty | yes | 纯 PDF | FAIL | 同上 |

复核计数（与 `C-empty.md` 的 15 卷对照）：
- **whole-volume-empty**: 13 卷（全部 FAIL，全部纯 PDF 源）
- **page_number-only**: 1 卷（YANGPU，FAIL，docx 源但未渲染 pages）
- **ok（已修复，应移出 C 类）**: 1 卷（2014-XUHUI-YIMO，PASS）
- **partial-empty / no-items**: 0 卷

> 即 `C-empty.md` 当前实际应记 14 卷（剔除 2014-XUHUI-YIMO）。原表 15 卷
> 含 XUHUI 是因为预检扫描 (10:13) 早于该卷重跑 (10:23)；详见该卷条目。

## 按建议动作分组 (grouped)

### A. 渲染 word/pages 后重跑转录（docx 源已就绪，只差 page 渲染）
- **2012-YANGPU-ERMO-DOC-BENCHMARK**
  - 现状：`word-source.yaml`(paragraph[472]) + `normalized.docx` + `media/` 已存在，
    但**没有** `word/pages/`；draft 用 paragraph-index schema，缺 page_number。
  - 动作：把 `normalized.docx` 渲染成 `word/pages/NNN.png`（参考
    `2014-XUHUI` 的 45 页 NNN.png），重跑转录让 writer 输出
    `{page_image, page_number}`；或扩展 resolver 支持 paragraph-index schema。

### B. 保持 PDF region evidence 或先做 docx 提取（纯 PDF 源，无 docx）
- 2024-HUANGPU-YIMO
- 2024-JINGAN-YIMO
- 2025-CHANGNING-YIMO
- 2025-HONGKOU-YIMO
- 2025-HUANGPU-YIMO
- 2025-JINGAN-YIMO
- 2025-JINSHAN-YIMO
- 2025-MINHANG-YIMO
- 2025-PUDONG-YIMO
- 2025-QINGPU-YIMO
- 2026-HUANGPU-TERM
- 2026-JINGAN-TERM
- 2026-QINGPU-TERM
  - 现状（13 卷一致）：源目录只有 PDF 提取产物（`NNN.png` + `001.jpg` +
    `manifest.json` + `extraction-report.md` + `page.html`），**没有**
    `word/`、docx 或 word-source.yaml。draft 走 `question_evidence`(box_px)
    PDF 裁剪路径，从未产出 word evidence，所以 25 题（HUANGPU-TERM 23 题）
    两个 role 全空。
  - 二选一（13 卷统一决策）：
    - **(b1) 务实路线**：扩展 resolver 把 PDF 卷的
      `question_evidence`(box_px) 视为合法 evidence 形态，避免为 13 卷
      纯 PDF 源凭空造 word evidence。
    - **(b2) 一致性路线**：为每卷获取/转换 docx（OCR 或 PDF→docx），
      渲染 `word/pages/`，重跑转录生成 word evidence。成本明显高于 (b1)。

### C. 已修复，落盘后移出 C 类
- **2014-XUHUI-YIMO (worktree)**
  - 现状：resolver 已 PASS（25 题，page-image schema，page_number 全正整数，
    layout=separated, last_page=45）。
  - 残留问题（非 word_evidence）：draft 在 `.codex/worktrees/`（被
    `.gitignore` 忽略，未入库），`staging/` 下无对应目录；87 处
    `page_image` 用绝对 worktree 路径，不可移植。
  - 动作：以相对路径（`documents/初三/2014届-上海市徐汇区-初三一模数学-试卷及参考答案/word/pages/NNN.png`，
    该目录已有 45 页 NNN.png）重跑/迁移 draft 到 staging，然后从 C 类名单移除。
