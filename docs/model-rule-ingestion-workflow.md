# 模型规则入库与轻量类型系统工作流

本文档固定当前 homework pipeline 中“结构分析 -> relation 规范化/入库 -> explanation 与 assignment 并行生成”的设计约定。

目标不是建立重型 Pydantic 数学类型系统，而是建立一套可检索、可组合、可扩充的轻量语义类型与 relation 入库流程。它服务于出题规则复用：例如“铅垂线面积反求点”输出点集，能够继续接到“平行四边形三点求第四点”这类模型。

当前优先范围：一次函数及一次函数应用。几何证明模型暂缓。

## 1. 核心判断

AI 已经能可靠完成多数初中数学解题，因此类型系统的主要价值不是“让 AI 会算”，而是：

- 让模型之间有稳定接口，便于检索和组合。
- 让 structural analysis 产出的出题规则能被数据库复用。
- 让 explanation / assignment generation 能按输入/输出类型搜索上下游模型。
- 让约束显式化，避免组合出退化、不唯一或题意混乱的问题。

因此系统需要的是：

```text
Type Registry + typed ports + single-direction relations + constraints
```

而不是：

```text
全学科强类型系统 + 复杂数学对象验证 + 重型 Pydantic schema
```

## 2. 三个层次

### 2.1 Type Registry

Type Registry 是活的语义词表。它负责把不同结构分析中的自然语言说法归一到 canonical type。

示例：

```yaml
types:
  Point2D:
    aliases: ["点", "坐标点", "点坐标", "动点", "待求点", "候选点"]
  CandidateSet<Point2D>:
    aliases: ["候选点集", "多解点", "满足条件的点", "所有可能点"]
    can_feed:
      - Point2D
    requires: ["selector_or_branching"]
  LinearFunction:
    aliases: ["一次函数", "一次函数解析式", "y=kx+b", "非竖直直线"]
    can_feed:
      - Line2D
    constraints: ["non_vertical"]
  Area:
    aliases: ["面积", "三角形面积"]
  IntervalSet:
    aliases: ["解集", "区间", "自变量取值范围"]
  Constraint:
    aliases: ["约束", "筛选条件", "位置条件", "题设条件"]
```

Registry 不是一次性写完的。每次模型入库时，structural analysis 可以提出 alias patch 或 new type candidate。

### 2.2 Model Family

Model family 是教学上的题型家族，例如：

- 铅垂线法面积
- 一次函数图像与一元一次不等式
- 两点确定一次函数
- 平行四边形固定顺序求第四点

Model family 可以保存自然语言解释、典型例题、非例、变式原则。但它不是数据库检索和组合的最小单位。

### 2.3 Relation

Relation 是入库和检索的核心单位。每条 relation 都是单箭头：

```text
given propositions + constraints -> derive propositions
```

同一个 model family 可以有多条 relation。例如“铅垂线法面积”既可以正向求面积，也可以反向由面积求点。

## 3. 正确入库流程

模型入库不要求结构分析阶段直接写成 DSL。正确流程是：

```text
1. structural analysis 先写 intuitive model draft
2. 从 intuitive givens / derives 中抽出 propositions
3. 总结 constraints
4. 生成 single-direction relations
5. 对 relation ports 做 Type Registry 对齐
6. 生成 type_registry_patch（如需补 aliases 或候选新类型）
7. 校验 relation 是否可检索、可组合
8. 入库 canonical relations
```

重要原则：

- 模型先自然描述，再类型对齐。
- 不能让每份结构分析自由发明类型名。
- 未知类型不能静默入库；只能作为 new type candidate 进入审核。
- 最终 explanation / assignment generation 读取 canonical relations，而不是读取原始散文描述。

## 4. Structural Analysis 输出扩展

未来 `01-structure-analysis.md` 可以增加一个“模型规则入库草案”段落。

建议结构：

```yaml
model_rule_draft:
  model_family_id: vertical_line_area
  name: 铅垂线法面积
  intuitive_given:
    - 底边两端点 A,B
    - 第三点 P 或 P 所在一次函数轨迹
    - 目标面积 S
  intuitive_derive:
    - 三角形面积
    - 满足面积条件的候选点
  type_registry_patch:
    aliases_to_add:
      - type_id: Point2D
        aliases: ["第三点", "动点P"]
      - type_id: LinearFunction
        aliases: ["P所在直线", "动点轨迹"]
    new_type_candidates: []
```

