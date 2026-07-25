---
name: math-pdf-question-bank-ingestion
description: "把数学试卷 PDF、扫描页、DOC 或 DOCX 快速提取成可审核的原卷单题库 staging，并在用户逐题批准后整卷原子晋升。Use when: 用户提供 PDF/图片/Word 试卷与参考答案，要求批量逐题提取、直接保存 Word 内题图/公式对象、保存来源凭证、进入题库或以后还原整卷。Skip when: 已有完整单题包只需审核/组卷，或只需阅读文档、普通解题、专题题库生成。"
---

# 数学试卷文档原卷入题库

## 目标和原则

PDF/扫描件冻结为不可变页图；Word 来源直接提取正文段落、题图和公式对象，不以
PDF 为中间格式。以一个紧凑 `paper.draft.yaml` 完成首次录入，再用通用脚本展开
正式 staging。最终产物兼容 `math-topic-question-bank` 原卷模式。

速度原则：

- 每卷只手写一个 draft；禁止创建卷专用 `build_*.py`。
- 不手写学生版，不逐题编译 PDF，不为轻微裁框问题循环返修。
- 批量展开、裁图、派生和结构审计必须交给脚本。
- 只保留两个状态：机器结构审计通过、用户人工批准。不要增加额外复核 gate。

开始前读取：

- `references/staging-draft-contract.md`
- `references/source-item-contract.md`
- DOC/DOCX 来源再读 `references/word-source-contract.md`
- `.codex/skills/math-topic-question-bank/SKILL.md` 的“模式 C”和“题库 Review UI”

## 固定流程

### 1. 按来源格式冻结

先确认试题和参考答案属于同一份卷，再按格式分流。

#### PDF 或扫描页

PDF 用仓库虚拟环境渲染到新目录：

```bash
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/render_pdf_pages.py \
  <paper.pdf> <source-archive-dir>
```

已有编号 PNG/JPEG 时只校验可读性。页图一旦被引用即不可变。

#### DOC 或 DOCX

DOC/DOCX 来源走双通道提取：**Word 解包取原始媒体图 + soffice 转 PDF 取渲染文本**。

```bash
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/extract_word_source.py \
  <paper.doc-or-docx> <source-archive-dir>/word
```

产出目录结构：

```text
word/
  source.docx|source.doc          # 原始文件副本
  normalized.docx                  # OOXML 规范化版本
  word-source.yaml                 # 段落结构 + 媒体清单 + PDF 页记录
  media/                           # Word 原始嵌入媒体（题图 PNG + 公式 WMF/EMF）
  ooxml/                           # 原始 XML 结构
  rendered.pdf                     # soffice 渲染的 PDF（公式已变为位图）
  pages/                           # PDF 逐页渲染的 PNG（001.png, 002.png, ...）
```

双通道各自职责：

| 通道 | 来源 | 产物 | 用途 |
|------|------|------|------|
| Word 解包 | `word/media/*` | 原始 PNG/WMF/EMF | `prompt`/`solution` 题图（几何图、统计图、照片等） |
| PDF 渲染 | `rendered.pdf` → `pages/*.png` | 渲染页图 | 公式转写、题干文本核对、`question_evidence` 审计凭证 |

关键规则：

- **公式转写以 PDF 渲染页为准**，不从 WMF 二进制猜测。PDF 里公式是渲染好的位图，
  可直接读取转为 LaTeX。
- **题图（几何图、函数图、表格、照片）以 Word 媒体原图为准**，因为 PDF 渲染可能
  降低分辨率或丢失透明度。
- `question_word_evidence` 和 `official_solution.word_evidence` 记录 `word-source.yaml`
  中的段落范围（Word 通道）；PDF 页图作为转写过程中的视觉参考和审计凭证。
- `.doc` 文件由 soffice 自动规范化为 `.docx` 后再走相同流程。
- 详细规则见 `references/word-source-contract.md`。

### 2. 单次浏览并写 compact draft

一次浏览完题目页和答案页，只写：

```text
staging/<paper-id>/paper.draft.yaml
```

draft 同时记录卷级信息、章节、每题结构化转写、题目/答案页、答案锚点和 crop。
格式读取 `references/staging-draft-contract.md`。

必须满足：

- 原题和官方解答忠实转写为可检索 LaTeX，不补写来源中没有的推理。
- 选择题保存四个纯选项正文，答案为 `A/B/C/D`。
- `problem` / `short_answer` 保存官方 `solution_steps`。
- 官方错字、跳步或疑点写入 `solution_notes`，不擅自修正。
- `paper-map` 的答案锚点抄录页上可见短文本，最后一题可用
  `<END_OF_SOURCE>`。
- Word 来源根据 `word-source.yaml` 的段落顺序和媒体关系定位题目与解析；公式对象
  结合邻近文本转写。不得把自动提取结果当成已经人工批准的真值。

禁止逐题创建 `source.yaml`、教师版、学生版或临时 Python 生成器。

