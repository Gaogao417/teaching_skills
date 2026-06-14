# 结构分析：一次函数与反比例函数交点、图像不等式与面积

## 原题

已知一次函数 $y_1=kx+b$ 与反比例函数 $y_2=\dfrac{m}{x}$ 的图像交于点 $A,B$。已知：

1. 点 $A$ 的横坐标为 $2$；
2. 点 $B$ 的横坐标为 $-1$；
3. 一次函数图像与 $y$ 轴交于点 $C(0,-1)$。

\begin{enumerate}[label=(\arabic*)]
  \item 求一次函数解析式、反比例函数解析式，以及点 $A,B$ 的坐标；
  \item 根据图像求不等式 $kx+b>\dfrac{m}{x}$ 的解集；
  \item 求 $\triangle OAB$ 的面积。
\end{enumerate}

## 一、题目场景

- 数学对象：一次函数 $y_1=kx+b$，反比例函数 $y_2=\dfrac{m}{x}$，两图像交点 $A,B$，坐标原点 $O$。
- 已知条件：两个交点横坐标 $2,-1$，直线截距 $b=-1$。
- 目标链条：
- 第 (1) 问：由三个独立条件求 $k,b,m,A,B$；条件可以是两个交点横坐标加一个参数，也可以是 $k,b,m$ 中任意两个参数加一个交点横坐标；
  - 第 (2) 问：把不等式翻译为图像上下关系，用交点和 $0$ 分段；
  - 第 (3) 问：用铅垂线法，把 $AB$ 与 $y$ 轴交点到目标点的竖直距离转成三角形面积。

## 二、核心结构

- 表面考点：一次函数、反比例函数、函数图像解不等式、铅垂线法求面积。
- 本质结构：同一个交点同时满足直线方程和反比例方程，交点横坐标给出后，先用条件求出两函数与交点，再把图像信息转成区间，把直线 $AB$ 与铅垂线的竖直距离转成面积。
- Block 链：
  - B1：由 $C(0,-1)$ 得 $b=-1$。
  - B2：设 $A(2,2k-1)$，$B(-1,-k-1)$。
  - B3：$A,B$ 同在 $y=\dfrac{m}{x}$ 上，所以 $2(2k-1)=(-1)(-k-1)$。
  - B4：解出 $k=1$，从而 $b=-1$，$m=2$。
  - B5：得到 $A(2,1)$，$B(-1,-2)$。
  - B6：解 $x-1>\dfrac{2}{x}$ 时，用交点 $-1,2$ 和 $x=0$ 分段看图像上下。
  - B7：面积用铅垂线法。设 $AB$ 与 $y$ 轴交于 $P$，必须先说明拆分：若 $A,B$ 在 $y$ 轴两侧，则 $S_{\triangle OAB}=S_{\triangle OPA}+S_{\triangle OPB}$；若在同侧，则用大三角形减小三角形。最后统一为 $S_{\triangle OAB}=\dfrac12\cdot OP\cdot|x_A-x_B|$。
- 条件包装网络：
  - 给 $x_A,x_B,b$：用直线表示 $A,B$，再由两个交点的 $xy=m$ 相等求 $k$。
  - 给 $k,b,x_A$：直线已知，先求 $A$ 和 $m$，再解 $kx+b=\dfrac{m}{x}$ 求另一个交点。
  - 给 $b,m,x_A$：先由 $m/x_A$ 求 $A$ 的纵坐标，再代入直线求 $k$，最后求另一个交点。
  - 给 $k,m,x_A$：先由 $m/x_A$ 求 $A$ 的纵坐标，再代入直线求 $b$，最后求另一个交点。
- 模型标签：
  - `function_intersection_parameter_solving`
  - `graph_inequality_by_vertical_order`
  - `vertical_line_area`

## 三、关键转化

- 交点转方程：点在反比例函数上等价于 $xy=m$，所以两个交点必须满足 $x_Ay_A=x_By_B$。
- 不等式转图像：$kx+b>\dfrac{m}{x}$ 等价于同一个 $x$ 下直线图像在双曲线图像上方。
- 面积转化：设 $AB$ 与 $y$ 轴交于 $P$。当 $O$ 为第三个顶点时，把 $\triangle OAB$ 拆成以 $OP$ 为公共底的三角形；它们到 $y$ 轴的水平距离分别是 $|x_A|,|x_B|$。若 $A,B$ 在 $y$ 轴两侧，则 $S_{\triangle OAB}=S_{\triangle OPA}+S_{\triangle OPB}$，所以水平距离相加；若 $A,B$ 在同侧，则 $S_{\triangle OAB}$ 等于大三角形减小三角形，所以水平距离相减。两种情况都统一为 $\dfrac12\cdot OP\cdot|x_A-x_B|$。

