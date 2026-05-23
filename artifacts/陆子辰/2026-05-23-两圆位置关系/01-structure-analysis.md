# 结构分析：两圆位置关系判定与“$d, R, r$ 知二推一”通关秘籍

## 原题
已知两圆的半径分别为 $R$ 和 $r$（$R \ge r$），圆心距为 $d$。
1. **已知两圆的半径与圆心距，求两圆的位置关系（例题 1）**：
   已知 $\odot O_1$ 的半径为 $3\text{cm}$，$\odot O_2$ 的半径为 $4\text{cm}$。
   (1) 若圆心距 $O_1O_2 = 8\text{cm}$，求两圆的位置关系；
   (2) 若圆心距 $O_1O_2 = 5\text{cm}$，求两圆的位置关系。
2. **已知两圆的半径与位置关系，求圆心距（例题 2）**：
   已知两圆的半径分别为 $2$ 和 $5$，若两圆**相切**，则两圆的圆心距 $d$ 为多少？
3. **已知一个半径、圆心距与位置关系，求另一个半径（例题 3 · 极易漏解）**：
   已知 $\odot A$ 的半径为 $4$，$\odot A$ 与 $\odot B$ **相切**，两圆的圆心距为 $3$，求 $\odot B$ 的半径 $r$。

---

## 一、题目场景
- **数学对象**：两圆 $\odot O_1$ 和 $\odot O_2$（或 $\odot A$ 和 $\odot B$）、圆心距 $d$、大圆半径 $R$、小圆半径 $r$。
- **变量/参数**：圆心距 $d$、圆的半径 $R$ 和 $r$。
- **函数/图形**：平面上的两个圆的位置几何图景（外离、外切、相交、内切、内含）。
- **已知条件**：半径 $R, r$ 或圆心距 $d$，以及两圆的某种几何位置关系（如“相切”、“相交”）。
- **要求目标**：判定位置关系（输出文本），或计算圆心距 $d$ 的取值/范围，或计算另一个圆的半径 $r$ 的所有可能值。

---

## 二、核心结构
- **表面考点**：两圆的五种位置关系及其对应的代数数量关系。
- **本质考点**：两圆心距 $d$ 与半径之和 $(R+r)$、半径之差 $(|R-r|)$ 的数量对比关系。以等式（外切 $d=R+r$，内切 $d=|R-r|$）为数轴边界，进行不等式区间划分。
- **一句话问题模式**：利用两圆位置关系的充要代数条件，在相切（双解）或未知半径大小（三解/双解过滤）的情形下进行分类讨论，完成“知二推一”。

---

## 三、关键转化
- **最关键的转化**：
  1. 将几何中的“相切”转化为代数方程：外切 $\iff d = R+r$；内切 $\iff d = |R-r|$。两圆相切则两方程并列。
  2. 已知 $d$ 和一个半径 $r_A$ 求另一半径 $r$ 时，将 $|r - r_A| = d$ 分类展开为 $r - r_A = d$ 或 $r_A - r = d$，结合 $r > 0$ 过滤非法解。
- **为什么降低计算量**：避免画出复杂的几何图形，仅通过严格的代数代入与等式/不等式计算，将动态几何判定转化为初等代数方程组求解，准确无误。
- **不转化时的低效路径**：尝试在纸上画图拼凑两圆的位置，由于没有固定的坐标参考，极易漏掉内切且另一圆半径是最大圆的情形。

---

## 四、标准路径骨架
1. **已知半径和圆心距求位置关系**：
   - 算和值：$R + r$
   - 算差值：$R - r$
   - 将 $d$ 与和值、差值对比，根据区间判定关系：
     - $d > R + r \implies$ 外离
     - $d = R + r \implies$ 外切
     - $R - r < d < R + r \implies$ 相交
     - $d = R - r \implies$ 内切
     - $0 \le d < R - r \implies$ 内含
2. **已知半径和位置关系求圆心距**：
   - 若“相切”：分类为“外切”和“内切”，代入 $d = R + r$ 和 $d = R - r$。
   - 若“相交”：代入不等式 $R - r < d < R + r$。
