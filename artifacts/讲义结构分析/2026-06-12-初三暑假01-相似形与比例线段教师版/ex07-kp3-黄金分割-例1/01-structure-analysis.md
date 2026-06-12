# 结构分析：黄金分割例1-由比例求线段长

## 原题
例1. （★★★★☆）如图，点B在线段AC上，且 $ \frac{BC}{AB}=\frac{AB}{AC} $ ，设AC=2，则AB的长为（    )

A. $ \frac{\sqrt{5}-1}{2} $ B. $ \frac{\sqrt{5}+1}{2} $ C. $ \sqrt{5}-1 $ D. $ \sqrt{5}+1 $

【配题说明】本题考查的是黄金分割的概念以及黄金比值，掌握一元二次方程的解法、理解黄金分割的概念是解题的关键.

【常规讲解】解： $ \because \frac{BC}{AB}=\frac{AB}{AC} $ $ \therefore AB^{2}=2\times(2-AB) $ $ \therefore AB^{2}+2AB-4=0 $ ，解得， $ AB_{1}=\sqrt{5}-1 $ $ AB_{2}=-\sqrt{5}-1 $ （舍去），

故选：C.

图形文字描述：B在线段AC上，所以 $AC=AB+BC$，且三点按 A-B-C 或 C-B-A 共线排列均不影响长度关系。本轮不使用原图，不从图像猜额外性质。

## 一、题目场景
- 数学对象：一条线段AC及其内部分点B。
- 变量/参数：设 $AB=x$，则 $BC=2-x$。
- 函数/图形：线段分割，无函数图像。
- 已知条件：$AC=2$，$B$ 在线段 $AC$ 上，$\frac{BC}{AB}=\frac{AB}{AC}$。
- 要求目标：求 $AB$ 的长度并选择选项。

## 二、核心结构
- 表面考点：黄金分割、比例式、一元二次方程。
- 本质考点：判断哪一段是比例中项，并把比例式转化为“比例中项的平方=另外两段乘积”。
- 一句话问题模式：内分点把全长分成两段，已知“短段:长段=长段:全长”，求较长段。

## 三、关键转化
- 最关键的转化：由 $\frac{BC}{AB}=\frac{AB}{AC}$ 得到 $AB^2=BC\cdot AC$，再用 $BC=AC-AB$。
- 为什么降低计算量：直接锁定 $AB$ 是比例中项，避免把黄金比公式背错或把较短段、较长段方向颠倒。
- 不转化时的低效路径：先套 $\frac{\sqrt5-1}{2}$ 或 $\frac{\sqrt5+1}{2}$，但不判断它对应“长段/全长”还是“短段/长段”，容易选A或B。

## 四、标准路径骨架
1. 先做什么：设 $AB=x$，由 $B$ 在线段 $AC$ 上确定 $0<x<2$。
2. 再做什么：写出 $BC=2-x$。
3. 建立什么关系：由比例式得到 $x^2=2(2-x)$。
4. 如何求解：化为 $x^2+2x-4=0$，取正且小于2的根。
5. 需要检查什么：负根舍去；正根 $\sqrt5-1$ 是否小于全长2；选项是否是长度而不是比值。

## 四点五、标准完整解与验算
- 关键交点/关键量：$AB=x$，$BC=2-x$，$AC=2$。
- 面积/方程/关系式：$AB^2=BC\cdot AC$。
- 完整求解过程：设 $AB=x$，则 $BC=2-x$。由 $\frac{BC}{AB}=\frac{AB}{AC}$，得 $x^2=2(2-x)$，即 $x^2+2x-4=0$。解得 $x=-1\pm\sqrt5$。因为 $x>0$，所以 $x=\sqrt5-1$。
- 最终答案：$AB=\sqrt5-1$，选C。
- 排除值：$-1-\sqrt5<0$，不是线段长度，舍去。
- 退化情形：$AB=0$ 或 $AB=2$ 都会使比例式或分割意义失效，不在题设范围内。
- 验算：$BC=2-(\sqrt5-1)=3-\sqrt5$；$AB^2=(\sqrt5-1)^2=6-2\sqrt5$，$BC\cdot AC=2(3-\sqrt5)=6-2\sqrt5$，相等。
- 本题最短可靠路径：设 $AB=x$，先判定 $AB$ 是 $BC$ 与 $AC$ 的比例中项，再列 $x^2=2(2-x)$，解方程并检查正负和范围。

