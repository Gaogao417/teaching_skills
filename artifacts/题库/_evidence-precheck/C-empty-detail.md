# C 类明细: word_evidence 空 / page_number 缺失诊断

只读诊断。对每卷只读取 representative `paper.draft.yaml` 与其引用的
`documents/初三/...` 源目录（仅检查存在性），统计每题
`question_word_evidence` / `official_solution.word_evidence` 的空缺情况与
每条 entry 的 `page_number` 有效性。**未修改任何 draft / source.yaml。**

字段说明：
- `question_word_evidence`：draft 里题干证据列表（resolver 期望每条含
  `page_image` + `page_number`）。
- `official_solution.word_evidence`：同上，解答证据。
- resolver 的两条硬错误：role 列表为空 → `must not be empty`；
  entry 的 `page_number` 非正整数 → `must be a positive integer`。

分类代号：
- **whole-volume-empty**(全空)：所有题两个 role 都缺 → 转录没产出 evidence。
- **page_number-only**(仅页号缺)：evidence entry 存在但缺/坏 page_number。
- **partial-empty**(部分空)：只有部分题空。
- **no-items**：draft 本身无 item。

---

## 2012-PUTUO-ERMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2012-PUTUO-ERMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2012届-上海市普陀区-初三二模数学-试卷及参考答案`
    - 存在: True
    - pages-pages/ = 30 png | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2012-YANGPU-ERMO-DOC-BENCHMARK

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2012-YANGPU-ERMO-DOC-BENCHMARK/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **0 / 25**
- official_solution.word_evidence 空/缺的题数: **0 / 25**
- page_number 缺失的 entry 数 (question | solution): **25 | 25**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **page_number-only**
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
    - word/ = True | word-source.yaml = True | word/pages/ = False | word/media/ = True
- **建议动作:** render word/ pages (NNN.png) then map paragraph ranges to page_number; or rewrite evidence to page-image schema. Current entries are paragraph-index schema with no page_number.

---

## 2024-HUANGPU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-HUANGPU-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2024届-上海市黄浦区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 9 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2024-JINGAN-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-JINGAN-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2024届-上海市静安区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 8 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-CHANGNING-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-CHANGNING-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市长宁区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 9 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-HONGKOU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-HONGKOU-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市虹口区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 8 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-HUANGPU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-HUANGPU-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市黄浦区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-JINGAN-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-JINGAN-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市静安区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-JINSHAN-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-JINSHAN-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市金山区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-MINHANG-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-MINHANG-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市闵行区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-PUDONG-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-PUDONG-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市浦东新区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2025-QINGPU-YIMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2025-QINGPU-YIMO/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/2025届-上海市青浦区-初三一模数学-试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 8 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2026-HUANGPU-TERM

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-HUANGPU-TERM/paper.draft.yaml`
- draft 存在: True
- 题数: **23**
- question_word_evidence 空/缺的题数: **23 / 23**
- official_solution.word_evidence 空/缺的题数: **23 / 23**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：23 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 23
- official_solution.word_evidence entry 形态:
    - `missing/None` × 23
- documents 源目录: `documents/初三/黄浦区-2025学年第一学期九年级期终考试-数学试卷及参考答案`
    - 存在: True
    - 顶层 *.png = 10 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2026-JINGAN-TERM

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-JINGAN-TERM/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/静安区-2025学年第一学期期末课程实施调研-九年级数学试卷`
    - 存在: True
    - 顶层 *.png = 11 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2026-QINGPU-TERM

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-QINGPU-TERM/paper.draft.yaml`
- draft 存在: True
- 题数: **25**
- question_word_evidence 空/缺的题数: **25 / 25**
- official_solution.word_evidence 空/缺的题数: **25 / 25**
- page_number 缺失的 entry 数 (question | solution): **0 | 0**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **whole-volume-empty**
- 注：25 题仍带 PDF 裁剪字段 `question_evidence`（`source`/`box_px`），说明是 PDF 源转录，未生成 word evidence。
- question_word_evidence entry 形态:
    - `missing/None` × 25
- official_solution.word_evidence entry 形态:
    - `missing/None` × 25
- documents 源目录: `documents/初三/青浦区-2025学年第一学期九年级期终学业质量调研-数学试卷`
    - 存在: True
    - 顶层 *.png = 8 | word/ = False | word-source.yaml = False | word/pages/ = False | word/media/ = False
- **建议动作:** re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)

---

## 2026-PUTUO-ERMO

- draft 路径: `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-PUTUO-ERMO/paper.draft.yaml`
- draft 存在: True
- 题数: **24**
- question_word_evidence 空/缺的题数: **0 / 24**
- official_solution.word_evidence 空/缺的题数: **0 / 24**
- page_number 缺失的 entry 数 (question | solution): **24 | 24**
- page_number 非正整数的 entry 数 (question | solution): **0 | 0**
- 分类: **page_number-only**
- question_word_evidence entry 形态:
    - `entry keys: {manifest, paragraph_end, paragraph_start}` × 24
- official_solution.word_evidence entry 形态:
    - `entry keys: {manifest, paragraph_end, paragraph_start}` × 24
- 示例 entry (item[0]):
  ```yaml
