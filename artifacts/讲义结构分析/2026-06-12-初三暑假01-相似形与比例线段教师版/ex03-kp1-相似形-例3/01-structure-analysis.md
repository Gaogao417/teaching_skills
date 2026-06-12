# 结构分析：相似四边形对应边求长

## 原题
例3. （★★★★☆）（2019·徐汇区期末）四边形 ABCD和四边形 $ A^{\prime} B^{\prime} C^{\prime} D^{\prime} $是相似图形，点 A、B、C、D分别与 $ A^{\prime} $ 、 $ B^{\prime} $ 、 $ C^{\prime} $ 、 $ D^{\prime} $对应，已知 $ BC=3 $ ， $ CD=2.4 $ ， $ B^{\prime} C^{\prime}=2 $ ，那么 $ C^{\prime} D^{\prime} $的长是___.

【配题说明】本题考查相似图形，解题的关键是熟练掌握相似多边形的性质。

【常规讲解】解： $ \because $四边形 $ A B C D\sim $四边形 $ A^{\prime}B^{\prime}C^{\prime}D^{\prime} $

$$
\therefore C D: C ^ {\prime} D ^ {\prime} = B C: B ^ {\prime} C ^ {\prime},
$$

$$
\therefore C ^ {\prime} D ^ {\prime} = 1. 6,
$$

故答案为：1.6.

题面辨认：OCR 中教师过程写作 `1. 6`，按小数规范为 `1.6`；相似对应顺序清楚，$BC$ 对应 $B'C'$，$CD$ 对应 $C'D'$。教师答案为 1.6，独立核对后正确。

## 一、题目场景
- 数学对象：两个相似四边形 ABCD 与 A'B'C'D'。
- 变量/参数：已知边 BC=3、CD=2.4、B'C'=2，未知 C'D'。
- 函数/图形：相似多边形，无函数图像。
- 已知条件：四边形相似，且对应点顺序为 A↔A'、B↔B'、C↔C'、D↔D'。
- 要求目标：求对应边 C'D' 的长度。

## 二、核心结构
- 表面考点：相似多边形对应边成比例。
- 本质考点：先按对应点顺序找对应边，再统一相似比方向列比例。
- 一句话问题模式：已知一组对应边求相似比，再把相似比迁移到另一组对应边。

## 三、关键转化
- 最关键的转化：由四边形 ABCD∼A'B'C'D' 得到 BC:B'C'=CD:C'D'。
- 为什么降低计算量：只需用一组对应边确定比例方向，再一乘一除求未知边。
- 不转化时的低效路径：试图画图或凭“变小了多少”心算，容易把比例方向写反。

## 四、标准路径骨架
1. 先做什么：读对应点顺序，确认 BC 对应 B'C'，CD 对应 C'D'。
2. 再做什么：由 BC=3、B'C'=2 得出新图相对原图的相似比为 2/3。
3. 建立什么关系：C'D'/CD = B'C'/BC = 2/3，或 CD:C'D'=BC:B'C'。
4. 如何求解：C'D'=2.4×2/3=1.6。
5. 需要检查什么：比例方向、单位正值、是否把 CD 对应到 C'D'。

## 四点五、标准完整解与验算
- 关键交点/关键量：相似比 $k=\frac{B'C'}{BC}=\frac{2}{3}$。
- 面积/方程/关系式：$\frac{C'D'}{CD}=\frac{B'C'}{BC}$。
- 完整求解过程：因为四边形 ABCD 与 A'B'C'D' 相似，且 B 对应 B'、C 对应 C'、D 对应 D'，所以边 BC 对应 B'C'，边 CD 对应 C'D'。由 $BC=3$、$B'C'=2$，第二个四边形相对第一个四边形的相似比为 $\frac{2}{3}$。因此 $C'D'=CD\cdot\frac{2}{3}=2.4\cdot\frac{2}{3}=1.6$。
- 最终答案：1.6。
- 排除值：无选项；若得到 3.6 或 0.9，多半是比例方向错误或对应边找错。
- 退化情形：默认四边形为非退化相似多边形，边长均为正。
- 验算：$CD:C'D'=2.4:1.6=3:2$，与 $BC:B'C'=3:2$ 一致。
- 本题最短可靠路径：先写 $C'D'/2.4=2/3$，直接得 1.6。

