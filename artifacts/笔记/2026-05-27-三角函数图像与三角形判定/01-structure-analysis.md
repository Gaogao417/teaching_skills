# 结构分析：三角函数图像与三角形判定

## 原题
已知函数 $y=f(x)$，$f(x)=A\sin(\omega x+\varphi)$，其中 $A>0,\omega>0,|\varphi|<\dfrac{\pi}{2}$，其部分图像如图所示：

1. 求 $y=f(x)$ 的解析式；
2. 在 $\triangle ABC$ 中，$a,b,c$ 分别是角 $A,B,C$ 的对边，若 $f(B)=1$，$a,b,c$ 成等差数列，判断 $\triangle ABC$ 的形状。

图中可读信息：最大值为 $2$，曲线经过 $(0,1)$，且在 $x=\dfrac{\pi}{6}$ 处达到一个峰值；结合图像位置，峰值对应当前显示的第一个相邻峰。

## 一、题目场景
- 数学对象：正弦型函数、三角形边角关系。
- 变量/参数：$A,\omega,\varphi$；三角形角 $B$ 与边 $a,b,c$。
- 函数/图形：$y=A\sin(\omega x+\varphi)$ 的局部图像。
- 已知条件：$A>0,\omega>0,|\varphi|<\dfrac{\pi}{2}$；图像给出最大值、$f(0)$、峰值横坐标；$f(B)=1$；$a,b,c$ 成等差数列。
- 要求目标：先求函数解析式，再用函数值确定角 $B$，最后判断三角形形状。

## 二、核心结构
- 表面考点：三角函数图像求解析式；余弦定理；等差数列。
- 本质考点：把“图像读数”转成参数方程，把“边成等差”转成 $2b=a+c$，再和余弦定理联立。
- 一句话问题模式：先由图像锁定 $A,\varphi,\omega$，再由 $f(B)$ 锁定角，最后用边角方程判断三角形。

## 三、关键转化
- 最关键的转化：$a,b,c$ 成等差数列 $\Rightarrow 2b=a+c$，而 $B=\dfrac{\pi}{3}$ 时余弦定理给出 $b^2=a^2+c^2-ac$。
- 为什么降低计算量：两个关系只含 $a,b,c$，消去 $b$ 后直接得到 $(a-c)^2=0$。
- 不转化时的低效路径：只凭“$B=60^\circ$”猜测等边，或在三角形角度上盲目引入 $A,C$。

## 四、标准路径骨架
1. 先做什么：从最大值读出 $A=2$，从 $f(0)=1$ 求 $\varphi$。
2. 再做什么：用峰值位置 $x=\dfrac{\pi}{6}$ 建立相位方程。
3. 建立什么关系：结合图像相邻峰位置/周期限制筛选 $\omega$。
4. 如何求解：得到 $f(x)=2\sin(2x+\dfrac{\pi}{6})$，再解 $f(B)=1$。
5. 需要检查什么：$B\in(0,\pi)$，相位解只能保留使 $B$ 在三角形内角范围内的值。

## 四点五、标准完整解与验算
- 关键交点/关键量：$A=2$，$f(0)=1$，峰值点横坐标 $x=\dfrac{\pi}{6}$。
- 面积/方程/关系式：$\sin\varphi=\dfrac12$；$\dfrac{\pi}{6}\omega+\dfrac{\pi}{6}=\dfrac{\pi}{2}+2k\pi$；$2b=a+c$；$b^2=a^2+c^2-ac$。
- 完整求解过程：
  - 最大值为 $2$，且 $A>0$，所以 $A=2$。
  - $f(0)=2\sin\varphi=1$，所以 $\sin\varphi=\dfrac12$。由 $|\varphi|<\dfrac{\pi}{2}$，得 $\varphi=\dfrac{\pi}{6}$。
  - 峰值在 $x=\dfrac{\pi}{6}$，故 $2\sin(\dfrac{\pi}{6}\omega+\dfrac{\pi}{6})=2$，即
    $\dfrac{\pi}{6}\omega+\dfrac{\pi}{6}=\dfrac{\pi}{2}+2k\pi$，所以 $\omega=2+12k$。
  - 由图像相邻峰位置可知周期不能过短，取 $\omega>0$ 且 $\omega<3$，所以 $k=0,\omega=2$。
  - 因此 $f(x)=2\sin(2x+\dfrac{\pi}{6})$。
  - $f(B)=1$，即 $\sin(2B+\dfrac{\pi}{6})=\dfrac12$。因 $B\in(0,\pi)$，所以 $2B+\dfrac{\pi}{6}\in(\dfrac{\pi}{6},\dfrac{13\pi}{6})$，可取 $2B+\dfrac{\pi}{6}=\dfrac{5\pi}{6}$，得 $B=\dfrac{\pi}{3}$。
  - 又 $a,b,c$ 成等差数列，所以 $2b=a+c$。
  - 由余弦定理，
    $b^2=a^2+c^2-2ac\cos\dfrac{\pi}{3}=a^2+c^2-ac$。
  - 代入 $4b^2=(a+c)^2$，得 $(a+c)^2=4a^2+4c^2-4ac$，即 $3(a-c)^2=0$，所以 $a=c$，进而 $a=b=c$。
