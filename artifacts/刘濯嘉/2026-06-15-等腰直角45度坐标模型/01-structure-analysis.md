# 结构分析：等腰直角与 45 度坐标模型复习

## 原题
给刘濯嘉生成复习讲义，主题为等腰直角三角形和 45 度相关的基本坐标模型：

1. 等腰直角三角形 $ABC$ 中知道两个点坐标，求第三个点坐标。
   - 若要求底角顶点 $C$：过直角顶点 $A$ 作竖线 $l$，过 $B,C$ 向 $l$ 作垂线，垂足分别为 $M,N$；证明两个小直角三角形全等；先用“右几上几”的语言读出 $\overrightarrow{AB}$ 的走法，再得到 $\overrightarrow{AC}$ 的走法，最后由 $A$ 到 $C$ 定坐标。
   - 若要求顶角顶点 $A$：取 $BC$ 中点 $D$，把 $\triangle DBA$ 看成等腰直角三角形，转化为“已知直角顶点 $D$ 和一个底角顶点 $B$，求另一个底角顶点 $A$”。
2. 45 度模型：已知 $A,B$ 坐标，若 $\angle ABC=45^\circ$ 或“把直线 $AB$ 绕 $B$ 旋转 $45^\circ$”，要求 $BC$ 解析式。思路是让 $A$ 当直角顶点，作等腰直角三角形 $ABP$，求出 $P$ 点坐标，则直线 $BP$ 就是 $BC$ 的候选直线。进一步可利用解析式与点 $C$ 或其他直线求交点、面积等。
3. 辨析提问：若只有 $A,B$ 坐标并要求 $\angle ACB=45^\circ$，应判断信息是否足够；一般不能唯一确定直线 $BC$，还需要 $C$ 所在直线、点 $C$ 的某个坐标或其他附加条件。

## 一、题目场景
- 数学对象：坐标平面中的等腰直角三角形、45 度旋转直线、一次函数直线。
- 变量/参数：点 $A(x_A,y_A)$、$B(x_B,y_B)$、待求点 $C$ 或辅助点 $P$。
- 函数/图形：直线 $BC$ 的解析式 $y=kx+b$，以及线段 $AB$ 旋转 $90^\circ$ 或由等腰直角生成 $45^\circ$。
- 已知条件：两个点坐标，等腰直角或某个角为 $45^\circ$。
- 要求目标：求第三点坐标、求经过旋转后直线的解析式、或辨析条件是否充分。

## 二、核心结构
### 2.1 表层信息
- 表面考点：坐标、等腰直角三角形、45 度、一次函数解析式。
- 题型功能：`composite_problem`
- 是否值得完整 structural analysis：是；理由：同一结构会以“求点坐标”“求直线解析式”“求交点/面积”等形式反复包装，学生容易只记公式而不识别入口。
- 一句话问题模式：已知一条线段的坐标走法，用等腰直角把它旋转 $90^\circ$，再用两个点确定点或直线。

### 2.2 结构表达
#### 判别条件表（概念辨析题用；不适用则写“无”）
- 必要条件：必须知道旋转中心或直角顶点；若只知道一个 $45^\circ$ 角，还要知道对应射线或待求点的约束。
- 充分条件：已知直角顶点和一个底角顶点，可以求另一个底角顶点的两个候选位置；若题目给出“在某侧/某象限/在某条直线上”，可确定唯一解。
- 常见干扰项：把 $x,y$ 坐标差直接当坐标；忘记旋转有两个方向；把 $\angle ABC=45^\circ$ 与 $\angle ACB=45^\circ$ 混同。
- 最短检查动作：先问“角的顶点是谁？旋转中心是谁？题目有没有给定方向或所在侧？”

