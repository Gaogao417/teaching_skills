---
name: math-adaptive-practice-latex-data
description: "根据结构分析和讲解内容生成自适应练习的 assignment.yaml，保留原 math-adaptive-practice-html 的教学逻辑。"
version: 0.1.0
triggers:
  - description: "已有 structure-analysis 和 explanation，需要生成练习 YAML"
  - description: "用户要求生成 practice assignment.yaml"
  - description: "用户提到 practice-latex-data 或练习 YAML"
skip:
  - description: "没有 01-structure-analysis.md（先运行 math-structure-analysis）"
  - description: "没有讲解内容（先运行 math-student-explanation-latex-data 或 html）"
  - description: "用户要求 HTML 输出（使用 math-adaptive-practice-html）"
  - description: "用户要求讲解而非练习"
---

# math-adaptive-practice-latex-data

## 职责

从 `01-structure-analysis.md` 和讲解内容生成 `03-adaptive-practice.assignment.yaml`。

保留原 `math-adaptive-practice-html` 的全部教学逻辑。

## 版本规则

每次生成练习必须**同时输出学生版和教师版**，通过 `meta.version` 控制：

- **学生版**（`version: "student"`）：纯净试卷，只有题干、选项、答题区。不含答案、解析、教师备注。
  但可以在题目后附带渐进提示（hints），提示以轻量框显示。
- **教师版**（`version: "teacher"`）：在学生版基础上，每道题后附带完整的解题步骤和答案。
  解答题（problem）必须包含分步骤的标准解答（solution_steps）。
- **同时输出**：默认生成两个文件：
  - `03-adaptive-practice.student.assignment.yaml`（`version: "student"`）
  - `03-adaptive-practice.teacher.assignment.yaml`（`version: "teacher"`）
  如果用户明确只要一个版本，则只生成一个。

## 输入

### 必需

- `artifacts/<学生名>/<YYYY-MM-DD-<subject>>/01-structure-analysis.md`
- `artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/02-student-explanation.assignment.yaml` 或 `02-student-explanation.html`

### 用户必须提供（缺一不可，否则先询问再出题）

1. **学生程度**：如"差生"、"中等偏弱"、"中等"、"好"
2. **每道小题用时**：如"2分钟"、"1分钟"、"30秒"
3. **每道大题用时**：如"5分钟"、"3分钟"

agent 不得自行假设用时，必须向用户确认后再出题。

## 输出

```text
artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/03-adaptive-practice.student.assignment.yaml
artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/03-adaptive-practice.teacher.assignment.yaml
```

中间产物（YAML）统一放入 `build/` 子目录。

## 教学逻辑（与 HTML 版一致）

### 时间预算

- **常规部分总量控制在 20 分钟 ± 2 分钟**
- **提高题单独一组，不计入 20 分钟**
- agent 根据用户提供的小题/大题用时计算题目数量

计算公式：

```
n_small × 小题用时 + n_large × 大题用时 ≈ 20
```

分配建议（agent 可灵活调整）：
- `n_small` = 选择题 + 填空题总数，建议 4~8 道
- `n_large` = 解答题，建议 2~3 道
- 若计算结果为非整数，向下取整并微调

**示例**：小题 2min、大题 5min → 4 小题 + 2 大题 = 4×2+2×5 = 18min ≈ 20min
**示例**：小题 1min、大题 3min → 5 小题 + 3 大题 = 5×1+3×3 = 14min → 调为 6 小题 + 3 大题 = 15min 或 5 小题 + 4 大题 = 17min

### 题目梯度

不管出多少题，梯度从易到难：
- 前 30%：L2 巩固（同结构换数）
- 中 40%：L3 换问法 / 换条件
- 后 30%：L4 易错陷阱 / 条件包装
- 提高题：L5 远迁移

### 提高题

- 独立成一组 section，标注"★ 提高题"
- **不计入 20 分钟总时间**
- 来源（两者结合）：
  1. 优先从 `01-structure-analysis.md` 的 `far_transfer_examples` 或 `l5_l6_deepening_variations` 选取
  2. 若无现成远迁移，基于 `variation_rules` 独立设计一道 L5 层级题
- 提高题的复杂度可以超出常规部分的 `complexity_budget`

### 通用规则

1. **难度只升一小步**
2. **保留核心结构**，不引入无关知识点
3. **提示渐进**：hint 1 指向动作，hint 2 接近答案
4. **答案经过自检**

### 档位规则

```text
A 独立完成，步骤清晰 → 升级到换问法/高阶变式
B 需提示但能完成 → 巩固当前结构
C 做对但有瑕疵 → 给同类题再练
D 有思路但卡住 → 给提示更多支架
E 完全不会 → 回退到前置知识点
F 连前置知识都不具备 → 需要重新讲解
```

