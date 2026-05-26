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

- `artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md`
- `artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.assignment.yaml` 或 `02-student-explanation.html`
- 学生画像（可选）

## 输出

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.assignment.yaml
```

## 教学逻辑（与 HTML 版一致）

### 练习设计原则

1. **每组最多 3 题**
2. **难度只升一小步**
3. **保留核心结构**，不引入无关知识点
4. **提示渐进**：hint 1 指向动作，hint 2 接近答案
5. **答案经过自检**

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

## 几何图使用规则

- 每道练习题都先做插图判定：几何大题一律需要图；几何题已知条件数大于 3 默认需要图；题干出现“如图/图中/下图”强制需要图。
- 已知条件计数按原子几何条件统计：长度、角度、相等、平行、垂直、共线、比例、中点、圆/切线/坐标等；复合句拆开计数。
- 练习题默认每道题单独生成图：每个需要图的题必须有唯一 `diagram_job_id`，输出到 `diagram/jobs/<diagram_job_id>/rendered/prompt.png`。
- 不要默认复用已有 `diagram/rendered/prompt.png`；只有原题讲义图可以复用原题图。练习题若确实复用，必须显式写 `reuse_from`。
- 如果某道新题需要新合成几何图，使用 `math-geometry-diagram-renderer` 按题目级 job 生成 `prompt/clean` 图；教师解析如需辅助线，另生成 `solution/annotated` 图。
- PNG 存在且不泄露答案时，按题型写入结构化字段：选择题 `diagram_col`，填空题组 `diagram_row`，解答题 `answer_space.diagram_col` 或 `answer_space.parts[].diagram_col`。
- 如果图形失败、跳过、不支持或图片缺失，使用 fallback 文本或教师手动画图建议，不插入破图。

```yaml
diagram_col:
  image_path: "diagram/jobs/c1-prompt/rendered/prompt.png"
  diagram_job_id: "c1-prompt"
  width: "0.30\\linewidth"
  caption: "观察点 D 在边 BC 上的位置。"
  variant: "prompt"
  disclosure_policy: "clean"
```

## 题目字段要求

### 选择题 (choice)

```yaml
type: "choice"
id: "c1"
points: 4
stem: "题干文本 $math$"
diagram_col:                    # 几何选择题需要图时使用；模板会强制竖排选项并把图放右栏
  image_path: "diagram/jobs/c1-prompt/rendered/prompt.png"
  diagram_job_id: "c1-prompt"
  width: "0.30\\linewidth"
  caption: "参考图"
  variant: "prompt"
  disclosure_policy: "clean"
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

同一组填空题需要多张图时，先输出对应 fillin block，再在这些 fillin block 后插入一个 `diagram_row`，并排放所有图，图下标对应题号；不要把 `diagram_row` 放在题目前面，也不要给每道填空题单独塞独立 `diagram` block。

```yaml
type: "diagram_row"
id: "fillin-diagrams-1"
needspace: "18\\baselineskip"
items:
  - label: "第 1 题"
    image_path: "diagram/jobs/f1-prompt/rendered/prompt.png"
    diagram_job_id: "f1-prompt"
    width: "0.23\\linewidth"
    variant: "prompt"
    disclosure_policy: "clean"
  - label: "第 2 题"
    image_path: "diagram/jobs/f2-prompt/rendered/prompt.png"
    diagram_job_id: "f2-prompt"
    width: "0.23\\linewidth"
    variant: "prompt"
    disclosure_policy: "clean"
```

```yaml
type: "fillin"
id: "f1"
points: 4
stem: "题干文本"
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
  parts:                         # 多问几何大题推荐每问一个答题区 + 右侧图栏
    - label: "(1)"
      height: "28mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part1-prompt/rendered/prompt.png"
        diagram_job_id: "p1-part1-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
    - label: "(2)"
      height: "32mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part2-prompt/rendered/prompt.png"
        diagram_job_id: "p1-part2-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
```

## Layout 和分页规则

大题跨页截断问题必须在 YAML 中通过 layout 控制：

1. **选择题、填空题**：每组题不要超过一页（约 6 道选择或 6 道填空需分两组）
2. **解答题**：每道大题加 `layout: { avoid_break: true }`，防止题目和答题区被截断
3. **解答题超过 3 小问**：去掉 `avoid_break`，让内容自然分页
4. **答案区**：必须 `layout: { break_before: true }`
5. **两组练习之间**：前一组的最后一个 section 加 `layout: { break_after: true }` 或后一组加 `break_before: true`

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
    structure_analysis: "artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md"
    explanation: "artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.assignment.yaml"

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
        layout:
          avoid_break: true
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
    structure_analysis: "artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md"
    explanation: "artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.assignment.yaml"

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
        layout:
          avoid_break: true

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
2. 题目数量不超过 3 题（每组）
3. 学生版不含 `answer`、`explanation`、`solution_steps`、`teaching` 字段
4. 教师版每道解答题必须有 `solution_steps`（分步骤标准解答）
5. 解答题题干用 `stem_latex`（不经过转义），不用 `stem`
6. 若使用几何图，确认每道题有独立 `diagram_job_id` 和 `diagram/jobs/<job-id>/rendered/prompt.png`；多题复用必须写 `reuse_from`；填空题 `diagram_row` 在对应题目后面；prompt 图不含辅助线或答案泄露，solution 图只出现在教师解析/讲解中
7. 答案经过自检（代入验证）
8. block scalar（`|`）字段中的 LaTeX 命令用单反斜杠 `\frac`（不是 `\\frac`）；双引号字符串中的 `\\frac` 会被 YAML 解析为 `\frac` 所以是正确的
9. 复杂度不超过 structure-analysis 预算
10. 答案区 answer_key 的 `visibility` 为 `"teacher"`
11. 大题有 `layout: { avoid_break: true }`（除非超过 3 小问）
12. 同时输出 student 和 teacher 两个文件

## Handoff

生成完毕后说明：

```
已生成学生版和教师版两个 YAML 文件：
- artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.student.assignment.yaml
- artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.teacher.assignment.yaml

下一步：使用 math-assignment-latex 渲染、检查并编译 PDF。

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.student.assignment.yaml \
  --out artifacts/<学生名>/YYYY-MM-DD-<内容>/03-practice-student.tex

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.teacher.assignment.yaml \
  --out artifacts/<学生名>/YYYY-MM-DD-<内容>/03-practice-teacher.tex

python math-assignment-latex/scripts/check_latex.py artifacts/<学生名>/YYYY-MM-DD-<内容>/03-practice-student.tex
python math-assignment-latex/scripts/check_latex.py artifacts/<学生名>/YYYY-MM-DD-<内容>/03-practice-teacher.tex

bash math-assignment-latex/scripts/compile_latex.sh artifacts/<学生名>/YYYY-MM-DD-<内容>/03-practice-student.tex
bash math-assignment-latex/scripts/compile_latex.sh artifacts/<学生名>/YYYY-MM-DD-<内容>/03-practice-teacher.tex
```
