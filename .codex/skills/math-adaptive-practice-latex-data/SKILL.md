---
name: math-adaptive-practice-latex-data
description: "根据 01-structure-analysis.md 和讲解 YAML 生成自适应练习 assignment.yaml。Use when: 已有结构分析和 02-student-explanation 的 assignment/resolved YAML，用户要求练习、practice YAML、学生版/教师版练习或端到端作业补齐练习阶段。Skip when: 没有结构分析、没有讲解内容、用户只要求讲解或只要求渲染 PDF。需要几何图时只声明 diagram_slot，不写 image_path/diagram_col；真实出图交给 math-geometry-diagram-renderer。"
version: 0.2.0
---

# math-adaptive-practice-latex-data

## 职责

从结构分析和讲解内容生成练习 YAML。这个 skill 只负责练习内容、学生/教师版本分离、练习题上的 `diagram_slot` 声明；不运行 renderer，不编译 PDF，所有调节判断都只服务本轮练习。

默认同时输出：

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.student.plan.assignment.yaml
artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.teacher.plan.assignment.yaml
```

若完全没有 `diagram_slot`，可直接输出：

```text
03-adaptive-practice.student.assignment.yaml
03-adaptive-practice.teacher.assignment.yaml
```

## 输入

- `01-structure-analysis.md`
- `02-student-explanation.assignment.yaml` 或 `02-student-explanation.resolved.assignment.yaml`
- 学生画像或学生回答诊断（可选，只作为本轮练习调节证据）

## 练习调节参数

根据结构分析、学生画像和可见证据，为本轮练习选择以下任务参数：

```yaml
teaching:
  teaching_goal: "本题训练的核心动作"
  expected_blocker: "本轮最可能卡住的位置"
  entry_point: "read_context | find_key_quantity | build_relation | solve_and_check | transfer"
  scaffold_level: "high | medium | low"
  variation_depth: "same_structure | changed_numbers | changed_question | changed_representation | packaged_condition | partially_hidden"
  complexity_note: "与 structure-analysis 的 complexity_budget 对齐"
  upgrade_rule: "学生可升级的可观察条件"
  fallback_move: "学生卡住时回退到哪个动作"
```

规则：

- 学生版不得包含 `answer`、`explanation`、`solution_steps`、`teaching`。
- 教师版可以包含 `teaching`，但字段必须描述本轮任务选择，不描述学生等级。
- 每组最多 3 题；只小步改变一个主维度。
- 保留核心结构，不引入无关知识点。
- 提示渐进：先提示动作，再接近答案。
- 所有答案必须先独立验算。

## 复杂度预算

遵守 `structure-analysis` 中的 `complexity_budget`：

- `max_next_step` 不超过预算。
- 不引入 `forbidden_load`。
- 算术保持干净：小整数、简单分数、可手算验证。
- 不同时隐藏结构和提高计算难度，除非学生证据明确支持低支架迁移。

## 几何图使用规则

- 本 skill 负责判断当前练习题是否需要在题目位置声明 `diagram_slot`；图的生成、gate、fallback 由 `math-geometry-diagram-renderer` 决定。
- 若题干出现“如图/图中/下图”，必须声明 `diagram_slot`。
- 几何大题或条件较多、仅靠文字会显著增加读题负担的几何题，应声明 `diagram_slot`。
- 每个需要图的练习题默认使用唯一 `diagram_slot.slot_id`。若复用构型，必须显式写 `reuse_geometry_from`，并保证题干条件完全一致。
- 学生版只声明 `prompt` / `clean` slot；教师版解析若需要辅助线，另声明 `solution` / `annotated` slot，并复用对应 prompt slot。
- plan YAML 不得写最终图片字段：不写 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row` 或 `answer_space.diagram_col`。
- 当前 collector/resolver 只扫描 block 级 `diagram_slot`、`answer_space.diagram_slot`、`answer_space.parts[].diagram_slot`。不要在 plan 阶段手写 `diagram_row.items[]`。

最小 slot 示例：

```yaml
diagram_slot:
  slot_id: "c1.prompt"
  diagram_ref: "c1.prompt"
  variant: "prompt"
  disclosure_policy: "clean"
  required: true
  on_failure: "fail_assignment"
  placement: "diagram_col"
  layout_role: "question_sidecar"
  width_hint: "0.30\\linewidth"
  caption: "观察点 D 在边 BC 上的位置。"
  engine: "geometric_scene"
  diagram_kind: "synthetic_geometry"
  teaching_intent: "practice_prompt"
  semantic_constraints:
    given_objects: ["A", "B", "C", "D"]
    given_constraints: ["D on BC", "AB=AC"]
```

