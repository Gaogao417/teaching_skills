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

文本、图片及其精确位置先收敛为 `paper.source.yaml`
（`math_exam_source_paper/v2`）。它用 RichContent 表达题干、A–D 选项、小问题干和
各级解答步骤内的图文顺序，是权威原卷数据。现有 `paper.draft.yaml` 仅由 projector
生成兼容视图，再交给共享脚本展开正式 staging；Agent 不直接编写 draft。

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
| `media/*` | SourceImageAsset 原始媒体（题图、选项图、小问题图、解答图等） |
| `pages/*.png` | **所有文字和公式转写**、题干核对、审计凭证、低置信图核对 |
| `word-source.yaml` 的 `image_attribution` | **图片归属主源**：每张题图的题号、prompt/solution 桶、置信度 |

- 文字和公式一律以 PDF 渲染页为准，不从 WMF/EMF 的 GDI 文字猜测
- 媒体是否为公式只看 OLE 绑定：绑 OLE → `formula`，未绑 → `diagram`；
  不得再按 `.wmf/.emf` 扩展名一律丢弃
- 疑似图文整块混排时创建 blocking asset review issue；人工确认后才可定为
  `mixed_content`，拿不准则保持 `needs_review` 并写明卡点
- **图片归属以段落流 `image_attribution` 为准**，不在 PDF 页上肉眼认图
- 独立题图以 Word 媒体原图为准（PDF 渲染会栅格化丢质量）
- `.doc` 文件由 soffice 自动规范化为 `.docx` 后再走相同流程
- 若题号状态机检测到向前断号、题号序列失步或图片归属结构坍缩，只废弃本次
  **全部图片归属结果**，不得保留“前半段看似正确”的 partial mapping。
  `word-source.yaml` 写入 `image_attribution_status: failed`、空
  `image_attribution` 和结构化错误；媒体、PDF 与页面仍正常产出，题干/解析文本观察
  继续运行。图片 adapter 必须拒绝 failed 状态。
- 图片归属失败后不得让 agent 按 `imageNN` 文件名、媒体顺序或相邻题号手工猜映射。
  含图题保留文本并标 `image_structure: needs_review`；纯文字题可继续。缺少作答必需
  图形的题不得进入完整 structural 输出。

### 2. 联合观察并生成 SourceQuestion v2

先准备只含卷级字段的 `paper-meta.yaml`。**先索引、后定点转写**：用 `pdftotext`
对 rendered.pdf 做逐页题号预扫，生成 `math_question_span_index/v1`，再让 MiMo 按
索引产生的确定性批次观察。批次首轮页面互不重叠，每批必须返回索引指定的预期题号；
漏报/多报/重复只触发对缺失题的定点补读，正常题冻结复用不重跑。模型结果仍必须经过
严格 contract 和确定性 merge，不能直接写 draft：