question_word_evidence:
- manifest: documents/初三/2026届-上海市普陀区-初三二模数学-试卷及解析/word/word-source.yaml
  paragraph_start: 7
  paragraph_end: 8
official_solution.word_evidence:
- manifest: documents/初三/2026届-上海市普陀区-初三二模数学-试卷及解析/word/word-source.yaml
  paragraph_start: 9
  paragraph_end: 11
  ```
- documents 源目录: `documents/初三/2026届-上海市普陀区-初三二模数学-试卷及解析`
    - 存在: True
    - word/ = True | word-source.yaml = True | word/pages/ = False | word/media/ = True
- **建议动作:** render word/ pages (NNN.png) then map paragraph ranges to page_number; or rewrite evidence to page-image schema. Current entries are paragraph-index schema with no page_number.

---

## 2014-XUHUI-YIMO (worktree)

- draft 路径: `.codex/worktrees/langgraph-question-ingestion/teaching_skills/build/question-ingestion/2014-XUHUI-YIMO/run-17440144d50c/structured/paper.draft.yaml`
- draft 存在: True

> draft 原文（小于 400 字节的 fixture）:
```yaml
schema: math_exam_staging_draft/v1
paper_id: fake
sections: []
```

- 题数: **0** (draft 无 items)
- 分类: **no-items**
- documents 源: None 存在=False
- 建议动作: re-ingest (draft is empty fixture; transcription never produced items)

---

## 汇总表 (summary)

| 卷 | 题数 | q空 | s空 | q缺pn | s缺pn | 分类 | 源在 | 建议动作 |
|---|---|---|---|---|---|---|---|---|
| 2012-PUTUO-ERMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2012-YANGPU-ERMO-DOC-BENCHMARK | 25 | 0 | 0 | 25 | 25 | page_number-only | yes | 渲染 word/pages 后补 page_number |
| 2024-HUANGPU-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2024-JINGAN-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-CHANGNING-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-HONGKOU-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-HUANGPU-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-JINGAN-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-JINSHAN-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-MINHANG-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-PUDONG-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2025-QINGPU-YIMO | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2026-HUANGPU-TERM | 23 | 23 | 23 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2026-JINGAN-TERM | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2026-QINGPU-TERM | 25 | 25 | 25 | 0 | 0 | whole-volume-empty | yes | 重跑 word 转录 / 按 PDF 源处理 |
| 2026-PUTUO-ERMO | 24 | 0 | 0 | 24 | 24 | page_number-only | yes | 渲染 word/pages 后补 page_number |
| 2014-XUHUI-YIMO (worktree) | 0 | - | - | - | - | no-items | NO | 重新转录（draft 为空） |

## 按建议动作分组 (grouped)

- **re-run word-evidence transcription for these PDF pages, or ingest as PDF-source (question_evidence already has page crops)**
    - 2012-PUTUO-ERMO
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
- **render word/ pages (NNN.png) then map paragraph ranges to page_number; or rewrite evidence to page-image schema. Current entries are paragraph-index schema with no page_number.**
    - 2012-YANGPU-ERMO-DOC-BENCHMARK
    - 2026-PUTUO-ERMO
- **re-ingest (draft is empty fixture; transcription never produced items)**
    - 2014-XUHUI-YIMO (worktree)

