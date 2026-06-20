---
name: math-homework-review
description: "快速审核已生成的数学作业产物，从流程完整性、数学正确性、结构分析、讲解质量、练习设计、几何插图与版式给出简短质量印象。Use when: PDF/YAML/TEX 已生成后需要最终独立审核，或用户要求快速审查 artifact 目录。Skip when: 需要重新生成内容、完整 YAML schema 审查、LaTeX 编译排错或真实出图。"
---

# math-homework-review

## 职责

对已完成的数学作业产物做一次快速独立审核，给教师一个大致质量印象。保持简短，不直接改写产物；只有用户明确要求修复时，才进入对应阶段修改或重新生成。

## 输入

接受以下任一输入：

- artifact 目录，如 `artifacts/<学生名>/<日期>-<主题>/`
- 若干具体产物路径
- 从当前 pipeline 运行中推断出的最新 artifact 目录

可检查的产物包括：

- `01-structure-analysis.md`
- `02-student-explanation.plan.assignment.yaml`, `.resolved.assignment.yaml`, `.assignment.yaml`, `.tex`, or `.pdf`
- `03-adaptive-practice.student.plan.assignment.yaml`, `.resolved.assignment.yaml`, `.assignment.yaml`, `.tex`, or `.pdf`
- `03-adaptive-practice.teacher.plan.assignment.yaml`, `.resolved.assignment.yaml`, `.assignment.yaml`, `.tex`, or `.pdf`
- `build.log` if compilation happened

文件缺失本身就是审核结论的一部分，归入“完整性”。

## 审核范围

只审核以下六项。

### 1. 流程完整性

检查各阶段产物是否齐全、衔接是否清楚：

- 是否有结构分析。
- 是否有讲解产物。
- 要求练习时，是否有学生版和教师版练习产物。
- 渲染和编译后是否有 TEX/PDF。
- 文件命名和 source-artifacts 引用是否没有明显错位。
- 若存在 `diagram_slot`，是否有对应 resolved YAML；最终渲染是否使用 resolved YAML，而不是直接渲染 plan YAML。

### 2. 数学正确性

检查主干数学结论，不做穷尽证明：

- 原题是否被准确保留。
- 标准解和最终答案是否可信。
- 关键代入、方程、结论、特殊情况是否自洽。
- 是否存在明显问题，如选项答案不一致、漏掉定义域/范围检查、忽略退化情形。

### 3. 结构分析质量

检查 `01-structure-analysis.md` 是否能作为后续生成的教学锚点：

- 是否抓住核心结构，而不只是写表面考点。
- 若采用新版结构分析，命题网络/模型标签是否清楚；关键关系是否写成可检查的 `P_i + P_j -> P_k`，而不是泛泛写“利用相似”“数形结合”。基础计算题也应把关键计算状态写成命题关系。
- 标准路径是否可执行、顺序是否合理。
- 最短可靠路径和常见卡点是否具体。
- 变式原则是否保留核心不变量，避免引入无关知识。
- 复杂度预算是否足够指导后续练习生成。

### 4. 学生讲解质量

检查讲解是否真正面向学生、可讲可学：

- 是否有清楚的题目拆解和解题路线。
- 关键想法是否用动作语言表达。
- 标准解法是否分步展开，而不是只给答案。
- 提问、提示、易错提醒是否围绕核心链条。
- 是否避免不必要的抽象话和额外知识。

### 5. 自适应练习设计

检查练习是否承接结构分析：

