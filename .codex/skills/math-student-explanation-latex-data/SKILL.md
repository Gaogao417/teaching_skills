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
7. 读取 `references/explanation-blocks.md`，按统一讲义单元模板设计内容。每个知识点/模型单元必须有 `section.title` 且设置 `show_title: true`。聚焦单题型或单一动作训练时默认例题优先：标题后直接进入题面，不在第一道例题前堆放完整路线、分类表、边界说明或大段知识总结。
8. 使用最小充分 block 组合：内容型标题 + `problemcard + route + dual_explanation` 是聚焦讲义的默认骨架；短定义或必要前置概念可用一条轻量提示。`solution`、`mistake`、`method_reminder` 都是按需 block，不得每个单元机械齐配。只有内容在例题步骤和 side items 中无法自然承载，且确实影响入口、分支判断或易错边界时才添加。
9. 若需要几何图，读取 `references/diagram-slot-contract.md`，只声明 plan 阶段的 `diagram_slot`。
10. 锁定本节训练目标和例题所求：不要主动扩展成“完整解出所有边角”、近似角度、重复验算或额外分类，除非这些就是本节目标；同时逐项核对题干中的每个所求量都在解答中出现，不能因精简而漏答。
11. 优先寻找一条能统一多个分支的可执行方法，让计算结果或几何条件承担分支判定；不要在学生尚未做例题前先给大而全的分类表。需要补充分支时，优先在 `side_items` 中放一个短反例/变式或用第二个例题解释结果含义。
12. 使用 `exam-zh-explanation` 模板输出 assignment YAML。输出后必须检查每个 `route.steps[].content_latex`：解答步骤只讲 how，要求简洁、严谨、规范；把讲 why、讲“所以然”、入口追问和易混判断移到 `dual_explanation.side_items` 的小贴士提问中。每条 side item 必须解决一个真实卡点，删除与步骤正文重复的解释。
   - 初中几何证明和连续推导默认用 `\because` / `\therefore` 组织“条件—结论”链；不要通篇只用“由、故、所以”的口语句式。
   - YAML block scalar 中的源码换行渲染后只是空格，不是可见换行。解答正文必须“一个推理动作一行”：用显式 `\\` 分行，`\because` 条件与 `\therefore` 结论各占一行；“解 $\triangle XXX$”的固定句式也单独成行。禁止只在 YAML 源文本中敲回车却不写 LaTeX 换行命令。
   - 出现“多个等腰三角形 + 相似”时，`side_items` 必须提醒学生先标顶角、底角、腰和底；两个等腰三角形相似时，对应关系确定后优先用“腰底比”，不重复倒角或重做一轮余弦计算。
   - 出现“解三角形”动作且用户无特殊说明时，使用固定句式：`\textbf{解 $\triangle XXX$}：已知……，……，……，得……。`一般三角形列三个独立已知量且至少含一边；等腰或直角三角形先写特殊性质，再写两个有效已知量。“得”后给出其余边角，但讲义正文可只保留本题后续会使用的结果。
13. 若用户直接修改了渲染后的 `.tex`，先用 Git diff 提取其结构性反馈，再把可复用调整落实到 assignment YAML 或 skill 规则；不要立即重渲染覆盖用户的 `.tex`。区分稳定偏好与单题临时改法，并检查用户精简稿是否仍完整回答题目。
14. 输出 YAML 后运行 schema 校验；如果校验失败，修 YAML，不把错误留给渲染阶段。

## References

- `references/explanation-blocks.md`: block type 字段、最小 YAML 结构、常见错误写法。
- `references/diagram-slot-contract.md`: `diagram_slot` 字段、clean/annotated 区分、plan/resolved 边界。
- `math-assignment-latex/references/assignment-schema.md`: 只有需要查完整 schema 时读取。

## 自检

输出前检查：

1. 所有 block 有唯一 `id` 和正确 `type`。
2. 已按 `references/explanation-blocks.md` 使用最小充分讲义结构，并根据任务确定单题型、小专题型或复习型规模；聚焦讲义没有在首个例题前堆放大段总览。
3. 每个讲义单元都有可见 `section.title` 和 `show_title: true`，标题不是“知识点讲解”“例题讲解”“公式清单”等空泛功能名。
4. 每个讲解主块都能对应到 `核心结构`、`知识点/模型锚点`、`出题人逻辑`、`学生卡点预测`或`推荐讲题任务包`中的一个明确依据；不要只对着摘要标签填表。
5. 若使用 canonical relation，讲解中的命题名称、条件和排除值与 relation propositions / constraints 一致。
6. 重写版本不是从旧 YAML 复制后局部打补丁；旧 YAML 只作为反馈来源或版式参考。
7. 已逐条检查 `route.steps[].content_latex`：每步只保留必要动作、公式和结论；删除冗长动机、类比、追问、口语解释。
8. 已把必要的“为什么这样做”“下一步该想到什么”“容易混在哪里”改写为少量、不可重复的 `dual_explanation.side_items`；能由步骤直接看出的内容不再写一遍。
9. 初中几何推导已在关键因果链中使用 `\because` / `\therefore`；若有等腰三角形之间的相似，已明示顶角/底角和腰/底，并优先检查腰底比路径。
10. 已检查可见分行：不把 YAML 源码换行当成排版换行；每个推理动作显式使用 `\\` 分行，`\because` 与 `\therefore` 不挤在同一行。
11. 出现“解三角形”时已使用固定句式，一般/等腰/直角三角形的已知量数量与特殊性质表述正确，且该句式单独成行。
12. 已逐项核对题干所求全部得到回答；没有擅自扩展到本节不训练的边、角、近似值或完整验算。
13. 若写 `solution`、`mistake` 或 `method_reminder`，每个 block 都有不可被例题步骤/side items 替代的独立作用；没有为了模板完整而机械添加。
14. 若有多个情形，已优先考虑统一方法 + 结果判别；分类表确有必要时也没有放在首例之前压过例题入口。
15. 若有图，已按 `references/diagram-slot-contract.md` 约束只声明 plan 图位。
16. YAML 通过 `python3 math-assignment-latex/scripts/validate_assignment.py <yaml>`。

## Diagram resolve

若 YAML 中存在 `diagram_slot`，下一步使用 `math-geometry-diagram-renderer` 生成 `02-student-explanation.resolved.assignment.yaml`。

## Review UI（本 skill 负责）

讲义内容生成后的 review 编排属于本 skill，不交给 `math-assignment-latex`。若无 `diagram_slot`，使用普通
assignment YAML；若有图，必须先完成 diagram resolve，再使用 resolved YAML。然后由本 skill 打开讲义专用
review UI：

```bash
./.venv/bin/python .codex/skills/math-student-explanation-latex-data/scripts/open_explanation_review.py <02-student-explanation.assignment.yaml|02-student-explanation.resolved.assignment.yaml>
```

本 skill 自己持有打开 UI 的入口脚本；共享 review server、模板和前端资源仍由底层 LaTeX 工具复用。
选择输入、启动 UI、等待用户确认和取得 reviewed YAML 的流程由本 skill 负责。用户确认并保存 reviewed YAML 后，才 handoff 给
`math-assignment-latex` 做验证、渲染、检查或编译；若用户明确要求跳过 review，记录该选择后直接 handoff。