这个 draft 不是最终入库对象。入库器要继续把它整理成 propositions、constraints 和 relations。

## 5. Relation 入库格式

Canonical relation 建议格式：

```yaml
relation_id: vertical_area_inverse_on_linear_locus
model_family_id: vertical_line_area
name: 铅垂线法面积反求一次函数轨迹上的动点
topic_tags: ["一次函数", "坐标面积", "铅垂线法"]

propositions:
  P1:
    statement: A,B 是三角形底边两端点
    ports:
      A: Point2D
      B: Point2D
  P2:
    statement: P 在一次函数轨迹上
    ports:
      moving_locus: LinearFunction
  P3:
    statement: 三角形 ABP 的面积为 S
    ports:
      target_area: Area
  P4:
    statement: 满足面积条件的候选点集
    ports:
      candidate_points: CandidateSet<Point2D>

constraints:
  C1: A,B 横坐标不同，便于使用铅垂线法
  C2: moving_locus 是非竖直一次函数
  C3: 面积 S 非负
  C4: 若下游需要单个 Point2D，必须提供筛选条件或允许分支

relation:
  given: [P1, P2, P3]
  derive: [P4]
  constraints: [C1, C2, C3, C4]

ports:
  inputs:
    A: Point2D
    B: Point2D
    moving_locus: LinearFunction
    target_area: Area
    filters: Constraint[]
  outputs:
    candidate_points: CandidateSet<Point2D>

generation_notes:
  - 先反向构造干净点 P，再计算面积，保证答案干净。
  - 绝对值方程可能产生 0/1/2 个候选。
  - 不使用点到直线距离公式。

non_examples:
  - 没有给 P 的轨迹却要求由面积唯一确定 P。
  - 横向宽度为 0 的底边配置。
```

## 6. 一次函数 v0 类型范围

一次函数及应用先只需要小型类型集合：

```text
Point2D
CandidateSet<Point2D>
LinearFunction
Line2D
Area
IntervalSet
Equation
Constraint
PositionConstraint
QuadrilateralConstraint
```

基础兼容关系：

```text
LinearFunction -> Line2D
CandidateSet<Point2D> -> Point2D，需要 selector/filter/branching
Point2D + Point2D -> LinearFunction，需要 x1 != x2
```

这些兼容关系用于检索和组合，不要求实现为强类型运行时。

## 7. 一次函数 v0 关系清单

第一批建议入库的 relations：

```yaml
- relation_id: two_points_determine_linear_function
  given: [P: Point2D, Q: Point2D]
  derive: [L: LinearFunction]
  constraints: [x_P != x_Q]

- relation_id: point_on_linear_function_forward
  given: [L: LinearFunction, x_value]
  derive: [P: Point2D]

- relation_id: linear_function_intercepts
  given: [L: LinearFunction]
  derive: [x_intercept: Point2D, y_intercept: Point2D]
  constraints: [k != 0 for x_intercept]

- relation_id: intersection_of_two_linear_functions
  given: [L1: LinearFunction, L2: LinearFunction]
  derive: [P: Point2D]
  constraints: [k1 != k2]

- relation_id: linear_inequality_by_graph
  given: [L1: LinearFunction, L2: LinearFunction, comparison, intersection_point]
  derive: [solution: IntervalSet]
  constraints: [endpoint_inclusion_depends_on_comparison]

- relation_id: vertical_area_forward
  given: [A: Point2D, B: Point2D, P: Point2D]
  derive: [area: Area]
  constraints: [x_A != x_B]

- relation_id: vertical_area_inverse_on_linear_locus
  given: [A: Point2D, B: Point2D, moving_locus: LinearFunction, target_area: Area]
  derive: [candidate_points: CandidateSet<Point2D>]
  constraints: [x_A != x_B, non_vertical_locus, selector_or_branching_if_single_point_needed]

- relation_id: parallelogram_fourth_point_fixed_order
  given: [A: Point2D, B: Point2D, C: Point2D, condition: QuadrilateralConstraint]
  derive: [D: Point2D]
  constraints: [condition == "parallelogram_ABCD", A_and_C_are_diagonal_vertices]

- relation_id: parallelogram_fourth_point_unordered
  given: [A: Point2D, B: Point2D, C: Point2D, condition: QuadrilateralConstraint]
  derive: [candidate_points: CandidateSet<Point2D>]
  constraints: [condition == "four_points_form_parallelogram", exclude_degenerate_duplicates]
```