## 五、出题人逻辑
- 诱导学生硬算的位置：选项中同时出现黄金比、黄金比倒数相关形式，诱导学生只背公式不看线段方向。
- 真正的捷径：把“中间项平方等于两端乘积”作为入口。
- 训练的可迁移能力：遇到黄金分割时先判断全长、较长段、较短段，再列平方关系。

## 六、学生卡点预测
- 读题/入手动作卡点：看到“如图”和比例式，不知道先设哪一段。
- 建模/关系入口卡点：把 $\frac{BC}{AB}=\frac{AB}{AC}$ 误读成 $BC^2=AB\cdot AC$，比例中项判断错。
- 求解/检查卡点：二次方程有两个根，未排除负根；把 $\frac{\sqrt5-1}{2}$ 当成 $AB$ 的长度，忽略 $AC=2$。

## 七、变式原则
- 核心不变量：一条线段被内部分点分割，比例中项是较长段，满足“较长段平方=全长乘较短段”。
- 表层特征：给全长、给比例式、选择长度。
- 可变维度：全长数值、所求线段、比例式书写方向、选择题改填空题。
- 深化阶梯：先复现设元列方程；再同结构换全长；再已知较长段求全长或短段；再给文字定义让学生自己判断比例中项。
- 允许的变换：把 $AC=2$ 换成 $AC=4,10,a$；把求 $AB$ 改为求 $BC$；把比例式改写为 $AB^2=AC\cdot BC$。
- 禁止的变换：同时引入相似三角形或坐标系导致主结构跑偏；不给点在线段上却仍默认内分；把外分点当作黄金分割。
- 表征切换：比例式、平方关系、黄金比 $\frac{\text{较长段}}{\text{全长}}=\frac{\sqrt5-1}{2}$ 之间切换。
- 包装方式：用“把一根长为2的木条分成两段”代替线段图。
- 近迁移例子：$AC=10$，$B$ 在线段 $AC$ 上且 $AB^2=AC\cdot BC$，求 $AB$。
- 远迁移例子：已知 $AB$ 是 $AC$ 和 $BC$ 的比例中项，给 $BC$ 求 $AC$。
- 反例/伪变式：若比例为 $\frac{AB}{BC}=\frac{AB}{AC}$，不能仍按黄金分割处理，因为比例中项和对象已改变。

## 八、计算复杂度预算
- 原题计算层级：一次设元，一元二次方程，根式化简。
- 允许小步上升到：含参数全长 $L$，答案写成 $\frac{\sqrt5-1}{2}L$。
- 禁止引入的计算负担：复杂二次根式、三角函数、相似形辅助线、多未知数联立。
- 必须保留的可见支架：点在线段上、全长=两段和、比例中项平方关系、正根检查。

## 九、推荐讲题任务包
- 建议的本轮教学入口：build_relation。
- 本题讲解目标：让学生能先判断 $AB$ 是比例中项，再用平方关系求长度。
- 不要直接讲的抽象话：不要只说“黄金比就是0.618”；不要先背公式再代。
- 必须先问的问题：比例式中哪个量在两边都出现？它是不是比例中项？
- 关键讲解顺序：读出线段和点序；设 $AB=x$；写 $BC=2-x$；列 $x^2=2(2-x)$；解方程；检查负根和范围；对照选项。
- 最适合的具体数值例子：全长2正好让较长段为 $\sqrt5-1$，可顺带说明 $\frac{AB}{AC}=\frac{\sqrt5-1}{2}$。
- 讲到哪里停下来让学生回答：列出 $x^2=2(2-x)$ 后，让学生完成方程求根和舍根。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：给线段全长和内分点，要求只写 $BC=AC-AB$ 与 $0<AB<AC$。
- 若卡在建模或关系入口，出什么题：给三种比例式，让学生圈出比例中项并写平方关系。
- 若卡在求解和检查，出什么题：给 $x^2=L(L-x)$，训练求根后排除负根。
- 若原题已稳，如何小步迁移：把全长2换成10，求较长段和较短段。
- 若结构识别已稳，如何深化/抽象/包装：只给“较长段是全长和较短段的比例中项”，让学生自己画线段并列式。
- 禁止出的跑偏变式：同时加入三角形相似证明、面积比或函数图像。

