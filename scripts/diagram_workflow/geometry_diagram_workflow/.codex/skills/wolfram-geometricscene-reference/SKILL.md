---
name: wolfram-geometricscene-reference
description: 在编写或审查 Wolfram GeometricScene、RandomInstance、TriangleMeasurement、PlanarAngle、GeometricAssertion 等合成几何代码时加载。提供所有常用函数的签名与传参类型，避免参数类型错误。
---

# Wolfram GeometricScene 函数参考

编写 GeometricScene 相关 WL 代码时，必须遵循以下函数签名与参数类型。

## 1. 核心场景与求解

### GeometricScene
```wl
GeometricScene[{p1, p2, ...}, {hyp1, hyp2, ...}]
GeometricScene[{{p1, p2, ...}, {k1, k2, ...}}, hyps]  (* 含标量参数 *)
```
- **第1参数**：点列表 `{p1, p2, ...}`，符号必须为 GeometricScene 内声明的点
- **第2参数**：假设列表，可包含区域、等式、GeometricAssertion 等

### RandomInstance
```wl
RandomInstance[scene]
RandomInstance[scene, n]
```
- **scene**：GeometricScene 对象
- 返回 GeometricScene 实例或实例列表

### TimeConstrained
```wl
TimeConstrained[expr, t, failexpr]
```
- 超时返回 `failexpr`，benchmark 建议用 `$Failed`

---

## 2. TriangleMeasurement（三角形测量）

**签名**：`TriangleMeasurement[tri, type]`

**关键**：`tri` 必须是**三角形**，不能是任意点列表。

| tri 合法形式 | 说明 |
|-------------|------|
| `{p1, p2, p3}` | 三点列表（隐含三角形） |
| `Triangle[{p1, p2, p3}]` | 显式三角形 |
| `Polygon[{p1, p2, p3}]` | 多边形（三顶点） |

**错误示例**：
```wl
(* BAD: points 可能是 4+ 点的列表 *)
BuildLayer3ROverR[points_List, minRatio_] := 
  { TriangleMeasurement[points, "Inradius"] > minRatio * TriangleMeasurement[points, "Circumradius"] }
```

**正确示例**：
```wl
(* GOOD: 显式取前 3 点构造三角形 *)
BuildLayer3ROverR[points_List, minRatio_] := Module[{tri},
  tri = Triangle[Take[points, 3]];
  { TriangleMeasurement[tri, "Inradius"] > minRatio * TriangleMeasurement[tri, "Circumradius"] }
]
```

**type 取值**：

| type | 含义 |
|------|------|
| `"Area"` | 面积 |
| `"Circumradius"` | 外接圆半径 |
| `"Inradius"` | 内切圆半径 |
| `"Perimeter"` | 周长 |
| `"Semiperimeter"` | 半周长 |
| `{"InteriorAngle", p}` | 顶点 p 的内角 |
| `{"ExteriorAngle", p}` | 顶点 p 的外角 |
| `{"Height", p}` | 从顶点 p 出发的高 |
| `{"Exradius", p}` | 顶点 p 对侧的旁切圆半径 |
| `"NinePointRadius"` | 九点圆半径 |

---

## 3. PlanarAngle（平面角）

**签名**：
```wl
PlanarAngle[{q1, p, q2}]           (* 角在 p，由 q1-p-q2 确定 *)
PlanarAngle[p, {q1, q2}]           (* 从 p 出发到 q1、q2 的两射线夹角 *)
PlanarAngle[..., "Interior"]      (* 三角形内角 *)
PlanarAngle[..., "Exterior"]       (* 三角形外角 *)
PlanarAngle[..., "Counterclockwise"] (* 逆时针角 *)
```

**参数**：
- `{q1, p, q2}`：p 为顶点，q1、q2 为边上点
- 可与 `GeometricScene` 中的符号点一起使用

**示例**：
```wl
PlanarAngle[{a, b, c}] > 15 Degree   (* 角 b 大于 15° *)
```

---

## 4. GeometricAssertion（几何断言）

**签名**：`GeometricAssertion[obj, prop]` 或 `GeometricAssertion[{obj1, obj2, ...}, prop]`

### 线方向（obj 为 Line）
| prop | 含义 |
|------|------|
| `"Horizontal"` | 水平 |
| `"Vertical"` | 垂直 |
| `"Rightward"` | 向右 |
| `"Leftward"` | 向左 |
| `"Upward"` | 向上 |
| `"Downward"` | 向下 |