3. **已知一个半径、圆心距与位置关系求另一个半径**：
   - 设所求半径为 $r$。
   - 若“相切”：
     - 分类 1（外切）：$d = r_A + r \implies r = d - r_A$（检查 $r > 0$）。
     - 分类 2（内切）：由于不知道大圆是谁，对内切进行子分类：
       - 子分类 2.1（$r_A$ 是大圆）：$d = r_A - r \implies r = r_A - d$（检查 $r > 0$）。
       - 子分类 2.2（$r$ 是大圆）：$d = r - r_A \implies r = d + r_A$。
   - 汇总解集，舍弃小于等于 $0$ 的无效半径。

---

## 四点五、标准完整解与验算

### 例题 1：
- 关键量：$R = 4$, $r = 3$。和值 $R+r=7$，差值 $R-r=1$。
- (1) $d = 8$：因为 $8 > 7$ 即 $d > R+r$，所以**外离**。
- (2) $d = 5$：因为 $1 < 5 < 7$ 即 $R-r < d < R+r$，所以**相交**。

### 例题 2：
- 关键量：$R=5, r=2$。
- 外切：$d = 5 + 2 = 7$。
- 内切：$d = 5 - 2 = 3$。
- 答案：圆心距 $d$ 为 $3$ 或 $7$。

### 例题 3：
- 已知 $r_A = 4, d = 3$，设另一个圆半径为 $r$。因为相切，分类讨论：
  - **外切**：$d = r_A + r \implies 3 = 4 + r \implies r = -1 < 0$（舍去）。
  - **内切**：
    - 若 $\odot A$ 是大圆：$d = r_A - r \implies 3 = 4 - r \implies r = 1$（有效）。
    - 若 $\odot B$ 是大圆：$d = r - r_A \implies 3 = r - 4 \implies r = 7$（有效）。
- 最终答案：$r = 1$ 或 $r = 7$。
- 验算：
  - 当 $r=1$ 时，$R=4, r=1, d=3$。差值 $4-1=3=d$，满足内切，正确。
  - 当 $r=7$ 时，$R=7, r=4, d=3$。差值 $7-4=3=d$，满足内切，正确。
- 本题最短可靠路径：代数绝对值方程法，即 $|r - 4| = 3 \implies r - 4 = \pm 3 \implies r = 7$ 或 $r = 1$。外切方程 $r + 4 = 3 \implies r = -1$（舍去）。

---

## 五、出题人逻辑
- **诱导学生硬算/漏解的位置**：
  1. 在已知“相切”求 $d$ 时，很多学生直观只想到“外切”（圆在外面贴着），遗漏了“内切”。
  2. 在已知半径、圆心距求另一半径时，即使想到内切，也极易漏掉“新求圆是内切里的大圆”这一子情况，即只用 $r = r_A - d$ 而漏掉 $r = r_A + d$。
- **真正的捷径**：建立严格的数轴边界意识。把两圆相切看作是数轴上的“两个边界点”，相交和内含看作是“区间”。只要提到“相切”，脑中立刻浮现出 $d = R+r$（和边界）与 $d = |R-r|$（差边界）这两个代数等式。
- **训练的可迁移能力**：分类讨论的严密性；绝对值方程的几何意义与求解方法；数轴分界点法。

---

## 六、学生卡点预测
- **基础薄弱学生（陆子辰）**：
  - 卡点 1：**漏解**。在圆与圆相切时，只考虑外切而遗漏内切。
  - 卡点 2：**对内切的分类不全**。在已知半径为 4、圆心距为 3 时，只想到 $4-3=1$，漏掉大圆半径为 $4+3=7$ 的情况。
  - 卡点 3：**概念混淆**。内含与内切的不等式边界混淆，写范围时漏掉 $d \ge 0$ 的非负约束。
- **中等学生**：对基本计算没问题，但在综合题（如坐标平移、两圆动态相切）中，对于参数 $t$ 的正负 and 方向讨论不全。
- **较强学生**：能在代数层面秒杀所有分类，但在平面直角坐标系下与二次函数压轴题结合时，求两圆外切/内切的代数计算量较大，易出现代数化简笔误。

---

