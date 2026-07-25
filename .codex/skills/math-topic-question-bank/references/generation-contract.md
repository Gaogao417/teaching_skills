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
- 题干执行“必要对象/情境 + 已知条件 + 任务目标”的最小表达。删除与训练目标无关的背景包装、重复条件、教学提示、指定方法、过程清单、验算要求和作答表演；解题动作写入教师解析。
- 有题图时，不在题干复述图中已经清楚呈现的点序、共线关系或内外位置；题干只补充图上无法可靠表达的数学条件。
- 语言和记号必须匹配学段。初中几何题干禁止用 `\in`、`\cap` 代替“点在线段上”“两线交于点”等教材表达。
- 多任务题逐项检查：每一项都必须是本题训练目标。辨错、证明、分类本身是目标时可以保留；普通计算题只问最终所求量。
- 题库学生版不带 `hints`。单张 prompt 图默认不加 caption；多图必须区分时只写中性图名，不在图注中提示方法。
- 相似三角形求边题中，普通题直接写“求某边的长”；提高题给出三条已知边，写“判断还可以求出哪条边，并求出它的长度”。相似判定、对应边、比例式和验算放入解析。

## 单题包

- 每个 teacher plan 只有一个 practice 题 block，id 等于 `Qxxx`。
- 题干、答案、解析放在同一个教师题块中。
- 学生版由 resolved 教师版派生，禁止再次改写题干。
- 无图题写 `diagram_requirement: none`；不要为了字段齐全造装饰图。
