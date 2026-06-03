---
name: math-student-explanation-latex-data
description: "根据 01-structure-analysis.md 生成学生讲解 assignment.yaml。Use when: 已有结构分析，用户要求讲解 YAML、explanation assignment.yaml、讲义内容或端到端作业补齐讲解阶段。Skip when: 没有结构分析、用户要求独立练习题、只要求几何图或只要求渲染 PDF。需要配图时只声明 diagram_slot，不写 image_path/diagram_col；真实出图交给 math-geometry-diagram-renderer。"
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
3. 设计讲解顺序：原题展示、读题拆解、路线图、分小问标准解、易错提醒、简短随堂检查、总结。
4. 使用 `exam-zh-explanation` 模板支持的 block type。需要字段细节时读取 `references/explanation-blocks.md`。
5. 若需要几何图，只写 `diagram_slot`。slot 字段规则读取 `references/diagram-slot-contract.md`。
6. 输出 YAML 后运行 schema 校验；如果校验失败，修 YAML，不把错误留给渲染阶段。

## 教学规则

- 原题用 `problemcard` + `stem_latex`，不要用普通 `step` 放原题。
- 路线图用 `route`；每个小问用 `dual_explanation`，并通过 `solution_step_ids` 复用路线图步骤。
- 每个小问讲解前必须带 `label` 和该小问 `stem_latex`，不要写成 `title: "第（X）问"`。
- 标准解法要分步展示；步骤标题和正文来自对应 `route.steps[]`。
- `variation_training` 只做一个短小动作确认。独立成套练习交给 `math-adaptive-practice-latex-data`。
- 数学公式用 `$...$` / `$$...$$`；block scalar 中 LaTeX 命令用单反斜杠。

## 几何图规则

- `diagram_request_packet.needs_diagram: true` 时，本 skill 只声明 `diagram_slot`，不调用 renderer。
- 原题展示只能用 `variant: prompt` + `disclosure_policy: clean`。
- 讲解步骤若需要辅助线、垂足、角标或推理标注，另声明 `variant: solution` + `disclosure_policy: annotated`，并用 `reuse_geometry_from` 指向 prompt slot。
- plan YAML 中不得出现 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row` 或最终 `type: diagram` 图片对象。
- 坐标图/函数图没有确定性 renderer 支持时，用 `hint` fallback，不制造空 slot。

## References

- `references/explanation-blocks.md`: block type 字段、最小 YAML 结构、常见错误写法。
- `references/diagram-slot-contract.md`: `diagram_slot` 字段、clean/annotated 区分、plan/resolved 边界。
- `math-assignment-latex/references/assignment-schema.md`: 只有需要查完整 schema 时读取。

## 自检

输出前检查：

1. 所有 block 有唯一 `id` 和正确 `type`。
2. 原题、每个小问题干、标准答案与结构分析和原题一致。
3. 每个 `dual_explanation.solution_step_ids` 都能在 `route.steps[].id` 中找到。
4. 若有图，只出现 `diagram_slot`，不出现 resolved 图片字段。
5. YAML 通过 `python3 math-assignment-latex/scripts/validate_assignment.py <yaml>`。

## Handoff

若 YAML 中存在 `diagram_slot`，下一步使用 `math-geometry-diagram-renderer` 生成 `02-student-explanation.resolved.assignment.yaml`。

若无 `diagram_slot` 或已得到 resolved YAML，下一步使用 `math-assignment-latex` 渲染并编译 PDF。