#### 情景量表（应用题用；不适用则写“无”）
| 量 | 类型/单位 | 题设关系 | 未知/已知 |
|---|---|---|---|
| $\overrightarrow{AB}$ 的走法 | 水平/竖直步数 | 由 $A$ 到 $B$ 读“右/左、上/下” | 已知 |
| $\overrightarrow{AC}$ 或 $\overrightarrow{AP}$ 的走法 | 旋转后的步数 | 与 $\overrightarrow{AB}$ 等长且垂直 | 未知 |
| 直线 $BP$ | 一次函数 | 由 $B,P$ 两点确定 | 待求 |

#### 命题网络（所有题型都写；简单题写简版）
- P1（题设）：已知 $A,B$ 两点坐标。
- P2（可推）：由 $A$ 到 $B$ 可读出走法，例如“右 $p$ 上 $q$”。
- P3（定理）：等腰直角中两腰相等且垂直，线段旋转 $90^\circ$ 后长度不变、方向互换。
- P4（构造）：过直角顶点作竖线，向竖线作垂线，可得到一对全等直角三角形。
- P5（可推）：若 $\overrightarrow{AB}$ 是“右 $p$ 上 $q$”，则一个垂直等长走法是“右 $q$ 下 $p$”，另一个是“左 $q$ 上 $p$”。
- P6（目标）：由直角顶点和旋转后的走法确定第三点坐标。
- P7（构造）：若要求顶角顶点 $A$，取 $BC$ 中点 $D$。
- P8（可推）：$\triangle DBA$ 是以 $D$ 为直角顶点的等腰直角三角形。
- P9（构造）：若 $\angle ABC=45^\circ$，构造等腰直角三角形 $ABP$，让 $A$ 为直角顶点。
- P10（可推）：$\angle ABP=45^\circ$，所以 $B,P,C$ 可共线，直线 $BP$ 是 $BC$ 的候选直线。
- P11（检查）：只有“已知 $A,B$ 且 $\angle ACB=45^\circ$”不能唯一确定 $BC$。
- R1：P1 -> P2，方法：读水平差和竖直差，用动作语言表达。
- R2：P2 + P3 + P4 -> P5，方法：旋转 $90^\circ$/全等小直角三角形。
- R3：P5 + 直角顶点坐标 -> P6，方法：从已知点按走法平移。
- R4：P7 + P8 -> 求顶角顶点，方法：中点转化为底角顶点模型。
- R5：P9 + P10 -> 求 $BC$ 解析式，方法：先求辅助点 $P$，再用两点式/待定系数法求直线。
- R6：P11 -> 条件辨析，方法：识别角顶点改变导致的 locus 问题。
- 目标：学生能在题面变化时先找“直角顶点/45 度顶点/旋转中心”，再选模型。

### 2.3 解题主链
```text
读 AB 走法 -> 旋转 90 度得到候选走法 -> 定点坐标或辅助点 -> 两点定直线 -> 交点/面积等后续问题
```

### 2.4 模型标签
- model_id：coordinate_isosceles_right_45
- model_name：坐标系中的等腰直角与 45 度旋转模型
- configuration：已知两个点，目标为第三点坐标或旋转直线解析式。
- 可迁移方向：求点坐标、求直线解析式、求交点、求三角形面积、判断条件是否充分。
- 非同构边界：只给 $\angle ACB=45^\circ$ 且无额外条件时，不能唯一确定 $BC$；引入圆、相似、三角函数时已超出本轮核心。

## 三、关键转化
- 最关键的转化：把“等腰直角/45 度”转化成“已知走法旋转 $90^\circ$”。
- 为什么降低计算量：不需要斜率乘积、三角函数或旋转公式，只做水平步数和竖直步数交换。
- 不转化时的低效路径：硬设未知点后列距离相等和垂直关系，会产生二次方程或复杂代数。

## 四、标准路径骨架
1. 先做什么：确定直角顶点或 45 度顶点，读出已知线段的走法。
2. 再做什么：把“右 $p$ 上 $q$”旋转成“右 $q$ 下 $p$”或“左 $q$ 上 $p$”。
3. 建立什么关系：两个小直角三角形全等，或等腰直角给出等长垂直。
4. 如何求解：由起点加走法得到点坐标；由两点求直线解析式。
5. 需要检查什么：两个方向是否都可能；题目有没有指定点的位置；角的顶点是否看错。

