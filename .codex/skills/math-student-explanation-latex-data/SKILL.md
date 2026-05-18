---
name: math-student-explanation-latex-data
description: "根据结构分析生成课堂讲解页 assignment.yaml，输出匹配 math-assignment-latex 的 exam-zh-explanation 讲义式 YAML。"
version: 0.1.0
triggers:
  - description: "已有 01-structure-analysis.md，需要生成讲解内容 YAML"
  - description: "用户要求生成 explanation assignment.yaml"
  - description: "用户提到 explanation-latex-data 或讲解 YAML"
skip:
  - description: "没有 01-structure-analysis.md（先运行 math-structure-analysis）"
  - description: "用户要求 HTML 输出（使用 math-student-explanation-html）"
  - description: "用户要求练习题（使用 math-adaptive-practice-latex-data）"
---

# math-student-explanation-latex-data

## 职责

从 `01-structure-analysis.md` 生成 `02-student-explanation.assignment.yaml`。

输出给 `math-assignment-latex` 的 `exam-zh-explanation` 模板使用。默认生成一页课堂讲解讲义：题目入口、读题提示、流程图、双栏讲解、答案/方法提醒。

## 输入

- `artifacts/<slug>/01-structure-analysis.md`
- 学生画像（可选）
- 教学目标（可选）

## 输出

```text
artifacts/<slug>/02-student-explanation.assignment.yaml
```

## 默认讲义结构

除非用户明确要求旧式分节讲解，默认使用以下 5 个 block，放在同一个 section 中：

1. `problem`：原题入口，使用 `stem_latex` 和可选 `subquestions`。
2. `reading_tip`：1-3 条读题提示，提醒先做什么、后续小问依赖什么。
3. `route`：2-4 步横向解题路线，优先 3 步。
4. `dual_explanation`：左栏放思考引导/易错提示，右栏放规范讲解；有递进小问时使用 `connection_items`。
5. `summary_dual`：左栏答案，右栏方法提醒。

保留原 HTML 版教学逻辑，但把它压缩映射到上述结构：

- 原题拆解 → `reading_tip` 和 `route`
- 关键想法 → `reading_tip` 或 `dual_explanation.left_items`
- 标准解法 → `dual_explanation.right_steps`
- 易错提醒 → `dual_explanation.left_items`
- 后续小问承接 → `dual_explanation.connection_items`
- 一句话总结/方法归纳 → `summary_dual.right_items`
- 最终答案 → `summary_dual.left_items`

## YAML 输出格式

```yaml
meta:
  title: "一次函数课堂讲解"
  example_label: "例题 2"
  subtitle: "一次函数 | 课堂讲解"
  grade: "..."
  subject: "数学"
  version: "teacher"
  source_artifacts:
    structure_analysis: "artifacts/<slug>/01-structure-analysis.md"

render:
  template: "exam-zh-explanation"
  paper_size: "a4paper"

sections:
  - id: "main"
    title: "课堂讲解"
    type: "explanation"
    visibility: "both"
    blocks:
      - type: "problem"
        id: "problem"
        label: "题目"
        stem_latex: "原题主干，公式使用 $...$"
        subquestions:
          - latex: "第一个小问；"
          - latex: "第二个小问。"

      - type: "reading_tip"
        id: "reading-tip"
        items:
          - latex: "先解决基础问，再处理依赖前面结论的后续问。"
          - latex: "点明这道题的核心递进关系。"

      - type: "route"
        id: "route"
        steps: [...]

      - type: "dual_explanation"
        id: "explanation"
        title: "讲解"
        left_title: "思考引导 / 易错提示"
        left_items: [...]
        right_title: "规范讲解"
        right_steps: [...]
        connection_title: "后两问如何承接"
        connection_items: [...]

      - type: "summary_dual"
        id: "summary"
        left_title: "答案"
        left_items: [...]
        right_title: "方法提醒"
        right_items: [...]
```

## 生成规则

- `meta.example_label` 用于左上角例题编号；没有编号时写 `"例题"` 或省略。
- `meta.subtitle` 写右上角栏目，如 `"一次函数 | 课堂讲解"`。
- 讲解页不要生成旧式 `original/breakdown/key-idea/solution/mistakes/questions/summary` 多 section，除非用户明确要求。
- 使用 `latex` 字段承载含公式的条目；纯文本可用 `text`。
- 不要把中文标点放进数学模式：写 `$A$、$B$`，不要写 `$A、B$`。
- `route.steps` 每步尽量 8-16 个汉字，避免流程框过长。
- `dual_explanation.left_items` 放 2-4 条“怎么想/哪里易错”，不要重复右栏计算。
- `dual_explanation.right_steps` 放 2-5 条规范步骤，每条能直接上课讲。
- 有多个小问且后问依赖前问时，必须写 `connection_items`。
- `summary_dual.left_items` 只放最终答案；`right_items` 放可迁移的方法提醒。

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md` 定义的 schema。

## 自检

输出前必须检查：
1. 所有 block 都有 id 且唯一
2. 所有 block 都有 type
3. 数学公式使用 `$...$` 和 `$$...$$` 格式
4. `problem` 至少有 `stem` 或 `stem_latex`
5. `route.steps` 非空
6. `dual_explanation.left_items` 和 `right_steps` 非空
7. `summary_dual.left_items` 和 `right_items` 非空
8. version 字段正确设置

## Handoff

生成完毕后说明：

```
下一步：使用 math-assignment-latex 渲染并编译 PDF。

python3 math-assignment-latex/scripts/render_assignment.py \
  artifacts/<slug>/02-student-explanation.assignment.yaml \
  --out artifacts/<slug>/04-assignment.tex

bash math-assignment-latex/scripts/compile_latex.sh \
  artifacts/<slug>/04-assignment.tex
```
