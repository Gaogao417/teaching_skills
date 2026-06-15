# 结构分析：平行四边形、矩形、菱形的存在性问题

## 原题
给刘濯嘉生成复习讲义，主题为平行四边形、矩形、菱形的坐标存在性问题。

1. 平行四边形：
   - 三定一动：已知 $A,B,C$，求 $D$。若题目说“平行四边形 $ABCD$”，则直接用对角线中点相同：$A+C=B+D$。若题目说“$A,B,C,D$ 构成平行四边形”，则要讨论 $A$ 与谁是对角顶点，分 $AB,AC,AD$ 三种对角线情况。
   - 两定两动：已知 $A,B$，并知道 $C,D$ 所在轨迹，或 $C,D$ 坐标可用未知数描述。做法仍是先把四个点坐标写出/设出，再按三种对角线配对列方程。
2. 矩形：
   - 常见为已知 $A,B$，给 $C$ 的轨迹，求 $D$。
   - 若题目说“矩形 $ABCD$”，则 $\angle ABC=90^\circ$，先设 $C$，用 $\triangle ABC$ 在 $B$ 处为直角列勾股定理求 $C$，再用平行四边形三定一动求 $D$。
   - 若题目说“$A,B,C,D$ 构成矩形”，则 $\triangle ABC$ 是直角三角形，直角可能在 $A,B,C$ 三个点，逐类求 $C$，再按对应对角线配对求 $D$。
3. 菱形：
   - 菱形存在性问题与矩形存在性问题结构相似。
   - 矩形讨论 $\triangle ABC$ 是直角三角形；菱形讨论 $\triangle ABC$ 是等腰三角形。求出 $C$ 后，再按平行四边形三定一动求 $D$。

## 一、题目场景
- 数学对象：坐标平面内的四边形存在性，点坐标，点在直线或简单轨迹上的参数表示。
- 变量/参数：已知点 $A,B,C$ 或 $A,B$；未知点 $D(x,y)$；动点 $C(t,\cdots)$、$D(s,\cdots)$。
- 函数/图形：动点常在直线、坐标轴或一次函数图像上。
- 已知条件：四边形类型与顶点顺序，或只说四点“构成”某特殊四边形。
- 要求目标：求动点坐标、判断存在性、列出所有可能点。

## 二、核心结构
### 2.1 表层信息
- 表面考点：平行四边形、矩形、菱形、坐标、距离公式、勾股定理。
- 题型功能：`existence_or_parameter`
- 是否值得完整 structural analysis：是；理由：同一几何对象会因“有顺序/无顺序”产生完全不同的分类，学生常漏情况或列错对角关系。
- 一句话问题模式：先设点坐标，再用“对角线中点相同”确定平行四边形；矩形额外加“直角”，菱形额外加“等腰”。

### 2.2 结构表达
#### 判别条件表
- 必要条件：
  - 平行四边形：存在一组对角线中点相同。
  - 矩形：先是平行四边形，且相邻边垂直；等价地，任取三个顶点形成直角三角形。
  - 菱形：先是平行四边形，且相邻边相等；等价地，任取三个顶点形成等腰三角形。
- 充分条件：
  - 已知 $A,B,C$ 三点且指定哪两个点对角，可唯一求出 $D$。
  - 若只说四点构成，则三种对角线配对都要讨论，满足条件的都保留。
- 常见干扰项：
  - 把“平行四边形 $ABCD$”和“$A,B,C,D$ 构成平行四边形”混为一谈。
  - 只讨论 $A,C$ 对角，漏 $A,B$ 对角和 $A,D$ 对角。
  - 矩形题只按 $\angle B=90^\circ$ 做，漏“构成矩形”时直角可能在 $A$ 或 $C$。
  - 菱形题只写一个等边条件，漏另两种等腰情况。
- 最短检查动作：先圈题目有没有固定顺序；再问“谁和谁是对角？”

#### 情景量表
| 量 | 类型/单位 | 题设关系 | 未知/已知 |
|---|---|---|---|
| $D(x,y)$ | 点坐标 | 待求动点 | 未知 |
| $C(t,\cdots)$ | 参数点 | 位于给定轨迹 | 未知或半未知 |
| 对角线中点 | 坐标关系 | $P+Q=R+S$ | 用于列方程 |
| 距离平方 | 数量 | 矩形用勾股，菱形用等腰 | 用于筛选 |