```bash
# 先建索引（试卷与答案分文件时分别建索引，答案文件传与 observe 相同的 offset）
./.venv/bin/python scripts/question_transcription/build_docx_span_index.py \
  --word-source <source-archive>/word/word-source.yaml \
  --output <build>/word.span-index.yaml

./.venv/bin/python scripts/question_transcription/observe_docx_pages.py \
  --word-source <source-archive>/word/word-source.yaml \
  --span-index <build>/word.span-index.yaml \
  --source-archive <source-archive> \
  --mimo-structured --cache-dir <build>/cache --output-dir <build>/windows

# 试卷与答案分文件时，答案页使用试卷页数作为 offset 续编；
# evidence 仍保留真实的 word-answers 子目录。
./.venv/bin/python scripts/question_transcription/build_docx_span_index.py \
  --word-source <source-archive>/word-answers/word-source.yaml \
  --output <build>/word-answers.span-index.yaml \
  --page-number-offset <exam-page-count>

./.venv/bin/python scripts/question_transcription/observe_docx_pages.py \
  --word-source <source-archive>/word-answers/word-source.yaml \
  --span-index <build>/word-answers.span-index.yaml \
  --source-archive <source-archive> --source-subdir word-answers \
  --page-number-offset <exam-page-count> \
  --mimo-structured --cache-dir <build>/cache --output-dir <build>/windows

./.venv/bin/python scripts/question_transcription/merge_docx_observations.py \
  --windows <build>/windows/*.yaml \
  --paper-meta <build>/paper-meta.yaml \
  --output <build>/docx-observation.yaml \
  --issues <build>/review-issues.yaml

./.venv/bin/python scripts/question_transcription/adapt_docx_transcription.py \
  --observation <build>/docx-observation.yaml \
  --output <build>/transcription.yaml

./.venv/bin/python scripts/question_transcription/workflow/adapters/source/adapt_docx_images.py \
  --word-source <source-archive>/word/word-source.yaml \
  --paper-id <paper-id> --source-archive <source-archive> \
  --output <build>/image-attribution.yaml

## provider/assembler 按 source_paper.schema 生成权威原卷
## <build>/paper.source.yaml

./.venv/bin/python scripts/question_transcription/project_source_paper.py \
  --source <build>/paper.source.yaml \
  --skeleton <build>/transcription.yaml \
  --issues <build>/review-issues.yaml \
  --resolutions <build>/review-resolutions.yaml \
  --output staging/<paper-id>/paper.draft.yaml \
  --report <build>/assembly-report.yaml
```

当 `image_attribution_status: failed` 时，跳过 `adapt_docx_images.py`，但仍运行
`observe_docx_pages.py`、merge 和 transcription adapter。文本产物与图片结构状态
独立；不得把空图片 bundle 解释成“本卷无图”。

`merge` 返回 2 或生成 `review-issues.yaml` 时，不得运行普通 adapter。盲观察冻结后
可用 `compare_existing_staging.py` 与已有 staging 对照，但对照只能追加待审候选，
不能改写 merge 的暂选结果。随后用 `build_review_staging.py` 创建隔离审核卷，在
Review UI 逐项裁决；裁决完成后运行：

```bash
./.venv/bin/python scripts/question_transcription/apply_review_resolutions.py \
  --observation <build>/docx-observation.yaml \
  --issues <review-staging>/review-issues.yaml \
  --resolutions <review-staging>/review-resolutions.yaml \
  --output <build>/docx-observation.resolved.yaml
```

只能对 resolved observation 重跑普通 adapter，并写入一个不含
`review-issues.yaml` 的全新正常 staging。隔离审核卷本身不可批准或晋升。

无 review sidecar 时省略对应参数。Projector 会先执行跨 bundle gate：
`needs_review`、未解决/过期的 blocking issue、review 结论与资产最终分类不一致，
任一存在都拒绝写 draft。

`MIMO_API_KEY` 只从环境读取，不写入文件或日志。MiMo 通过 PydanticAI
tool calling 按 span index 的非重叠首轮批次统一转写数学题干、公式、选项、答案和
原解析，但不输出或消费 DOCX bbox。媒体必须由 adapter 转成 PydanticAI
`BinaryContent`，不能把 OpenAI message dict 直接传给 `Agent.run()`。输出在模型
边界由 Pydantic contract 验证；缺题/重复题只定点补读对应索引页，已通过题冻结复用。
百炼 `qwen3.5-ocr` 仅作为显式降级 provider：只有 MiMo 不可用且操作者主动传入
`--bailian-ocr` 时才逐页运行，不与 MiMo 串行重复处理。

模型/结构 provider 的 `medium`/`low` 图片归属统一为 `needs_review`；人工确认前
不会进入结构输出。跨页范围最终仍由后续确定性证据展开器补齐。

文字、公式与跨页来源：
1. 在 `word/pages/*.png` 上按题号视觉锚点定位题干**第一页**和官方解答
   **第一页**；先把这两个 seed 页分别写入 `question_word_evidence` 和
   `official_solution.word_evidence`
2. draft 写完后必须运行确定性的跨页展开器；它根据下一题 seed 页和文档末页补齐
   每一道题的连续页区间，不使用多模态模型：

   ```bash
   ./.venv/bin/python \
     .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py \
     staging/<paper-id>/paper.draft.yaml --repo-root .
   ```

