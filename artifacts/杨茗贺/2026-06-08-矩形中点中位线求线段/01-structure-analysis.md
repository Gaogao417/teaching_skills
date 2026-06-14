# 结构分析：矩形中点中位线求线段

## 原题
如图，在矩形 $ABCD$ 中，$AB=6$，$BD=10$，$O$ 为对角线 $BD$ 的中点，$E$ 为边 $BC$ 上一点，连接 $AE$。取 $AE$ 的中点 $F$，连接 $OF$。若 $BE=2$，则 $OF$ 的长为多少？

图形文字说明：矩形按 $A$ 左上、$B$ 左下、$C$ 右下、$D$ 右上标记，点 $E$ 在 $BC$ 上且靠近 $B$，$O$ 在对角线 $BD$ 上，$F$ 在 $AE$ 上。

## 一、题目场景
- 数学对象：矩形 $ABCD$，对角线 $BD$，边上点 $E$，中点 $O,F$。
- 变量/参数：已知 $AB=6$，$BD=10$，$BE=2$。
- 函数/图形：矩形内的线段中点与中位线结构。
- 已知条件：$O$ 是 $BD$ 的中点，$F$ 是 $AE$ 的中点，$E$ 在 $BC$ 上。
- 要求目标：求 $OF$ 的长度。

## 二、核心结构
- 表面考点：矩形、勾股定理、中点。
- 本质考点：补取第三个中点，把两个已有中点分别放进两个三角形的中位线。
- 一句话问题模式：平行线间有两条截线，已知截线端点位置，求两个截线中点之间的距离。

## 三、关键转化
- 最关键的转化：取 $M$ 为 $AB$ 的中点，使 $M,O$ 成为 $\triangle ABD$ 的两边中点，$M,F$ 成为 $\triangle ABE$ 的两边中点。
- 为什么降低计算量：不用求 $O,F$ 的坐标，也不用算斜率；直接用中位线得到 $MO=\dfrac12AD$，$MF=\dfrac12BE$，再相减。
- 不转化时的低效路径：建立坐标系，求 $A,B,C,D,E,O,F$ 坐标后用距离公式；虽然可行，但没有训练到“补中点”的几何结构。

## 四、标准路径骨架
1. 先做什么：由矩形和勾股定理求 $BC=AD=8$。
2. 再做什么：取 $AB$ 的中点 $M$。
3. 建立什么关系：在 $\triangle ABD$ 中，$M,O$ 是两边中点；在 $\triangle ABE$ 中，$M,F$ 是两边中点。
4. 如何求解：用中位线定理得 $MO=4$，$MF=1$，所以 $OF=MO-MF=3$。
5. 需要检查什么：确认 $M,F,O$ 共线且 $F$ 在 $MO$ 上，不能把 $MO$ 与 $MF$ 误加。

## 四点五、标准完整解与验算
- 关键交点/关键量：$BC=\sqrt{BD^2-AB^2}=\sqrt{100-36}=8$，所以 $AD=8$。
- 面积/方程/关系式：中位线关系 $MO=\dfrac12AD$，$MF=\dfrac12BE$。
- 完整求解过程：
  1. 在矩形 $ABCD$ 中，$\angle ABC=90^\circ$，所以
     $$
     BC=\sqrt{BD^2-AB^2}=\sqrt{10^2-6^2}=8.
     $$
     因此 $AD=BC=8$。
  2. 取 $M$ 为 $AB$ 的中点。
  3. 在 $\triangle ABD$ 中，$M$ 是 $AB$ 的中点，$O$ 是 $BD$ 的中点，所以 $MO$ 是中位线：
     $$
     MO=\frac12AD=4.
     $$
  4. 在 $\triangle ABE$ 中，$M$ 是 $AB$ 的中点，$F$ 是 $AE$ 的中点，所以 $MF$ 是中位线：
     $$
     MF=\frac12BE=1.
     $$
  5. 两条中位线都平行于 $BE,AD$，而 $BE\parallel AD$，所以 $M,F,O$ 在同一直线上。图中 $F$ 在 $M$ 与 $O$ 之间，因此
     $$
     OF=MO-MF=4-1=3.
     $$
- 最终答案：$3$。
- 排除值：无。
- 退化情形：若 $E$ 与 $B$ 重合或 $BE$ 超出 $BC$，结构会退化；本题 $BE=2<BC=8$，合法。
- 验算：坐标验算可设 $B(0,0),A(0,6),C(8,0),D(8,6),E(2,0)$，则 $O(4,3),F(1,3)$，$OF=3$。
- 本题最短可靠路径：勾股求宽，补 $AB$ 中点 $M$，两次中位线，相减。

