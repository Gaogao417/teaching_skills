---
name: math-adaptive-practice-latex-data
description: "根据 01-structure-analysis.md 和讲解 YAML 生成自适应练习 assignment.yaml。Use when: 已有结构分析和 02-student-explanation 的 assignment/resolved YAML，用户要求练习、practice YAML、学生版/教师版练习或端到端作业补齐练习阶段。Skip when: 没有结构分析、没有讲解内容、用户只要求讲解或只要求渲染 PDF。需要几何图时只声明 diagram_slot，不写 image_path/diagram_col；真实出图交给 math-geometry-diagram-renderer。"
---

# math-adaptive-practice-latex-data

## 职责

从结构分析和讲解内容生成练习 YAML。这个 skill 只负责练习内容、学生/教师版本分离和练习题上的 `diagram_slot` 声明；不运行 renderer，不编译 PDF。

默认同时输出：

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.student.plan.assignment.yaml
artifacts/<学生名>/YYYY-MM-DD-<内容>/03-adaptive-practice.teacher.plan.assignment.yaml
```

若完全没有 `diagram_slot`，可直接输出：

```text
03-adaptive-practice.student.assignment.yaml
03-adaptive-practice.teacher.assignment.yaml
```

## 输入

- `01-structure-analysis.md`
- `02-student-explanation.assignment.yaml` 或 `02-student-explanation.resolved.assignment.yaml`
- 学生画像或 `03-student-response-diagnosis.md`（可选，只作为本轮调节证据）

## 工作流

1. 读取结构分析中的 `canonical_solution`、`practice_task_packet`、`variation_rules`、`complexity_budget`；如果存在，也读取 `proposition_network`、`model_tags`、`application_quantity_network`。
2. 若有学生回答诊断，读取其中的 `entry_point`、`scaffold_level`、`variation_depth`、`fallback_move`。
3. 为本轮练习选择一个主要训练动作，最多小步改变一个主维度。
4. 生成学生版和教师版 YAML。学生版不含答案、解析、教学备注；教师版含答案、解析、分步解法和本轮调节说明。
5. 若练习题需要图，只写 `diagram_slot`。slot 字段规则读取 `references/practice-diagram-slot.md`。
6. 输出 YAML 后运行 schema 校验；如果校验失败，修 YAML。

## 调节参数

教师版题目可写入：

```yaml
teaching:
  teaching_goal: "本题训练的核心动作"
  expected_blocker: "本轮最可能卡住的位置"
  entry_point: "read_context | find_entry | build_relation | solve_and_check | transfer | hidden_structure | reverse_construct"
  scaffold_level: "high | medium | low"
  variation_depth: "same_structure | changed_numbers | changed_question | changed_representation | packaged_condition | partially_hidden | reverse_construct"
  complexity_note: "与 structure-analysis 的 complexity_budget 对齐"
  upgrade_rule: "学生可升级的可观察条件"
  fallback_move: "学生卡住时回退到哪个动作"
```

`entry_point` 必须与 `math-structure-analysis` 的 Teaching Entry Ladder 保持一致；不要再使用旧值 `find_key_quantity`。

## 出题规则

- 每组最多 3 题；只小步改变一个主维度。
- 保留核心结构，不引入无关知识点。若结构分析包含命题网络，练习变式必须保留同一组关键 proposition/relation 或明确只改变一个 relation 的方向；若包含 `model_tags.configuration`，优先围绕同一 model 的 configuration 做换数、换问法或反向构造。
- 遵守 `complexity_budget.max_next_step`，不引入 `forbidden_load`。
- 算术保持干净：小整数、简单分数、可手算验证。
- 不同时隐藏结构和提高计算难度，除非学生证据明确支持低支架迁移。
- 提示渐进：先提示动作，再接近答案。
- 所有答案必须先独立验算。
- 不出现长期标签、评级、档位字段。

## 版本分离

- 学生版不得包含 `answer`、`explanation`、`solution_steps`、`teaching`。
- 教师版可以包含 `answer`、`explanation`、`solution_steps`、`teaching`。
- 解答题题干含公式或 enumerate 时，用 `stem_latex`，不要用 `stem`。
- 教师版必须添加 `answer_key` section；答案区使用 `layout: { break_before: true }`。

## References

- `references/practice-blocks.md`: `choice`、`fillin`、`problem` 最小字段和学生/教师版差异。
- `references/practice-diagram-slot.md`: 练习题 `diagram_slot` 放置位置和 plan/resolved 边界。
- `math-assignment-latex/references/assignment-schema.md`: 只有需要完整 schema 时读取。

## 自检

输出前检查：

1. 所有 block id 唯一。
2. 每组题量不超过 3 题。
3. 学生版不含答案、解析、分步解法、教学备注。
4. 教师版答案经过代入或逻辑验算，解答题有 `solution_steps`。
5. `entry_point` 和 `variation_depth` 使用当前枚举。
6. 若使用几何图，plan YAML 只写 `diagram_slot`，不写最终图片字段。
7. YAML 通过 `python3 math-assignment-latex/scripts/validate_assignment.py <yaml>`。

## Handoff

若任一 YAML 中存在 `diagram_slot`，下一步使用 `math-geometry-diagram-renderer` 生成 resolved YAML。

得到 resolved YAML 后，或确认普通 assignment YAML 中不存在 `diagram_slot` 后，下一步使用 `math-assignment-latex` 渲染并编译 PDF。
