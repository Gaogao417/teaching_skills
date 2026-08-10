# 原卷快速录入 Draft 契约

## 目录

- [目的](#目的)
- [最小示例](#最小示例)
- [图片绑定](#图片绑定)
- [状态与限制](#状态与限制)

## 目的

每卷只手写一个 `paper.draft.yaml`。不要为每卷创建临时 `build_*.py`，也不要手写
25 份重复的 `source.yaml`、教师版和学生版。通用展开脚本负责生成固定样板，
物化脚本负责裁图、派生学生版和刷新哈希。

draft 必须放在最终 `staging/<paper-id>/paper.draft.yaml`。根字段：

- `schema: math_exam_staging_draft/v1`
- `paper`：`id`、`title`、`grade`、`subject`、`source_archive`，可选
  `duration`。
- `question_bank`：相对 `paper.yaml` 的正式题库路径。
- `sections[]`：章节，每章直接包含 `items[]`。

## 最小示例

```yaml
schema: math_exam_staging_draft/v1
paper:
  id: 2026-DEMO
  title: 2026 年示例卷
  grade: 九年级
  subject: 数学
  source_archive: documents/初三/2026-DEMO
question_bank: ../../question-bank.yaml
sections:
  - id: choice
    title: 一、选择题
    items:
      - item_id: Q001
        question_number: 1
        question_type: choice
        points: 4
        question_evidence:
          - source: documents/初三/2026-DEMO/001.png
            box_px: [80, 220, 1010, 380]
        prompt: []
        official_solution:
          start_anchor: '1. B'
          end_anchor: '2. D'
          crops:
            - source: documents/初三/2026-DEMO/006.png
              box_px: [80, 180, 1010, 240]
        block:
          stem_latex: 下列结论正确的是
          choices: [选项一, 选项二, 选项三, 选项四]
          answer: B
          clue: 逐项验证结论，排除不成立的。
```

每题必须有：

- `item_id`、`question_number`、`question_type`、`points`；
- 至少一条来源证据：PDF/扫描件用 `question_evidence` 页图 crop，Word 用
  `question_word_evidence` 整页图 + 页码；两者皆可，至少其一；
- `official_solution.start_anchor`、`end_anchor`，以及至少一个页图 crop 或
  Word 整页图证据；
- `block.stem_latex`、`block.answer`；
- 选择题恰好四个选项；
- `problem` / `short_answer` 含 `block.solution_steps`，且必须逐条复刻原解答，
  不得简化/合并/改写（保留中间结论、分类讨论分支、推理链）；
- `block.clue` 写解题思路提示，所有题型都写，不复读 `answer`。

crop 使用 `source`、`box_px`，可选 `whiteout_px`、`output`、`width`、
`label`、`assignment_path`。哈希、默认输出名和图片元数据由脚本生成。

DOC/DOCX 直接提取的独立题图使用完整媒体尺寸，例如：

```yaml
prompt:
  - source: documents/初三/PAPER-2026/word/media/image27.png
    box_px: [0, 0, 456, 255]
    width: 120mm
```

不得仅按 Word 媒体文件名判断题号；图片归属（哪张 `media/*` 属于哪道题、是题图
还是解析图）必须在 PDF 渲染页 `word/pages/*.png` 上按版面位置和邻近题号视觉锚点
确认。Word 来源用整页图 + 页码作为原题与官方解答证据，不要求页图 crop：

```yaml
question_word_evidence:
  - page_image: documents/初三/PAPER-2026/word/pages/002.png
    page_number: 2
official_solution:
  word_evidence:
    - page_image: documents/初三/PAPER-2026/word/pages/005.png
      page_number: 5
```

`page_image` 指向渲染后的整页 PNG（`word/pages/NNN.png`），`page_number` 即
文件名序号（1-based）。物化时写入 `page_image_sha256`；Review UI 在来源 section
右上角渲染成页码胶囊，点击可打开整页图。整页图证据不进入 `content_hash`——
源文件是不可变归档，无需漂移检测；转写内容（`stem_latex`/`solution_steps`）
在 hash 中，转写错误仍会触发重审。

以上两个字段都是有序页数组，不是“代表页”。跨页题干和跨页解答必须逐页列出完整
连续区间；题干与解答同页时允许两个数组共同引用该页。DOC/DOCX draft 必须在展开前
运行 `math-docx-question-bank-ingestion/scripts/word_evidence_pages.py`，且
`--check` 通过。共享 staging 审计会再次计算期望区间并拒绝缺页数据。

对于 Word 来源，PDF 渲染页（`word/pages/*.png`）同时作为公式转写的视觉参考：
draft 中的 `stem_latex` 和 `solution_steps` 内容应对照该渲染页准确转写，
不从 WMF 二进制猜测公式内容。

## 图片绑定

单个 `prompt` 默认绑定到题块 `/diagram_col`。单个 `solution` 默认绑定到
`/solution_steps/0/diagram_col`。多图时每张都必须用 JSON Pointer
`assignment_path` 指定位置，例如：

```yaml
prompt:
  - source: documents/初三/2026-DEMO/004.png
    box_px: [600, 420, 960, 760]
    assignment_path: /stem_image
solution:
  - source: documents/初三/2026-DEMO/008.png
    box_px: [650, 300, 990, 520]
    assignment_path: /solution_steps/1/diagram_col
```

`official_solution` 自动按 crop 顺序生成 `source_solution_images`，不在
`block` 中重复填写。`question_evidence` 不进入学生版或教师版题面。

### 多图放置（image placement）

当某题的 `prompt` 或 `solution` 出现多张图（例如宝山 Q24 三张连续题图）时，
v1 draft 的 `stem_latex` 是标量字符串，无法把多图分别插入"问题背景／数据测量／
问题解决"三段文本之间。**展开（expand）前**，`materialize_image_group.resolve_placement_decisions`
会把同一 `assignment_path` 下的多图纵向合成成一张组合 PNG，并把该角色替换为单个
带 `assignment_path` 的 crop，从而不触发 `every crop needs assignment_path`。

合成结果与决策依据写入 `staging/<paper>/placement-decisions.yaml`：

```yaml
placements:
  - question_id: Q024
    kind: image_group
    role: prompt
    image_ids: [image295.png, image301.png, image302.png]
    assignment_path: /diagram_col
    layout: vertical
    composed_source: items/Q024/assets/prompt-group.png
    warnings:
      - code: grouped_adjacent_to_scalar_stem
        message: Q024 prompt: 3 images share the scalar path /diagram_col; ...
```

`grouped_adjacent_to_scalar_stem` 是**非阻塞** warning（顺序与归属无歧义，仅版式
降级为相邻图组），不会暂停工作流。真正歧义（例如两张图声称不同 part 但 v1 无法
表达）才会进入 `needs_review` 并暂停。expander 不负责组合图片、不选择布局、不猜
步骤；多图必须在到达 expander 之前已被放置步骤合并为单图。

## 状态与限制

- draft 展开时把 `human_review` 设为 `pending`。
- 已出现 `review.yaml` 后禁止重新展开 draft；需要修改时先回到审核意见并明确
  作废旧决定。
- 展开脚本不识别 OCR、不判断数学内容，只消除重复样板代码。
- 首次结构审计不等于内容正确；只有用户在 Review UI 中批准当前哈希后才可晋升。