#### 命题网络
- P1（题设）：已知若干定点坐标和动点轨迹。
- P2（构造）：设出所有未知点坐标，例如 $C(t,\cdots)$、$D(x,y)$。
- P3（定理）：平行四边形对角线互相平分，因此对角顶点坐标和相等。
- P4（目标）：若已知平行四边形 $ABCD$，则 $A,C$ 对角，$D=A+C-B$。
- P5（构造）：若四点“构成”平行四边形，分 $A,B$ 对角、$A,C$ 对角、$A,D$ 对角。
- P6（定理）：矩形中任取三个顶点构成直角三角形。
- P7（定理）：菱形中任取三个顶点构成等腰三角形。
- P8（可推）：矩形 $ABCD$ 的顺序固定时，$\angle ABC=90^\circ$。
- P9（可推）：菱形 $ABCD$ 的顺序固定时，$AB=BC$。
- P10（检查）：排除点重合、面积为 $0$、或同一答案重复计数。
- R1：P1 -> P2，方法：把轨迹条件参数化。
- R2：P2 + P3 + 固定顺序 -> P4，方法：对角线中点坐标相等。
- R3：P2 + P3 + 无固定顺序 -> P5，方法：三种对角配对分类。
- R4：P5 + P6 -> 矩形候选，方法：分别令 $\angle A,\angle B,\angle C$ 为直角并列勾股。
- R5：P5 + P7 -> 菱形候选，方法：分别列 $AB=AC$、$AB=BC$、$AC=BC$。
- R6：候选点 + P10 -> 最终答案，方法：代回轨迹和几何条件检查。
- 目标：建立“设点坐标 -> 分类 -> 列方程 -> 求解 -> 回代筛选”的稳定流程。

### 2.3 解题主链
```text
看问法是否固定顺序 -> 设动点坐标 -> 平行四边形用对角和 -> 矩形加直角/菱形加等腰 -> 求参数 -> 回代求D -> 排重和检查退化
```

### 2.4 模型标签
- model_id：coordinate_quadrilateral_existence
- model_name：坐标四边形存在性：平行四边形/矩形/菱形
- configuration：三定一动、两定两动、固定顺序、无固定顺序。
- 可迁移方向：求第四点、动点轨迹交点、所有存在点、参数范围、与函数图像结合。
- 非同构边界：梯形、正方形、圆上点、复杂二次曲线属于后续扩展；本轮不引入。

## 三、关键转化
- 最关键的转化：把“特殊四边形存在”转化为“三角形条件 + 平行四边形对角关系”。
- 为什么降低计算量：平行四边形只需线性方程；矩形/菱形只在确定 $C$ 时使用一次距离条件，求 $D$ 回到线性关系。
- 不转化时的低效路径：分别写平行、垂直、长度相等，多方程混在一起，容易漏解或算错。

## 四、标准路径骨架
1. 先做什么：读题目是否固定顺序；把已知点和动点坐标全部写出来。
2. 再做什么：若固定顺序，按题目顺序确定对角顶点；若无固定顺序，列三种对角配对。
3. 建立什么关系：平行四边形列坐标和；矩形列勾股直角；菱形列等腰距离。
4. 如何求解：先求参数或 $C$，再用对应平行四边形公式求 $D$。
5. 需要检查什么：点是否重合，三点是否共线，答案是否重复，是否满足轨迹条件。

## 四点五、标准完整解与验算
- 关键交点/关键量：对角顶点配对；距离平方 $AB^2,AC^2,BC^2$；动点参数。
- 面积/方程/关系式：
  - 平行四边形固定顺序 $ABCD$：$D=A+C-B$。
  - 四点构成平行四边形：$D=A+B-C$，$D=A+C-B$，$D=B+C-A$ 三类。
  - 矩形三类直角：$AB^2+AC^2=BC^2$，$AB^2+BC^2=AC^2$，$AC^2+BC^2=AB^2$。
  - 菱形三类等腰：$AB=AC$，$AB=BC$，$AC=BC$。
- 完整求解过程：
  - 平行四边形 $ABCD$：若 $A(1,2)$，$B(4,3)$，$C(6,7)$，则 $D=A+C-B=(1+6-4,2+7-3)=(3,6)$。
  - 四点构成平行四边形：同样的 $A,B,C$，三种候选为 $A+B-C=(-1,-2)$，$A+C-B=(3,6)$，$B+C-A=(9,8)$。
  - 矩形 $ABCD$：已知 $A(0,0)$，$B(4,0)$，$C$ 在 $x=4$ 上，设 $C(4,t)$。固定顺序时 $\angle ABC=90^\circ$，直接 $C$ 在过 $B$ 的竖线上，且不与 $B$ 重合；若题目给 $C$ 在第一象限且另有限制可确定 $t$。常规存在性题会给一条轨迹或方程让 $t$ 被解出。
  - 矩形“构成”：设 $C(t,2t-2)$，分别列三种勾股方程，求出所有 $C$，再按直角位置对应公式求 $D$。
  - 菱形“构成”：设 $C(t,\cdots)$，分别列三种等腰方程，求出所有 $C$，再按对应对角配对求 $D$。