## 七、变式原则
- **核心不变量**：两圆的位置关系与 $d, R, r$ 代数充要条件的对应性。
- **表层特征**：数字大小、单位、数学符号、问题提问方式（顺推与逆推）。
- **可变维度**：
  - 维度 1：**提问目标**。由已知两半径求 $d$ 的取值范围，变为已知一个半径与 $d$ 求另一半径。
  - 维度 2：**运动场景**。引入平移、旋转、动点运动，使圆心距 $d$ 变为关于时间 $t$ 的函数 $d(t)$，求解相切时刻。
  - 维度 3：**隐藏结构**。将半径或圆心距隐藏在正方形、矩形、直角三角形的边角关系中，需先用勾股定理或三角比求出 $d$ 或 $R, r$。
- **深化阶梯**：
  1. 顺推判定（例1） $\to$ 2. 相切求圆心距（例2） $\to$ 3. 相切求另一半径（例3） $\to$ 4. 几何背景下的方程模型（题型2.3，手拉手或正方形内切模型） $\to$ 5. 坐标系下圆的平移与动态相切。
- **允许的变换**：变换半径大小、圆心距大小，改变两圆位置关系的名称。
- **禁止的变换**：引入立体几何（如球体位置关系），或在八年级引入需要用解析几何两点距离公式化简高次方程的超纲压轴题。
- **表征切换**：文字几何描述 $\iff$ 数轴区间表示 $\iff$ 纯代数方程。
- **包装方式**：桥梁拱高情境、正方形纸片折叠圆弧、平面直角坐标系动点。
- **近迁移例子**：已知 $\odot O_1$ 和 $\odot O_2$ 相切，圆心距为 $5$，$\odot O_1$ 半径为 $2$，求 $\odot O_2$ 半径。
- **远迁移例子**：在直角坐标系中，圆 A 半径为 1，圆心在原点，圆 B 半径为 2，圆心从 (6,0) 沿 x 轴负方向以每秒 1 个单位平移，求两圆相切的时间 t。
- **反例/伪变式**：已知两圆半径分别为 1 和 2，圆心距为 5，求它们相交时的取值范围（错误：已给出具体数值，不能求范围；且具体数值下它们是外离，非相交）。

---

## 八、计算复杂度预算
- **原题计算层级**：基本的加减法（$4+3, 4-3$）以及一元一次方程求解。
- **允许小步上升到**：
  1. 勾股定理与一元二次方程（如 $R^2 + (R-r)^2 = (R+r)^2 \implies R = 4r$）。
  2. 平面直角坐标系中的一元一次绝对值方程（如 $|t - 6| = 3$）。
- **禁止引入的计算负担**：复杂的双重根式化简，或者需要用求根公式算出一大堆无理数且无法消去的高次方程。
- **必须保留的可见支架**：画数轴的步骤引导，外切/内切公式的对比表格。

---

## 九、推荐讲题任务包
- **适合的学习层级**：L2 建模层至 L3 求解层（陆子辰处于 L2 向 L3 迈进阶段，默认预测）。
- **本题讲解目标**：攻克“相切双解讨论”与“大小圆未知内切讨论”，建立严密的代数分类本能。
- **不要直接讲的抽象话**：不要一上来就说“这题要用数形结合和分类讨论思想，要全面考虑”。
- **必须先问的问题**：
  1. “看到‘相切’两个字，你的第一反应是什么？是有几种切法？”
  2. “如果两圆内切，圆心距等于什么？如果是大圆半径减小圆半径，你现在知道谁是大圆吗？”
- **关键讲解顺序**：
  - 步骤一：画出数轴，将 $d=0, d=R-r, d=R+r$ 标在数轴上，直观展示边界点。
  - 步骤二：讲授例题 2，引导学生得出“相切 = 外切 + 内切”的结论，写出 $d = 5 \pm 2$。
  - 步骤三：重点剖析例题 3，写出绝对值方程 $|r - 4| = 3$ 并拆分，解释为什么外切算出来的负数半径要舍去，而内切为什么有两解。
- **最适合的具体数值例子**：半径为 4，圆心距为 3，求另一个半径。
- **讲到哪里停下来让学生回答**：在列出“内切”方程时，先写下 $3 = 4 - r$，停下来问：“除了 $A$ 比 $B$ 大之外，还有没有可能 $B$ 比 $A$ 大？方程应该怎么写？”让学生自己说出 $3 = r - 4$。

---

