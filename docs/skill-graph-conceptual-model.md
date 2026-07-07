# 技能图谱概念说明

本文档固定 `teaching_skills` 中“技能图谱”和 “Skill Trace” 的语义。它服务于后续
`skill-trace-ingestion` MVP：Codex 可以先为一道题生成可审阅的动作链，用户审阅后再入库，并把这条动作链作为讲解、练习和提示生成的上游事实源。

## 1. 核心泛化

比例题里常见的教学动作是：

```text
要求什么？
它和什么已知量作比？
```

一次函数、解析几何和应用题中，需要把这句话泛化成：

```text
要求什么对象？
它由哪些已知关系约束？
这些关系能转化成什么表达式或方程？
```

因此底层动作链不是“作比”，而是：

```text
目标量定位
-> 找到目标量所在的关系
-> 选择最有用的关系
-> 把关系转化成数学表达
-> 计算并按题目范围筛选
```

这个复合策略可以命名为：

```yaml
abstract_strategy:
  id: target_first_relation_selection
  name: 目标驱动选关系
  description: 先看要求量，再找它所在的关系链，并选择最省未知量的表达方式。
```

比例题中的表现：

```text
要求 ED
-> 找 ED 属于哪组对应线段
-> 找到 AE:ED = AB:BC
-> 用份数或比例计算
```

一次函数中的表现：

```text
要求 P 的坐标
-> 找 P 被哪些关系约束
-> 点在直线上可参数化，面积条件可列方程
-> 解方程并按范围筛选
```

## 2. 四层动作坐标

技能图谱中的 `cognitive_layer` 不是知识点层级，也不是把标准解答逐句拆开的
step trace。它记录的是学生完成本题所需要的可训练 skill：如果这个能力缺失，
能否据此设计针对性练习、提示或诊断。

判定时先问这个动作在做什么：

| 层级 | 判定问题 | 只允许表达的动作 |
|---|---|---|
| `L0_structure` | 题目属于什么结构模型，目标量和已知量处在什么关系中？ | 识别题型结构、目标-已知关系、整体部分、对应关系、范围关系，不做路径选择。 |
| `L1_encoding` | 已识别的关系如何写成数学表达？ | 写比例、方程、参数式、份数关系、面积关系、范围不等式，不做数值计算。 |
| `L2_execution` | 表达式推出的数值或结果是多少？ | 代入、化简、计算、解方程、求数值、筛选候选。 |
| `L3_strategy` | 为什么先做这个、用哪个关系或表示方式？ | 选择参照量、关系链、方法顺序、是否用份数法、是否避免设元。 |

### L0_structure：结构识别

识别题目中的结构模型和关系网络，还不决定解法、不列式、不计算。不要把
“读出一个字母或数值”单独当作核心 skill；核心在于学生是否看出这些对象为什么
构成一个可用的数学结构。

比例题示例：

- 识别本题是比例/份数问题，需要建立目标量与已知量的比例关系。
- 识别要求量 `BC` 和已知量 `AC=40` 处在同一个整体部分结构中。
- `B` 在 `A,C` 之间，`AC` 是由 `AB` 和 `BC` 组成的整体。
- `AB:AC=3:8` 是 `AB` 与整体 `AC` 的比，不是 `AB:BC`。
- 两个三角形共高，或两段是对应线段。

一次函数示例：

- 目标是点坐标、解析式、参数还是面积。
- 点 `P` 在直线 `y = kx + b` 上。
- 两条直线有交点。
- 某点在 x 轴或 y 轴上。
- 三角形的底在 x 轴上，高可用纵坐标表示。

### L1_encoding：条件转化

把 L0 已经识别出的关系翻译成数学表达，不计算具体结果。

比例题示例：

- 由 `AB:AC=3:8` 写出 `AB份数:AC份数=3:8`。
- 由整体部分关系写出 `BC份数 = AC份数 - AB份数`。
- 写出 `BC = AC * (BC份数)/(AC份数)`。
- 共高三角形面积比转成底边比。

一次函数示例：

- 点 `P` 在 `y = 2x + 1` 上，设 `P(t, 2t + 1)`。
- 两条直线交点满足 `k1x + b1 = k2x + b2`。
- 点到 x 轴距离转为 `|y_P|`。
- 面积条件转为 `S = 1/2 * 底 * 高`。