### 3. 图片只做一次合理绑定或定位

PDF/扫描件有四类图片；Word 只要求题面确实需要的 `prompt` / `solution` 图片：

- `question_evidence`：PDF/扫描件的完整原题审计凭证，不进入题面。
- `prompt`：学生作答必需的独立题图、表格、照片或强排版材料。
- `solution`：官方解答中的独立解答图，绑定具体解答步骤。
- `official_solution`：PDF/扫描件的完整官方答案来源凭证。

普通“文字 + 单图”题用 `stem_latex` 加独立 `prompt`；纯文字题不建 prompt。
只有材料框、复杂表格、照片与说明强绑定时才用 `stem_image`。不得把整题截图复制成
普通 prompt。

来源优先级：

1. DOC/DOCX 中可明确归属的独立 `word/media/*` 原图；使用完整图片
   `box_px: [0, 0, width, height]`。
2. 多张 Word 图片共同组成一个不可拆布局时，使用段落顺序确定性组合；无法可靠恢复
   时标记人工核对，不自动转 PDF。
3. PDF/扫描件才从页图裁 `prompt` / `solution`。

公式碎片默认只辅助 LaTeX 转写，不作为 `prompt`。Word 直接提取图清晰但像素较小时，
保留原图和哈希；不得用生成式重画替代来源。Word 的完整原题与官方解答证据来自
带哈希的段落范围，不要求页图。

题图只尝试一次：

- 主体和必要标签完整即可。
- 水印、少量邻近文字、宽边或最佳裁框不确定时，保留当前 crop，写
  `prompt_status: needs_human_crop` 和具体说明，继续下一题。
- 不得为了“更美观”“更紧凑”或消除上述轻微瑕疵反复修改 bbox、重裁或重复物化；
  contact sheet 视觉更好不是继续迭代的条件。
- 只有以下硬错误允许再次裁切：整题截图误作普通 prompt；主体或必要标签缺失；
  混入其他题导致语义错误；题号、四个选项或答案证据错位；学生版发生答案泄漏。

原卷归档不使用 `diagram_slot`，不重画原图。

### 4. 一次展开、物化和结构审计

```bash
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py \
  staging/<paper-id>/paper.draft.yaml

./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/materialize_staging.py \
  staging/<paper-id> --repo-root .

./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py \
  staging/<paper-id> --repo-root .
```

展开脚本统一生成 `paper.yaml`、`paper-map.yaml`、每题 `source.yaml`、
`teacher.resolved.assignment.yaml`。物化脚本裁图、派生学生版、刷新哈希；内容
变化时自动把人工审核状态重置为 pending。审计脚本按来源格式检查页图 crop 或 Word
段落范围、哈希、图片引用和学生/教师隔离，并生成全卷 contact sheet。

默认 `STAGING VALID ... gate=structural` 只表示结构正确、可进入复核，不表示转写
内容已经正确。不得把它汇报为“用户已批准”。

结构审计后只看 contact sheet 的异常题，不逐像素检查全部题。若只剩轻微裁框问题，
保留 `needs_human_crop`，不要重新物化全卷。

### 5. 用户审核与晋升

结构审计通过后启动 Review UI，由用户逐题对照来源证据、contact sheet 和转写，重点
检查题号、四选项、答案映射、跨页答案、公式单位、题图主体和官方解答保真：

```bash
./.venv/bin/python \
  .codex/skills/math-topic-question-bank/scripts/open_question_bank_review.py
```

`review.yaml` 是唯一内容审核凭证，并绑定当前 `content_hash`；修改文字或图片后旧
决定自动过期。全部题目由用户批准后运行：

```bash
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py \
  staging/<paper-id> --repo-root . --require-approved-review

./.venv/bin/python \
  .codex/skills/math-topic-question-bank/scripts/promote_exam_paper.py \
  staging/<paper-id>/paper.yaml <question-bank.yaml>
```

只能整卷原子晋升；任何一题失败都不得部分进入正式题库。

## 批量调度

- 先扫描完整 staging，已有 `paper.yaml`、完整 items 和 contact sheet 的卷不重复做。
- 一名 worker 一次只负责一卷并独占其目录；多卷可并行。
- 每卷使用与当前真实 `paper_id` 对齐且不复用的任务名；完成该卷后结束 turn 并释放
  槽位。不得沿用上一卷的任务名处理后续试卷。
- 首次录入时间只统计到 `gate=structural`；用户审核单独计时。
- 进度汇报写当前真实 `paper_id` 和该 turn 已运行时间，并只列：
  structural valid、human approved、`needs_human_crop`、硬错误返修和真实阻塞数。
- 不因单卷异常修改共享合同或增加临时门禁。

## 停止条件

默认自动化交付点是：draft 已展开、全卷已物化、结构审计通过、contact sheet 已
生成，人工审核状态保持 pending。只有当前哈希全部获用户批准时才可晋升。