## 四点五、标准完整解与验算
- 关键交点/关键量：$\overrightarrow{AB}$ 的水平步数和竖直步数；辅助点 $P$；中点 $D$。
- 面积/方程/关系式：直线可用两点式或待定系数法；后续面积用坐标底高或分割法。
- 完整求解过程：
  - 底角顶点：若 $A(1,2)$，$B(2,6)$，则从 $A$ 到 $B$ 是“右 $1$ 上 $4$”。等腰直角在 $A$ 处为直角，另一腰可取“右 $4$ 下 $1$”，得 $C(5,1)$；另一个候选为“左 $4$ 上 $1$”，得 $C(-3,3)$。若题目给 $C$ 在第四象限或在 $A$ 的右下方，则取 $C(5,1)$。
  - 顶角顶点：若 $B(1,5)$，$C(7,-1)$，中点 $D(4,2)$。从 $D$ 到 $B$ 是“左 $3$ 上 $3$”。把它旋转 $90^\circ$，候选走法为“右 $3$ 上 $3$”或“左 $3$ 下 $3$”，所以 $A(7,5)$ 或 $A(1,-1)$。再由题目位置限制取一个。
  - $45^\circ$ 直线：若 $A(1,1)$，$B(4,3)$，从 $A$ 到 $B$ 是“右 $3$ 上 $2$”。作等腰直角三角形 $ABP$，以 $A$ 为直角顶点，取 $\overrightarrow{AP}$ 为“右 $2$ 下 $3$”，得 $P(3,-2)$。直线 $BP$ 过 $B(4,3)$、$P(3,-2)$，斜率 $k=5$，所以 $BP:y=5x-17$。另一个方向取 $P'(-1,4)$，得到另一条候选直线 $y=-\frac15x+\frac{19}{5}$。
- 最终答案：本专题答案依具体数值和方向条件确定；无方向条件时写两个候选。
- 排除值：直线求解析式时若两点横坐标相同，应写成 $x=a$，不能强行写 $y=kx+b$。
- 退化情形：$A,B$ 重合时不能构成三角形；只给一个 45 度角而无位置约束时可能不唯一。
- 验算：旋转后的走法与原走法长度相同；水平竖直步数互换；两条线段点积为 $0$ 的直观检查可用“横竖交叉抵消”给教师侧说明。
- 本题最短可靠路径：读走法、换顺序变方向、定点、求线。

## 五、出题人逻辑
- 诱导学生硬算的位置：设 $C(x,y)$ 后列 $AB=AC$ 与 $AB\perp AC$。
- 真正的捷径：用全等小直角三角形读出旋转后的水平/竖直走法。
- 训练的可迁移能力：从几何条件识别旋转中心，并把几何语言转成坐标动作。

## 六、学生卡点预测
- 读题/入手动作卡点：分不清哪个点是直角顶点、哪个角是 $45^\circ$。
- 建模/关系入口卡点：知道等腰直角但不知道怎么把它变成坐标走法。
- 求解/检查卡点：漏掉另一个旋转方向；求直线时把点代错；忘记条件不足时要说明“不唯一”。

## 七、变式原则
- 核心不变量：已知线段的走法经 $90^\circ$ 旋转，得到等长垂直线段。
- 表层特征：点的坐标、在某侧、求点还是求直线、是否带后续面积。
- 可变维度：换数、换目标、换角顶点、加入方向限制、加入交点或面积。
- 深化阶梯：
  1. 原题复现：给 $A,B$ 求 $C$。
  2. 同结构换数：换成负坐标或跨象限。
  3. 同结构换问法：给 $B,C$ 求 $A$。
  4. 同结构换表征：由点坐标转为直线解析式。
  5. 条件包装：说成“绕 $B$ 旋转 $45^\circ$”。
  6. 结构部分隐藏：先求 $BC$ 再与另一条直线求交点/面积。
  7. 反向构造：判断某条直线是否可能是 $45^\circ$ 旋转线。