- 最终答案：$f(x)=2\sin(2x+\dfrac{\pi}{6})$；$\triangle ABC$ 为等边三角形。
- 排除值：$\omega=2+12k$ 中只取 $k=0$；$f(B)=1$ 的边界相位不取。
- 退化情形：三角形边长为正，$a=c$ 后 $b=a$，不退化。
- 验算：$f(\dfrac{\pi}{3})=2\sin(\dfrac{5\pi}{6})=1$；等边三角形满足 $B=\dfrac{\pi}{3}$ 且边成等差。
- 本题最短可靠路径：图像三信息定函数，再用 $f(B)$ 定角，最后“等差边 + 余弦定理”消元。

## 五、出题人逻辑
- 诱导学生硬算的位置：峰值相位的多解、$f(B)=1$ 的多解、三角形边角混合关系。
- 真正的捷径：每一步都先转成一个标准等式：读图、相位、等差、余弦定理。
- 训练的可迁移能力：从图像信息提取参数；从数列关系翻译成边长方程；用余弦定理完成形状判定。

## 六、学生卡点预测
- 基础薄弱学生：不知道 $A$ 是振幅；把 $\varphi$ 解成两个值；不知道边成等差就是 $2b=a+c$。
- 中等学生：能求出 $\omega=2+12k$，但不会用图像周期限制筛选；解 $f(B)=1$ 时多取或漏取。
- 较强学生：第（2）问能列关系，但容易把余弦定理中的对边搞错。

## 七、变式原则
- 核心不变量：图像定参 $\rightarrow$ 函数值定角 $\rightarrow$ 边角关系判形。
- 表层特征：振幅、初值、峰值横坐标、$f(B)$ 的数值、边长数列关系。
- 可变维度：改变 $A,\varphi,\omega$；把 $f(B)=1$ 改为 $f(B)=A/2$；把等差边保留为同一结构。
- 深化阶梯：先只求解析式，再加角的范围筛选，再加余弦定理判形。
- 允许的变换：保持角 $B$ 可解为常见角；保持边关系能化成低次方程。
- 禁止的变换：引入非特殊角、复杂反三角函数、多周期难筛选、三角形不等式大讨论。
- 表征切换：函数图像、相位方程、三角形边角示意图。
- 包装方式：考试压轴小问、专题讲解例题、综合练习。
- 近迁移例子：同样由峰值与初值求 $A,\omega,\varphi$，再判断三角形是否等腰/等边。
- 远迁移例子：由余弦函数图像定参，再把函数值用作几何角。
- 反例/伪变式：只练三角函数图像但不接三角形；只练余弦定理但没有函数定角。

## 八、计算复杂度预算
- 原题计算层级：中等，核心计算为特殊角和二次式化简。
- 允许小步上升到：换一组特殊角或振幅，保留 $\sin$ 值为 $1/2,\sqrt2/2$ 等。
- 禁止引入的计算负担：复杂周期枚举、非特殊角、三角形边长具体求值的大量算术。
- 必须保留的可见支架：图像关键读数、角范围、等差转化、余弦定理对象对应。

## 九、推荐讲题任务包
- 适合的学习层级：高中三角函数基础到中等综合。
- 本题讲解目标：让学生会把两段题意串起来，而不是把三角函数和三角形割裂处理。
- 不要直接讲的抽象话：不要只说“数形结合”“综合运用”，要落到每个条件怎么翻译。
- 必须先问的问题：图像给了哪三个可用信息？$a,b,c$ 成等差应该写成什么？
- 关键讲解顺序：读图定 $A$ 和 $\varphi$；峰值定 $\omega$；$f(B)$ 定 $B$；等差边和余弦定理联立。
- 最适合的具体数值例子：$\sin\varphi=\dfrac12$，$2B+\dfrac{\pi}{6}=\dfrac{5\pi}{6}$。
- 讲到哪里停下来让学生回答：求出 $B=\dfrac{\pi}{3}$ 后，停下来让学生写出余弦定理和 $2b=a+c$。

## 十、推荐练题任务包
- 若学生在 L0-L1，出什么题：只读振幅、初值和峰值求一个正弦函数。
- 若学生在 L2，出什么题：加入 $f(B)$ 求特殊角。
- 若学生在 L3，出什么题：加入边成等差和余弦定理判断形状。
- 若学生在 L4，如何迁移：改变振幅和相位，但仍让 $B$ 为特殊角。
- 若学生达到 L5-L6，如何深化/抽象/包装：讨论“边成等差 + 某个角”在什么角度下推出等边。
- 禁止出的跑偏变式：需要大量三角恒等变形或复杂反函数求角的题。

