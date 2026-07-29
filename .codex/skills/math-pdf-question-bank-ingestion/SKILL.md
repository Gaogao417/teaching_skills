---
name: math-pdf-question-bank-ingestion
description: "把数学试卷 PDF、扫描页快速提取成可审核的原卷单题库 staging，并在用户逐题批准后整卷原子晋升。Use when: 用户提供 PDF/扫描件试卷与参考答案，要求批量逐题提取、裁切页图、保存来源凭证、进入题库。Skip when: 来源是 DOC/DOCX（用 math-docx-question-bank-ingestion）；已有完整单题包只需审核/组卷。"
---

# 数学试卷 PDF/扫描件原卷入题库

## 目标和原则

PDF/扫描件冻结为不可变页图。多模态 provider 一次产生文本转录和图片 bbox 的联合
观察，经两个标准 Bundle 和统一 DraftAssembler 生成 `paper.draft.yaml`，再用通用
脚本展开正式 staging。Agent 不直接编写 draft。

速度原则：

- 每卷只手写一个 draft；禁止创建卷专用 `build_*.py`。
- 不手写学生版，不逐题编译 PDF，不为轻微裁框问题循环返修。
- 批量展开、裁图、派生和结构审计必须交给脚本。
- 只保留两个状态：机器结构审计通过、用户人工批准。不要增加额外复核 gate。

开始前读取：

- `references/staging-draft-contract.md`
- `references/source-item-contract.md`
- `.codex/skills/math-topic-question-bank/SKILL.md` 的"模式 C"和"题库 Review UI"

## 共享脚本

以下脚本位于本 skill 目录，同时被 `math-docx-question-bank-ingestion` 共享：

| 脚本 | 用途 |
|------|------|
| `scripts/expand_staging_draft.py` | 展开 draft 为正式 staging 文件 |
| `scripts/materialize_staging.py` | 裁图、派生学生版、刷新哈希 |
| `scripts/audit_staging.py` | 结构审计 + contact sheet |
| `scripts/paper_map_contracts.py` | paper-map 校验 |
| `references/staging-draft-contract.md` | draft 格式契约 |
| `references/source-item-contract.md` | 单题来源契约 |

## 固定流程

### 1. 渲染 PDF 页图

```bash
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/render_pdf_pages.py \
  <paper.pdf> <source-archive-dir>
```

已有编号 PNG/JPEG 时只校验可读性。页图一旦被引用即不可变。

### 2. 单次联合观察并生成标准 Bundle

先生成不可变页面 manifest，并准备只含卷级字段的 `paper-meta.yaml`：

```bash
./.venv/bin/python scripts/question_transcription/pdf_source_manifest.py \
  --paper-id <paper-id> --source-archive <source-archive> \
  --pages-dir <source-archive> --engine pdftoppm \
  --pdf <paper.pdf> --output <build>/pdf-source.yaml

./.venv/bin/python scripts/question_transcription/observe_pdf_pages.py \
  --manifest <build>/pdf-source.yaml \
  --paper-meta <build>/paper-meta.yaml \
  --cache-dir <build>/cache --output-dir <build>/windows

./.venv/bin/python scripts/question_transcription/merge_pdf_observations.py \
  <build>/windows/*.observation.yaml \
  --output <build>/pdf-observation.yaml \
  --issues <build>/review-issues.yaml

./.venv/bin/python scripts/question_transcription/adapt_pdf_transcription.py \
  --observation <build>/pdf-observation.yaml \
  --output <build>/transcription.yaml

./.venv/bin/python scripts/question_transcription/adapt_pdf_images.py \
  --detection <build>/pdf-observation.yaml \
  --output <build>/image-attribution.yaml

./.venv/bin/python scripts/question_transcription/assemble_paper_draft.py \
  --transcription <build>/transcription.yaml \
  --images <build>/image-attribution.yaml \
  --output staging/<paper-id>/paper.draft.yaml \
  --report <build>/assembly-report.yaml
```