### 点顺序（obj 为点列表）
| prop | 含义 |
|------|------|
| `"Counterclockwise"` | 逆时针 |
| `"Clockwise"` | 顺时针 |
| `"Distinct"` | 不共点 |
| `"Collinear"` | 共线 |
| `"Cyclic"` | 共圆 |

### 线与线
| prop | 含义 |
|------|------|
| `"Parallel"` | 平行 |
| `"Perpendicular"` | 垂直 |
| `"Concurrent"` | 共点 |

### 多边形
| prop | 含义 |
|------|------|
| `"Convex"` | 凸 |
| `"Equilateral"` | 等边 |
| `"Regular"` | 正多边形 |
| `"Rectangle"` | 矩形 |

### 对象间关系
| prop | obj | 含义 |
|------|-----|------|
| `"Congruent"` | 两个同类几何对象组成的列表 | 全等 |
| `"Similar"` | 两个同类多边形/三角形组成的列表 | 相似 |

三角形的顶点顺序直接表达对应关系。例如 `A↔D, B↔E, C↔F`：

```wl
GeometricAssertion[
  {Triangle[{A, B, C}], Triangle[{D, E, F}]},
  "Congruent"
]

GeometricAssertion[
  {Triangle[{A, B, C}], Triangle[{D, E, F}]},
  "Similar"
]
```

不要改成三参数形式，不要添加 `VertexMap`，也不要把一个全等/相似条件展开成多组边长和角度条件。

```wl
(* BAD *)
GeometricAssertion[Triangle[{A, B, C}], "Congruent", Triangle[{D, E, F}]]
GeometricAssertion[Triangle[{A, B, C}], Triangle[{D, E, F}], "Congruent"]
```

**示例**：
```wl
GeometricAssertion[Line[{b, c}], "Horizontal"]
GeometricAssertion[{b, c, a}, "Counterclockwise"]
GeometricAssertion[{a, b, c}, "Distinct"]
```

---

## 5. 几何对象与量

### 基本构造
| 函数 | 签名 | 说明 |
|------|------|------|
| `Line[{p1, p2, ...}]` | 线段 | 按顺序经过各点 |
| `Triangle[{p1, p2, p3}]` | 三角形 | 三点定义 |
| `Polygon[{p1, p2, ...}]` | 多边形 | 顶点列表 |
| `Circle[p, r]` | 圆 | 圆心 p，半径 r |
| `CircleThrough[{p1, p2, ...}]` | 过点的圆 | 经过指定点 |
| `Disk[p, r]` | 圆盘 | 圆心 p，半径 r |
| `Midpoint[{p, q}]` | 中点 | 线段 pq 的中点 |
| `InfiniteLine[{p, q}]` | 直线 | 过 p、q 的无穷直线 |
| `HalfLine[{p, q}]` | 射线 | 从 p 经 q 的射线 |
| `AngleBisector[{p, q, r}]` | 角平分线 | 角 q 的平分线 |
| `PerpendicularBisector[{p, q}]` | 垂直平分线 | pq 的垂直平分线 |

### 几何量
| 函数 | 签名 | 说明 |
|------|------|------|
| `EuclideanDistance[p, q]` | 两点距离 | 欧氏距离 |
| `Area[reg]` | 面积 | 区域面积 |
| `Perimeter[reg]` | 周长 | 区域周长 |
| `ArcLength[reg]` | 弧长 | 弧或边界的长度 |
| `RegionMeasure[reg]` | 测度 | 1D/2D 测度 |
| `PolygonAngle[poly, p]` | 多边形角 | 顶点 p 处的内角 |

### TriangleCenter（三角形中心）

**签名**：`TriangleCenter[tri, type]` 或 `TriangleCenter[tri]`（默认返回重心）

**关键**：`tri` 必须是**三角形**，与 TriangleMeasurement 使用相同的三角形形式。

| tri 合法形式 | 说明 |
|-------------|------|
| `{p1, p2, p3}` | 三点列表（隐含三角形） |
| `Triangle[{p1, p2, p3}]` | 显式三角形 |
| `Polygon[{p1, p2, p3}]` | 多边形（三顶点） |

**type 取值**：

