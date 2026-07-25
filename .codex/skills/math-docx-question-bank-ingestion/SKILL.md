---
name: math-docx-question-bank-ingestion
description: "把数学试卷 DOC/DOCX 快速提取成可审核的原卷单题库 staging。Use when: 用户提供 Word 试卷（DOC/DOCX）与参考答案，要求批量逐题提取、保存题图、转写公式、进入题库。Skip when: 来源是 PDF/扫描件（用 math-pdf-question-bank-ingestion）；已有完整单题包只需审核/组卷。"
---

# 数学试卷 DOC/DOCX 原卷入题库

## 目标

DOC/DOCX 来源走**双通道提取**：

1. **Word 解包**：提取段落结构、原始嵌入媒体（题图 PNG + 公式 WMF/EMF）
2. **PDF 渲染**：soffice 转 PDF 后逐页渲染为 PNG（公式已变为可读位图）

以一个紧凑 `paper.draft.yaml` 完成首次录入，再用共享脚本展开正式 staging。

## 开始前读取

- `../math-pdf-question-bank-ingestion/references/staging-draft-contract.md`
- `../math-pdf-question-bank-ingestion/references/source-item-contract.md`
- `references/docx-source-contract.md`
- `../math-pdf-question-bank-ingestion/SKILL.md` 的"步骤 2-5"（draft 格式、图片绑定、展开/物化/审计、用户审核）

## 固定流程

### 1. 双通道提取

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
  word-source.yaml              # 段落结构 + 媒体清单 + PDF 页记录
  media/                        # Word 原始嵌入媒体（题图 PNG + 公式 WMF）
  rendered.pdf                  # soffice 渲染的 PDF
  pages/                        # PDF 逐页渲染的 PNG
```

| 通道 | 产物 | 用途 |
|------|------|------|
| Word 解包 | `media/*` | `prompt`/`solution` 题图（几何图、统计图、照片等） |
| PDF 渲染 | `pages/*.png` | 公式转写、题干核对、审计凭证 |

- 公式转写以 PDF 渲染页为准，不从 WMF 二进制猜测
- 题图以 Word 媒体原图为准，保留原始分辨率
- `.doc` 文件由 soffice 自动规范化为 `.docx` 后再走相同流程

### 2. 写 compact draft

浏览 PDF 渲染页和 Word 段落结构，写 `staging/<paper-id>/paper.draft.yaml`。

公式转写流程：
1. 在 `word-source.yaml` 中定位题目段落范围
2. 读取对应 PDF 渲染页（根据段落范围估算页码）
3. 从渲染页读取公式内容，转为可检索 LaTeX
4. 写入 `block.stem_latex` 或 `block.solution_steps`

题图处理：
- 独立几何图/统计图/照片 → 引用 `word/media/*` 原图，`box_px: [0, 0, w, h]`
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