- 最终答案：由具体轨迹确定；若多种分类成立，必须全部列出。
- 排除值：点重合、三点共线、四边形面积为 $0$、不满足给定轨迹的参数。
- 退化情形：$C=A$ 或 $C=B$ 时无法构成有效四边形；两种分类可能给出同一点，需要排重。
- 验算：把候选点代回原轨迹，再检查对角线中点是否相同；矩形检查勾股，菱形检查相邻边相等。
- 本题最短可靠路径：先分类，再列方程，不边算边猜图形。

## 五、出题人逻辑
- 诱导学生硬算的位置：直接设 $D(x,y)$，同时列平行、垂直、相等，导致方程太多。
- 真正的捷径：所有四边形先回到平行四边形对角线；矩形/菱形只负责筛选 $C$。
- 训练的可迁移能力：识别“固定顺序”和“构成”的差别，并能按对角关系分类。

## 六、学生卡点预测
- 读题/入手动作卡点：看不出“平行四边形 $ABCD$”与“四点构成平行四边形”的区别。
- 建模/关系入口卡点：不会把三种对角情况写成坐标和方程；矩形/菱形不知道该在三角形 $ABC$ 上分类。
- 求解/检查卡点：漏情况、重复答案未合并、点重合未排除、距离平方计算出错。

## 七、变式原则
- 核心不变量：存在性问题先分类，再用坐标关系列方程。
- 表层特征：三定一动、两定两动、动点在坐标轴/直线/函数图像上、固定顺序/无固定顺序。
- 可变维度：换图形类型、换问法、换轨迹、增加排除条件。
- 深化阶梯：
  1. 固定顺序平行四边形三定一动。
  2. 无固定顺序平行四边形三定一动。
  3. 两定两动平行四边形，列两元一次方程。
  4. 固定顺序矩形，先求 $C$ 再求 $D$。
  5. 无固定顺序矩形，三种直角分类。
  6. 菱形存在性，三种等腰分类。
  7. 条件包装：动点在一次函数上，要求所有 $C,D$。
- 允许的变换：整数坐标、简单一次函数轨迹、坐标轴轨迹、距离平方为小整数。
- 禁止的变换：复杂二次曲线、多参数范围讨论、圆与切线、三角函数。
- 表征切换：点坐标、参数点、对角线中点、距离平方、方程组。
- 包装方式：“四点构成”“以某四点为顶点”“存在点 $D$ 使得……”“点 $C$ 在直线上”。
- 近迁移例子：给 $A,B,C$ 求所有 $D$ 使四点构成平行四边形。
- 远迁移例子：给 $A,B$ 和 $C$ 在直线 $y=x+1$ 上，求所有矩形或菱形的 $C,D$。
- 反例/伪变式：只按固定顺序做“构成”题；菱形题误用直角条件；矩形题误用等腰条件。

## 八、计算复杂度预算
- 原题计算层级：坐标和、一次方程、简单平方差。
- 允许小步上升到：一元二次方程但可因式分解出整数根。
- 禁止引入的计算负担：复杂根式、参数不等式、多个动点非线性联立。
- 必须保留的可见支架：分类表、公式表、每类对应的 $D$ 公式。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先讲平行四边形三定一动，再把矩形/菱形看成“先找 $C$，再求 $D$”。
- 本题讲解目标：让学生掌握存在性题的分类框架，而不是只会算一个固定公式。
- 不要直接讲的抽象话：不要只说“分类讨论”，要写清“按谁和谁对角/谁是直角/哪两边相等”。
- 必须先问的问题：题目有没有固定顺序？已知点里哪两个可能是对角？动点坐标怎么设？
- 关键讲解顺序：平行四边形对角关系 -> 无顺序三分类 -> 矩形直角三分类 -> 菱形等腰三分类。
- 最适合的具体数值例子：$A(1,2),B(4,3),C(6,7)$ 求所有平行四边形第四点。
- 讲到哪里停下来让学生回答：让学生补出三种 $D$ 公式；让学生判断矩形三类勾股分别对应哪个 $D$ 公式。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：判断固定顺序还是构成，写出要讨论几类。
- 若卡在建模或关系入口，出什么题：只要求列出三种 $D$ 公式，不求复杂参数。
- 若卡在求解和检查，出什么题：给简单轨迹，求 $C$ 参数并回代检查。
- 若原题已稳，如何小步迁移：从平行四边形迁移到矩形直角分类。
- 若结构识别已稳，如何深化/抽象/包装：从矩形迁移到菱形等腰分类，并加入一次函数轨迹。
- 禁止出的跑偏变式：正方形综合、圆上动点、复杂参数范围。