### 每道题必须包含

```yaml
id: "q1"
question_type: "choice"  # choice/fillin/problem/short_answer
points: 4
stem: "题干文本"
answer: "答案"
explanation: "解析"
solution_steps: [...]
teaching:
  teaching_goal: "训练目标"
  expected_blocker: "预期卡点"
  mastery_band: "B"
  upgrade_rule: "升级条件"
  downgrade_rule: "降级条件"
  complexity_note: "复杂度说明"
hints:
  - content: "提示 1"
  - content: "提示 2"
answer_space:
  type: "lines"
  height: "25mm"
```

### 复杂度预算

遵守 structure-analysis 中的 `complexity_budget`：
- 不使用丑陋的算术（除非结构需要）
- max_next_step 不超过预算
- 不引入 forbidden_load

## 题目字段要求

### 选择题 (choice)

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
answer: "B"
explanation: "解析文本"          # 教师版显示
teaching:                        # 教师版显示
  teaching_goal: "..."
  expected_blocker: "..."
  mastery_band: "B"
  complexity_note: "..."
```

### 填空题 (fillin)

空白处用 `\fillin`，放在 stem 文本中空白应该在的位置（句号/单位之前）。不要用 `\_\_\_` 或其他手动横线。

```yaml
type: "fillin"
id: "f1"
points: 4
stem: "则 $\odot O$ 的半径为\fillin。"
answer: "填空答案"
explanation: "解析文本"          # 教师版显示
teaching:
  teaching_goal: "..."
  mastery_band: "A"
```

### 解答题 (problem)

**重要**：题干含 LaTeX 公式或 enumerate 时，必须用 `stem_latex`（原样输出），不要用 `stem`。

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
answer: "(1) $y = 2x + 3$；(2) 在图像上。"
explanation: |
  (1) 代入 $A(2,7)$：$2k + b = 7$。代入 $B(-1,1)$：$-k + b = 1$。
  两式相减：$3k = 6$，$k = 2$，$b = 3$。
solution_steps:                  # 教师版分步骤展示
  - title: "代入列方程组"
    content: "代入 $(2,7)$ 得 $2k + b = 7$，代入 $(-1,1)$ 得 $-k + b = 1$。"
  - title: "消元求解"
    content: "两式相减：$3k = 6$，$k = 2$。回代：$b = 3$。"
  - title: "检验点 C"
    content: "将 $x = 3$ 代入 $y = 2x + 3 = 9$，等于 $C$ 的纵坐标。"
teaching:
  teaching_goal: "..."
  expected_blocker: "..."
  mastery_band: "B"
hints:                           # 学生版也可以看到
  - content: "先列方程组求 $k$ 和 $b$，再把 $C$ 的横坐标代入。"
  - content: "两式相减可以快速消去 $b$。"
answer_space:
  type: "steps"
  height: "60mm"
  step_count: 4
```

## Layout 和分页规则

YAML 中不设置任何分页规则。题干+答题区不可跨页截断由模板自动处理（problem/short_answer 类型 block 自动加 `\needspace`）。

## YAML 输出格式

### 学生版 (03-adaptive-practice.student.assignment.yaml)

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
    structure_analysis: "artifacts/<学生名>/<YYYY-MM-DD-<subject>>/01-structure-analysis.md"
    explanation: "artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/02-student-explanation.assignment.yaml"

render:
  template: "exam-zh-practice"
  paper_size: "a4paper"
  answer_key_position: "after_page_break"

sections:
  - id: "choice"
    title: "一、选择题（每题 4 分，共 24 分）"
    type: "practice"
    visibility: "student"
    blocks:
      - type: "choice"
        id: "c1"
        points: 4
        stem: "..."
        choices: { A: "...", B: "...", C: "...", D: "..." }
        hints:
          - content: "提示..."

      - type: "choice"
        id: "c2"
        # ...

  - id: "fillin"
    title: "二、填空题（每题 4 分，共 16 分）"
    type: "practice"
    visibility: "student"
    blocks:
      - type: "fillin"
        id: "f1"
        points: 4
        stem: "..."
        hints:
          - content: "提示..."

  - id: "problems"
    title: "三、解答题（每题 10 分，共 20 分）"
    type: "practice"
    visibility: "student"
    blocks:
      - type: "problem"
        id: "p1"
        points: 10
        label: "第 1 题"
        stem_latex: |
          ...
        hints:
          - content: "提示 1"
          - content: "提示 2"
        answer_space:
          type: "steps"
          height: "60mm"
          step_count: 4

  # 学生版不含答案区和教师备注