## 四、标准路径骨架

1. 由 $C(0,-1)$ 得 $b=-1$。
2. 把 $x_A=2,x_B=-1$ 代入直线，表示 $A(2,2k-1),B(-1,-k-1)$。
3. 由 $A,B$ 同在 $y=\dfrac{m}{x}$ 上列 $2(2k-1)=(-1)(-k-1)$，解 $k$。
4. 求出 $A,B$ 坐标和 $m$，写出两个函数解析式。
5. 第 (2) 问用 $-1,0,2$ 分段；选直线在双曲线上方的区间。
6. 第 (3) 问找出 $AB$ 与 $y$ 轴交点 $P$，用铅垂线法计算 $\triangle OAB$ 面积。

## 五、标准完整解与验算

由 $C(0,-1)$ 在直线 $y_1=kx+b$ 上，得 $b=-1$，所以 $y_1=kx-1$。

因为 $A$ 的横坐标为 $2$，$B$ 的横坐标为 $-1$，且 $A,B$ 在直线 $y=kx-1$ 上，所以
$$
A(2,2k-1),\qquad B(-1,-k-1).
$$

又 $A,B$ 都在反比例函数 $y_2=\dfrac{m}{x}$ 上，所以交点坐标满足 $xy=m$：
$$
2(2k-1)=(-1)(-k-1).
$$
解得
$$
4k-2=k+1,\qquad 3k=3,\qquad k=1.
$$
于是
$$
y_1=x-1,\qquad A(2,1),\qquad B(-1,-2).
$$
代入反比例函数得
$$
m=2\cdot1=2,
$$
所以
$$
y_2=\frac{2}{x}.
$$

第 (2) 问：
$$
kx+b>\frac{m}{x}\Longleftrightarrow x-1>\frac{2}{x}.
$$
两图像交点横坐标为 $-1,2$，反比例函数在 $x=0$ 处无定义。用 $-1,0,2$ 分段：
$$
(-\infty,-1),\quad(-1,0),\quad(0,2),\quad(2,+\infty).
$$
由图像上下关系，直线在双曲线上方的区间为
$$
(-1,0)\quad\text{和}\quad(2,+\infty).
$$
因此不等式解集为
$$
-1<x<0\quad\text{或}\quad x>2.
$$

第 (3) 问：

直线 $AB$ 就是 $y=x-1$，与 $y$ 轴交于点 $P(0,-1)$，所以 $OP=1$。

因为 $A,B$ 在 $y$ 轴两侧，可把 $\triangle OAB$ 拆成 $\triangle OPA$ 与 $\triangle OPB$，这里是“相加”的拆分。两者都以 $OP$ 为底，高分别是 $A,B$ 到 $y$ 轴的水平距离 $|x_A|,|x_B|$，所以
$$
S_{\triangle OAB}
=\frac12OP\cdot|x_A|+\frac12OP\cdot|x_B|
=\frac12OP\cdot(|x_A|+|x_B|)
=\frac12OP\cdot|x_A-x_B|.
$$
代入 $OP=1,x_A=2,x_B=-1$：
$$
S_{\triangle OAB}
=\frac12\cdot1\cdot|2-(-1)|
=\frac32.
$$

验算：

- $A(2,1)$、$B(-1,-2)$ 均满足 $y=x-1$ 和 $y=\dfrac2x$。
- $x=0$ 不能进入第 (2) 问解集。
- 面积为正数，且 $O,A,B$ 不共线。

## 六、出题人逻辑

- 第 (1) 问不是单纯套待定系数法，而是要用“交点同属两函数”把 $k$ 和 $m$ 连起来。
- 第 (2) 问训练学生把代数不等式读成图像上下关系，避免盲目通分。
- 第 (3) 问把函数交点坐标转为铅垂线面积，训练坐标与图形量的切换。

## 七、学生卡点预测