## 五、出题人逻辑
- 诱导学生硬算的位置：给出四边形和多个对应点，诱导学生忽略对应顺序或把比例写反。
- 真正的捷径：对应边一锁定，直接用同一相似比。
- 训练的可迁移能力：从三角形相似迁移到任意相似多边形，保持“对应顺序优先”的动作。

## 六、学生卡点预测
- 读题/入手动作卡点：不读“点 A、B、C、D 分别与 A'、B'、C'、D' 对应”，导致不知道哪条边对应哪条边。
- 建模/关系入口卡点：会背“对应边成比例”，但不会把 $BC:B'C'=CD:C'D'$ 写成统一方向。
- 求解/检查卡点：把 $2.4\times\frac{3}{2}$ 算成 3.6，忘记第二个图形比第一个图形小。

## 七、变式原则
- 核心不变量：相似多边形中，对应点确定对应边；任意两组对应边的比相等。
- 表层特征：四边形、三个已知边长、求一条对应边。
- 可变维度：多边形类型、相似比方向、已知边位置、问原图边或像图边、数字小数/分数。
- 深化阶梯：原题复现；同结构换数；换问原图边长；隐藏相似比在周长中；加入“对应顺序打乱”的读题训练。
- 允许的变换：把 2.4 换成可整除小数或分数；把四边形换成三角形/五边形；要求先写相似比再求边。
- 禁止的变换：加入角度追踪、面积比或多步辅助线证明，除非本轮目标转为综合相似。
- 表征切换：文字条件、简单示意图、比例表、对应边配对表。
- 包装方式：模型缩放、地图比例、相似照片边长。
- 近迁移例子：两个相似五边形中已知一组对应边和另一条原图边，求像图边。
- 远迁移例子：已知相似比和周长，求某条边或反求原图边。
- 反例/伪变式：只给两条非对应边长度就列比例，是伪变式，因为对应关系未确认。

## 八、计算复杂度预算
- 原题计算层级：一层比例乘法，含小数 2.4。
- 允许小步上升到：分数或小数相似比，一步反求未知边。
- 禁止引入的计算负担：二元方程组、复杂小数、面积比平方与边长比混用。
- 必须保留的可见支架：对应点顺序、对应边配对、统一比例方向。

## 九、推荐讲题任务包
- 建议的本轮教学入口：build_relation、solve_and_check。
- 本题讲解目标：训练学生先找对应边，再用统一方向的相似比求未知边并验算。
- 不要直接讲的抽象话：不要只说“交叉相乘”；不要跳过对应关系直接代数。
- 必须先问的问题：BC 对应哪条边？CD 对应哪条边？第二个四边形相对第一个是放大还是缩小？
- 关键讲解顺序：读对应点；配对应边；确定相似比 2/3；迁移到 CD；用比值验算。
- 最适合的具体数值例子：若原图一条边 3 变成 2，那么原图另一条边 2.4 也乘 2/3。
- 讲到哪里停下来让学生回答：写出 $C'D'/2.4=2/3$ 后停下，让学生算出 1.6 并解释为什么不是 3.6。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：给相似多边形对应点顺序，让学生只配对应边，不计算。
- 若卡在建模或关系入口，出什么题：给一组对应边求相似比，再填另一组边的比例式。
- 若卡在求解和检查，出什么题：同结构一层计算，要求最后用两个比值相等验算。
- 若原题已稳，如何小步迁移：改问原图边长，训练用相似比倒数。
- 若结构识别已稳，如何深化/抽象/包装：把对应顺序写成 ABCD∼A'D'C'B' 等非直观顺序，让学生先确认边对应。
- 禁止出的跑偏变式：面积比平方、辅助线证明、复杂综合几何。