3. 题目与解析交替排版时自动使用 `interleaved`；先整卷题目、后整卷答案时自动使用
   `separated`。自动判断失败必须人工确认后传 `--layout`，不得跳过
4. `question_word_evidence` 必须覆盖完整题干涉及的全部页；
   `official_solution.word_evidence` 必须覆盖答案/分析/详解到下一题前的全部页。
   题干与解答同页时，该页允许同时出现在两个数组；跨页不得只填首页、末页或代表页
5. 从完整渲染页区间读取文字和公式，转为可检索 LaTeX，写入
   `QuestionTranscriptionBundle.content`

图文位置处理：
- 读取 `word-source.yaml` 的段落锚和粗粒度 `image_attribution`，再写入 v2 精确 target：
  `question_stem`、`choice(A-D)`、`part_stem(part_id)`、
  `question_solution_step(step_id)` 或
  `part_solution_step(part_id, step_id)`。
- 图必须同时出现在对应 RichContent 的 `ImageNode` 中；不允许把所有图笼统塞进
  `prompt`，也不允许用 `prompt: []` 掩盖未完成的图像归属。
  - **`high`**：可直接绑定精确 target，资产优先引用 `word/media/*` 原图
  - **`medium`**：写入后对照 PDF 渲染页或图本身确认。常见情形：
    - 四个图像选项：可靠时拆成 A/B/C/D 四个 choice target；不可可靠拆分时保留
      choice panel，并要求人工确认 A–D mapping
    - 合成图：整体作为一个目标节点，禁止假装已拆分
    - 多小问图：绑定具体 `part_id`；解答图还要绑定具体 `step_id`
  - **`low`**：必须人工核对后再写——图跨多段重复、题号切片存疑、或 orphan
- 纯文字+公式题 → 不创建 prompt，公式在 stem_latex 中

`paper.source.yaml` 是无损权威数据；projector 会把 RichContent 图降为旧 draft 的
prompt/official_solution 图片列表，并为纯图选项生成兼容占位文本。现有 latex-data
skills 暂不改 schema，仍消费旧 staging；未来若需要按原位置排版，应直接读取
SourceQuestion v2，不能反向从兼容 draft 猜回 A–D/小问/步骤归属。

### 3-5. 展开、物化、审计、用户审核

与 `math-pdf-question-bank-ingestion` 共享脚本：

展开前必须先确认跨页证据完整：

```bash
./.venv/bin/python \
  .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py \
  staging/<paper-id>/paper.draft.yaml --repo-root . --check
```

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

## 通知 Review UI 失效缓存

物化/换图后（写完 `staging/<paper-id>/` 下任一 `source.yaml` /
`teacher.resolved.assignment.yaml` / `student.resolved.assignment.yaml`），
调用一次 notify，让本地 Review UI 的读模型重建，避免显示陈旧内容：

```bash
./.venv/bin/python \
  .codex/skills/math-topic-question-bank/scripts/notify_catalog_version.py \
  --bank-dir staging/<paper-id>
# 若已知 Review UI 端口，追加 --endpoint http://127.0.0.1:8877 --bank staging:<源>:<paper-id> 立即重建
```

`.catalog-version` 是可重建的失效标记（`.gitignore` 已忽略）。详情见
`docs/review-server-performance-redesign.md` §5/§7。

## 依赖

| 工具 | 用途 | 必需？ |
|------|------|--------|
| `soffice` (LibreOffice) | DOC→DOCX 规范化 + DOCX→PDF 渲染 | 是 |
| `pdftoppm` | PDF→PNG 页面渲染 | 是 |
| `pdftotext`（Poppler） | DOCX rendered PDF 的逐页题号预扫（建 span index） | 是 |
| `pydantic-ai`（Python 包） | MiMo tool calling、`BinaryContent` 多模态输入与结构化输出验证 | 是 |

安装 LibreOffice：`brew install --cask libreoffice`；安装 Poppler（提供
`pdftoppm` 和 `pdftotext`）：`brew install poppler`。