## 十点五、推荐图形请求包（可选）
- 是否需要图：true
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：线段AC，内点B，标注 $AC=2$、$AB=x$、$BC=2-x$。
- 需要突出给学生看的关系：B 在线段 AC 上；$AB$ 是比例中项；$AC=AB+BC$。
- 图中不能暗示的错误性质：不要暗示 $AB=BC$；不要把 B 画成中点；不要出现额外角度或平行关系。
- 图失败时的降级方案：使用文字线段关系“B在线段AC上，AC=AB+BC”。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "线段内分黄金分割，已知全长和比例式求比例中项长度",
  "core_transformation": "由 BC/AB=AB/AC 判断 AB 是 BC 与 AC 的比例中项，转化为 AB^2=BC*AC",
  "solution_skeleton": ["设 AB=x 且 0<x<2", "由 B 在线段 AC 上得 BC=2-x", "列 x^2=2(2-x)，解方程并舍负根"],
  "canonical_solution": {
    "key_quantities": ["AC=2", "AB=x", "BC=2-x"],
    "equation": "x^2=2(2-x)",
    "answer_set": ["AB=sqrt(5)-1", "选C"],
    "excluded_values": ["x=-1-sqrt(5)"],
    "degenerate_cases": ["AB=0", "AB=AC"],
    "verification": "(sqrt(5)-1)^2=2(3-sqrt(5))，且 0<sqrt(5)-1<2",
    "shortest_reliable_path": "判断 AB 为比例中项，再列平方关系求正根"
  },
  "common_blockers": {
    "read_context_or_find_entry": ["不知道先设 AB 还是 BC", "忽略 B 在线段 AC 上"],
    "build_relation": ["比例中项判断错", "把黄金比公式对应到错误线段"],
    "solve_and_check": ["负根未舍", "把比值误当长度"]
  },
  "variation_rules": {
    "core_invariant": "较长段是全长和较短段的比例中项",
    "surface_features": ["线段图", "全长给定", "比例式给定"],
    "variation_dimensions": ["全长数值", "所求对象", "比例式呈现", "题型"],
    "depth_ladder": ["原题复现", "同结构换数", "同结构换问法", "文字定义包装", "反向给比例中项求全长"],
    "allowed_transforms": ["AC 改为 4、10 或 L", "求 BC", "比例式改写成平方关系"],
    "forbidden_transforms": ["加入无关相似三角形", "默认外分点为黄金分割", "同时改变多个核心条件"],
    "cognitive_load_budget": "保持一元二次方程或黄金比直接缩放，不增加多未知量",
    "representation_options": ["线段图", "比例式", "平方关系", "文字定义"],
    "packaging_options": ["木条分割", "绳子分割", "线段内点"],
    "near_transfer_examples": ["AC=10，AB^2=AC*BC，求 AB"],
    "far_transfer_examples": ["给较长段，反求全长和较短段"],
    "non_examples": ["比例式改变为 AB/BC=AB/AC 后仍按黄金分割求"]
  },
  "complexity_budget": {
    "original_level": "一元二次方程根式解",
    "max_next_step": "全长参数 L 的黄金分割长度表达",
    "forbidden_load": ["复杂根式运算", "三角函数", "相似形综合"],
    "required_scaffolds": ["全长=两段和", "比例中项平方关系", "正根和范围检查"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["build_relation", "solve_and_check"],
    "goal": "会判断比例中项并列出黄金分割平方关系",
    "avoid_abstract_phrases": ["黄金比直接套公式", "记住0.618就行"],
    "must_ask_first": ["比例式中哪个线段重复出现？", "这个重复出现的线段对应长段还是短段？"],
    "teaching_sequence": ["读点在线段上的关系", "设 AB=x", "写 BC=2-x", "列平方关系", "解方程", "检查正负和范围"],
    "concrete_probe_example": "若 AC=10 且 AB 是 AC 和 BC 的比例中项，AB 应约等于 6.18 还是 3.82？",
    "pause_points": ["列方程后", "求出两个根后", "对照选项前"]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": ["标出全长、较长段、较短段"],
    "build_relation_tasks": ["由比例式写平方关系"],
    "solve_and_check_tasks": ["解 x^2=L(L-x) 并舍负根"],
    "transfer_tasks": ["换全长求长段或短段"],
    "hidden_structure_or_reverse_tasks": ["文字定义中识别比例中项"],
    "forbidden_variations": ["引入相似三角形综合证明"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "synthetic_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C"],
      "segments": ["AC", "AB", "BC"],
      "curves": [],
      "constraints": ["B on segment AC", "AC=2", "AB=x", "BC=2-x"]
    },
    "teaching_focus": ["AB is the proportional mean", "AC=AB+BC"],
    "must_not_imply": ["不要暗示 AB=BC", "不要把 B 画成中点", "不要添加额外几何性质"],
    "fallback": "textual_diagram_description"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.plan.assignment.yaml 或 02-student-explanation.assignment.yaml。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。本轮只生成结构分析，供用户审阅。
