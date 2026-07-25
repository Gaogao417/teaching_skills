# 单题来源与图片角色契约

## 目录

- [目录与职责](#目录与职责)
- [paper-map.yaml 示例](#paper-mapyaml-示例)
- [source.yaml 示例](#sourceyaml-示例)
- [用户审核凭证](#用户审核凭证)
- [教师版引用](#教师版引用)
- [题图人工补裁标记](#题图人工补裁标记)
- [四类角色的自动约束](#四类角色的自动约束)

## 目录与职责

`paper.yaml` 保存卷级元数据、章节和题目顺序。`paper-map.yaml` 保存轻量的
题目页/答案页导航和答案起止锚点。每题 `source.yaml` 保存精确裁切框、图片角色和
哈希。map 不复制像素框或哈希，`source.yaml` 不重复答案文本锚点。

最小目录：

```text
staging/<paper-id>/
├── paper.draft.yaml
├── paper.yaml
├── paper-map.yaml
├── qa/
└── items/Q001/
    ├── source.yaml
    ├── review.yaml                     # 用户作出决定后才出现
    ├── teacher.resolved.assignment.yaml
    ├── student.resolved.assignment.yaml
    └── assets/
```

## paper-map.yaml 示例

```yaml
schema: math_exam_paper_map/v1
paper_id: PAPER-2026
items:
  - item_id: Q024
    question_number: 24
    question_pages:
      - documents/初三/PAPER-2026/005.png
    official_solution:
      pages:
        - documents/初三/PAPER-2026/007.png
        - documents/初三/PAPER-2026/008.png
      start_anchor: '24. 解：'
      end_anchor: '25. 解：'
  - item_id: Q025
    question_number: 25
    question_pages:
      - documents/初三/PAPER-2026/005.png
    official_solution:
      pages:
        - documents/初三/PAPER-2026/008.png
        - documents/初三/PAPER-2026/009.png
      start_anchor: '25. 解：'
      end_anchor: '<END_OF_SOURCE>'
```

规则：

- `items` 顺序必须与 `paper.yaml` 完全一致。
- `question_pages` 必须等于该题 `question_evidence` crop 的有序去重
  `source` 路径。
- `official_solution.pages` 必须等于该题 `official_solution` crop 的有序去重
  `source` 路径。
- `start_anchor` 抄录答案起点处的短文本；`end_anchor` 抄录下一题答案起点。
- 最后一题或来源到此结束时，`end_anchor` 使用 `<END_OF_SOURCE>`。
- anchor 只辅助人工确认裁切边界，不进入 `content_hash`。

## source.yaml 示例

```yaml
schema: math_exam_item_source/v1
item_id: Q024
source_key: PAPER-2026-Q24
paper_id: PAPER-2026
question_number: 24
question_type: problem
points: 12
section_title: 三、解答题
source_directory: documents/初三/PAPER-2026
crops:
  question_evidence:
    - source: documents/初三/PAPER-2026/005.png
      source_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
      box_px: [80, 395, 1005, 855]
      whiteout_px: []
      output: assets/source-question.png
      output_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
  prompt:
    - source: documents/初三/PAPER-2026/005.png
      source_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
      box_px: [680, 600, 950, 870]
      whiteout_px: []
      output: assets/prompt-01.png
      output_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
  solution:
    - source: documents/初三/PAPER-2026/008.png
      source_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
      box_px: [655, 315, 1000, 490]
      whiteout_px: [[0, 0, 35, 175]]
      output: assets/solution-01.png
      output_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
  official_solution:
    - source: documents/初三/PAPER-2026/007.png
      source_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
      box_px: [105, 1200, 1015, 1527]
      whiteout_px: []
      output: assets/official-solution-01.png
      output_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
    - source: documents/初三/PAPER-2026/008.png
      source_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
      box_px: [105, 100, 1015, 900]
      whiteout_px: []
      output: assets/official-solution-02.png
      output_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
transcription:
  question_status: author_pass
  official_solution_status: author_pass
  human_review: pending
  prompt_status: author_pass
  prompt_review_notes: []
content_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
```

首次作者编写时可用 64 个零作为待刷新哈希；`materialize_staging.py` 会用真实
SHA-256 覆盖它们。

## 用户审核凭证

Review UI 为每题生成 `review.yaml`，包含 `item_id`、`source_key`、当前
`content_hash`、`status`、审核时间和意见。它是唯一内容审核凭证：

- `status: approved` 且哈希与 `source.yaml` 一致时才算用户批准；
- 文字或图片变化会使旧决定过期；
- `audit_staging.py --require-approved-review` 检查全卷决定；
- 不再设置或检查独立复核状态。

## 教师版引用

解答图必须放在对应步骤中，不能只堆在答案末尾：

```yaml
solution_steps:
  - title: 第（1）问
    content: '$\because\ \cdots$，$\therefore\ \cdots$。'
    diagram_col:
      image_path: assets/solution-01.png
      width: 58mm
      variant: solution
      disclosure_policy: teacher_only
source_solution_images:
  - image_path: assets/official-solution-01.png
    width: 0.96\linewidth
    variant: source_solution
    disclosure_policy: teacher_only
    label: 官方原解答第 1 页
  - image_path: assets/official-solution-02.png
    width: 0.96\linewidth
    variant: source_solution
    disclosure_policy: teacher_only
    label: 官方原解答第 2 页
```

强排版题使用完整原题图片：

```yaml
stem_latex: '忠实转写的可检索题干……'
stem_image:
  image_path: assets/prompt-full-question.png
  width: 0.98\linewidth
  variant: prompt
  disclosure_policy: clean
```

普通题图可用题块级 `diagram_col`，但 `image_path` 必须来自 `crops.prompt`。
此处“题图”只指题目中的独立几何图、函数图像、表格、照片等视觉对象，不指整道题
的截图。完整题目截图属于 `question_evidence`；纯文字题不得创建 `prompt`。

DOC/DOCX 来源中，`crops.prompt` / `crops.solution` 应优先引用直接提取的
`word/media/*`，完整原图的 `box_px` 为 `[0, 0, width, height]`。公式媒体辅助
LaTeX 转写；完整来源凭证写入 `word_evidence.question` 和
`word_evidence.official_solution`，引用 `word-source.yaml` 的段落范围。

选择题的 `choices` 可使用有序列表或 `A/B/C/D` 映射，但每个值只能包含选项正文。
不得把 `0.`、`1.`、`2.`、`3.` 或 `A.`、`B.`、`C.`、`D.` 再写进值中；题库审核页
和试卷渲染器负责统一添加 `A/B/C/D` 标签。每道选择题必须恰有四个非空选项，
教师版 `answer` 必须是 `A/B/C/D` 之一；只有原题截图而没有结构化 `choices`
视为未完成录入。

## 题图人工补裁标记

题图做一次合理裁切后，如果只剩水印、少量邻近文字、边界不美观或最佳裁框不确定，
保留当前可审核图并记录：

```yaml
transcription:
  prompt_status: needs_human_crop
  prompt_review_notes:
    - '题图右下有公众号水印；人工补裁时保留点 A、B、C 标签。'
```

`needs_human_crop` 产生警告但不阻塞 staging；Review UI 必须醒目展示该标记。
整题截图充当 `prompt`、主体被截断或缺少解题必需图形仍是硬错误。

## 四类角色的自动约束

| crop 角色 | 数量 | 教师版引用 | 学生版引用 |
|---|---:|---|---|
| `question_evidence` | PDF/扫描件至少 1；Word 可为 0 | 不要求 | 禁止 |
| `prompt` | 0 或多张 | 每张恰好 1 次 | 每张恰好 1 次 |
| `solution` | 0 或多张 | 每张在 `solution_steps` 中恰好 1 次 | 禁止 |
| `official_solution` | PDF/扫描件至少 1；Word 可为 0 | 有图时按序引用 | 禁止 |

每题仍必须有完整来源证据：页图 crop 与对应 Word 段落范围二选一。两种来源都没有是
硬错误。

`audit_staging.py` 还会拒绝学生版中的 `answer`、`explanation`、
`solution_steps`、`solution_notes`、`source_solution_images`、`teaching`、
`teacher_only` 图片和任何 `diagram_slot`。
