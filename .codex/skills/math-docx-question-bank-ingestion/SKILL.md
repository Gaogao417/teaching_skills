---
name: math-docx-question-bank-ingestion
description: "把数学试卷 DOC/DOCX 快速提取成可审核的原卷单题库 staging。Use when: 用户提供 Word 试卷（DOC/DOCX）与参考答案，要求批量逐题提取、保存题图、转写公式、进入题库。Skip when: 来源是 PDF/扫描件（用 math-pdf-question-bank-ingestion）；已有完整单题包只需审核/组卷。"
---

# 数学试卷 DOC/DOCX 原卷入题库

## 目标

DOC/DOCX 来源只从 Word 拿两类不可替代的素材，其余与 PDF 来源一致：

1. **Word 媒体原图**：独立题图/解析图（几何图、统计图、照片等）。PDF 渲染会二次
   栅格化并丢透明度，所以图必须从 `word/media/*` 取。
2. **PDF 渲染页**：soffice 把同一份 DOCX 转 PDF 后逐页渲染为 PNG。**所有文字和
   公式都从这里转写**——DOCX 里的公式是 WMF/EMF 矢量对象，无法直接读取。

以一个紧凑 `paper.draft.yaml` 完成首次录入，再用共享脚本展开正式 staging。

## 开始前读取

- `../math-pdf-question-bank-ingestion/references/staging-draft-contract.md`
- `../math-pdf-question-bank-ingestion/references/source-item-contract.md`
- `references/docx-source-contract.md`
- `../math-pdf-question-bank-ingestion/SKILL.md` 的"步骤 2-5"（draft 格式、图片绑定、展开/物化/审计、用户审核）

## 固定流程

### 1. 提取媒体原图 + 渲染 PDF 页

```bash
./.venv/bin/python \
  .codex/skills/math-docx-question-bank-ingestion/scripts/extract_docx_source.py \
  <paper.doc-or-docx> <source-archive-dir>/word
```

产出：

```text
word/
  source.docx|source.doc       # 原始文件副本
  normalized.docx               # OOXML 规范化版本
  word-source.yaml              # 媒体清单 + PDF 页记录
  media/                        # Word 原始嵌入媒体（题图 PNG + 公式 WMF）
  rendered.pdf                  # soffice 渲染的 PDF
  pages/                        # PDF 逐页渲染的 PNG
```

| 产物 | 用途 |
|------|------|
| `media/*` | `prompt`/`solution` 题图（几何图、统计图、照片等），保留原始分辨率与透明度 |
| `pages/*.png` | **所有文字和公式转写**、题干核对、审计凭证、低置信图核对 |
| `word-source.yaml` 的 `image_attribution` | **图片归属主源**：每张题图的题号、prompt/solution 桶、置信度 |

- 文字和公式一律以 PDF 渲染页为准，不从 WMF 二进制猜测
- **图片归属以段落流 `image_attribution` 为准**，不在 PDF 页上肉眼认图
- 独立题图以 Word 媒体原图为准（PDF 渲染会栅格化丢质量）
- `.doc` 文件由 soffice 自动规范化为 `.docx` 后再走相同流程

### 2. 写 compact draft

浏览 PDF 渲染页 `word/pages/*.png`，写 `staging/<paper-id>/paper.draft.yaml`。
录入方式与 `math-pdf-question-bank-ingestion` 一致——题号、文字、公式、图片归属
全部在渲染页上按版面/视觉锚点确认。

文字与公式转写：
1. 在 `word/pages/*.png` 上按题号视觉锚点定位题目所在页
2. 把该页路径和页码填入 `question_word_evidence`（或 `official_solution.word_evidence`）
3. 从渲染页读取文字和公式内容，转为可检索 LaTeX
4. 写入 `block.stem_latex` 或 `block.solution_steps`

题图处理：
- 读取 `word-source.yaml` 的 `image_attribution`，按置信度消费：
  - **`high`**：直接写入 `prompt`/`solution`，引用 `word/media/*` 原图，
    `box_px: [0, 0, w, h]`，无需看 PDF
  - **`medium`**：写入后对照 PDF 渲染页或图本身确认。常见情形：
    - 多选项题（如 Q2 四个图书馆标志）：段落流会给同一题多张图，全部挂 prompt
    - 合成图（一张 PNG 含多个子图）：按实际挂 1 条
    - 多小问图（"如图1…（2）如图2…"）：第二张图可能被算到 solution，看 PDF 确认
  - **`low`**：必须人工核对后再写——图跨多段重复、题号切片存疑、或 orphan
- 纯文字+公式题 → 不创建 prompt，公式在 stem_latex 中

### 3-5. 展开、物化、审计、用户审核

与 `math-pdf-question-bank-ingestion` 共享脚本：

```bash
# 展开
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py \
  staging/<paper-id>/paper.draft.yaml

# 物化
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/materialize_staging.py \
  staging/<paper-id> --repo-root .

# 审计
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py \
  staging/<paper-id> --repo-root .

# 审核
./.venv/bin/python \
  .codex/skills/math-topic-question-bank/scripts/open_question_bank_review.py
```

## 依赖

| 工具 | 用途 | 必需？ |
|------|------|--------|
| `soffice` (LibreOffice) | DOC→DOCX 规范化 + DOCX→PDF 渲染 | 是 |
| `pdftoppm` | PDF→PNG 页面渲染 | 是 |

安装 LibreOffice：`brew install --cask libreoffice`