## 五、出题人逻辑
- 诱导学生硬算的位置：看到矩形、对角线、中点，容易直接上坐标或距离公式。
- 真正的捷径：已有 $O,F$ 两个中点时，主动补第三个中点 $M$，让它同时服务两个三角形。
- 训练的可迁移能力：在平行线间求中点连线时，把“中点”转成“中位线长度是第三边一半”。

## 六、学生卡点预测
- 读题/入手动作卡点：只盯着 $OF$，不知道为什么要在 $AB$ 上新增点。
- 建模/关系入口卡点：知道 $O,F$ 是中点，但不会把它们分别放进 $\triangle ABD$ 和 $\triangle ABE$。
- 求解/检查卡点：算出 $MO=4$、$MF=1$ 后误写 $OF=5$，没有判断点的顺序。

## 七、变式原则
- 核心不变量：补取同一条边的中点，让两个已有中点分别构成两条平行中位线，目标段等于两个半边长之差。
- 表层特征：矩形、对角线中点、边上点、截线中点。
- 可变维度：矩形边长、对角线长度、边上点到端点距离、所求中点连线长度或反求边上距离。
- 深化阶梯：先同结构换数，再反求 $BE$，再把矩形换成两条平行线间的图形表达。
- 允许的变换：保持 $E$ 在 $BC$ 上，保持 $O$ 是 $BD$ 中点、$F$ 是 $AE$ 中点，允许换 $AB,BD,BE$。
- 禁止的变换：把 $E$ 放到非平行边上，或取消中点条件后仍要求套中位线。
- 表征切换：几何图、文字描述、坐标验算三种表征可切换。
- 包装方式：把“矩形”包装成“两条平行线间的两条截线”。
- 近迁移例子：给 $AB=8,BD=17,BE=5$，求同样的 $OF$。
- 远迁移例子：在梯形或两条平行线之间，两条截线的中点连线长度与两底端点距离的关系。
- 反例/伪变式：若 $F$ 不是 $AE$ 中点，而是三等分点，则不能直接用中位线。

## 八、计算复杂度预算
- 原题计算层级：一次勾股，两个一半，相减。
- 允许小步上升到：勾股数换成仍整洁的 $8,15,17$ 或 $5,12,13$。
- 禁止引入的计算负担：复杂根式、相似三角形多层套算、坐标距离平方根。
- 必须保留的可见支架：图上明确 $O,F$ 是中点，并让辅助中点 $M$ 可被学生看到。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先问“还缺哪个中点，能让 $O$ 和 $F$ 分别进入中位线？”
- 本题讲解目标：让学生会主动补取 $AB$ 的中点 $M$，并把 $MO$、$MF$ 分别解释为中位线。
- 不要直接讲的抽象话：不要只说“利用中位线定理”而不说明取哪个点、在哪个三角形里用。
- 必须先问的问题：$O$ 是哪条线段的中点？$F$ 是哪条线段的中点？如果想用中位线，还需要补哪个中点？
- 关键讲解顺序：求 $AD$；取 $M$；看 $\triangle ABD$ 得 $MO$；看 $\triangle ABE$ 得 $MF$；判断相减。
- 最适合的具体数值例子：$AD=8$，$BE=2$，一半分别是 $4$ 和 $1$。
- 讲到哪里停下来让学生回答：画出 $M$ 后，停下来让学生说出 $MO$ 和 $MF$ 分别等于哪条边的一半。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：只标两个中点，让学生补第三个中点并圈出两个三角形。
- 若卡在建模或关系入口，出什么题：给出图，让学生填写“在 $\triangle \_\_\_$ 中，哪两个点是中点”。
- 若卡在求解和检查，出什么题：给 $AD,BE$ 直接求 $OF$，训练相减和点序判断。
- 若原题已稳，如何小步迁移：换数或反求 $BE$。
- 若结构识别已稳，如何深化/抽象/包装：去掉矩形名称，只给两条平行线和两条截线。
- 禁止出的跑偏变式：不要同时引入角平分线、垂线、圆等新结构。