| type | 含义 | 别名 |
|------|------|------|
| `"Centroid"` | 重心（三条中线交点） | 默认值 |
| `"Circumcenter"` | 外心（外接圆圆心） | |
| `"Incenter"` | 内心（内切圆圆心） | |
| `"Orthocenter"` | 垂心（三条高交点） | |
| `"NinePointCenter"` | 九点圆圆心 | |
| `"SymmedianPoint"` | 陪位重心 | |
| `{"Foot", p}` | 从顶点 p 出发的高与对边的交点 | |
| `{"Midpoint", p}` | 顶点 p 对边的中点 | |
| `{"Excenter", p}` | 顶点 p 对侧的旁切圆圆心 | |
| `{"AngleBisectingCevianEndpoint", p}` | 顶点 p 的角平分线与对边交点 | |
| `{"CevianEndpoint", center, p}` | 过顶点 p 和指定中心的塞瓦线与对边交点 | |

**示例**：
```wl
(* 重心 *)
G == TriangleCenter[{B, P, Q}, "Centroid"]
G == TriangleCenter[{B, P, Q}]  (* 等价写法 *)

(* 内心 *)
I == TriangleCenter[{A, B, C}, "Incenter"]

(* 外心 *)
O == TriangleCenter[Triangle[{A, B, C}], "Circumcenter"]

(* 顶点 A 的高与对边的交点（垂足） *)
H = TriangleCenter[{A, B, C}, {"Foot", A}]
```

### 三角形构造与其他函数
| 函数 | 签名 | 说明 |
|------|------|------|
| `TriangleConstruct[{p,q,r}, spec]` | 三角形构造 | "Incircle", "Circumcircle", "Altitude" 等 |
| `TriangleMeasurement[tri, type]` | 三角形测量 | 见上文 |

---

## 6. 常见错误与修正

### 错误 1：TriangleMeasurement 传入非三角形
```wl
(* BAD *)
TriangleMeasurement[points, "Inradius"]   (* points 可能含 4+ 点 *)
(* GOOD *)
tri = Triangle[Take[points, 3]];
TriangleMeasurement[tri, "Inradius"]
```

### 错误 2：PlanarAngle 三点顺序错误
```wl
(* angle at vertex b *)
PlanarAngle[{a, b, c}]   (* GOOD: b 在中间 *)
PlanarAngle[{b, a, c}]   (* 不同角：在 a *)
```

### 错误 3：使用未声明点
- GeometricScene 的点列表必须包含所有在假设中出现的符号

### 错误 4：混淆 Equal 与几何量
```wl
(* 边长相等 *)
EuclideanDistance[a, b] == EuclideanDistance[a, c]
(* 而非 AB == AC，除非 AB、AC 在场景中已定义为量 *)
```

点属于线段/直线必须直接使用 `Element`，不要套入 `GeometricAssertion`：

```wl
Element[F, Line[{A, D}]]                         (* GOOD *)
GeometricAssertion[Element[F, Line[{A, D}]]]     (* BAD *)
GeometricAssertion[F, "Element", Line[{A, D}]]  (* BAD *)
```

### 错误 5：重心使用坐标计算而非 TriangleCenter
```wl
(* BAD: 在 GeometricScene 中使用坐标运算 *)
G == (B + P + Q)/3   (* 这不是有效的几何约束语法 *)

(* GOOD: 使用 TriangleCenter *)
G == TriangleCenter[{B, P, Q}, "Centroid"]
(* 或简化为 *)
G == TriangleCenter[{B, P, Q}]
```

**原因**：在 GeometricScene 的符号求解中，点不是坐标值，不能直接进行向量加减。必须使用几何函数如 `TriangleCenter`、`Midpoint` 等。

---

## 7. 参考资料

- [Synthetic Geometry Guide](https://reference.wolfram.com/language/guide/SyntheticGeometry.html)
- [Synthetic Geometry Tutorial](https://reference.wolfram.com/language/tutorial/SyntheticGeometry.html)
- [TriangleMeasurement](https://reference.wolfram.com/language/ref/TriangleMeasurement.html)
- [GeometricAssertion](https://reference.wolfram.com/language/ref/GeometricAssertion.html)
- [PlanarAngle](https://reference.wolfram.com/language/ref/PlanarAngle.html)
- [GeometricScene](https://reference.wolfram.com/language/ref/GeometricScene.html)
- [TriangleCenter](https://reference.wolfram.com/language/ref/TriangleCenter.html)