```

### 教师版 (03-adaptive-practice.teacher.assignment.yaml)

与学生版结构相同，区别在 `meta.version` 和每个 block 的 `answer`/`explanation`/`solution_steps`/`teaching` 字段。

```yaml
meta:
  title: "...专题练习（教师版）"
  subtitle: "..."
  grade: "..."
  subject: "..."
  duration: "20分钟"
  total_points: 24
  version: "teacher"
  source_artifacts:
    structure_analysis: "artifacts/<学生名>/<YYYY-MM-DD-<subject>>/01-structure-analysis.md"
    explanation: "artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/02-student-explanation.assignment.yaml"

render:
  template: "exam-zh-practice"
  paper_size: "a4paper"
  answer_key_position: "after_page_break"

sections:
  - id: "choice"
    title: "一、选择题（每题 4 分，共 24 分）"
    type: "practice"
    visibility: "both"
    blocks:
      - type: "choice"
        id: "c1"
        points: 4
        stem: "..."
        choices: { A: "...", B: "...", C: "...", D: "..." }
        answer: "B"
        explanation: "解析..."
        teaching:
          teaching_goal: "..."
          expected_blocker: "..."
          mastery_band: "B"

  - id: "problems"
    title: "三、解答题"
    type: "practice"
    visibility: "both"
    blocks:
      - type: "problem"
        id: "p1"
        points: 10
        stem_latex: |
          ...
        answer: "..."
        explanation: |
          完整解析文本...
        solution_steps:
          - title: "步骤 1"
            content: "..."
          - title: "步骤 2"
            content: "..."
        teaching:
          teaching_goal: "..."
          expected_blocker: "..."
          mastery_band: "B"

  - id: "answer-key"
    title: "参考答案"
    type: "answer_key"
    visibility: "teacher"
    blocks:
      - type: "step"
        id: "ak-choice"
        title: "选择题"
        content: |
          1. B  2. A  3. C  ...
      - type: "step"
        id: "ak-fillin"
        title: "填空题"
        content: |
          1. $3$  2. $(2,0)$  ...
      - type: "step"
        id: "ak-problem"
        title: "解答题"
        content: |
          第 1 题：(1) $y = 2x + 3$；(2) 在图像上。
          第 2 题：...
```

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md` 定义的 schema。

## 自检

输出前必须检查：
1. 所有 block id 唯一
2. 用户已提供学生程度、小题用时、大题用时三项信息
3. 常规部分题目总量 ≈ 20 分钟（± 2 分钟），提高题单独不计入
4. 学生版不含 `answer`、`explanation`、`solution_steps`、`teaching` 字段
5. 教师版每道解答题必须有 `solution_steps`（分步骤标准解答）
6. 解答题题干用 `stem_latex`（不经过转义），不用 `stem`
7. 答案经过自检（代入验证）
8. block scalar（`|`）字段中的 LaTeX 命令用单反斜杠 `\frac`（不是 `\\frac`）；双引号字符串中的 `\\frac` 会被 YAML 解析为 `\frac` 所以是正确的
9. 常规部分复杂度不超过 structure-analysis 预算（提高题可超出）
10. 答案区 answer_key 的 `visibility` 为 `"teacher"`
11. 同时输出 student 和 teacher 两个文件
12. 填空题空白用 `\fillin`（放在 stem 中正确位置），不用 `\_\_\_`
13. 提高题独立 section

## Handoff

生成完毕后说明：

```
已生成学生版和教师版两个 YAML 文件：
- artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/03-adaptive-practice.student.assignment.yaml
- artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/03-adaptive-practice.teacher.assignment.yaml

下一步：使用 math-assignment-latex 渲染、检查并编译 PDF。

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/03-adaptive-practice.student.assignment.yaml \
  --out artifacts/<学生名>/<YYYY-MM-DD-<subject>>/03-practice-student.tex

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<学生名>/<YYYY-MM-DD-<subject>>/build/03-adaptive-practice.teacher.assignment.yaml \
  --out artifacts/<学生名>/<YYYY-MM-DD-<subject>>/03-practice-teacher.tex

python math-assignment-latex/scripts/check_latex.py artifacts/<学生名>/<YYYY-MM-DD-<subject>>/03-practice-student.tex
python math-assignment-latex/scripts/check_latex.py artifacts/<学生名>/<YYYY-MM-DD-<subject>>/03-practice-teacher.tex

bash math-assignment-latex/scripts/compile_latex.sh artifacts/<学生名>/<YYYY-MM-DD-<subject>>/03-practice-student.tex
bash math-assignment-latex/scripts/compile_latex.sh artifacts/<学生名>/<YYYY-MM-DD-<subject>>/03-practice-teacher.tex
```