### L2_execution：运算执行

对已经写出的表达式做代入、化简、求值或筛选。这里不再判断该用哪条关系。

典型动作：

- 计算 `8 - 3 = 5`。
- 代入 `AC=40`，写成 `40 * 5 / 8`。
- 计算 `40 * 5 / 8 = 25`。
- 解一次方程或方程组。
- 化简比例或代数式。
- 解绝对值方程。
- 检查并删除不满足范围的候选解。

### L3_strategy：策略控制

决定先看什么、先求什么、选哪个参照量、选哪个关系链、用什么表示方式。

典型动作：

- 决定从目标量出发找它所在的关系链。
- 决定用已知整体 `AC` 作为参照量来表示 `BC`。
- 求点坐标时检查需要几个独立约束。
- 点在直线上时优先设 `P(t, kt+b)`，避免先设两个无约束未知量。
- 看到总量和比例时优先用份数法，不急着设元。
- 解出候选后回到图形范围筛选。

复合动作必须拆开。“先看要求什么，要求的东西和什么已知量作比”不是一个
trace step，也不是要把“读出要求量”和“读出已知量”机械拆成两个核心节点。它
应先落到可训练 skill，再记录本题表现：

```text
L0: name=比例结构识别，student_action_norm=识别本题要用目标量与已知量的份数比求线段。
L3: name=目标参照量建模，student_action_norm=决定用已知整体 AC=40 作为参照量来表示 BC。
L0: name=整体部分结构识别，student_action_norm=看出 AC 是 AB 和 BC 合成的整体。
L1: name=比例对象校准，student_action_norm=把 AB:AC=3:8 理解为 AB 与 AC 的份数关系。
L1: name=目标份数表达，student_action_norm=用整体份数减已知部分份数表达 BC 的份数。
L1: name=目标参照比例表达，student_action_norm=写出 BC = AC * (BC份数)/(AC份数)。
L2: name=比例值计算，student_action_norm=代入并计算 BC=25。
```

## 3. 复用层级

`reuse_level` 表示一个动作节点的复用范围。MVP 中每个 trace step 必须同时有
`cognitive_layer` 和 `reuse_level`。

| reuse_level | 图谱层 | 含义 | 示例 |
|---|---|---|---|
| `generic_action` | 抽象策略层 | 跨专题复用的动作 | 目标驱动选关系、约束数量检查、用结构减少未知量 |
| `domain_action` | 领域关系层 | 某个数学领域内复用的转化 | 点在线上参数化、对应线段转比例、共高面积比转底边比 |
| `pattern_step` | 题型路径层 | 某类题中的稳定步骤 | 直线上动点 + 面积条件求坐标的路径步骤 |
| `instance_step` | 题目实例层 | 只服务当前题目的具体对应 | 本题 ED 对应 BC、本题 AB=4 是底 |

推荐的图谱结构是：

```text
抽象策略层：跨专题复用
  -> 领域关系层：同领域复用
  -> 题型路径层：组织练习和诊断
  -> 题目实例层：具体题目证据
```

复用性来自分层引用，而不是把每一道题都做成一张独立大图。

## 4. Skill Trace 与 Skill Graph 的边界

Skill Graph 是可复用动作网络。Skill Trace 是某一道题被审阅后的标准动作链。

```text
题目实例
-> 引用题型路径
-> 题型路径引用领域关系节点
-> 领域关系节点引用抽象策略节点
```

MVP 只要求稳定保存 problem-level reviewed trace，不要求自动合并 canonical skill node。也就是说：

- Codex 可以生成 `SkillTraceDraft`。
- 用户必须在 review UI 中审阅后才入库。
- reviewed trace 可以引用或暗含图谱节点，但不能自动改写 canonical 图谱。
- 后续讲解和练习先读取 reviewed trace，再逐步发展 canonical node 合并能力。

## 5. 节点设计规则

每个 trace step 只能表达一个可训练 skill 在本题中的一次表现。不要把
Skill Trace 写成标准解答的逐行步骤；如果某一步只是普通读数、代入或小算术，
通常应作为支撑细节，而不是核心 skill。

`step.name` 不是本题动作描述，而是可复用的技能节点名。具体到本题的对象、
数值和动作细节应写在 `student_action_norm`。

命名规则：

