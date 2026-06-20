---
name: math-homework-pipeline
description: "端到端轻量调度器：检查数学作业 artifact 缺哪一步，并按 LaTeX/YAML 流水线委托给结构分析、讲解 YAML、练习 YAML、几何图 resolve、LaTeX render/compile 和最终审核。Use when: 用户给数学题要求完整作业/PDF，或要求端到端补齐缺失阶段。Skip when: 用户只要求某个单独阶段、只要求几何图、只要求 LaTeX 排错或只要求审核。"
---

# math-homework-pipeline

## 职责

这是一个薄调度器。它只负责检查 artifact 目录中已有和缺失的产物，然后按顺序调用对应 skill 或脚本。

本 skill 不直接生成题目内容，不直接写讲解或练习 YAML，不决定哪些题必须配图，不写 `diagram_slot` / `image_path`，不运行 diagram 细节判断，也不修改 LaTeX 模板。

## 触发与跳过

使用本 skill：

- 用户给了一道数学题，要求生成完整作业或完整 PDF
- 用户提到 homework-pipeline / pipeline
- 用户说“帮我把这道题做成作业”
- 用户要求端到端补齐缺失阶段

跳过本 skill：

- 只要求结构分析：使用 `math-structure-analysis`
- 只要求讲解 YAML：使用 `math-student-explanation-latex-data`
- 只要求练习 YAML：使用 `math-adaptive-practice-latex-data`
- 只要求几何图：使用 `math-geometry-diagram-renderer`
- 只要求 PDF 渲染或 LaTeX 排错：使用 LaTeX 渲染相关脚本

## 调度规则

```text
如果没有 01-structure-analysis.md
→ 调用 math-structure-analysis

如果已有结构分析
→ 调用 math-model-rule-ingestion，将可复用规则规范化为 canonical relations

如果 relation 阶段完成或明确 needs_review/fallback，且没有讲解 YAML
→ 调用 math-student-explanation-latex-data，读取结构分析和 canonical relations

如果 relation 阶段完成或明确 needs_review/fallback，且没有练习 YAML
→ 调用 math-adaptive-practice-latex-data，优先检索 canonical relations；检索失败时退回结构分析变式原则

如果用户要求“综合”“提高难度”“压轴”“多题型”或类似目标
→ 练习阶段必须显式执行模型覆盖计划：检索主模型和相邻模型，先生成每道综合题的 typed `relation_chain`，确认上游 outputs 能进入下游 inputs，再反向生成题面；教师版 teaching 必须留下 source_relations/model_fusion/relation_chain 证据

如果讲解或练习 plan YAML 中存在 diagram_slot
→ 调用 math-geometry-diagram-renderer
→ 只使用 renderer 产出的 resolved YAML 进入 LaTeX 渲染

如果已有可渲染 YAML 但没有 .tex
→ 运行 math-assignment-latex 的 render_assignment.py

如果已有 .tex 但没有 .pdf
→ 运行 math-assignment-latex 的 compile_latex.sh

如果编译失败
→ 摘要 build.log，反馈最小修复建议，并回到对应 YAML 或模板阶段

如果 PDF 已生成
→ 使用 math-homework-review 给出快速质量印象
```

## 产物判定

讲解阶段常见产物：

```text
02-student-explanation.plan.assignment.yaml      # 需要 diagram_slot 时的计划稿
02-student-explanation.resolved.assignment.yaml  # renderer 解析后的可渲染稿
02-student-explanation.assignment.yaml           # 无图或已可直接渲染的稿
```

练习阶段常见产物：

```text
03-adaptive-practice.student.plan.assignment.yaml
03-adaptive-practice.teacher.plan.assignment.yaml
03-adaptive-practice.student.resolved.assignment.yaml
03-adaptive-practice.teacher.resolved.assignment.yaml
03-adaptive-practice.student.assignment.yaml
03-adaptive-practice.teacher.assignment.yaml
```

选择进入 LaTeX 的 YAML 时：

- 优先使用 `*.resolved.assignment.yaml`
- 若不存在 `diagram_slot`，可使用普通 `*.assignment.yaml`
- 不要把仍含 `diagram_slot` 的 plan YAML 直接交给 LaTeX renderer

## 边界

- 哪些题需要讲解图，由 `math-student-explanation-latex-data` 决定。
- 哪些练习题需要配图、slot 放在哪里、是否学生版 clean / 教师版 annotated，由 `math-adaptive-practice-latex-data` 决定。
- 结构分析后的模型规则规范化和入库，由 `math-model-rule-ingestion` 决定；pipeline 只读取其 applied / needs_review / rejected 状态。
- “综合/提高难度”不是同一模型多出几道变式，也不是几个 relation 标签并列。pipeline 必须把它作为练习阶段的 typed chain 需求传递给 `math-adaptive-practice-latex-data`，并在最终审核时检查教师版是否有可读的 `relation_chain` 证据。
- 如何 collect / batch / gate / resolve，是否真的生成 PNG，是否允许 fallback，由 `math-geometry-diagram-renderer` 决定。
- 最终 PDF 的数学、教学、版式和插图质量印象，由 `math-homework-review` 决定。
- commit 分类遵循仓库根目录 `AGENTS.md`，不要在 pipeline skill 内重新定义规则。

## 每阶段输出

完成每阶段后输出：

```text
当前阶段：[阶段名]
产物路径：[文件路径]
下一步：[命令或说明]
需要人工检查：是/否
```

最终审核阶段输出：

```text
当前阶段：作业审核
审核对象：[artifact 目录]
审核方式：math-homework-review
审核印象：[通过 / 基本可用但需小修 / 建议回退重做]
下一步：[放行给学生 / 修复具体阶段 / 回退重新生成]
```

## 不做事项

- 不直接写结构分析、讲解、练习题或答案
- 不直接写 model rule patch 或 canonical relations
- 不直接写 `diagram_slot`、`image_path`、`diagram_col`、`diagram_row`
- 不判断几何图语义是否满足题干
- 不把 plan YAML 直接送入 LaTeX
- 不替代 renderer 的真实出图链路
- 不替代 final review