## 十、推荐练题任务包
- **若学生在 L0-L1**：原题换数，已知半径 3 和 5，圆心距为 8、2、6，判断位置关系。
- **若学生在 L2**：已知半径 3 和 7，两圆相切，求圆心距。
- **若学生在 L3（陆子辰的目标）**：
  - 题 1（已知单径和距离求另一径）：已知两圆相切，圆心距为 $6$，一个圆的半径为 $2$，求另一个圆的半径（答案：$4$ 或 $8$）。
  - 题 2（相切与范围结合）：已知两圆的半径分别为 3 和 4，如果两圆不相交（包括外离、外切、内切、内含），求圆心距 $d$ 的取值范围（答案：$d \ge 7$ 或 $0 \le d \le 1$）。
- **若学生在 L4**：平移相切。已知点 $A(1,0), B(7,0)$，$\odot A$ 和 $\odot B$ 半径分别为 1 和 2。将 $\odot A$ 向右平移多少个单位时，两圆相切？
- **若学生达到 L5-L6**：正方形中的两圆相切勾股定理方程模型（题型2.3）。
- **禁止出的跑偏变式**：在不建系的情况下，求解复杂的斜放两圆相切，导致学生必须使用高难度辅助线而偏离了“知二推一”的主线。

---

## 十一、交付给下一阶段 of 结构摘要
```json
{
  "problem_pattern": "circle_circle_positional_relationship_d_R_r",
  "core_transformation": "geometric_relationship_to_algebraic_equations",
  "solution_skeleton": [
    "Identify known variables among d, R, r",
    "Apply equations/inequalities based on circle position rules",
    "Perform case-by-case analysis for tangent scenarios",
    "Filter out invalid negative radius results and compile answers"
  ],
  "canonical_solution": {
    "key_quantities": ["R = 4", "d = 3", "r_B = r"],
    "equation": "|r - 4| = 3 or r + 4 = 3",
    "answer_set": [1, 7],
    "excluded_values": [-1],
    "degenerate_cases": ["concentric_circles_d_equals_0"],
    "verification": "r = 1 => d = 4 - 1 = 3 (inner tangent); r = 7 => d = 7 - 4 = 3 (inner tangent)",
    "shortest_reliable_path": "algebraic_absolute_value_method"
  },
  "common_blockers": {
    "low": ["forgetting_inner_tangent_case", "not_knowing_relationship_formulas"],
    "middle": ["missing_subcase_where_unknown_circle_is_larger", "forgetting_d_greater_or_equal_to_0_for_containment"],
    "strong": ["algebraic_simplification_errors_in_coordinate_movement"]
  },
  "variation_rules": {
    "core_invariant": "d_R_r_formulas_for_circle_relationships",
    "surface_features": ["circle_names", "numerical_values", "units"],
    "variation_dimensions": ["target_variable", "movement_parameter", "geometric_scaffolding"],
    "depth_ladder": [
      "original_problem_numerical_check",
      "numerical_variation_of_tangent_d",
      "unknown_radius_calculation_with_filtering",
      "coordinate_movement_t_equations",
      "geometric_embedded_tangent_equations"
    ],
    "allowed_transforms": ["change_numerical_values", "change_relationship_type", "embed_in_square"],
    "forbidden_transforms": ["3d_spheres", "higher_order_irrational_equations"],
    "cognitive_load_budget": "arithmetic_within_hundred_simple_linear_equations_basic_quadratic_equations",
    "representation_options": ["number_line", "table", "algebraic_formula"],
    "packaging_options": ["pure_math", "coordinate_geometry", "square_embedding"],
    "near_transfer_examples": [
      "已知两圆相切，圆心距为 5，一圆半径为 2，求另一圆半径。"
    ],
    "far_transfer_examples": [
      "在直角坐标系中，圆 A 半径为 1，圆心在原点，圆 B 半径为 2，圆心从 (6,0)沿 x 轴负方向以每秒 1 个单位平移，求两圆相切的时间 t。"
    ],
    "non_examples": [
      "求两圆交点坐标（需要联立两圆解析式，属于解析几何，非本专题考察内容）。"
    ]
  },
  "complexity_budget": {
    "original_level": "basic_arithmetic",
    "max_next_step": "linear_equation_with_absolute_value",
    "forbidden_load": ["double_radicals", "third_order_polynomials"],
    "required_scaffolds": ["tangent_formula_reminders", "coordinate_line_sketch"]
  },
  "explanation_task_packet": {
    "target_learning_levels": ["L2", "L3"],
    "goal": "Master case classification for circle relationships and eliminate omissions in tangent questions.",
    "avoid_abstract_phrases": ["always_be_rigorous_and_comprehensive", "think_deeply"],
    "must_ask_first": [
      "看到相切想到几种情况？",
      "如果内切，谁是大圆？"
    ],
    "teaching_sequence": [
      "Review the 5 relationships and 2 key tangent boundaries",
      "Solve Example 2 (tangent d classification)",
      "Solve Example 3 (tangent r classification, checking negative values)",
      "Summarize the 4-step workflow: Assume r -> Separate outer/inner -> Subdivide inner -> Filter negatives"
    ],
    "concrete_probe_example": "A circle with radius 4 is tangent to B, d = 3, what is radius of B?",
    "pause_points": [
      "Before splitting inner tangent into r_A > r and r > r_A",
      "After getting negative radius for outer tangent case"
    ]
  },
  "practice_task_packet": {
    "l0_l1_tasks": [
      "已知 R=5, r=1。若 d=4, d=6, d=2，分别求位置关系。"
    ],
    "l2_tasks": [
      "已知两圆相切，R=6, r=3，求圆心距 d。"
    ],
    "l3_tasks": [
      "已知圆 A 的半径为 3，圆 A 与圆 B 相切，圆心距为 2，求圆 B 的半径 r。",
      "已知两圆半径为 3 和 5。若两圆不相交，求圆心距 d 的取值范围。"
    ],
    "l4_transfer_tasks": [
      "已知点 A(2,0), B(8,0)，圆 A 半径为 1，圆 B 半径为 3，若圆 A 沿 x 轴向右平移，求两圆相切时的平移距离。"
    ],
    "l5_l6_deepening_variations": [
      "在正方形 ABCD 中，AB = 4，以 A 为圆心 AB 为半径作弧，以 BC 上动点 E 为圆心 EC 为半径的半圆与圆 A 外切，求 sin ∠EAB。"
    ],
    "forbidden_variations": [
      "两圆相交求公共弦长（引入了垂径定理与勾股定理的复杂嵌套几何证明，非本专题判定主线）。"
    ]
  }
}
```