- 是否保留同一个核心结构。
- 难度是否只小步上升。
- 每组题量是否足够聚焦。
- 提示是否渐进，而不是一上来给答案。
- 学生版和教师版是否分工清楚，教师版承担答案和教学备注。
- 必须抽查教师版 `teaching.variation_depth` 与题干实际变化是否一致；如果只是换数，不能接受标成表征切换、隐藏结构或反向构造。
- 必须对每个 2-3 题练习组做“变式覆盖”判断：是否至少覆盖两个真实深化层级；若同一组题都停留在同结构换数，应在本维度明确判为需修。
- 必须检查压轴题或收束题是否只是前题的子集、筛选版或换数版；若是，不能把它评价为迁移或综合。
- 如果用户要求“综合”“提高难度”“压轴”或“多题型”，必须检查教师版是否记录 `source_relations` / `model_fusion` / `relation_chain` 或等价证据；若只有 relation 标签而没有 chain，应判定为缺少 typed fusion 证据。
- 对综合题逐题判断是否真实融合 2-3 个 model/relation：每个 model 必须改变入口、约束、目标转换、筛选或验算方式。只在题面出现反比例/二次函数/面积字样，但解法仍由单一矩形关系秒杀，不算真实融合。
- fusion 的核心审核标准：一个 relation 的 `outputs` 是否真实成为另一个 relation 的 `inputs`。若只是同一素材的并列小问、共同底边/共同点名、或人为贴多个 `source_relations`，不算融合。
- 若 `relation_chain` 中出现 `CandidateSet<T>` 接入下游 `T`，必须看到 selector/filter/branching；若没有，应判为需要回退到练习生成阶段。
- 检查题型形式是否与“多题型”目标一致。若用户要求多题型或题量较多却全部是 `problem` 解答题，应在练习设计中说明不足，除非题目目标明确只要解答题。
- 审核不能只查文件清单、页数、学生版答案泄露；这些只能作为版式/流程证据，不能替代选题质量判断。

### 6. 几何插图与版式

只在产物含几何题或结构分析/YAML 声明需要图时审核；非几何作业可写“不适用”。

- 是否符合前序图形契约：结构分析/YAML 声明需要图的题是否有图；题干出现“如图/图中/下图”时是否有对应 `diagram_slot` 或 resolved 图片。
- plan YAML 是否只含 `diagram_slot`，没有手写 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row` 或 `answer_space.diagram_col`。
- resolved YAML 是否已把 slot 解析为题型可用图片字段；选择题图栏、填空题图位、解答题答题区图栏是否和模板契约匹配。
- 每道需要图的练习题是否有独立 `diagram_slot.slot_id` / resolved `diagram_job_id`；若共用图，是否显式写了 `reuse_geometry_from`。
- 是否存在多道练习题偷偷引用同一 `image_path` 但没有显式复用声明的情况；有则判为需回退修复。
- solution 图若存在，抽查其是否显式复用 prompt 构型；若相关 workflow 结果暴露了复用检查字段，再参考该字段判断是否需回退修复。
- prompt 原题图是否 clean：只含题目已知对象和顶点标签，没有辅助线、推理标注或答案泄露；solution/teacher 图才可 annotated。
- PDF 缩小预览中顶点标签是否清楚可读，图尺寸是否不过大。
- 不只审核图片是否存在；还要抽查题干点序和图中点序是否一致，尤其是 `B,C,H,D`、`C 在 B,H 之间`、`D 在射线 BC 上` 这类条件。若 `workflow_result.json` 显示 `usable=true` 但预览点序不合题意，判为需回退重画。

## 输出格式

输出简短印象，不写完整审计报告。使用格式：

```text
审核印象：通过 / 基本可用但需小修 / 建议回退重做

1. 流程完整性：...
2. 数学正确性：...
3. 结构分析：...
4. 讲解质量：...
5. 练习设计：...
6. 几何插图与版式：...

最需要关注：...
建议下一步：...
```

每个编号项控制在一到两句话。证据不足时，说明缺少哪个文件，不要猜测。

## 边界

- 不做完整 YAML schema 审查；需要时使用 `validate_assignment.py` 或 `math-assignment-latex/scripts/batch_yaml_review.py`。
- 不详细排查 LaTeX 编译；只有 `build.log` 明确显示问题时才简述。
- 不重新生成结构分析、YAML、TEX 或 PDF。
- 不把结论表述为“数学保证正确”；这只是快速独立审核。
