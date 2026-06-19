---
name: math-model-rule-ingestion
description: "将 01-structure-analysis.md 中的模型规则草案规范化为 typed relations，并写入 YAML 模型规则库。Use when: 已有结构分析，需要把一次函数/坐标面积/坐标存在性等可复用出题规则入库，或 homework pipeline 在结构分析后进入 relation 规范化阶段。Skip when: 只要求讲解/练习内容且无需更新模型库，或题目明确属于暂不入库的几何证明模型。"
---

# math-model-rule-ingestion

## 职责

读取 `01-structure-analysis.md`，把其中可复用的出题规则整理成模型库 patch，并尝试写入 canonical relation YAML。

本 skill 不生成学生讲义、不生成练习题、不修改 assignment YAML、不渲染 PDF。

## 输入

- 一个 `01-structure-analysis.md`
- 可选：明确的 model family / relation 目标

## 输出

默认输出到：

```text
model_rules/patches/<analysis-slug>.model-rule.patch.yaml
```

并尝试调用：

```bash
python3 scripts/model_rules/apply_model_rule_patch.py <patch.yaml>
```

成功时更新：

```text
model_rules/type_registry.yaml
model_rules/relations.yaml
```

## 工作流

1. 读取结构分析全文，优先使用 `model_rule_draft` 段落。
2. 若没有 `model_rule_draft`，只从 `核心结构`、`变式原则`、`推荐练题任务包` 中提取 intuitive givens / derives；不要从学生讲解或练习 YAML 反推模型。
3. 对照 `model_rules/type_registry.yaml`，给每个 input/output 标注 canonical type。
4. 生成 patch，必须包含：
   - `source_analysis_path`
   - `model_family`
   - `type_registry_patch`
   - `relations`
   - `review_status`
5. 调用 `python3 scripts/model_rules/validate_model_rules.py --patch <patch.yaml>`。
6. 若校验通过，调用 `python3 scripts/model_rules/apply_model_rule_patch.py <patch.yaml>`。
7. 若输出 `needs_review`，不要强行改库；向用户报告缺失类型、alias 冲突或 relation 约束问题。

## Patch 规则

- `review_status` 初始写 `ready`。
- 新 alias 写入 `type_registry_patch.aliases_to_add`。
- 未知类型写入 `type_registry_patch.new_type_candidates`，并预期 apply 阶段进入 `needs_review`。
- relation 必须是单箭头；一个模型有多个方向时拆成多条 relation。
- 若输出 `CandidateSet<T>`，constraints 必须说明下游接 `T` 时需要 selector、filter 或 branching。
- `relation_id`、`model_family_id`、canonical type id 和 port type 是机器检索用稳定键，可以保留英文 snake_case。
- `name`、`topic_tags`、`propositions.statement`、`constraints`、`generation_notes`、`non_examples` 等人读字段优先写中文；不要把英文 slug 当成可读约束入库。

## 入库边界

第一版只入库：

- 一次函数
- 一次函数图像与不等式
- 坐标面积 / 铅垂线法
- 一次函数轨迹上的平行四边形存在性

几何证明题暂不入库；结构分析可保留命题网络，但 patch 中写：

```yaml
review_status: rejected
review_notes:
  - 几何证明模型暂不进入 v0 模型规则库
```

## 常用命令

```bash
python3 scripts/model_rules/validate_model_rules.py
python3 scripts/model_rules/validate_model_rules.py --patch model_rules/patches/example.model-rule.patch.yaml
python3 scripts/model_rules/apply_model_rule_patch.py model_rules/patches/example.model-rule.patch.yaml
python3 scripts/model_rules/search_model_rules.py --topic 一次函数
python3 scripts/model_rules/search_model_rules.py --output-type 'CandidateSet<Point2D>'
```

## Handoff

完成后向下游交付：

```text
当前阶段：模型规则入库
结构分析：[path]
patch：[path]
状态：applied / needs_review / rejected
relation_ids：[...]
下一步：math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 可并行消费 canonical relations
```