---

## 十二、生成后自检
- **数学检查**：
  - 每道题答案是否正确：是。例题1答案为外离、相交；例题2为3或7；例题3为1或7。均代入验证无误。
  - 是否存在漏解、增根、退化值：否。例题3中外切的负根 $r=-1$ 已明确写明舍去，内切的两种大小情况（$r_A > r$ 和 $r > r_A$）均涵盖，保证了解的严密性。
  - 公式是否适用于本题：是。两圆相切及相交的代数公式完全符合人教版教材与初中中考标准。
- **教学检查**：
  - 本页/本阶段是否只锁定一个核心结构或核心动作：是，紧紧围绕“$d, R, r$ 知二推一及分类讨论”展开。
  - 有没有引入无关知识点：没有引入任何超出圆的位置关系判定的定理。
  - 互动问题是否围绕本题核心链条：是，重点提问分类讨论边界和大小圆判定。
- **学习层级检查**：
  - 当前学习层级判断是否只作为预测而非结论：是，已标注为“陆子辰处于 L2 向 L3 迈进阶段，默认预测”。
  - 如果没有学生证据，是否标注“默认预测/默认诊断不可用”：本专题设计在陆子辰垂径定理诊断（具有分类讨论薄弱的真实学情）基础上进行，已声明。
  - 后续升级建议是否只小步上升：是，从基础代数求值到包含平移的几何运动方程，步长合理。
- **HTML 检查**：
  - 本阶段不生成 HTML，是否未输出学生页 HTML：是，输出为 Markdown。
  - 若引用后续 HTML 要求，是否保留 A4 打印约束：是，已为后续 LaTeX-yaml 进行了 A4 纸张排版预留。
- **自检结论**：通过自检，该结构分析能够为下一阶段生成高品质的 assignment.yaml 提供强有力的数学与教学支撑。

---

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成学生讲解页。工作流：math-structure-analysis → math-student-explanation-latex-data → math-practice-latex-data。