## 十点五、推荐图形请求包（可选）
- 是否需要图：需要。
- 图形类型：`function_graph` 为主；三角形部分可用 `synthetic_geometry` 的简化示意，但不需要强行走 GeometricScene。
- 用图意图：`student_explanation` / `practice_prompt`。
- 需要出现的对象：正弦曲线、坐标轴、峰值点、$f(0)$；三角形 $ABC$ 与边 $a,b,c$、角 $B$。
- 需要突出给学生看的关系：峰值横坐标和相位；角 $B$ 是边 $b$ 的对角；$2b=a+c$。
- 图中不能暗示的错误性质：三角形示意图不能画出等边外观来提前泄露结论；函数图不能暗示未给出的周期结论。
- 图失败时的降级方案：讲解页写读图提示，练习题只保留函数图或让学生手画三角形示意。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "正弦图像定参 + 函数值定三角形角 + 等差边余弦定理判形",
  "core_transformation": "a,b,c成等差转为2b=a+c；B=pi/3时代入余弦定理",
  "solution_skeleton": ["读图定A和phi", "峰值相位定omega并筛选", "由f(B)=1求B", "等差边与余弦定理联立判形"],
  "canonical_solution": {
    "key_quantities": ["A=2", "phi=pi/6", "omega=2", "B=pi/3"],
    "equation": "2b=a+c, b^2=a^2+c^2-ac",
    "answer_set": ["f(x)=2sin(2x+pi/6)", "triangle ABC is equilateral"],
    "excluded_values": ["omega=2+12k except k=0", "phase boundary solutions for B"],
    "degenerate_cases": ["side lengths positive; no degenerate triangle after a=b=c"],
    "verification": "f(pi/3)=1 and equilateral triangle satisfies all side-angle conditions",
    "shortest_reliable_path": "graph readings -> parameter equations -> f(B) -> AP sides plus law of cosines"
  },
  "common_blockers": {
    "low": ["cannot read amplitude", "does not translate AP sides", "confuses angle and side notation"],
    "middle": ["keeps all omega branches", "solves f(B)=1 without angle range"],
    "strong": ["uses law of cosines with the wrong opposite side"]
  },
  "variation_rules": {
    "core_invariant": "graph-to-parameter then angle-to-shape",
    "surface_features": ["amplitude", "initial value", "peak x-coordinate", "function value at B"],
    "variation_dimensions": ["change A", "change phi", "change omega", "change special angle B"],
    "depth_ladder": ["read graph", "solve phase", "filter angle", "combine with triangle relation"],
    "allowed_transforms": ["keep special angles", "keep AP side relation"],
    "forbidden_transforms": ["non-special inverse trig", "long periodic casework", "heavy side-length arithmetic"],
    "cognitive_load_budget": "one small step above original only",
    "representation_options": ["function graph", "phase equation", "triangle side-angle sketch"],
    "packaging_options": ["example explanation", "student practice", "teacher solution"],
    "near_transfer_examples": ["change A=3 and phi=pi/6", "use sin value sqrt2/2"],
    "far_transfer_examples": ["cosine graph determines an angle used in geometry"],
    "non_examples": ["only graph reading without triangle", "only geometry without function angle"]
  },
  "complexity_budget": {
    "original_level": "medium",
    "max_next_step": "same structure with changed special-angle numbers",
    "forbidden_load": ["non-special angles", "multi-branch inverse trig", "complex triangle inequality cases"],
    "required_scaffolds": ["graph key readings", "angle range", "AP relation", "law of cosines target side"]
  },
  "explanation_task_packet": {
    "target_learning_levels": ["L2", "L3"],
    "goal": "build the chain from graph readings to triangle shape",
    "avoid_abstract_phrases": ["数形结合", "综合运用"],
    "must_ask_first": ["图像给了哪三个读数？", "边成等差写成什么式子？"],
    "teaching_sequence": ["read A", "solve phi", "use peak to solve omega", "solve B", "combine AP and cosine law"],
    "concrete_probe_example": "If sin(2B+pi/6)=1/2 and B in (0,pi), which B remains?",
    "pause_points": ["after omega branch equation", "after B=pi/3"]
  },
  "practice_task_packet": {
    "l0_l1_tasks": ["read A and phi from graph"],
    "l2_tasks": ["solve omega from a peak point"],
    "l3_tasks": ["use f(B) and AP sides to judge shape"],
    "l4_transfer_tasks": ["change graph parameters but keep the same final triangle structure"],
    "l5_l6_deepening_variations": ["ask when AP sides plus a fixed angle force equilateral"],
    "forbidden_variations": ["non-special angles and heavy computation"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "function_graph",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["(0,1)", "(pi/6,2)", "A", "B", "C"],
      "segments": ["AB", "BC", "CA"],
      "curves": ["y=2sin(2x+pi/6)"],
      "constraints": ["B is opposite side b", "2b=a+c"]
    },
    "teaching_focus": ["read graph values", "match angle B to opposite side b", "translate AP sides"],
    "must_not_imply": ["triangle is equilateral before proof", "extra function periods not shown"],
    "fallback": "textual_diagram_description"
  }
}
```
