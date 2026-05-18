# LaTeX 迁移审计：HTML 体系 → 教学 DSL

## 1. 审计范围

- `artifacts/assets/edu-print.css` — 671 行，定义全部 edu-* 语义样式
- `.codex/skills/math-structure-analysis/SKILL.md` — Stage 1，Markdown 输出
- `.codex/skills/math-student-explanation-html/SKILL.md` — Stage 2，HTML 输出
- `.codex/skills/math-adaptive-practice-html/SKILL.md` — Stage 3，HTML 输出
- `.codex/skills/math-student-response-diagnosis/SKILL.md` — Optional，Markdown 输出

## 2. edu-* 组件审计表

| edu class | 教学语义 | YAML 字段 | LaTeX 映射 | 适用 skill | 学生可见 | 教师可见 | 分页规则 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `edu-page` | A4 页面容器 | (render 层) | `\begin{document}` | explanation/practice | 是 | 是 | 页面级 |
| `edu-title` | 作业标题 | `meta.title` | `\title{...}` | explanation/practice | 是 | 是 | 无 |
| `edu-subtitle` | 副标题/标签 | `meta.subtitle` | `\maketitle` 下方 | explanation/practice | 是 | 是 | 无 |
| `edu-problem-card` | 原题卡片 | `original_problem` | `problemcard` 环境 | explanation | 是 | 是 | avoid-break |
| `edu-problem-title` | 原题标题 | (标题文本) | `\textbf{...}` | explanation | 是 | 是 | 无 |
| `edu-problem-stem` | 原题题干 | `stem` | 题干文本 | explanation | 是 | 是 | 无 |
| `edu-section` | 大节容器 | `sections[].title` | `\section{...}` | explanation/practice | 是 | 是 | 无 |
| `edu-section-title` | 大节标题 | `sections[].title` | `\section{...}` | explanation/practice | 是 | 是 | break-after:avoid |
| `edu-subsection-title` | 小节标题 | `blocks[].title` | `\subsection{...}` | explanation | 是 | 是 | 无 |
| `edu-task-table` | 题目拆解表 | `task_table` | `tabular` 环境 | explanation | 是 | 是 | avoid-break |
| `edu-object-table` | 目标表 | `object_table` | `tabular` 环境 | explanation | 是 | 是 | avoid-break |
| `edu-route` | 解题路线图 | `route` | `routemap` 环境 | explanation | 是 | 是 | avoid-break |
| `edu-key-idea` | 关键想法 | `key_idea` | `keyideabox` 环境 | explanation | 是 | 是 | avoid-break |
| `edu-step` | 步骤 | `solution_steps[]` | `step` 环境 | explanation/practice | 是 | 是 | 无 |
| `edu-step-title` | 步骤标题 | `steps[].title` | `\textbf{...}` | explanation/practice | 是 | 是 | break-after:avoid |
| `edu-step-why` | 步骤原因 | `steps[].why` | `\\small ...` | explanation | 是 | 是 | 无 |
| `edu-substep` | 子步骤 | `steps[].substeps[]` | 嵌套列表 | explanation | 是 | 是 | 无 |
| `edu-question` | 思考题 | `check_questions[]` | `thinkbox` 环境 | explanation | 是 | 是 | avoid-break |
| `edu-question-title` | 思考题标题 | `questions[].title` | `\textbf{...}` | explanation | 是 | 是 | 无 |
| `edu-mistake` | 易错提醒 | `mistakes[]` | `mistakebox` 环境 | explanation/practice | 是 | 是 | avoid-break |
| `edu-hint` | 提示 | `hints[]` | `hintbox` 环境 | practice | 是 | 是 | 无 |
| `edu-hint-title` | 提示标题 | (固定文本) | `\textbf{提示}` | practice | 是 | 是 | break-after:avoid |
| `edu-answer-space` | 答题区(空白) | `answer_space` (type:blank) | `\vspace{...}` | practice | 是 | 是 | 无 |
| `edu-answer-lines` | 答题区(横线) | `answer_space` (type:lines) | `\answerarea` | practice | 是 | 是 | 无 |
| `edu-answer-steps` | 分步答题区 | `answer_space` (type:steps) | `answerstep` 环境 | practice | 是 | 是 | 无 |
| `edu-answer-key` | 答案页 | `answer_key` | `\clearpage` + solution | practice | 否(分页后) | 是 | break-before:always |
| `edu-teacher-note` | 教师备注 | `teacher_notes` | teacher 版渲染 | explanation/practice | 否 | 是 | no-print |
| `edu-student-note` | 学生备注 | `student_notes` | 普通框 | explanation | 是 | 是 | 无 |
| `edu-training-goal` | 训练目标 | `teaching.teaching_goal` | teacher 版渲染 | practice | 否 | 是 | no-print |
| `edu-expected-blocker` | 预期卡点 | `teaching.expected_blocker` | teacher 版渲染 | practice | 否 | 是 | no-print |
| `edu-judge` | 升降级判断 | `teaching.upgrade_rule` / `downgrade_rule` | teacher 版渲染 | practice | 否 | 是 | no-print |
| `edu-upgrade` | 升级标记 | upgrade_rule | `\textbf{↑}` | practice | 否 | 是 | no-print |
| `edu-downgrade` | 降级标记 | downgrade_rule | `\textbf{↓}` | practice | 否 | 是 | no-print |
| `edu-review` | 巩固标记 | review_rule | `\textbf{→}` | practice | 否 | 是 | no-print |
| `edu-practice-problem` | 练习题卡片 | `blocks[]` (practice) | `question`/`problem` 环境 | practice | 是 | 是 | avoid-break |
| `edu-practice-title` | 练习题标题 | `blocks[].title` | 题号+标题 | practice | 是 | 是 | break-after:avoid |
| `edu-tag` | 标签 | `teaching.mastery_band` | 小标签 | practice | 否 | 是 | no-print |
| `edu-formula` | 公式 | 行内数学 | `\[ ... \]` | explanation | 是 | 是 | avoid-break |
| `edu-formula-key` | 关键公式 | `key_formulas[]` | `\boxed{...}` | explanation | 是 | 是 | avoid-break |
| `edu-subproblem` | 子问题 | `subproblems[]` | subproblem 环境 | explanation | 是 | 是 | 无 |
| `edu-subproblem-title` | 子问题标题 | `subproblems[].title` | `\textbf{...}` | explanation | 是 | 是 | 无 |
| `edu-blank-line` | 填空线 | `answer_space` 内 | `\fillin[]` | explanation/practice | 是 | 是 | 无 |
| `page-break` | 分页 | `layout.break_before` | `\clearpage` | explanation/practice | 是 | 是 | break-before:always |
| `u-avoid-break` | 不分页 | `layout.avoid_break` | `\needspace` | explanation/practice | 是 | 是 | avoid-break |