- 允许的变换：小整数坐标；给出点在某侧；给出一条简单直线求交点。
- 禁止的变换：同时引入圆、三角函数、复杂参数或无理数斜率；没有额外条件却要求唯一答案。
- 表征切换：坐标点、走法语言、直线解析式、交点面积。
- 包装方式：“等腰直角”“直线绕点旋转 $45^\circ$”“与已知线成 $45^\circ$”。
- 近迁移例子：给 $A(0,1),B(3,5)$，求 $C$ 在 $A$ 右下方的坐标。
- 远迁移例子：先求 $45^\circ$ 直线，再与 $y=x+1$ 的交点构成三角形面积。
- 反例/伪变式：只说 $\angle ACB=45^\circ$，没有 $C$ 的约束，却要求唯一的 $BC$ 解析式。

## 八、计算复杂度预算
- 原题计算层级：整数坐标、一次函数斜率、简单中点。
- 允许小步上升到：负坐标、分数斜率、一个交点或一个面积。
- 禁止引入的计算负担：根式三角函数、复杂二次方程、参数讨论、多条曲线。
- 必须保留的可见支架：动作语言“右/左、上/下”；方向条件；两点定直线。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先从一个“右 $1$ 上 $4$”的具体例子讲底角顶点，再讲中点转化，最后讲 45 度直线。
- 本题讲解目标：让学生会把等腰直角和 45 度都转化为旋转后的走法。
- 不要直接讲的抽象话：不要直接说“旋转矩阵”“向量坐标公式”“斜率乘积为 $-1$”。
- 必须先问的问题：这个角的顶点是谁？哪条线段要旋转？题目指定哪一侧了吗？
- 关键讲解顺序：读走法 -> 旋转走法 -> 定第三点 -> 两点定直线 -> 条件不足辨析。
- 最适合的具体数值例子：$A(1,2),B(2,6)$，从 $A$ 到 $B$ 是“右 $1$ 上 $4$”。
- 讲到哪里停下来让学生回答：说出旋转后的另一个走法；判断 $\angle ACB=45^\circ$ 是否能唯一求 $BC$。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：只问“角的顶点是谁、直角顶点是谁、要旋转哪条线段”。
- 若卡在建模或关系入口，出什么题：给 $A,B$，只要求写两个候选走法，不求坐标。
- 若卡在求解和检查，出什么题：给方向限制，求 $C$ 并验算长度相等。
- 若原题已稳，如何小步迁移：给 $B,C$ 求 $A$，加入中点 $D$。
- 若结构识别已稳，如何深化/抽象/包装：求 $45^\circ$ 直线解析式，并与另一条直线求交点或面积。
- 禁止出的跑偏变式：没有额外条件的 $\angle ACB=45^\circ$ 唯一求线；复杂圆周角题。

