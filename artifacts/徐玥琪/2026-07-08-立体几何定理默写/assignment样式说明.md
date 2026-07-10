# 立体几何定理默写 assignment 样式说明

## 每道题的固定结构

每道默写题都按“三件套”组织：

1. 定理表述
   - 写出完整定理表述。
   - 可以做少量挖空，但必须保留学生能判断定理类型的关键词。
   - 这一行直接作为题干出现，不加栏目名。
   - 题干用于默写“这是什么定理”，不要写成解题提示。

2. 竖式填空
   - 使用竖排推导格式。
   - 挖空可以出现在左边条件，也可以出现在右边结论。
   - 这一部分直接放公式，不加栏目名。
   - 推荐格式：

     ```tex
     \[
     \left.
     \begin{aligned}
     &\text{条件 1}\\
     &\text{条件 2}\\
     &\underline{\hspace{3.5cm}}
     \end{aligned}
     \right\}
     \Longrightarrow
     \text{结论}
     \]
     ```

   - 如果考结论，也可以写成：

     ```tex
     \[
     \left.
     \begin{aligned}
     &\text{条件 1}\\
     &\text{条件 2}
     \end{aligned}
     \right\}
     \Longrightarrow
     \underline{\hspace{4cm}}
     \]
     ```

3. 配图
   - 每道题都配一个对应图形。
   - 图形只服务“认对象、认位置关系、认结论”，不要在图中塞过多文字说明。
   - 图中需要标出题目里出现的点、线、面、交线、垂足、角或距离。
   - 推荐与竖式填空并排：左侧放竖排条件组，右侧放图；若公式较长，也可以左图右公式。

## 固定图规则

本目录的定理默写 assignment 使用固定图，不临时生成图。

- 固定图索引见 `fixed_theorem_diagrams/catalog.yaml`。
- 固定图源数据见 `fixed_theorem_diagrams/specs.yaml`，生成链路是“定理条件 -> 三维坐标 -> tikz-3dplot TikZ”。
- 每条定理对应一个 `theorem_id` 和一个 `tikz_path`。
- assignment 题目中直接写 `diagram_col.tikz_path`，不要再为已入库定理声明 `diagram_slot`。
- 图上标签必须与左侧条件组对应：左侧出现的对象，右图必须能找到；右图不出现左侧没有的构造点、平面顶点或真实题目载体。
- 两个平面相交的固定图必须在图源中声明 `plane_intersection_line`，不能只画两个四边形；交线由 renderer 从两个平面方程自动求出并最后高亮，平面统一使用半透明样式。
- 固定图采用灰阶线型语法：实线是定理原对象，虚线是辅助线、投影线、高度线或背景边，较粗实线是交线；不要用多种鲜艳颜色承担数学关系。
- 固定图视角要优先打开核心线线夹角，避免原线、辅助线和交线在投影后重叠。
- 如果新增定理，先补 `specs.yaml` 并运行生成脚本，生成/更新固定图和 catalog，再出作业。

推荐引用格式：

```yaml
diagram_col:
  kind: tikz
  tikz_path: fixed_theorem_diagrams/tikz/b03-line-plane-parallel-judge.fragment.tex
  width: 55mm
  variant: prompt
  disclosure_policy: clean
  caption: ""
```

## 单题推荐呈现

学生看到的题目应长这样：

```text
1. 如果一条直线和一个平面内的 ______ 平行，那么这条直线和这个平面平行。

   [竖排条件组 + Longrightarrow + 填空]    [配图]
```

教师版在同一题后补答案即可，不额外加入“提示”“小贴士”“思路导航”等解释性噪音。

## 内容边界

- 这是“定理默写”assignment，不是讲义。
- 每题只考一个定理或一个稳定变形，不把多个定理串成长证明。
- 题面尽量短，重点放在定理表述、竖式结构和图形对象识别。
- 学生版不出现答案；教师版可以给出完整原文、填空答案和必要的覆盖清单。
