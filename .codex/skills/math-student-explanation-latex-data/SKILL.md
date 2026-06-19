---
name: math-student-explanation-latex-data
description: "根据 01-structure-analysis.md 生成学生讲解 assignment.yaml。Use when: 已有结构分析，用户要求讲解 YAML、explanation assignment.yaml、讲义内容、知识点复习、专题复习、期末复习、薄弱点讲义或端到端作业补齐讲解阶段。Skip when: 没有结构分析、用户要求独立练习题、只要求几何图或只要求渲染 PDF。需要配图时按 diagram-slot-contract 声明 diagram_slot；真实出图交给 math-geometry-diagram-renderer。"
---

# math-student-explanation-latex-data

## 职责

从 `01-structure-analysis.md` 生成讲解内容 YAML。讲解只负责把结构分析中的知识点/模型锚点、原题/例题和关键动作排成学生讲义，不生成独立成套练习。

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
- `model_rules/relations.yaml` 中相关 canonical relations（若 math-model-rule-ingestion 已 applied）
- 学生画像或本次教学目标（可选）

## 工作流

1. 读取 `01-structure-analysis.md` 全文。生成前先在内部列出：
   - `核心结构`、`关键转化`、`标准路径骨架`中的主线 relation。
   - 若 `model_rules/relations.yaml` 中存在相关 relation，读取其 propositions / constraints，使讲解术语与模型库一致。
   - `知识点/模型锚点`中的建议讲义标题、核心公式/定理、使用条件、入口信号和易混边界。
   - `出题人逻辑`、`学生卡点预测`、`推荐讲题任务包`中的讲解意图和入口顺序。
   - `标准完整解与验算`、`推荐图形请求包`（如有）中的硬约束。
2. 可用 `python3 scripts/model_rules/search_model_rules.py --topic <topic>` 或 relation id 检索模型库；若没有匹配 relation，继续使用结构分析 prose，不阻断讲解生成。
3. 先独立核对原题、标准解和关键限制；不要把结构分析里的错误机械抄入 YAML。
4. 不读取、不依赖末尾 JSON 摘要；若旧结构分析仍带 JSON，把它视为历史冗余，不能作为讲解设计依据。
5. 若是在重写或生成 v2，可以查看旧 YAML 的版式问题和用户反馈，但不要 `cp` 旧 YAML 当新版本种子。先按结构分析重新设计 block 顺序，再决定哪些旧内容值得保留。
6. 确定讲义规模，而不是切换讲解模式：
   - 单题型：1 个知识点/模型单元，原题作为例题。
   - 小专题型：1-3 个知识点/模型单元，每个单元 1-2 个例题。
   - 复习型：多个知识点/模型单元，每个单元独立成组。
7. 读取 `references/explanation-blocks.md`，按统一讲义单元模板设计内容。每个知识点/模型单元必须有 `section.title` 且设置 `show_title: true`；即使不写 `solution` 知识点陈述 block，也不能省略可见标题。
8. 每个讲义单元默认采用：内容型标题 + 可选 `solution` 知识点陈述 + 若干例题讲解（`problemcard + route + dual_explanation`）+ `mistake` 易错提醒 + `method_reminder` 方法提醒。核心公式不要放进小字号 `step`；`solution.title` 要写内容型标题，`method_reminder` 只做节末策略总结。
9. 若需要几何图，读取 `references/diagram-slot-contract.md`，只声明 plan 阶段的 `diagram_slot`。
10. 使用 `exam-zh-explanation` 模板输出 assignment YAML。输出后必须检查每个 `route.steps[].content_latex`：解答步骤只讲 how，要求简洁、严谨、规范；把讲 why、讲“所以然”、入口追问和易混判断移到 `dual_explanation.side_items` 的小贴士提问中。
11. 输出 YAML 后运行 schema 校验；如果校验失败，修 YAML，不把错误留给渲染阶段。

## References

- `references/explanation-blocks.md`: block type 字段、最小 YAML 结构、常见错误写法。
- `references/diagram-slot-contract.md`: `diagram_slot` 字段、clean/annotated 区分、plan/resolved 边界。
- `math-assignment-latex/references/assignment-schema.md`: 只有需要查完整 schema 时读取。

## 自检

输出前检查：

1. 所有 block 有唯一 `id` 和正确 `type`。
2. 已按 `references/explanation-blocks.md` 使用统一讲义单元模板，并根据任务确定单题型、小专题型或复习型规模。
3. 每个讲义单元都有可见 `section.title` 和 `show_title: true`，标题不是“知识点讲解”“例题讲解”“公式清单”等空泛功能名。
4. 每个讲解主块都能对应到 `核心结构`、`知识点/模型锚点`、`出题人逻辑`、`学生卡点预测`或`推荐讲题任务包`中的一个明确依据；不要只对着摘要标签填表。
5. 若使用 canonical relation，讲解中的命题名称、条件和排除值与 relation propositions / constraints 一致。
6. 重写版本不是从旧 YAML 复制后局部打补丁；旧 YAML 只作为反馈来源或版式参考。
7. 已逐条检查 `route.steps[].content_latex`：每步只保留必要动作、公式和结论；删除冗长动机、类比、追问、口语解释。
8. 已把必要的“为什么这样做”“下一步该想到什么”“容易混在哪里”改写为 `dual_explanation.side_items` 中的短小贴士提问，而不是塞进标准解答正文。
9. 若写 `solution` block，核心公式和概念陈述已放入全宽 `solution` block，且 `solution.title` 是内容型标题；`step` 只用于短过渡；`method_reminder` 只放方法总结。
10. 若有图，已按 `references/diagram-slot-contract.md` 约束只声明 plan 图位。
11. YAML 通过 `python3 math-assignment-latex/scripts/validate_assignment.py <yaml>`。

## Handoff

若 YAML 中存在 `diagram_slot`，下一步使用 `math-geometry-diagram-renderer` 生成 `02-student-explanation.resolved.assignment.yaml`。

若无 `diagram_slot` 或已得到 resolved YAML，下一步使用 `math-assignment-latex` 渲染并编译 PDF。
