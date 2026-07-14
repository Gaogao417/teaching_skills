# 30-Item Generation Contract

## 先做覆盖表

`coverage-plan.yaml` 至少记录：

```yaml
topic: 平行线对应边比例
source_explanation: ...
target_count: 30
slots:
  - id: Q001
    difficulty: foundation
    training_action: 从平行关系写出正确比例式
    question_type: fillin
    variation_dimension: changed_numbers
    diagram_requirement: prompt_only
    number_selection:
      database_id: question-bank-training-numbers
      family_id: rational_multiple_pairs
      entry_id: rational-3-over-4-x-2
```

先确认 30 个 slot 不重复，再生成单题包。不要边写边临时凑满数量。

`number_selection` 仅在题位使用共享数值库时填写。它必须来自
`select_training_numbers.py` 的未禁用结果；一个题位选定后，教师题、学生题和图形中的数字都必须保持一致。

## 默认分层

- `foundation` 10 题：识别入口、直接应用、单一关系。
- `standard` 12 题：换问法、换表示、缺一步中间量、常见包装。
- `challenge` 8 题：部分隐藏、反向构造、两步链条或辨析非例。

若 explanation 明确不支持挑战层，允许调整分布，但要在 coverage plan 写理由，不能引入 explanation 之外的新模型冒充同专题题。

## 去重规则

两题若只替换数字、点名或图形朝向，而解题入口、关系链、所求量和错误诱因都相同，只算同一题位的弱变体。30 题中同一弱变体最多出现 2 次。

每题至少明确一个主变化维度：

- `changed_numbers`
- `changed_question`
- `changed_representation`
- `packaged_condition`
- `partially_hidden`
- `reverse_construct`
- `non_example_discrimination`

相邻题只提高一个主维度。不要同时隐藏结构并大幅增加计算。

## 数学质量

- 先独立求解并验算，再写入教师版。
- 答案应闭合；存在性题必须列全候选并筛选。
- 数值保持适合学生手算，除非 explanation 明确训练复杂计算。
- 题干不得泄露 `source_relations`、难度标签或教师意图。
- 教师版可保留 `teaching`，但抽题不依赖该字段重新生成题目。

## 单题包

- 每个 teacher plan 只有一个 practice 题 block，id 等于 `Qxxx`。
- 题干、答案、解析放在同一个教师题块中。
- 学生版由 resolved 教师版派生，禁止再次改写题干。
- 无图题写 `diagram_requirement: none`；不要为了字段齐全造装饰图。