若 merge 生成 `review-issues.yaml`，普通 adapter 会拒绝继续。冻结盲观察后可运行
`compare_existing_staging.py`，但旧 staging 只作为待审候选，绝不自动覆盖模型
结果。用 `build_review_staging.py` 生成隔离审核卷，在 Review UI 对照页图/bbox
逐字段裁决；再用 `apply_review_resolutions.py` 生成无冲突 observation，并从普通
adapter 重跑。含 `review-issues.yaml` 的隔离卷不能通过 approved audit 或晋升。

MiMo 使用环境中的 `MIMO_API_KEY`，同一次调用返回文字、公式、证据框和独立题图
bbox。模型自报 `accepted` 仍会默认降级为 `needs_review`；只有人工核对 crop 后才
允许用 `adapt_pdf_images.py --allow-model-accepted` 重新生成图片 Bundle。

必须满足：

- 原题和解答忠实转写为可检索 LaTeX。
- `solution_steps` 必须逐条复刻原解答，不得简化、合并或改写：保留每一个推理步骤、
  中间结论、分类讨论分支、角的对应和比例变形。原解答分 8 步，转写就要 8 步，不得
  压成 3 句话。"提炼要点"是 `clue` 的职责，不是 `solution_steps` 的。
- `clue` 写解题思路提示（一句话点明考点或思路），所有题型都写。不得复读 `answer`，
  不得写"参考答案：X"这类冗余前缀。
- 选择题保存四个纯选项正文，答案为 `A/B/C/D`。
- `problem` / `short_answer` 保存 `solution_steps`。
- 原解答错字、跳步或疑点写入 `solution_notes`，不擅自修正。
- `paper-map` 的答案锚点抄录页上可见短文本，最后一题可用
  `<END_OF_SOURCE>`。

禁止逐题创建 `source.yaml`、教师版、学生版或临时 Python 生成器。

### 3. 图片只做一次合理绑定或定位

PDF/扫描件有四类图片：

- `question_evidence`：完整原题审计凭证，不进入题面。
- `prompt`：学生作答必需的独立题图、表格、照片或强排版材料。
- `solution`：官方解答中的独立解答图，绑定具体解答步骤。
- `official_solution`：完整官方答案来源凭证。

普通"文字 + 单图"题用 `stem_latex` 加独立 `prompt`；纯文字题不建 prompt。
只有材料框、复杂表格、照片与说明强绑定时才用 `stem_image`。不得把整题截图复制成
普通 prompt。

从页图裁 `prompt` / `solution`。

题图只尝试一次：

- 主体和必要标签完整即可。
- 水印、少量邻近文字、宽边或最佳裁框不确定时，保留当前 crop，写
  `prompt_status: needs_human_crop` 和具体说明，继续下一题。
- 不得为了"更美观""更紧凑"或消除上述轻微瑕疵反复修改 bbox、重裁或重复物化；
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
变化时自动把人工审核状态重置为 pending。审计脚本按来源格式检查页图 crop、哈希、
图片引用和学生/教师隔离，并生成全卷 contact sheet。

默认 `STAGING VALID ... gate=structural` 只表示结构正确、可进入复核，不表示转写
内容已经正确。不得把它汇报为"用户已批准"。

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

### 6. 通知 Review UI 失效缓存

物化/换图/晋升后（写完 `staging/<paper-id>/` 下任一 `source.yaml` /
`teacher.resolved.assignment.yaml` / `student.resolved.assignment.yaml`），
调用一次 notify，让本地 Review UI 的读模型重建，避免显示陈旧内容：

```bash
./.venv/bin/python \
  .codex/skills/math-topic-question-bank/scripts/notify_catalog_version.py \
  --bank-dir staging/<paper-id>   # bump .catalog-version（跨进程，文件系统级）
# 若已知 Review UI 端口，追加 --endpoint http://127.0.0.1:8877 --bank staging:<源>:<paper-id> 立即重建
```

`.catalog-version` 是可重建的失效标记（`.gitignore` 已忽略），不会进版本库。详情见
`docs/review-server-performance-redesign.md` §5/§7。

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
