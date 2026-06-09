---
name: math-student-explanation-latex-data
description: "根据 01-structure-analysis.md 生成学生讲解 assignment.yaml。Use when: 已有结构分析，用户要求讲解 YAML、explanation assignment.yaml、讲义内容或端到端作业补齐讲解阶段。Skip when: 没有结构分析、用户要求独立练习题、只要求几何图或只要求渲染 PDF。需要配图时按 diagram-slot-contract 声明 diagram_slot；真实出图交给 math-geometry-diagram-renderer。"
---

# math-student-explanation-latex-data

## 职责

从 `01-structure-analysis.md` 生成讲解内容 YAML。讲解只负责“讲懂原题和关键动作”，不生成独立成套练习。

默认输出：

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.plan.assignment.yaml
```

若完全没有 `diagram_slot`，可直接输出：

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.assignment.yaml
```

## 输入

- `01-structure-analysis.md`
- 学生画像或本次教学目标（可选）

## 工作流

1. 读取结构分析中的 `canonical_solution`、`explanation_task_packet`、`common_blockers`、`diagram_request_packet`。
2. 先独立核对原题、标准解和关键限制；不要把结构分析里的错误机械抄入 YAML。
3. 读取 `references/explanation-blocks.md`，按其中的 block 规则设计讲解内容。
4. 若需要几何图，读取 `references/diagram-slot-contract.md`，只声明 plan 阶段的 `diagram_slot`。
5. 使用 `exam-zh-explanation` 模板输出 assignment YAML。输出后必须检查每个 `route.steps[].content_latex`：解答步骤只讲 how，要求简洁、严谨、规范；把讲 why、讲“所以然”、入口追问和易混判断移到 `dual_explanation.side_items` 的小贴士提问中。
6. 输出 YAML 后运行 schema 校验；如果校验失败，修 YAML，不把错误留给渲染阶段。

## References

- `references/explanation-blocks.md`: block type 字段、最小 YAML 结构、常见错误写法。
- `references/diagram-slot-contract.md`: `diagram_slot` 字段、clean/annotated 区分、plan/resolved 边界。
- `math-assignment-latex/references/assignment-schema.md`: 只有需要查完整 schema 时读取。

## 自检

输出前检查：

1. 所有 block 有唯一 `id` 和正确 `type`。
2. 已按 `references/explanation-blocks.md` 约束生成讲解 block。
3. 已逐条检查 `route.steps[].content_latex`：每步只保留必要动作、公式和结论；删除冗长动机、类比、追问、口语解释。
4. 已把必要的“为什么这样做”“下一步该想到什么”“容易混在哪里”改写为 `dual_explanation.side_items` 中的短小贴士提问，而不是塞进标准解答正文。
5. 若有图，已按 `references/diagram-slot-contract.md` 约束只声明 plan 图位。
6. YAML 通过 `python3 math-assignment-latex/scripts/validate_assignment.py <yaml>`。

## Handoff

若 YAML 中存在 `diagram_slot`，下一步使用 `math-geometry-diagram-renderer` 生成 `02-student-explanation.resolved.assignment.yaml`。

若无 `diagram_slot` 或已得到 resolved YAML，下一步使用 `math-assignment-latex` 渲染并编译 PDF。