- 读题/入口卡点：只看到 $kx+b$、$\dfrac{m}{x}$，不知道先由 $C(0,-1)$ 得 $b=-1$。
- 建关系卡点：会写 $A(2,2k-1)$，但不会用反比例函数的 $xy=m$ 把 $A,B$ 连起来。
- 图像不等式卡点：忘记 $x=0$ 也要作为断点，或把“直线在上方”看反。
- 面积卡点：不会找 $AB$ 与 $y$ 轴交点；漏掉三角形面积的 $\dfrac12$；不清楚为什么水平宽度是 $|x_A-x_B|$。

## 八、变式原则

- 核心不变量：
  - 交点同时满足两个函数；
  - 图像解不等式看同一横坐标下谁在上方；
  - 铅垂线法：用直线 $AB$ 与目标点之间的竖直距离乘横向宽度的一半。
- 一二问迁移边界：不做远迁移，但必须允许“同结构换条件包装”。可给两个交点横坐标加一个参数，也可给 $k,b,m$ 中任意两个参数加一个交点横坐标；目标仍是求两个函数、两个交点，再解同类图像不等式。
- 第三问近迁移：仍求 $\triangle OAB$ 面积，只换干净数字。
- 第三问远迁移：
  - 改成求 $\triangle PAB$ 面积，其中 $P$ 给在坐标轴上；
  - 或给定 $\triangle PAB$ 面积，且 $P$ 在反比例函数或坐标轴上，反求 $P$ 的坐标。
- 禁止变式：
  - 一二问不要改成二次函数、复杂分式不等式、含绝对值不等式；
  - 第三问远迁移不要同时引入复杂动点范围和多解分类。

## 九、计算复杂度预算

- 原题计算层级：中低计算，重点是结构连接。
- 允许小步上升：换成 $x_A=3,x_B=-2$ 这类干净根；面积结果允许整数或半整数。
- 禁止负担：高次方程、不可整除参数、复杂根式面积、需要大量分类讨论的动点。
- 必须保留支架：交点横坐标、直线截距、图像、$x=0$ 不可取提醒、铅垂线法公式来源。

## 十、推荐讲题任务包

- 讲解目标：让学生会按“求参 -> 交点坐标 -> 图像区间 -> 铅垂线法面积”的顺序解完整题。
- 必须先问：
  1. $C(0,-1)$ 先告诉了哪个参数？
  2. $A,B$ 在反比例函数上，哪个乘积相同？
  3. $kx+b>\dfrac{m}{x}$ 在图上是什么意思？
  4. $AB$ 与 $y$ 轴交于哪里？为什么面积公式里有 $\dfrac12$？
- 关键讲解顺序：先完整求参，再用同一张图解不等式，最后用铅垂线法算面积并说明公式来源。

## 十一、推荐练题任务包

- 近迁移 1：给 $x_A,x_B,b$，同结构换数，仍求函数、交点、不等式解集、$\triangle OAB$ 面积。
- 近迁移 2：给 $k,b,x_A$，让两个交点同在第一象限，训练 $0$ 不在两个交点之间时仍要作为断点；面积仍为 $\triangle OAB$。
- 远迁移 1：给 $b,m,x_A$，一二问保持同结构，第三问改求点 $P$ 在 $y$ 轴上时 $\triangle PAB$ 面积。
- 远迁移 2：给 $k,m,x_A$，一二问保持同结构，第三问给 $P$ 在反比例函数上及 $\triangle PAB$ 面积，反求 $P$ 的坐标。

## 十二、推荐图形请求包

- 是否需要图：需要。
- 图形类型：`function_graph`。
- 图意图：讲解和练习都需要 clean 函数图；教师可在讲解时额外标出分段。
- 需要出现的对象：坐标轴、直线、双曲线、交点 $A,B$，必要时标出点 $P$。
- 需要突出给学生看的关系：交点横坐标和 $0$ 的分段，直线/双曲线上下关系，面积三角形顶点。
- 图中不能暗示的错误性质：不要把 $x=0$ 画成可取点；不要把 $A,B$ 标签放反；不要在学生版图中泄露不等式解集。

## 十三、交付给下一阶段的结构摘要 JSON

