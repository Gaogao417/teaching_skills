# Practice Block Reference

只在生成 `exam-zh-practice` YAML 时读取。

## choice

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
  entry_point: "find_entry"
  scaffold_level: "medium"
  variation_depth: "changed_numbers"
  complexity_note: "..."
  upgrade_rule: "..."
  fallback_move: "..."
```

## fillin

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

## problem

题干含 LaTeX 公式或 enumerate 时，必须用 `stem_latex`。

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

## Minimal Student YAML

```yaml
meta:
  title: "...专题练习"
  subtitle: "..."
  grade: "..."
  subject: "数学"
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

教师版与学生版结构一致，但 `meta.version: "teacher"`，题目中可加入答案、解析、`solution_steps` 和 `teaching`，并添加 `answer_key` section。