## 十点五、推荐图形请求包（可选）
- 是否需要图：是。
- 图形类型：`coordinate_geometry`。
- 用图意图：`student_explanation`。
- 需要出现的对象：矩形 $ABCD$，点 $E,O,F$，辅助点 $M$，线段 $AE,BD,OF,MO,MF$。
- 需要突出给学生看的关系：$M,O$ 是 $\triangle ABD$ 的两边中点；$M,F$ 是 $\triangle ABE$ 的两边中点；$MO$ 与 $MF$ 共线。
- 图中不能暗示的错误性质：不要把 $OF$ 画成斜线；不要暗示 $F$ 是 $MO$ 中点；不要让 $E$ 超过 $BC$ 中点。
- 图失败时的降级方案：用坐标描述 $B(0,0),A(0,6),C(8,0),D(8,6),E(2,0),M(0,3),F(1,3),O(4,3)$。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "矩形内两条截线的中点连线长度",
  "core_transformation": "取 AB 的中点 M，使 MO 和 MF 分别成为三角形 ABD、ABE 的中位线",
  "solution_skeleton": ["勾股求 BC=AD", "取 AB 中点 M", "两次中位线求 MO 与 MF", "用 OF=MO-MF"],
  "canonical_solution": {
    "key_quantities": ["BC=AD=8", "MO=4", "MF=1"],
    "equation": "OF=AD/2-BE/2",
    "answer_set": ["3"],
    "excluded_values": [],
    "degenerate_cases": ["BE 必须在 BC 范围内"],
    "verification": "坐标验算 O(4,3), F(1,3), OF=3",
    "shortest_reliable_path": "补取 AB 中点 M，两次中位线后相减"
  },
  "common_blockers": {
    "read_context_or_find_entry": ["不知道为什么要新增中点 M"],
    "build_relation": ["不能把 O,F 分别放进两个三角形的中位线"],
    "solve_and_check": ["把 4 和 1 相加，忽略点序"]
  },
  "variation_rules": {
    "core_invariant": "同一辅助中点连接两个已有中点，形成两条同向中位线，目标段为半边长之差",
    "surface_features": ["矩形", "边上点", "对角线中点", "截线中点"],
    "variation_dimensions": ["换数", "反求 BE", "改成平行线间截线表达"],
    "depth_ladder": ["原题复现", "同结构换数", "反求边上距离", "去掉矩形包装为平行线间问题"],
    "allowed_transforms": ["保持 E 在 BC 上", "保持 O,F 为中点", "保持 AB 与 CD 平行、AD 与 BC 平行"],
    "forbidden_transforms": ["取消中点条件", "把 E 放到非平行边上", "引入非必要圆或角平分线"],
    "cognitive_load_budget": "一次勾股、两个一半、一次相减",
    "representation_options": ["几何图", "坐标验算", "平行线间截线"],
    "packaging_options": ["矩形题", "平行线间线段题"],
    "near_transfer_examples": ["AB=8,BD=17,BE=5，求 OF"],
    "far_transfer_examples": ["两条平行线间两条截线端点距离已知，求截线中点连线"],
    "non_examples": ["F 不是 AE 中点却仍套中位线"]
  },
  "complexity_budget": {
    "original_level": "一次勾股 + 中位线",
    "max_next_step": "反求 BE 或换整洁勾股数组",
    "forbidden_load": ["复杂根式", "多层相似", "坐标距离公式主解"],
    "required_scaffolds": ["明确辅助点 M", "标出两个三角形", "提示相减而非相加"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["find_entry", "build_relation"],
    "goal": "学生能主动补取 AB 中点 M，并说清两个中位线关系",
    "avoid_abstract_phrases": ["直接用中位线", "显然"],
    "must_ask_first": ["O、F 分别是哪条线段的中点？", "还缺哪个中点可以组成中位线？"],
    "teaching_sequence": ["求 AD", "取 M", "在三角形 ABD 中看 MO", "在三角形 ABE 中看 MF", "相减得 OF"],
    "concrete_probe_example": "AD=8, BE=2，所以一半分别为 4 和 1",
    "pause_points": ["画出 M 后让学生说 MO、MF 分别是哪条边的一半"]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": ["给图补辅助中点 M"],
    "build_relation_tasks": ["填写两个中位线所在三角形"],
    "solve_and_check_tasks": ["判断 OF 是 4-1 还是 4+1"],
    "transfer_tasks": ["换数求 OF 或反求 BE"],
    "hidden_structure_or_reverse_tasks": ["平行线间截线中点距离问题"],
    "forbidden_variations": ["引入角平分线或圆导致结构跑偏"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "coordinate_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "D", "E", "O", "F", "M"],
      "segments": ["AB", "BC", "CD", "DA", "BD", "AE", "MO", "MF", "OF"],
      "curves": [],
      "constraints": ["AB=6", "BD=10", "BE=2", "O is midpoint of BD", "F is midpoint of AE", "M is midpoint of AB"]
    },
    "teaching_focus": ["补取 M", "两次中位线", "OF=MO-MF"],
    "must_not_imply": ["不要暗示 F 是 MO 的中点", "不要把 OF 画成斜线", "不要让 E 超出 BC"],
    "fallback": "textual_diagram_description"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.plan.assignment.yaml 或 02-student-explanation.assignment.yaml。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