```json
{
  "problem_pattern": "一次函数与反比例函数交点求参、图像解不等式、铅垂线法面积综合",
  "core_transformation": "交点满足直线方程且满足 xy=m；kx+b>m/x 等价于直线在双曲线上方；三角形面积用铅垂线法",
  "solution_skeleton": [
    "由 C(0,-1) 得 b=-1",
    "用交点横坐标在直线上表示 A,B",
    "用 A,B 在反比例函数上列 xy 相等，求 k,m",
    "用交点横坐标和 0 分段，根据图像上下关系写不等式解集",
    "找 AB 与 y 轴交点 P，用 S=1/2*OP*|x_A-x_B| 求 S_{OAB}"
  ],
  "canonical_solution": {
    "functions": {
      "linear": "y=x-1",
      "inverse": "y=2/x"
    },
    "points": {
      "A": [2, 1],
      "B": [-1, -2],
      "O": [0, 0]
    },
    "inequality_solution": "-1<x<0 or x>2",
    "area_OAB": "3/2",
    "excluded_values": ["x=0", "x=-1 and x=2 for strict inequality"],
    "verification": "A,B satisfy both functions; selected intervals match graph order; area formula gives positive value"
  },
  "block_chain": [
    "B1: C(0,-1) -> b=-1",
    "B2: x_A=2, x_B=-1 -> A(2,2k-1), B(-1,-k-1)",
    "B3: A,B on y=m/x -> 2(2k-1)=(-1)(-k-1)",
    "B4: solve -> k=1, m=2",
    "B5: graph inequality -> breakpoints -1,0,2",
    "B6: vertical-line area -> first state the split: opposite sides use S_OPA+S_OPB, same side use larger-minus-smaller; then S=1/2*OP*|x_A-x_B|"
  ],
  "model_tags": [
    "function_intersection_parameter_solving",
    "graph_inequality_by_vertical_order",
    "vertical_line_area"
  ],
  "common_blockers": {
    "find_entry": ["不知道先用 C(0,-1) 求 b", "不知道交点横坐标如何转成点坐标"],
    "build_relation": ["不会用 xy=m 连接两个交点", "图像解不等式漏掉 x=0"],
    "solve_and_check": ["交点误取入严格不等式", "面积公式漏掉 1/2 或找错铅垂距离"],
    "transfer": ["面积目标一变成 PAB 就不知道仍可用铅垂线法"]
  },
  "variation_rules": {
    "core_invariant": "交点同属两函数；图像上下解不等式；铅垂线法面积转化",
    "near_transfer": ["一二三问全部同结构换数", "可以改变条件包装，如 x_A,x_B,b 或 k,b,x_A", "第三问仍求 OAB 面积"],
    "far_transfer": ["一二问不远迁移，但可改变条件包装", "只把第三问改为 PAB 面积或由面积反求 P"],
    "forbidden_variations": ["一二问换成复杂纯代数不等式", "第三问同时加入复杂动点范围和多分支分类"]
  },
  "complexity_budget": {
    "original_level": "中低计算，整系数和半整数面积",
    "max_next_step": "第三问单独做面积目标迁移",
    "forbidden_load": ["高次方程", "复杂根式", "绝对值不等式", "二次函数压轴"],
    "required_scaffolds": ["函数图像", "交点横坐标", "x=0 断点", "铅垂线法公式来源"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["find_entry", "build_relation", "solve_and_check"],
    "goal": "讲清完整三问链条：求参、图像解不等式、铅垂线法面积",
    "teaching_sequence": ["由条件求函数", "求 A,B 坐标", "分段解不等式", "找 AB 与 y 轴交点", "说明铅垂线面积公式来源"],
    "pause_points": ["写出 A,B 坐标表达式后", "列 xy=m 方程前", "写不等式解集前", "找出 AB 与 y 轴交点后"]
  },
  "practice_task_packet": {
    "near_transfer_tasks": ["给 x_A,x_B,b 的同结构换数题，第三问求 OAB 面积", "给 k,b,x_A 的同结构换条件题，并安排 A,B 同在第一象限"],
    "far_transfer_tasks": ["给 b,m,x_A，第三问求 PAB 面积", "给 k,m,x_A，第三问由面积反求 P"],
    "forbidden_variations": ["一二问远迁移", "复杂动点分类"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "function_graph",
    "diagram_intent": "student_explanation_and_practice",
    "objects_hint": {
      "points": ["A", "B", "O", "optional P"],
      "curves": ["line y=kx+b", "hyperbola y=m/x"],
      "constraints": ["x=0 is not in domain", "A,B are true intersections"]
    },
    "teaching_focus": ["breakpoints", "vertical order", "triangle area vertices"],
    "must_not_imply": ["do not include x=0 as a solution", "do not swap A and B", "do not leak answers in student diagrams"],
    "fallback": "textual_diagram_description"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.assignment.yaml；再使用 math-adaptive-practice-latex-data 生成学生版和教师版练习。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