- `name` 用抽象、稳定、可复用的短语，例如“比例结构识别”“目标参照量建模”“整体部分结构识别”“目标参照比例表达”。
- `name` 不写本题字母、数值或完整动作，例如不要写“定位要求量 BC”“填入 BC 和 AC 份数”。
- `student_action_norm` 才写本题动作，例如“先确定题目要求的是 BC”。
- `reuse_level=instance_step` 的节点也应尽量保留可复用名称；实例证据放在 `student_action_norm` 和 `common_errors`。

`is_core_step` 表示这个 skill 是否是当前题型最值得诊断和训练的核心能力：

- `true`：缺失后会导致这类题不会做、做繁或迁移失败；后续针对性练习应围绕它设计。
- `false`：只是本题的辅助读数、普通代入、简单计算、格式收尾或可放入提示的细节。
- 不要把 `is_core_step` 理解成“是否在标准解答主路径上”，否则会把所有步骤都标成 core。

不要把一个 step 写成：

```text
找对应并计算结果
```

应拆成：

```text
L0: name=对应关系识别，student_action_norm=找到 ED 对应 BC。
L1: name=对应比例表达，student_action_norm=写出 AE:ED = AB:BC。
L2: name=比例值计算，student_action_norm=计算 ED 的长度。
```

节点抽象度要适中：

- 策略节点尽量抽象，便于跨专题复用。
- 条件转化节点保持领域化，便于同类题检索。
- 题型路径节点负责组合，不作为最小原子。
- 实例节点只保存证据，不直接升格为 canonical 节点。
- 不要用 `reuse_level` 修补 `cognitive_layer` 的模糊；前者只表示复用范围，后者只表示动作类型。

一个高复用抽象节点示例：

```yaml
abstract_strategy:
  id: reduce_unknowns_by_structure
  name: 用结构关系减少未知量
  description: 不直接设多个未知量，而是利用已知结构把目标量表示成一个参数或若干份。
```

它在不同领域中的表现：

```text
比例题：AE:ED = 2:3 -> 设 AE=2份，ED=3份
一次函数：P 在 y=2x+1 上 -> 设 P(t, 2t+1)
几何面积：共高三角形面积比等于底边比 -> 不求高，只看底边份数
```

## 6. 同类习题的相关性

不要只按表面题型判断相关性。

近相关：共享领域转化节点。

```text
点在线上代入
直线动点参数化
面积条件转坐标方程
```

中相关：共享抽象策略节点。

```text
先看目标量
再找约束关系
避免无目的设元
```

远相关：只共享执行技能。

```text
解一次方程
化简代数式
```

教学生成时，近相关和中相关更适合组织变式与即时提示；远相关只能说明计算基础有关，不应直接当作同类思路训练。

## 7. 一次函数示例路径

题目：

```text
点 P 在直线 y = 2x + 1 上，A(0,0)，B(4,0)。若 S_ABP = 10，求 P 的坐标。
```

动作链：

```text
L3: 要求 P 的坐标，先判断 P 需要几个约束。
L0: P 在直线 y = 2x + 1 上。
L1: 设 P(t, 2t + 1)。
L0: AB 在 x 轴上，P 到 AB 的高是 |y_P|。
L1: 写出 1/2 * 4 * |2t + 1| = 10。
L2: 解绝对值方程。
L3: 根据象限、线段、图形范围筛选。
```

对应引用：

```yaml
problem_id: linear_area_point_001
surface_topic: 一次函数与面积
pattern_id: linear_point_by_line_and_area

uses:
  abstract_strategy:
    - target_first_relation_selection
    - constraint_count_check
    - reduce_unknowns_by_structure

  domain_relation:
    - point_on_line_to_param
    - area_to_coordinate_equation
    - range_to_inequality

  execution:
    - solve_absolute_value_equation
    - filter_candidate_solutions
```

## 8. 对下游生成的约束

reviewed trace 是后续 explanation / assignment 的上游事实源。

下游生成应遵守：

- 学生讲解先给动作规范，再给算式。
- 练习题围绕 core steps 设计，不只换数字。
- 学生版 PDF 不暴露内部字段名，例如 `relation_chain`、`CandidateSet`、`reuse_level`。
- 可以在教师侧保留 trace step、target step 和诊断证据。
- 当 reviewed trace 与自由分析冲突时，以 reviewed trace 为准，必要时回到用户审阅。
