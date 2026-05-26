# 结构分析：双勾股求边长

## 原题
如图，在三角形 $ABC$ 中，点 $D$ 在射线 $BC$ 上，且 $C$ 在 $B,D$ 之间，$AD=AB$。已知 $AB=15$，$AC=13$，且 $2BD=9BC$，求 $BC$ 的长。

## 一、题目场景
- 数学对象：三角形 $ABC$，点 $D$ 在直线 $BC$ 上，$AD=AB$ 构成以 $A$ 为顶点的等腰三角形 $ABD$。
- 变量/参数：设 $BC=x$，过 $A$ 作 $AH\perp BD$，垂足为 $H$。
- 函数/图形：纯几何线段关系，无函数图像。
- 已知条件：$AB=15$，$AC=13$，$AD=AB$，$2BD=9BC$。
- 要求目标：求 $BC$。

## 二、核心结构
- 表面考点：勾股定理、等腰三角形三线合一、线段比例。
- 本质考点：把同一条高 $AH$ 放进两个直角三角形中，用两次勾股相减消去高。
- 一句话问题模式：等腰给中点，边长条件给底边比例，两次勾股相减求底边。

## 三、关键转化
- 最关键的转化：由 $AD=AB$ 且 $AH\perp BD$，得到 $H$ 是 $BD$ 的中点，所以 $BH=HD=\dfrac12BD$。
- 为什么降低计算量：不需要直接求高 $AH$，两次勾股相减即可消去 $AH^2$。
- 不转化时的低效路径：直接设多个线段和高，列两个含 $AH$ 的方程后陷入多未知量。

## 四、标准路径骨架
1. 先做什么：过 $A$ 作 $AH\perp BD$。
2. 再做什么：利用 $AD=AB$ 判断 $H$ 是 $BD$ 中点。
3. 建立什么关系：由 $2BD=9BC$ 得 $BD=\dfrac92BC$，从而 $BH=\dfrac94BC$，$CH=BH-BC=\dfrac54BC$。
4. 如何求解：在 $\triangle ABH$ 和 $\triangle ACH$ 中分别用勾股定理，再相减。
5. 需要检查什么：点序必须是 $B-C-D$，所以 $H$ 在 $C,D$ 之间，$CH=BH-BC$ 为正。

## 四点五、标准完整解与验算
- 关键交点/关键量：垂足 $H$，线段 $BH$、$CH$、$AH$。
- 面积/方程/关系式：
  - $BH=\dfrac94BC$
  - $CH=\dfrac54BC$
  - $AB^2=AH^2+BH^2$
  - $AC^2=AH^2+CH^2$
- 完整求解过程：
  设 $BC=x$。因为 $2BD=9BC$，所以 $BD=\dfrac92x$。又因为 $AD=AB$，在等腰三角形 $ABD$ 中，底边 $BD$ 上的高 $AH$ 也是中线，所以
  $$
  BH=\frac12BD=\frac94x.
  $$
  由于点序为 $B-C-D$，所以
  $$
  CH=BH-BC=\frac94x-x=\frac54x.
  $$
  在两个直角三角形中用勾股定理：
  $$
  15^2=AH^2+\left(\frac94x\right)^2,\qquad
  13^2=AH^2+\left(\frac54x\right)^2.
  $$
  两式相减：
  $$
  225-169=\left[\left(\frac94\right)^2-\left(\frac54\right)^2\right]x^2
  =\frac{81-25}{16}x^2=\frac72x^2.
  $$
  所以 $56=\dfrac72x^2$，$x^2=16$，又 $x>0$，故 $x=4$。
- 最终答案：$BC=4$。
- 排除值：$BC=-4$ 不符合线段长度。
- 退化情形：若 $D$ 不在 $C$ 的外侧，$CH$ 的表达会改变；本题已指定 $C$ 在 $B,D$ 之间。
- 验算：$BC=4$ 时，$BD=18$，$BH=9$，$CH=5$。由 $AB=15$ 得 $AH=\sqrt{15^2-9^2}=12$；再验 $AC=\sqrt{12^2+5^2}=13$，成立。
- 本题最短可靠路径：作高 $AH$，由等腰得 $BH$，由比例得 $CH$，两次勾股相减。

## 五、出题人逻辑
- 诱导学生硬算的位置：看到 $AD=AB$ 只记成等边关系，却没有想到作底边高。
- 真正的捷径：用等腰三角形三线合一把 $BH$ 和 $CH$ 都表示成 $BC$ 的倍数。
- 训练的可迁移能力：识别“同高双直角三角形”，用勾股相减消元。

