---
name: math-homework-review
description: "审核完整数学作业产物，从六个角度给出简短质量印象：流程完整性、数学正确性、结构分析质量、学生讲解质量、自适应练习设计、几何插图与版式。用于 PDF 生成后的最终独立审核子任务，或用户要求快速审查已生成作业时。不要用于完整 YAML schema 审查、LaTeX 编译排错或重新生成内容。"
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

### 6. 几何插图与版式

只在产物含几何题或结构分析/YAML 声明需要图时审核；非几何作业可写“不适用”。

- 该有图的题是否有图：几何大题一律有图；几何题已知条件数大于 3 默认有图；“如图/图中/下图”题必须有图。
- plan YAML 是否只含 `diagram_slot`，没有手写 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row` 或 `answer_space.diagram_col`。
- resolved YAML 是否已把 slot 解析为题型可用图片字段；选择题图栏、填空题图位、解答题答题区图栏是否和模板契约匹配。
- 每道需要图的练习题是否有独立 `diagram_slot.slot_id` / resolved `diagram_job_id`；若共用图，是否显式写了 `reuse_geometry_from`。
- 是否存在多道练习题偷偷引用同一 `image_path` 但没有显式复用声明的情况；有则判为需回退修复。
- solution 图若存在，检查对应 `workflow_result.json` 中的 `solution_reuse_check.locked_points_same` 是否为 true；否则判为需回退修复。
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

- 不做完整 YAML schema 审查；需要时使用 `math-yaml-review` 或 `validate_assignment.py`。
- 不详细排查 LaTeX 编译；只有 `build.log` 明确显示问题时才简述。
- 不重新生成结构分析、YAML、TEX 或 PDF。
- 不把结论表述为“数学保证正确”；这只是快速独立审核。