## 题目字段要求

### choice

```yaml
type: "choice"
id: "c1"
points: 4
stem: "题干文本 $math$"
choices:
  A: "选项 A"
  B: "选项 B"
  C: "选项 C"
  D: "选项 D"
hints:
  - content: "先找题目中真正不变的量。"
answer: "B"              # 仅教师版
explanation: "解析文本"   # 仅教师版
teaching:                 # 仅教师版
  teaching_goal: "..."
  expected_blocker: "..."
  entry_point: "find_key_quantity"
  scaffold_level: "medium"
  variation_depth: "changed_numbers"
  complexity_note: "..."
  upgrade_rule: "..."
  fallback_move: "..."
```

### fillin

```yaml
type: "fillin"
id: "f1"
points: 4
stem: "题干文本"
hints:
  - content: "先把已知条件转成等量关系。"
answer: "填空答案"        # 仅教师版
explanation: "解析文本"   # 仅教师版
```

### problem

题干含 LaTeX 公式或 enumerate 时，必须用 `stem_latex`，不要用 `stem`。

```yaml
type: "problem"
id: "p1"
points: 10
label: "第 1 题"
stem_latex: |
  已知一次函数 $y = kx + b$ 的图像经过点 $A(2, 7)$ 和点 $B(-1, 1)$。
  \begin{enumerate}[label=(\arabic*)]
    \item 求这个一次函数的解析式；
    \item 判断点 $C(3, 9)$ 是否在该函数的图像上。
  \end{enumerate}
hints:
  - content: "先列方程组求 $k$ 和 $b$，再把 $C$ 的横坐标代入。"
answer_space:
  type: "steps"
  height: "60mm"
  step_count: 4
layout:
  avoid_break: true
answer: "(1) $y = 2x + 3$；(2) 在图像上。"  # 仅教师版
solution_steps:                                  # 仅教师版
  - title: "代入列方程组"
    content: "代入 $(2,7)$ 得 $2k + b = 7$，代入 $(-1,1)$ 得 $-k + b = 1$。"
  - title: "消元求解"
    content: "两式相减：$3k = 6$，$k = 2$。回代：$b = 3$。"
```

## YAML 输出格式

学生版：

```yaml
meta:
  title: "...专题练习"
  subtitle: "..."
  grade: "..."
  subject: "..."
  duration: "20分钟"
  total_points: 24
  version: "student"
  source_artifacts:
    structure_analysis: "artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md"
    explanation: "artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.resolved.assignment.yaml"

render:
  template: "exam-zh-practice"
  paper_size: "a4paper"
  answer_key_position: "after_page_break"

sections:
  - id: "choice"
    title: "一、选择题"
    type: "practice"
    visibility: "student"
    blocks: []
```

教师版与学生版结构一致，但 `meta.version: "teacher"`，题目中可加入答案、解析、`solution_steps` 和 `teaching`，并添加 `answer_key` section：

```yaml
sections:
  - id: "answer-key"
    title: "参考答案"
    type: "answer_key"
    visibility: "teacher"
    layout:
      break_before: true
    blocks:
      - type: "step"
        id: "ak-choice"
        title: "选择题"
        content: "1. B  2. A  3. C"
```

## Layout 和分页规则

1. 选择题、填空题每组控制在一页内。
2. 解答题默认加 `layout: { avoid_break: true }`；超过 3 小问时允许自然分页。
3. 答案区必须 `layout: { break_before: true }`。
4. 两组练习之间可用 `break_after` 或 `break_before` 控制分页。

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md`。

## 自检

输出前必须检查：

1. 所有 block id 唯一。
2. 每组题量不超过 3 题。
3. 学生版不含 `answer`、`explanation`、`solution_steps`、`teaching`。
4. 教师版解答题有分步骤 `solution_steps`。
5. 不出现长期标签或档位字段。
6. 解答题题干用 `stem_latex`，LaTeX block scalar 中用单反斜杠。
7. 若使用几何图，plan YAML 只写 `diagram_slot`，不写最终图片字段。
8. 答案经过代入或逻辑验算。
9. 复杂度不超过 structure-analysis 预算。
10. 同时输出 student 和 teacher 两个文件，除非用户明确只要一个版本。

## Handoff

生成完毕后说明：

```text
已生成学生版和教师版两个 YAML 文件。

若任一 YAML 中存在 diagram_slot：
下一步：使用 math-geometry-diagram-renderer 走真实 collect/batch/gate/resolve 链路，生成 resolved YAML。

得到 resolved YAML 后，或确认普通 assignment YAML 中不存在 diagram_slot 后：
下一步：使用 math-assignment-latex 渲染、检查并编译 PDF。
```