## 六、学生卡点预测
- 基础薄弱学生：不知道要过 $A$ 作垂线，或不知道等腰三角形底边上的高也是中线。
- 中等学生：能列两个勾股式，但不会把 $BH$、$CH$ 都用 $BC$ 表示。
- 较强学生：能做出原题，但换成 $BD$ 与 $BC$ 的其他比例后容易漏掉点序。

## 七、变式原则
- 核心不变量：两个直角三角形共享高 $AH$，已知两条斜边，用线段条件表达两个底边，再勾股相减。
- 表层特征：边长数字、$BD$ 与 $BC$ 的比例、所求对象。
- 可变维度：换 $AB,AC$；换 $BD:kBC$；反向给 $BC$ 求 $AC$；隐藏点序描述。
- 深化阶梯：先保留图形和比例，再换数字，再换问法，最后让学生判断条件是否足够。
- 允许的变换：保持 $D$ 在射线 $BC$ 上且 $C$ 在 $B,D$ 之间；保持 $AD=AB$；保持两条已知边分别落在两次勾股中。
- 禁止的变换：引入三角函数、相似证明大链条、面积法混入无关目标、比例导致 $H$ 不在可解释位置。
- 表征切换：文字题、简图题、给出线段比例表。
- 包装方式：把 $2BD=9BC$ 写成“$BD$ 是 $BC$ 的 $\dfrac92$ 倍”或“$BD:BC=9:2$”。
- 近迁移例子：已知 $AB=17$，$AC=10$，$BD=4BC$，求 $BC$。
- 远迁移例子：两个共高直角三角形中，已知两条斜边和底边差，求底边。
- 反例/伪变式：只给 $AD=AB$ 和一条边长，没有第二条边长或边比例，不能唯一求 $BC$。

## 八、计算复杂度预算
- 原题计算层级：一次作辅助线、两个勾股式、一次相减、一次开方。
- 允许小步上升到：比例系数变成简单分数，最后仍能开出整数或根式。
- 禁止引入的计算负担：复杂二次方程、三角函数、多个未知点位置讨论。
- 必须保留的可见支架：点序说明、垂足 $H$、$BH$ 和 $CH$ 的表达。

## 九、推荐讲题任务包
- 适合的学习层级：L1-L3。
- 本题讲解目标：让学生知道“等腰 + 作底边高”会把图形拆成两个可用勾股的直角三角形。
- 不要直接讲的抽象话：不要空说“转化思想”“构造公共量”，要直接指向作高和消去 $AH^2$。
- 必须先问的问题：“$AD=AB$ 说明 $A$ 到哪两个点距离相等？如果作 $AH\perp BD$，$H$ 在 $BD$ 上是什么点？”
- 关键讲解顺序：作高 → 中点 → 表示 $BH,CH$ → 两个勾股式 → 相减 → 验算。
- 最适合的具体数值例子：原题的 $AB=15,AC=13,2BD=9BC$。
- 讲到哪里停下来让学生回答：得到 $BH=\dfrac94BC$ 后，让学生自己写 $CH=\dfrac54BC$。

## 十、推荐练题任务包
- 若学生在 L0-L1，出什么题：只问“作高后 $BH$ 等于多少”，不立刻求边长。
- 若学生在 L2，出什么题：给两条边和一个比例，要求列出两个勾股式。
- 若学生在 L3，出什么题：完整求 $BC$，并要求验算高。
- 若学生在 L4，如何迁移：换成已知 $BC$ 和一条斜边，求另一条斜边。
- 若学生达到 L5-L6，如何深化/抽象/包装：让学生判断给定两条边和一个线段关系是否足以确定 $BC$。
- 禁止出的跑偏变式：不要混入角平分线定理、三角函数、圆幂定理。