## 3. 各 Skill 需要的 DSL 字段

### math-student-explanation 需要

```yaml
meta:
  title, subtitle, grade, subject, version, show_answers
render:
  template, paper_size
original_problem:       # 原题卡片
  stem, conditions, question_text
task_table:             # 题目拆解表
  known, target, keywords, ignore
route:                  # 解题路线
  steps[]
key_idea:               # 关键想法
  title, content
solution_steps:         # 标准解法
  - title, content, why, formula, substeps[]
check_questions:        # 边讲边问
  - title, question, answer
mistakes:               # 易错提醒
  - title, content
key_formulas:           # 核心公式
  - formula, description
summary:                # 一句话总结
  content
teacher_notes:          # 教师备注
  - content
student_notes:          # 学生备注
  - content
answer_spaces:          # 答题区
  - type, height
```

### math-adaptive-practice 需要

```yaml
meta:
  title, subtitle, grade, subject, version, show_answers,
  source_artifacts.structure_analysis, source_artifacts.explanation
render:
  template, paper_size, answer_key_position
sections:
  - id, title, type, visibility, layout
    blocks:
      - id, question_type, points, title, stem
        choices          # choice 类型
        answer
        explanation
        solution_steps[]
        hints[]
        answer_space:
          type, height
        teaching:
          teaching_goal, expected_blocker, mastery_band,
          upgrade_rule, downgrade_rule, complexity_note
```

### math-student-response-diagnosis 教师版字段

```yaml
diagnosis:
  mastery_band:         # A-F
  confidence:           # 0-1
  main_blocker:         # 主要卡点
  secondary_blockers[]  # 次要卡点
  mastered_actions[]    # 已掌握
  unmastered_actions[]  # 未掌握
  allowed_abstraction   # 允许抽象层级
  next_move:            # 下一步教学建议
  practice_instruction  # 练习生成指令
```

## 4. 旧 edu-* → LaTeX 映射总结

### 直接映射（exam-zh 内置）

| HTML 模式 | exam-zh LaTeX |
| --- | --- |
| 选择题 | `\begin{question}[points=N]` + `\begin{choices}` |
| 填空题 | `\begin{question}[points=N]` + `\fillin[答案]` |
| 解答题 | `\begin{problem}[points=N]` + `\begin{solution}` |
| 答案页 | `\clearpage` + `question/show-answer=true` |

### 需自定义环境（preamble 中定义）

| edu 语义 | 自定义 LaTeX 环境 |
| --- | --- |
| 原题卡片 | `\begin{problemcard}` |
| 解题路线 | `\begin{routemap}` |
| 关键想法 | `\begin{keyideabox}` |
| 易错提醒 | `\begin{mistakebox}` |
| 提示 | `\begin{hintbox}` |
| 思考题 | `\begin{thinkbox}` |
| 分步答题 | `\begin{answerstep}` |
| 教师备注 | `\begin{teachernote}` (teacher 版) |
| 训练目标 | `\begin{traininggoal}` (teacher 版) |

### 版本控制规则

```text
version=student:
  不渲染 solution, teachernote, traininggoal, hintbox(仅教师)
  \paren 和 \fillin 不显示答案

version=teacher:
  渲染全部内容
  \paren[答案], \fillin[答案] 显示答案
  solution 完整输出

version=both:
  先输出 student 版内容
  \clearpage 后输出 teacher 附加内容
```

## 5. 验收清单

- [x] math-student-explanation DSL 字段已列出
- [x] math-adaptive-practice DSL 字段已列出
- [x] math-student-response-diagnosis 教师版字段已列出
- [x] 旧 edu-* 组件 → LaTeX 映射已完成
- [x] 可见性规则已标注（学生/教师/no-print）
- [x] 分页规则已标注（avoid-break / page-break）
