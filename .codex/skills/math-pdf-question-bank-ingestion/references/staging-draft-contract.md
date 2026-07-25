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
          explanation: 官方参考答案：B。
```

每题必须有：

- `item_id`、`question_number`、`question_type`、`points`；
- PDF/扫描件至少一个 `question_evidence` crop；Word 至少一个
  `question_word_evidence` 段落范围；
- `official_solution.start_anchor`、`end_anchor`，以及至少一个页图 crop 或 Word
  段落范围；
- `block.stem_latex`、`block.answer`；
- 选择题恰好四个选项；
- `problem` / `short_answer` 含 `block.solution_steps`。

crop 使用 `source`、`box_px`，可选 `whiteout_px`、`output`、`width`、
`label`、`assignment_path`。哈希、默认输出名和图片元数据由脚本生成。

DOC/DOCX 直接提取的独立题图使用完整媒体尺寸，例如：

```yaml
prompt:
  - source: documents/初三/PAPER-2026/word/media/image27.png
    box_px: [0, 0, 456, 255]
    width: 120mm
```

不得仅按 Word 媒体文件名判断题号；归属必须来自 `word-source.yaml` 的段落关系。
Word 使用段落范围作为原题与官方解答证据，不要求页图 crop。

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

## 状态与限制

- draft 展开时把 `human_review` 设为 `pending`。
- 已出现 `review.yaml` 后禁止重新展开 draft；需要修改时先回到审核意见并明确
  作废旧决定。
- 展开脚本不识别 OCR、不判断数学内容，只消除重复样板代码。
- 首次结构审计不等于内容正确；只有用户在 Review UI 中批准当前哈希后才可晋升。