## 十点五、推荐图形请求包（可选）
- 是否需要图：可选。
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：两个相似四边形 ABCD 与 A'B'C'D'，标出 BC、CD、B'C'、C'D'。
- 需要突出给学生看的关系：BC 对应 B'C'，CD 对应 C'D'；第二个图形是第一个图形按 2/3 缩小。
- 图中不能暗示的错误性质：不要画成矩形或平行四边形；不要暗示角度特殊；不要让点顺序模糊。
- 图失败时的降级方案：用对应边表格代替图。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "相似多边形对应边成比例求未知边",
  "core_transformation": "由对应点顺序确定对应边，再用一组对应边得到相似比并迁移到目标边",
  "solution_skeleton": ["读对应点顺序", "确认 BC 对应 B'C'、CD 对应 C'D'", "用 B'C'/BC=2/3 求 C'D'=2.4×2/3"],
  "canonical_solution": {
    "key_quantities": ["BC=3", "CD=2.4", "B'C'=2", "similarity_ratio_from_ABCD_to_A'B'C'D'=2/3"],
    "equation": "C'D'/CD = B'C'/BC = 2/3",
    "answer_set": ["1.6"],
    "excluded_values": [],
    "degenerate_cases": ["默认相似四边形非退化，边长为正"],
    "verification": "2.4:1.6=3:2，与 3:2 一致。",
    "shortest_reliable_path": "C'D'=2.4×(2/3)=1.6。"
  },
  "common_blockers": {
    "read_context_or_find_entry": ["不读对应点顺序", "不知道 BC 对应 B'C'"],
    "build_relation": ["比例方向不统一", "把非对应边拿来相比"],
    "solve_and_check": ["把缩小比写成放大比", "不做比值验算"]
  },
  "variation_rules": {
    "core_invariant": "对应点决定对应边，对应边比相等",
    "surface_features": ["相似四边形", "三个边长", "求一条边"],
    "variation_dimensions": ["多边形类型", "相似比方向", "已知边位置", "数字形式", "对应顺序是否直观"],
    "depth_ladder": ["原题复现", "同结构换数", "换问原图边", "对应顺序打乱", "隐藏相似比在周长或文字情境中"],
    "allowed_transforms": ["换成三角形或五边形", "换成分数或整洁小数", "改问相似比或另一条对应边"],
    "forbidden_transforms": ["加入面积比平方", "加入辅助线证明", "复杂综合几何"],
    "cognitive_load_budget": "保持一层比例计算，重点训练对应边和方向。",
    "representation_options": ["文字条件", "示意图", "对应边表", "比例式"],
    "packaging_options": ["模型缩放", "地图比例", "相似照片"],
    "near_transfer_examples": ["相似五边形已知一组对应边和另一条原图边求像图边"],
    "far_transfer_examples": ["已知相似比和周长反求某条边"],
    "non_examples": ["未说明对应关系时直接把两条给定边列成比例"]
  },
  "complexity_budget": {
    "original_level": "一层比例乘法，含简单小数",
    "max_next_step": "一步反求未知边或使用整洁分数相似比",
    "forbidden_load": ["二元方程组", "复杂小数", "面积比平方混入边长比"],
    "required_scaffolds": ["对应点顺序", "对应边配对", "统一比例方向", "比值验算"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["build_relation", "solve_and_check"],
    "goal": "让学生先找对应边，再统一比例方向求边长并验算。",
    "avoid_abstract_phrases": ["直接交叉相乘", "照着比例套"],
    "must_ask_first": ["BC 对应哪条边？", "CD 对应哪条边？", "第二个图形相对第一个是放大还是缩小？"],
    "teaching_sequence": ["读对应点", "配对应边", "确定相似比", "迁移到目标边", "用比值验算"],
    "concrete_probe_example": "原图边 3 变为 2，所以原图边 2.4 变为 2.4×2/3。",
    "pause_points": ["让学生写出 C'D'/2.4=2/3", "让学生解释为什么不是 3.6"]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": ["只给相似多边形记号，让学生配对应边"],
    "build_relation_tasks": ["由一组对应边写出相似比和目标比例式"],
    "solve_and_check_tasks": ["一层计算后用比值相等验算"],
    "transfer_tasks": ["改问原图边长，训练倒用相似比"],
    "hidden_structure_or_reverse_tasks": ["对应顺序非直观时先确认目标边对应关系"],
    "forbidden_variations": ["面积比平方题", "辅助线证明题", "复杂综合几何题"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "synthetic_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "D", "A'", "B'", "C'", "D'"],
      "segments": ["BC", "CD", "B'C'", "C'D'"],
      "curves": [],
      "constraints": ["ABCD similar to A'B'C'D'", "B'C'/BC = 2/3", "C'D' corresponds to CD"]
    },
    "teaching_focus": ["corresponding side pairing", "same similarity ratio transfers to target side"],
    "must_not_imply": ["不要画成矩形", "不要暗示平行四边形", "不要让对应点顺序模糊"],
    "fallback": "textual_diagram_description"
  }
}
```

下一步建议：本轮只供用户审阅结构分析；若审阅通过，再使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.plan.assignment.yaml 或 02-student-explanation.assignment.yaml。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