## 8. 组合示例

目标：生成“面积条件先求点，再用该点求平行四边形第四点”的题。

检索链：

```text
vertical_area_inverse_on_linear_locus
  outputs CandidateSet<Point2D>

parallelogram_fourth_point_fixed_order
  inputs Point2D
```

组合器发现：

```text
CandidateSet<Point2D> can_feed Point2D
但需要 selector/filter/branching
```

于是题目必须满足其中一种：

- 给定“取第一象限的点”之类的筛选条件。
- 允许两个候选点分别产生两个 D。
- assignment 设计成分支讨论题。

生成后必须自检：

- 候选点是否在 moving_locus 上。
- 候选点代回面积是否等于 target_area。
- D 是否满足平行四边形固定顺序关系。
- 是否存在点重合、面积为 0、重复答案等退化。

## 9. Explanation / Assignment Generation 的检索方式

生成讲解和作业时不直接把散文结构分析当作唯一依据，而是读取结构分析中的教学事实，并查 relation 索引获得可复用规则。

两类下游并行消费同一套 canonical relations：

- explanation generation：主要使用结构分析中的标准解、卡点、讲题任务包，同时读取 relation 的 propositions / constraints，保证讲解语言和模型库一致。
- assignment generation：主要使用 relation 的 input/output types、constraints、generation_notes 和 non_examples，做变式、组合与自检。

建议索引：

```text
by_output_type:
  Point2D -> [...]
  CandidateSet<Point2D> -> [...]
  Area -> [...]

by_input_type:
  Point2D -> [...]
  LinearFunction -> [...]
  Area -> [...]

by_topic:
  一次函数 -> [...]
  坐标面积 -> [...]

by_relation_signature:
  Area -> CandidateSet<Point2D>
  Point2D + Point2D -> LinearFunction
  Point2D + Point2D + Point2D -> Point2D

by_constraint:
  non_vertical
  fixed_order
  unordered
  selector_or_branching
```

assignment generator 可以按教学目标检索：

```text
目标：一次函数面积 + 坐标存在性
搜索：Area -> CandidateSet<Point2D> -> Point2D
匹配：vertical_area_inverse_on_linear_locus -> parallelogram_fourth_point_fixed_order
```

## 10. 入库闸门

relation 入库前必须通过以下检查：

- 每个 input/output port 都引用 canonical type。
- 新 alias 必须写入 type_registry_patch，不能只出现在散文里。
- 未知 type 必须进入 new_type_candidates，不能直接入库。
- relation 必须是单箭头。
- constraints 里必须说明唯一性、多解、退化和筛选条件。
- 如果输出是 CandidateSet<T>，必须说明下游接 T 时的 selector/filter/branching 策略。
- 每条 relation 至少有一个典型例和一个 non-example。

## 11. 与 Homework Pipeline 的关系

目标工作流：

```text
math-structure-analysis
  -> 生成 01-structure-analysis.md
  -> 附带 model_rule_draft

model-rule-ingestion
  -> 对齐 Type Registry
  -> 生成 propositions / constraints / relations
  -> 入库 canonical relations
  -> 更新 aliases 或提出 new type candidates

并行下游：

math-student-explanation-latex-data
  -> 读取结构分析中的数学事实、标准路径、卡点和讲题任务包
  -> 读取 canonical relation 的 propositions / constraints
  -> 生成 02-student-explanation.assignment.yaml

math-adaptive-practice-latex-data
  -> 根据学生、主题、卡点和目标检索 canonical relations
  -> 读取 generation_notes / constraints / non_examples
  -> 生成 03-adaptive-practice.assignment.yaml
  -> 自检 relation 是否被保留
```

一句话原则：

```text
Structural analysis 负责发现规则；
model-rule-ingestion 负责类型归一和 relation 入库；
explanation 和 assignment generation 并行消费 canonical relations。
```
