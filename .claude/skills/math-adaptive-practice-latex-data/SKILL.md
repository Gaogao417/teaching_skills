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

## 输入

- `artifacts/<slug>/01-structure-analysis.md`
- `artifacts/<slug>/02-student-explanation.assignment.yaml` 或 `02-student-explanation.html`
- 学生画像（可选）

## 输出

```text
artifacts/<slug>/03-adaptive-practice.assignment.yaml
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

## YAML 输出格式

```yaml
meta:
  title: "...专题练习"
  subtitle: "..."
  grade: "..."
  subject: "..."
  duration: "20分钟"
  total_points: 24
  version: "student"
  show_answers: false
  source_artifacts:
    structure_analysis: "artifacts/<slug>/01-structure-analysis.md"
    explanation: "artifacts/<slug>/02-student-explanation.assignment.yaml"

render:
  template: "exam-zh-practice"
  paper_size: "a4paper"
  answer_key_position: "after_page_break"

sections:
  - id: "practice-main"
    title: "一、核心练习"
    type: "practice"
    visibility: "student"
    blocks:
      - type: "choice"
        id: "q1"
        ...
      - type: "fillin"
        id: "q2"
        ...
      - type: "problem"
        id: "q3"
        ...

  - id: "answer-key"
    title: "二、参考答案"
    type: "answer_key"
    visibility: "student"
    layout:
      break_before: true
    blocks:
      - type: "step"
        id: "ak1"
        title: "第 1 题"
        content: "解答..."
```

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md` 定义的 schema。

## 自检

输出前必须检查：
1. 所有 block id 唯一
2. 题目数量不超过 3 题
3. 每题都有 teaching 字段
4. 答案经过自检（代入验证）
5. 复杂度不超过 structure-analysis 预算
6. 数学公式使用 `$...$` 格式

## Handoff

生成完毕后说明：

```
下一步：使用 math-assignment-latex 渲染并编译 PDF。

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<slug>/03-adaptive-practice.assignment.yaml \
  --out artifacts/<slug>/04-assignment.tex
```