## 十点五、推荐图形请求包（可选）
- 是否需要图：否。此专题核心是坐标分类表和方程，不依赖精确几何图。
- 图形类型：`coordinate_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：$A,B,C,D$ 四点和对角线。
- 需要突出给学生看的关系：对角线中点相同、三角形 $ABC$ 的直角/等腰分类。
- 图中不能暗示的错误性质：不要固定成一种对角关系；不要把“构成”题画成只有 $ABCD$ 顺序。
- 图失败时的降级方案：用分类表替代。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "坐标四边形存在性：平行四边形、矩形、菱形",
  "core_transformation": "先设动点坐标并按对角/直角/等腰分类，再列方程求参数和D",
  "structure_representation": {
    "task_type": "existence_or_parameter",
    "is_full_structural_analysis_worthy": true,
    "reason": "固定顺序与无顺序构成会改变分类数量，矩形和菱形又分别追加直角/等腰筛选",
    "surface_topic": "特殊四边形坐标存在性",
    "model_name": "坐标四边形存在性分类模型"
  },
  "concept_criteria": {
    "necessary_conditions": ["平行四边形对角线中点相同", "矩形有直角", "菱形有相邻边相等"],
    "sufficient_conditions": ["固定顺序时确定对角配对", "无顺序构成时三种对角配对全讨论"],
    "common_distractors": ["漏分类", "混淆ABCD与构成", "矩形菱形条件互用"],
    "shortest_check": "先看是否固定顺序，再确定对角配对"
  },
  "application_quantity_network": {
    "quantities": [
      {"name": "D", "type": "coordinate_point", "unit": "none", "known_or_unknown": "unknown", "relation": "由对角线中点相同求出"},
      {"name": "C", "type": "parameter_point", "unit": "none", "known_or_unknown": "unknown_or_given", "relation": "由轨迹设参数"},
      {"name": "distance_squared", "type": "number", "unit": "square_unit", "known_or_unknown": "derived", "relation": "矩形/菱形筛选条件"}
    ],
    "model_equations": ["P+Q=R+S", "right triangle Pythagorean equations", "isosceles distance equations"],
    "target": "求所有存在的C,D或D"
  },
  "proposition_network": {
    "propositions": [
      {"id": "P1", "source": "given", "statement": "已知定点和动点轨迹", "type": "coordinate_setup"},
      {"id": "P2", "source": "construction", "statement": "设出未知点坐标", "type": "parameterization"},
      {"id": "P3", "source": "theorem", "statement": "平行四边形对角线互相平分", "type": "parallelogram"},
      {"id": "P4", "source": "theorem", "statement": "矩形三顶点构成直角三角形", "type": "rectangle"},
      {"id": "P5", "source": "theorem", "statement": "菱形三顶点构成等腰三角形", "type": "rhombus"},
      {"id": "P6", "source": "check", "statement": "排除退化与重复答案", "type": "verification"}
    ],
    "relations": [
      {"id": "R1", "given": ["P1"], "derive": "P2", "method": "轨迹参数化", "teaching_note": "先把坐标写全"},
      {"id": "R2", "given": ["P2", "P3"], "derive": "D_candidates", "method": "对角线中点坐标相等", "teaching_note": "固定顺序一类，构成题三类"},
      {"id": "R3", "given": ["D_candidates", "P4"], "derive": "rectangle_candidates", "method": "三种直角勾股分类", "teaching_note": "直角在A/B/C"},
      {"id": "R4", "given": ["D_candidates", "P5"], "derive": "rhombus_candidates", "method": "三种等腰距离分类", "teaching_note": "AB=AC, AB=BC, AC=BC"},
      {"id": "R5", "given": ["P6"], "derive": "final_answers", "method": "回代和排重", "teaching_note": "不可省略"}
    ],
    "target": "所有满足条件的点坐标",
    "main_chain": ["P1", "P2", "P3", "P4/P5", "P6", "Answer"],
    "branch_cases": ["固定顺序", "无顺序构成", "三种直角", "三种等腰"],
    "diagram_dependent_relations": []
  },
  "model_tags": {
    "model_id": "coordinate_quadrilateral_existence",
    "model_name": "坐标四边形存在性分类模型",
    "configuration": {
      "given": ["fixed points", "moving point trajectory", "quadrilateral type"],
      "target": "all coordinate candidates"
    },
    "transfer_directions": ["parallelogram", "rectangle", "rhombus", "fixed order", "unordered constitution"],
    "non_isomorphic_boundaries": ["square", "trapezoid", "circle locus", "complex parameter range"]
  },
  "solution_skeleton": ["判断问法", "设点坐标", "分类列方程", "求参数", "回代求D", "排除退化"],
  "canonical_solution": {
    "key_quantities": ["对角线配对", "距离平方", "动点参数"],
    "equation": "P+Q=R+S plus Pythagorean/equal-distance constraints",
    "answer_set": ["由具体数值决定，可能多解"],
    "excluded_values": ["点重合", "三点共线", "重复答案"],
    "degenerate_cases": ["C=A", "C=B", "面积为0"],
    "verification": "代回轨迹、对角线中点、直角或等腰条件",
    "shortest_reliable_path": "先平行四边形分类，再追加矩形/菱形筛选"
  },
  "common_blockers": {
    "read_context_or_find_entry": ["分不清ABCD和构成", "不知道先设点"],
    "build_relation": ["不会写三种对角关系", "矩形/菱形分类条件错"],
    "solve_and_check": ["漏解", "重复计数", "不排除退化"]
  },
  "variation_rules": {
    "core_invariant": "坐标存在性先分类再列方程",
    "surface_features": ["固定顺序", "构成", "点在轨迹上", "图形类型"],
    "variation_dimensions": ["changed_question", "changed_representation", "packaged_condition", "partially_hidden"],
    "depth_ladder": ["固定顺序平行四边形", "无顺序平行四边形", "两定两动", "固定顺序矩形", "无顺序矩形", "菱形", "函数轨迹包装"],
    "allowed_transforms": ["整数点", "坐标轴轨迹", "一次函数轨迹", "简单距离平方"],
    "forbidden_transforms": ["复杂二次曲线", "圆切线", "正方形综合"],
    "cognitive_load_budget": "每题只增加一种分类或一个简单轨迹条件",
    "representation_options": ["坐标和", "中点", "距离平方", "方程组"],
    "packaging_options": ["构成某图形", "存在点D", "点C在某直线上"],
    "near_transfer_examples": ["给A,B,C求所有平行四边形D"],
    "far_transfer_examples": ["给A,B和C在一次函数上求矩形或菱形的C,D"],
    "non_examples": ["无顺序题只按ABCD顺序做", "矩形题用等腰条件"]
  },
  "complexity_budget": {
    "original_level": "整数坐标、一次方程、简单勾股/等腰",
    "max_next_step": "可因式分解的一元二次",
    "forbidden_load": ["复杂根式", "双参数非线性联立", "参数范围讨论"],
    "required_scaffolds": ["分类表", "每类D公式", "回代检查"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["find_entry", "build_relation", "transfer"],
    "goal": "讲清平行四边形、矩形、菱形存在性的一套分类流程",
    "avoid_abstract_phrases": ["分类讨论即可", "显然成立"],
    "must_ask_first": ["是否固定顺序", "谁和谁对角", "C点如何设"],
    "teaching_sequence": ["平行四边形", "矩形", "菱形"],
    "concrete_probe_example": "A(1,2), B(4,3), C(6,7)",
    "pause_points": ["让学生写三种D公式", "让学生匹配矩形直角和D公式", "让学生匹配菱形等腰和D公式"]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": ["判断ABCD与构成"],
    "build_relation_tasks": ["写三种对角关系", "列直角/等腰方程"],
    "solve_and_check_tasks": ["解简单参数并回代"],
    "transfer_tasks": ["矩形和菱形从三角形ABC筛选"],
    "hidden_structure_or_reverse_tasks": ["一次函数轨迹包装"],
    "forbidden_variations": ["正方形圆综合", "复杂参数范围"]
  },
  "diagram_request_packet": {
    "needs_diagram": false,
    "diagram_type": "coordinate_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "D"],
      "segments": ["diagonals", "sides"],
      "curves": ["optional line locus"],
      "constraints": ["midpoints coincide", "right angle or equal sides"]
    },
    "focus": "分类关系而非比例绘图",
    "must_not_imply": ["不要固定一种对角关系", "不要暗示矩形或菱形唯一"],
    "fallback": "使用分类表"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.assignment.yaml；随后使用 math-adaptive-practice-latex-data 生成学生版和教师版练习。工作流：math-structure-analysis -> math-student-explanation-latex-data -> math-adaptive-practice-latex-data -> math-assignment-latex render/compile -> math-homework-review。