## 十点五、推荐图形请求包（可选）
- 是否需要图：否。本轮讲义重点是动作语言，文字和坐标走法足够；若课堂需要，可手动画竖线和垂线。
- 图形类型：`coordinate_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：点 $A,B,C$，过 $A$ 的竖线，垂足 $M,N$。
- 需要突出给学生看的关系：水平步数与竖直步数交换。
- 图中不能暗示的错误性质：不要只画一个方向导致学生忘记另一解。
- 图失败时的降级方案：用“右/左、上/下”的文字路线替代。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "等腰直角/45度坐标旋转模型",
  "core_transformation": "把已知线段的坐标走法旋转90度，再用于求点或求45度直线",
  "structure_representation": {
    "task_type": "composite_problem",
    "is_full_structural_analysis_worthy": true,
    "reason": "同一模型有求点、求线、求交点和条件辨析等多种包装",
    "surface_topic": "等腰直角三角形、45度、一次函数",
    "model_name": "坐标系中的等腰直角与45度旋转模型"
  },
  "concept_criteria": {
    "necessary_conditions": ["知道旋转中心或直角顶点", "知道方向限制或接受两个候选"],
    "sufficient_conditions": ["已知直角顶点和一个底角顶点", "已知AB并指定angle ABC的45度方向"],
    "common_distractors": ["把角顶点看错", "漏掉另一旋转方向", "把坐标差当坐标"],
    "shortest_check": "先问角的顶点、旋转中心、方向条件"
  },
  "application_quantity_network": {
    "quantities": [
      {"name": "AB走法", "type": "horizontal_vertical_steps", "unit": "格", "known_or_unknown": "known", "relation": "由A到B读取"},
      {"name": "旋转后走法", "type": "horizontal_vertical_steps", "unit": "格", "known_or_unknown": "unknown", "relation": "水平竖直交换并改变一个方向"},
      {"name": "直线BP", "type": "linear_function", "unit": "none", "known_or_unknown": "target", "relation": "由B和辅助点P确定"}
    ],
    "model_equations": ["k=(y_P-y_B)/(x_P-x_B)", "y-y_B=k(x-x_B)"],
    "target": "第三点坐标或45度直线解析式"
  },
  "proposition_network": {
    "propositions": [
      {"id": "P1", "source": "given", "statement": "已知A,B两点坐标", "type": "coordinate_points"},
      {"id": "P2", "source": "derived", "statement": "读出AB的水平/竖直走法", "type": "step_vector"},
      {"id": "P3", "source": "theorem", "statement": "等腰直角两腰等长且垂直", "type": "geometry"},
      {"id": "P4", "source": "construction", "statement": "旋转90度得到候选走法", "type": "rotation"},
      {"id": "P5", "source": "target", "statement": "确定第三点或辅助点P", "type": "coordinate_point"},
      {"id": "P6", "source": "target", "statement": "由两点确定45度直线", "type": "linear_function"},
      {"id": "P7", "source": "check", "statement": "检查角顶点与方向条件是否足够", "type": "condition_check"}
    ],
    "relations": [
      {"id": "R1", "given": ["P1"], "derive": "P2", "method": "读坐标走法", "teaching_note": "用右几上几，不先讲向量公式"},
      {"id": "R2", "given": ["P2", "P3"], "derive": "P4", "method": "全等小直角三角形/90度旋转", "teaching_note": "水平竖直交换"},
      {"id": "R3", "given": ["P4"], "derive": "P5", "method": "按走法平移", "teaching_note": "方向条件决定取哪一个"},
      {"id": "R4", "given": ["P5"], "derive": "P6", "method": "两点定直线", "teaching_note": "注意竖直线特例"},
      {"id": "R5", "given": ["P7"], "derive": "P6", "method": "条件充分性判断", "teaching_note": "angle ACB=45 alone is not unique"}
    ],
    "target": "能稳定求坐标、求45度直线并辨析不唯一",
    "main_chain": ["P1", "P2", "P4", "P5", "P6"],
    "branch_cases": ["两个旋转方向", "顶角顶点用中点转化", "angle ACB条件不足"],
    "diagram_dependent_relations": []
  },
  "model_tags": {
    "model_id": "coordinate_isosceles_right_45",
    "model_name": "坐标系中的等腰直角与45度旋转模型",
    "configuration": {
      "given": ["A,B coordinates", "isosceles right or 45 degree condition"],
      "target": "point coordinate or line equation"
    },
    "transfer_directions": ["find third point", "find vertex point", "find 45-degree line", "intersection and area"],
    "non_isomorphic_boundaries": ["only angle ACB=45 with AB known is not enough for a unique BC line"]
  },
  "solution_skeleton": ["读AB走法", "旋转90度得候选走法", "定点或定线", "检查方向与条件充分性"],
  "canonical_solution": {
    "key_quantities": ["AB的水平步数", "AB的竖直步数", "辅助点P", "中点D"],
    "equation": "line through two points",
    "answer_set": ["按具体题目确定一个或两个候选"],
    "excluded_values": ["A=B退化", "竖直线不能写成y=kx+b"],
    "degenerate_cases": ["无方向条件时两解", "ACB=45且无额外条件时不唯一"],
    "verification": "旋转后长度相等且垂直，直线经过两个确定点",
    "shortest_reliable_path": "读走法 -> 旋转 -> 平移 -> 两点定线"
  },
  "common_blockers": {
    "read_context_or_find_entry": ["看错角顶点", "不知道先读哪条线段"],
    "build_relation": ["不会把等腰直角转成水平竖直交换", "不会用中点转化顶角顶点"],
    "solve_and_check": ["漏另一个方向", "求直线解析式代错点", "不知道条件不足要说明"]
  },
  "variation_rules": {
    "core_invariant": "已知走法旋转90度得到等长垂直走法",
    "surface_features": ["坐标", "方向限制", "角顶点", "求点或求线"],
    "variation_dimensions": ["changed_numbers", "changed_question", "changed_representation", "packaged_condition"],
    "depth_ladder": ["复现底角顶点", "换数", "顶角顶点中点转化", "45度求线", "求交点/面积", "条件辨析"],
    "allowed_transforms": ["整数坐标", "负坐标", "简单分数斜率", "一条额外直线"],
    "forbidden_transforms": ["三角函数", "复杂参数", "无条件唯一化ACB=45"],
    "cognitive_load_budget": "每题最多改变一个主维度",
    "representation_options": ["动作语言", "坐标", "一次函数解析式"],
    "packaging_options": ["等腰直角", "旋转45度", "与已知线成45度"],
    "near_transfer_examples": ["已知A,B求C", "已知B,C求A"],
    "far_transfer_examples": ["求45度线后与另一线交点并求面积"],
    "non_examples": ["只给A,B和angle ACB=45却要求唯一BC解析式"]
  },
  "complexity_budget": {
    "original_level": "整数坐标与一次函数",
    "max_next_step": "加入一个简单交点或面积",
    "forbidden_load": ["根式三角函数", "复杂二次方程", "圆周角综合"],
    "required_scaffolds": ["右/左上/下动作语言", "方向限制", "两点定直线"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["find_entry", "build_relation", "transfer"],
    "goal": "讲清底角顶点、顶角顶点、45度直线三类题的统一做法",
    "avoid_abstract_phrases": ["旋转矩阵", "向量坐标公式", "斜率乘积"],
    "must_ask_first": ["角的顶点是谁", "哪条线段要旋转", "题目是否指定方向"],
    "teaching_sequence": ["底角顶点", "顶角顶点中点转化", "45度求线", "ACB条件辨析"],
    "concrete_probe_example": "A(1,2), B(2,6): 右1上4",
    "pause_points": ["让学生说出另一种旋转方向", "让学生判断ACB=45是否唯一"]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": ["判断角顶点和旋转中心"],
    "build_relation_tasks": ["写出旋转后的两个候选走法"],
    "solve_and_check_tasks": ["求点坐标并验算"],
    "transfer_tasks": ["求45度直线解析式", "求交点/面积"],
    "hidden_structure_or_reverse_tasks": ["判断ACB=45条件是否足够"],
    "forbidden_variations": ["无额外条件唯一求ACB=45的BC"]
  },
  "diagram_request_packet": {
    "needs_diagram": false,
    "diagram_type": "coordinate_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "M", "N"],
      "segments": ["AB", "AC"],
      "curves": [],
      "constraints": ["AM vertical", "BM horizontal", "CN horizontal"]
    },
    "focus": "水平竖直步数交换",
    "must_not_imply": ["不要只暗示一个方向", "不要把ACB=45画成唯一直线"],
    "fallback": "用动作语言替代图形"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.assignment.yaml；随后使用 math-adaptive-practice-latex-data 生成学生版和教师版练习。工作流：math-structure-analysis -> math-student-explanation-latex-data -> math-adaptive-practice-latex-data -> math-assignment-latex render/compile -> math-homework-review。
