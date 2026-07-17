# Wolfram GeometricScene 出题构图参考

本参考用于把数学题的结构化条件写成可求解的 Wolfram `GeometricScene`。权威语法来源为仓库
`GeometricScene-Builder/.opencode/skills` 中的 GeometricScene、约束库和 solve-pattern 文档；本文件按
教学出题场景重新组织，并补充本仓库的一题一图、prompt/solution 复用和 gate 约束。

## 目录

1. [基本原则](#基本原则)
2. [场景骨架与求解](#场景骨架与求解)
3. [点与区域的隶属关系](#点与区域的隶属关系)
4. [直线关系与点序](#直线关系与点序)
5. [长度、比例与分点](#长度比例与分点)
6. [角与角平分线](#角与角平分线)
7. [三角形与特殊点](#三角形与特殊点)
8. [四边形与多边形](#四边形与多边形)
9. [圆](#圆)
10. [相似、全等与面积](#相似全等与面积)
11. [常用辅助线构造](#常用辅助线构造)
12. [防退化与版面约束](#防退化与版面约束)
13. [prompt 与 solution](#prompt-与-solution)
14. [常见错误](#常见错误)
15. [出题场景覆盖清单](#出题场景覆盖清单)

## 基本原则

1. 先表达题目事实，再添加最少量版面约束。
2. 点在直线、线段、射线、圆或区域上，使用 `Element[point, region]`。
3. 不使用 `GeometricAssertion[..., "Collinear"]` 表达共线；把其中一个点写成另两个点所定区域的元素。
4. `GeometricAssertion` 用于平行、垂直、方向、点互异、顺逆时针、凸性等几何性质。
5. 长度、比例、角、周长、面积分别使用 `EuclideanDistance`、量的等式/不等式、`PlanarAngle`、
   `Perimeter`/`TriangleMeasurement`、`Area`。不要把 `AB`、`AC` 当成已经定义的数值变量。
6. 所有出现在约束里的点必须在 `GeometricScene` 第一参数中声明。
7. 固定专题的 scene spec 可由模板程序确定性生成，无需 LLM；仍必须运行 Wolfram 求解、TikZ、gate 和 resolve。
8. 普通综合几何默认使用 **0 个固定坐标**。需要控制朝向时，优先只给一条基准边添加 `"Horizontal"`，
   必要时再加 `"Rightward"`；不要用三个顶点坐标把三角形钉死。
9. 为每个点声明角色：`anchors` 是题设的基础点，但 anchor 不等于固定坐标，默认仍保持符号化；
   `constructed` 是题设构造点，`auxiliary` 是解答新增点。后两类禁止由 Python/LLM 先算坐标再回填。
10. 固定坐标本身就是几何约束。若点的位置已经由边长、角、垂直、平行或隶属关系确定，不得再添加
    坐标等式重复约束；尤其禁止同时固定三角形三个顶点坐标并再写边长、角度条件。

## 场景骨架与求解

只含点：

```wl
scene = GeometricScene[
  {A, B, C, D},
  {
    Element[D, Line[{B, C}]],
    EuclideanDistance[B, D] == EuclideanDistance[D, C]
  }
];
```

含标量参数：

```wl
scene = GeometricScene[
  {{A, B, C, O}, {r}},
  {
    r > 0,
    Element[A, Circle[O, r]],
    Element[B, Circle[O, r]],
    Element[C, Circle[O, r]]
  }
];
```

对应的 `scene_payload` 应同时记录角色，例如：

```json
{
  "point_roles": {
    "anchors": ["A", "B", "C"],
    "constructed": ["D", "E", "P"],
    "auxiliary": ["F"]
  }
}
```

题设中的原始顶点可以列入 `anchors`，但这不授权为它们写坐标。是否固定坐标只看 `scene_code` 中
有没有 `A == {x, y}`；角色名称本身不是坐标约束。例如，已知两边及夹角的三角形应直接由度量
约束确定，只用一条边控制朝向：

```wl
GeometricScene[
  {A, B, C},
  {
    EuclideanDistance[A, B] == 10,
    EuclideanDistance[A, C] == 13,
    PlanarAngle[{B, A, C}] == 30 Degree,
    GeometricAssertion[Line[{A, C}], "Horizontal"],
    GeometricAssertion[Line[{A, C}], "Rightward"],
    GeometricAssertion[{A, C, B}, "Counterclockwise"]
  }
]
```

以下写法错误：三个顶点的坐标已经唯一决定三角形，又重复加入边长和角度约束；任何一处数值或方向
不完全一致都会使场景不可解。

```wl
GeometricScene[
  {A, B, C},
  {
    A == {0, 0}, B == {5 Sqrt[3], 5}, C == {13, 0},
    EuclideanDistance[A, B] == 10,
    EuclideanDistance[A, C] == 13,
    PlanarAngle[{B, A, C}] == 30 Degree
  }
]
```

标量参数不是点，不写入 `points` 或 `point_roles`。运行时允许上述双列表第一参数形式；单独把点列表
多套一层（`GeometricScene[{{A,B,C}}, ...]`）仍是错误。

求解必须使用确定种子和超时，并且只采样一次：

```wl
inst = TimeConstrained[
  BlockRandom[SeedRandom[seed]; RandomInstance[scene]],
  timeout,
  $Failed
];

result = Which[
  inst === $Failed,
    <|"success" -> False, "fail_type" -> "timeout"|>,
  Head[inst] =!= GeometricScene,
    <|"success" -> False, "fail_type" -> "invalid_head"|>,
  True,
    <|
      "success" -> True,
      "fail_type" -> "",
      "parameters" -> inst["Parameters"],
      "algebraic" -> inst["AlgebraicFormulation"]
    |>
];
```

先求解，后渲染；调试时复用同一个 `inst`，不得再次 `RandomInstance`。

## 点与区域的隶属关系

### 在线段、直线、射线上

```wl
Element[D, Line[{B, C}]]          (* D 在线段 BC 上，包含端点 *)
Element[P, InfiniteLine[{A, D}]]  (* P 在直线 AD 上 *)
Element[Q, HalfLine[{A, B}]]      (* Q 在从 A 经 B 的射线上 *)
```

题目写“D 在线段 BC 内”时，排除端点：

```wl
Element[D, Line[{B, C}]]
EuclideanDistance[B, D] > 0
EuclideanDistance[D, C] > 0
```

三点共线时，优先选择能同时表达点序的写法：

```wl
Element[A, Line[{P, C}]]          (* P-A-C，A 位于线段 PC *)
Element[P, InfiniteLine[{A, C}]]  (* 只要求 P、A、C 共线，不限定点序 *)
```

### 在圆、圆盘和多边形区域中

```wl
Element[P, Circle[O, r]]
Element[P, Disk[O, r]]
Element[P, Triangle[{A, B, C}]]
Element[P, Polygon[{A, B, C, D}]]
```

圆周用 `Circle`，圆内部用 `Disk`；不要混用。

### 交点

交点不需要先算坐标，声明它同时属于两个区域：

```wl
Element[P, Line[{A, D}]]
Element[P, Line[{B, E}]]
```

若交点可落在延长线上，改用 `InfiniteLine`：

```wl
Element[P, InfiniteLine[{A, D}]]
Element[P, InfiniteLine[{B, E}]]
```

## 直线关系与点序

### 平行与垂直

```wl
GeometricAssertion[
  {Line[{A, B}], Line[{C, D}]},
  "Parallel"
]

GeometricAssertion[
  {Line[{A, H}], Line[{B, C}]},
  "Perpendicular"
]
```

`Line` 的端点只负责确定方向；若题目说的是整条直线，点的隶属关系仍应单独用 `InfiniteLine` 表达。

### 方向与顺逆时针

这些是版面约束，不是题目结论：

```wl
GeometricAssertion[Line[{B, C}], "Horizontal"]
GeometricAssertion[Line[{B, C}], "Rightward"]
GeometricAssertion[{B, C, A}, "Counterclockwise"]
GeometricAssertion[{A, B, C}, "Distinct"]
```

只在方向不会暗示额外数学性质时使用。

### 点序

`Element[A, Line[{P, C}]]` 只保证 A 在线段 PC 上。若必须严格区分 `P-A-C`，再排除端点；若题干给出
分点比，则比例约束本身通常已经排除端点。

```wl
Element[A, Line[{P, C}]]
EuclideanDistance[P, A] > 0
EuclideanDistance[A, C] > 0
```

## 长度比例与分点

### 固定长度与等长

```wl
EuclideanDistance[A, B] == 5
EuclideanDistance[A, B] == EuclideanDistance[A, C]
```

### 线段比例

`AB:AC = m:n`：

```wl
n EuclideanDistance[A, B] == m EuclideanDistance[A, C]
```

不要用浮点近似代替整数交叉相乘。

### 内分点

`BD:DC = m:n`：

```wl
Element[D, Line[{B, C}]]
n EuclideanDistance[B, D] == m EuclideanDistance[D, C]
```

中点优先使用构造函数：

```wl
M == Midpoint[{B, C}]
```

也可显式写成：

```wl
Element[M, Line[{B, C}]]
EuclideanDistance[B, M] == EuclideanDistance[M, C]
```

### 外分点与延长线

外分点必须使用 `InfiniteLine`，再用距离比例和必要的方向约束排除错误分支：

```wl
Element[D, InfiniteLine[{B, C}]]
n EuclideanDistance[B, D] == m EuclideanDistance[D, C]
```

若题图必须固定在 C 的外侧，可额外采用弱坐标方向/点序约束；不要把外分误写成 `Line[{B,C}]`。

## 角与角平分线

`PlanarAngle[{A, B, C}]` 的顶点是中间的 B。

### 固定角、等角、直角

```wl
PlanarAngle[{A, B, C}] == 60 Degree
PlanarAngle[{A, B, C}] == PlanarAngle[{D, E, F}]
PlanarAngle[{A, B, C}] == 90 Degree
```

直角也可用线关系表达：

```wl
GeometricAssertion[
  {Line[{B, A}], Line[{B, C}]},
  "Perpendicular"
]
```

### 角平分线

构造式：

```wl
Element[D, AngleBisector[{A, B, C}]]
```

或用等角和 D 的隶属关系显式表达：

```wl
Element[D, Line[{A, C}]]
PlanarAngle[{A, B, D}] == PlanarAngle[{D, B, C}]
```

后一种写法更方便控制 D 落在对边线段上。

### 角度防退化

```wl
TriangleMeasurement[{A, B, C}, {"InteriorAngle", B}] > 10 Degree
```

只把它作为版面质量约束；若题目本身给定角度，不再叠加强约束。

## 三角形与特殊点

### 等腰、等边、直角三角形

```wl
EuclideanDistance[A, B] == EuclideanDistance[A, C]

EuclideanDistance[A, B] == EuclideanDistance[B, C]
EuclideanDistance[B, C] == EuclideanDistance[C, A]

GeometricAssertion[
  {Line[{A, B}], Line[{A, C}]},
  "Perpendicular"
]
```

### 中线、高、垂直平分线

```wl
M == Midpoint[{B, C}]
Element[M, Line[{B, C}]]

H == TriangleCenter[{A, B, C}, {"Foot", A}]

Element[O, PerpendicularBisector[{A, B}]]
```

高也可显式表达，便于控制垂足在边上还是延长线上：

```wl
Element[H, InfiniteLine[{B, C}]]
GeometricAssertion[
  {Line[{A, H}], Line[{B, C}]},
  "Perpendicular"
]
```

### 三角形中心

```wl
G == TriangleCenter[{A, B, C}, "Centroid"]
I == TriangleCenter[{A, B, C}, "Incenter"]
O == TriangleCenter[{A, B, C}, "Circumcenter"]
H == TriangleCenter[{A, B, C}, "Orthocenter"]
N == TriangleCenter[{A, B, C}, "NinePointCenter"]
```

不要写 `(A+B+C)/3`；GeometricScene 中的符号点不是坐标向量。

### 三角形测量

```wl
TriangleMeasurement[Triangle[{A, B, C}], "Area"]
TriangleMeasurement[Triangle[{A, B, C}], "Perimeter"]
TriangleMeasurement[Triangle[{A, B, C}], "Inradius"]
TriangleMeasurement[Triangle[{A, B, C}], "Circumradius"]
TriangleMeasurement[Triangle[{A, B, C}], {"Height", A}]
```

参数必须是三角形或恰好三个点，不能把任意长度的点列表传入。

## 四边形与多边形

### 平行四边形

```wl
GeometricAssertion[{Line[{A, B}], Line[{C, D}]}, "Parallel"]
GeometricAssertion[{Line[{B, C}], Line[{D, A}]}, "Parallel"]
GeometricAssertion[{A, B, C, D}, "Distinct"]
GeometricAssertion[{A, B, C, D}, "Counterclockwise"]
```

### 矩形、菱形、正方形、梯形

矩形可直接使用多边形断言：

```wl
GeometricAssertion[Polygon[{A, B, C, D}], "Rectangle"]
```

需要精确控制教学条件时，建议拆开：

```wl
GeometricAssertion[{Line[{A, B}], Line[{C, D}]}, "Parallel"]
GeometricAssertion[{Line[{B, C}], Line[{D, A}]}, "Parallel"]
GeometricAssertion[{Line[{A, B}], Line[{B, C}]}, "Perpendicular"]
```

菱形用四边等长；正方形在菱形上增加一个直角。梯形只写题干给定的那一组对边平行，不额外暗示另一组。

### 凸性与正多边形

```wl
GeometricAssertion[Polygon[{A, B, C, D}], "Convex"]
GeometricAssertion[Polygon[{A, B, C, D}], "Regular"]
```

只有题干明确给出时才使用 `Regular`、`Rectangle`、`Equilateral` 等强性质。

## 圆

### 圆心、半径、圆周点

```wl
GeometricScene[
  {{O, A, B, C}, {r}},
  {
    r > 0,
    Element[A, Circle[O, r]],
    Element[B, Circle[O, r]],
    Element[C, Circle[O, r]]
  }
]
```

也可用三点定圆：

```wl
Element[D, CircleThrough[{A, B, C}]]
```

### 共圆

四点共圆优先写成第四点属于前三点的外接圆：

```wl
Element[D, CircleThrough[{A, B, C}]]
```

避免只写自然语言 `A,B,C,D cyclic`。

### 直径、弦、圆心角

```wl
O == Midpoint[{A, B}]
Element[A, Circle[O, r]]
Element[B, Circle[O, r]]

Element[A, Circle[O, r]]
Element[B, Circle[O, r]]             (* AB 为弦 *)

PlanarAngle[{A, O, B}] == 80 Degree  (* 圆心角 *)
```

### 切线

用切点在圆上、切点在线上、半径垂直切线三项表达：

```wl
Element[T, Circle[O, r]]
Element[T, InfiniteLine[{A, B}]]
GeometricAssertion[
  {Line[{O, T}], Line[{A, B}]},
  "Perpendicular"
]
```

### 两圆相交

```wl
Element[P, Circle[O1, r1]]
Element[P, Circle[O2, r2]]
```

若需要两个交点，分别声明 P、Q 并添加 `Distinct`。

## 相似全等与面积

### 相似三角形

题干直接给出两个三角形相似时，使用原生 `"Similar"` 断言；顶点顺序表达对应关系：

```wl
GeometricAssertion[
  {Triangle[{A, B, C}], Triangle[{D, E, F}]},
  "Similar"
]
```

不要把一个明确的相似条件重新展开成 AA、SSS 比例或其他证明条件。只有题干本身给的是角相等或边长比例时，才逐条翻译那些原始条件。

以下三参数形式错误：

```wl
GeometricAssertion[Triangle[{A, B, C}], "Similar", Triangle[{D, E, F}]]
GeometricAssertion[Triangle[{A, B, C}], Triangle[{D, E, F}], "Similar"]
```

### 全等三角形

题干直接给出两个三角形全等时，使用原生 `"Congruent"` 断言；顶点顺序表达对应关系：

```wl
GeometricAssertion[
  {Triangle[{A, B, C}], Triangle[{D, E, F}]},
  "Congruent"
]
```

不要添加 `VertexMap`，也不要把一个明确的全等条件展开成 SSS/SAS/ASA 等证明条件。题干若只给出三组边相等，则仍按三组距离等式逐条翻译，因为那才是原始条件。

### 面积、周长与面积比

```wl
Area[Triangle[{A, B, C}]] == 24
Perimeter[Triangle[{A, B, C}]] == 18
n Area[Triangle[{A, B, C}]] == m Area[Triangle[{D, E, F}]]
```

面积比同样优先整数交叉相乘，避免不必要的浮点数。

## 常用辅助线构造

### 过一点作平行线并交另一条边

```wl
Element[F, InfiniteLine[{A, D}]]
GeometricAssertion[
  {Line[{E, F}], Line[{B, C}]},
  "Parallel"
]
```

如果 F 必须在线段 AD 上，把 `InfiniteLine` 改为 `Line[{A,D}]`。

### 作垂线/垂足

```wl
Element[H, InfiniteLine[{B, C}]]
GeometricAssertion[
  {Line[{A, H}], Line[{B, C}]},
  "Perpendicular"
]
```

### 作中点、角平分线、垂直平分线

```wl
M == Midpoint[{B, C}]
Element[D, AngleBisector[{A, B, C}]]
Element[O, PerpendicularBisector[{A, B}]]
```

### 延长边得到交点

```wl
Element[P, InfiniteLine[{A, B}]]
Element[P, InfiniteLine[{C, D}]]
```

不要为了得到交点先在 Python 中求坐标；让 Wolfram 负责求解和一致性校验。

## 防退化与版面约束

先使用弱约束：

```wl
GeometricAssertion[{A, B, C}, "Distinct"]
GeometricAssertion[{B, C, A}, "Counterclockwise"]
GeometricAssertion[Line[{B, C}], "Horizontal"]
```

必要时再加无量纲形状约束：

```wl
TriangleMeasurement[{A, B, C}, {"InteriorAngle", B}] > 10 Degree

TriangleMeasurement[Triangle[{A, B, C}], "Inradius"] /
  TriangleMeasurement[Triangle[{A, B, C}], "Circumradius"] > 0.10

TriangleMeasurement[Triangle[{A, B, C}], {"Height", A}] /
  TriangleMeasurement[Triangle[{A, B, C}], "Perimeter"] > 0.08
```

风险从低到高：方向约束 < 单个角下界 < 半径/高的比例约束。不要在第一轮叠加多个强约束。

若场景缺少尺度，固定一条与题意无冲突的基准长度：

```wl
EuclideanDistance[B, C] == 6
```

## prompt 与 solution

prompt 只含题干已知事实；solution 必须锁定 prompt 的所有基础点，再增加辅助点和辅助约束。

```json
{
  "reuse_geometry_from": "q1-prompt",
  "add_auxiliary": {
    "add_points": ["H"],
    "hypotheses_wl": [
      "Element[H, InfiniteLine[{B, C}]]",
      "GeometricAssertion[{Line[{A, H}], Line[{B, C}]}, \"Perpendicular\"]"
    ]
  }
}
```

规则：

- solution 不得重新随机生成 A、B、C 等基础点。
- 新增辅助点必须加入 solution 的点列表。
- prompt 不得出现辅助线、相似结论、答案或解题提示。
- 同一题可复用自己的 prompt；不同题之间不得共享 resolved 图资产。

## 常见错误

### 用 Collinear 代替隶属关系

```wl
(* BAD *)
GeometricAssertion[{P, A, C}, "Collinear"]

(* GOOD: 同时表达 P-A-C *)
Element[A, Line[{P, C}]]
```

### 把线段与直线混淆

```wl
Element[P, Line[{A, B}]]          (* P 被限制在线段 AB 上 *)
Element[P, InfiniteLine[{A, B}]]  (* P 可在延长线上 *)
```

### 角顶点写错

```wl
PlanarAngle[{A, B, C}]  (* 顶点 B *)
```

### 使用未声明点

约束、区域、辅助构造中出现的每个符号点，都必须在 `GeometricScene` 第一参数声明。

### 把点当坐标向量

```wl
(* BAD *)
G == (A + B + C)/3

(* GOOD *)
G == TriangleCenter[{A, B, C}, "Centroid"]
```

### 用浮点数表达精确比例

```wl
(* BAD *)
EuclideanDistance[A, B] == 0.6667 EuclideanDistance[A, C]

(* GOOD: AB:AC = 2:3 *)
3 EuclideanDistance[A, B] == 2 EuclideanDistance[A, C]
```

### 为了好看添加题干没有的特殊性质

不得擅自添加等腰、直角、正多边形、对称、共圆等强性质。版面调整优先使用方向、顺逆时针、角下界等弱约束。

## 出题场景覆盖清单

提交 scene spec 前逐项检查题目涉及的类别：

- 点：线段内点、直线上点、射线上点、交点、内分点、外分点、中点。
- 线：共线、平行、垂直、延长线、垂直平分线、角平分线。
- 长度：固定长度、等长、线段和差、整数比例、相似比例。
- 角：固定角、等角、直角、内角、外角、圆心角。
- 三角形：一般、等腰、等边、直角、中线、高、三角形中心。
- 四边形：平行四边形、矩形、菱形、正方形、梯形、凸多边形。
- 圆：圆周点、圆盘内点、共圆、弦、直径、切线、两圆交点。
- 关系：相似、全等、面积、周长、面积比。
- 辅助构造：过点作平行线、垂线、延长边、连接中点、作角平分线。
- 质量：所有点已声明、点序正确、无退化、尺度稳定、不泄露答案、solution 锁定 prompt。

若题目包含本清单之外的合成几何对象，并且本机有同级 `GeometricScene-Builder` checkout，先查
`GeometricScene-Builder/.opencode/skills/wolfram-geometricscene-reference/SKILL.md`；否则查 Wolfram
Synthetic Geometry 官方参考。不要猜测函数签名。