## 十点五、推荐图形请求包（可选）
- 是否需要图：是，但若没有图也可用文字描述完成。
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：点 $B,C,H,D$ 共线且顺序为 $B-C-H-D$，点 $A$ 在直线 $BD$ 上方，连 $AB,AC,AD,AH$。
- 需要突出给学生看的关系：$AH\perp BD$，$BH=HD$，$CH=BH-BC$。
- 图中不能暗示的错误性质：不要把 $C$ 画成 $H$，不要暗示 $AC=AD$，不要把 $H$ 画到 $BC$ 外侧。
- 图失败时的降级方案：用文字提示“先画 $B-C-H-D$，再从 $H$ 向上画 $A$”。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "等腰三角形底边高 + 共高双勾股求线段",
  "core_transformation": "由 AD=AB 和 AH 垂直 BD 得 H 为 BD 中点，再把 BH、CH 都表示成 BC 的倍数",
  "solution_skeleton": ["作 AH 垂直 BD", "用等腰三角形三线合一得到 BH=BD/2", "根据 2BD=9BC 表示 BH、CH", "在 ABH 与 ACH 中两次勾股并相减"],
  "canonical_solution": {
    "key_quantities": ["BC=x", "BH=9x/4", "CH=5x/4", "AH=12"],
    "equation": "15^2-13^2=((9/4)^2-(5/4)^2)x^2",
    "answer_set": ["BC=4"],
    "excluded_values": ["BC=-4"],
    "degenerate_cases": ["若点序不是 B-C-D，CH 表达不同"],
    "verification": "BC=4 时 BD=18, BH=9, CH=5, AH=12, 满足 9-12-15 与 5-12-13",
    "shortest_reliable_path": "作高，等腰取中点，比例表达底边，两次勾股相减"
  },
  "common_blockers": {
    "low": ["不知道作 AH 垂直 BD", "不知道等腰底边高也是中线"],
    "middle": ["CH=BH-BC 容易写错", "两次勾股后不会相减消去 AH^2"],
    "strong": ["换比例或换点序后没有重新判断 H 的位置"]
  },
  "variation_rules": {
    "core_invariant": "两个直角三角形共享高，两个底边由同一个未知量表示",
    "surface_features": ["边长数字", "BD 与 BC 的比例", "所求线段"],
    "variation_dimensions": ["换数", "换问法", "隐藏比例表达", "反向构造"],
    "depth_ladder": ["原题复现", "同结构换数", "同结构换问法", "条件包装", "充分性判断"],
    "allowed_transforms": ["保持 D 在射线 BC 上且 C 在 B,D 之间", "保持 AD=AB", "保持两次勾股可消去公共高"],
    "forbidden_transforms": ["引入三角函数", "引入圆或相似大链条", "比例导致点序多解"],
    "cognitive_load_budget": "最多一个辅助线、两个勾股式、一次相减",
    "representation_options": ["文字题", "简图题", "线段比例表"],
    "packaging_options": ["BD:BC=9:2", "2BD=9BC", "BD 是 BC 的 9/2 倍"],
    "near_transfer_examples": ["AB=17, AC=10, BD=4BC, 求 BC"],
    "far_transfer_examples": ["共高双直角三角形，已知两条斜边和底边差，求底边"],
    "non_examples": ["只给 AD=AB 与一条边，缺少比例条件，不能唯一确定 BC"]
  },
  "complexity_budget": {
    "original_level": "L2-L3：辅助线 + 两次勾股 + 消元",
    "max_next_step": "比例可换成简单整数比或简单分数比",
    "forbidden_load": ["三角函数", "复杂二次方程", "多种点序分类"],
    "required_scaffolds": ["点序", "垂足 H", "BH 与 CH 的表达"]
  },
  "explanation_task_packet": {
    "target_learning_levels": ["L1", "L2", "L3"],
    "goal": "建立双勾股消去公共高的操作感",
    "avoid_abstract_phrases": ["数形结合", "转化思想"],
    "must_ask_first": ["AD=AB 后，A 在 BD 的什么线上？", "作 AH 垂直 BD 后，H 是什么点？"],
    "teaching_sequence": ["画点序", "作高", "得中点", "表达线段", "列两次勾股", "相减求 BC"],
    "concrete_probe_example": "若 BC=x，BD=9x/2，那么 BH 和 CH 分别是多少？",
    "pause_points": ["学生写出 BH=9x/4", "学生写出 CH=5x/4", "学生完成两式相减"]
  },
  "practice_task_packet": {
    "l0_l1_tasks": ["只判断 H 是 BD 中点", "只表达 BH 与 CH"],
    "l2_tasks": ["列出两个勾股式，不要求完整求解"],
    "l3_tasks": ["完整求 BC 并验算"],
    "l4_transfer_tasks": ["已知 BC 与一条斜边，求另一条斜边"],
    "l5_l6_deepening_variations": ["判断哪些条件组合足够双勾股"],
    "forbidden_variations": ["需要三角函数或相似综合的题"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "synthetic_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "H", "D"],
      "segments": ["AB", "AC", "AD", "AH", "BC", "CH", "HD"],
      "curves": [],
      "constraints": ["B,C,H,D collinear", "AH perpendicular BD", "BH=HD", "C between B and H"]
    },
    "teaching_focus": ["先作高", "再看中点", "最后看两个直角三角形"],
    "must_not_imply": ["不要暗示 C=H", "不要暗示 AC=AD", "不要把 H 画到 BC 外侧"],
    "fallback": "textual_diagram_description"
  }
}
```
