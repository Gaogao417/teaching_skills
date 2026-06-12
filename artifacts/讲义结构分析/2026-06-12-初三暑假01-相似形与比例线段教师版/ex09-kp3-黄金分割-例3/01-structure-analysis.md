# 结构分析：黄金分割例3-正方形构造中的黄金分割点

## 原题
例3. （★★★★☆）如图，以长为2的线段AB为边作正方形ABCD，取AB的中点P，连接 PD .在BA的延长线上取点F，使 $ P F=P D $ .以AF为边作正方形AMEF，点M在AD上.

(1) 求线段 AM、DM的长；

(2) 求证： $ A M^{2}=A D\cdot D M $；

(3) 请指出图中的黄金分割点.

## 【配题说明】考查黄金比的综合应用，黄金分割题目中容易出现别的黄金分割.

【常规讲解】（1）P是AB的中点，AB=2，可知 AP=1，根据勾股定理得：

PD $ =\sqrt{A D^{2}+A P^{2}}=\sqrt{5} $ ，则 PF=PD $ =\sqrt{5} $ ， AM=AF=PF-AP $ =\sqrt{5}-1 $，

DM=AD-AM=3 $ -\sqrt{5} $ ；

证明： $ A M^{2}=\left(\sqrt{5}-1\right)^{2}=6-2\sqrt{5}=2\times\left(3-\sqrt{5}\right)=A D\cdot D M $即证；

根据定义可知 M是线段 AD的黄金分割点，类似的，我们可以得到 $ A B^{2}=B F\cdot A F=4 $ ，可知 A是线段 BF的黄金分割点.

图形文字描述：按题干可确定 $ABCD$ 是边长2的正方形，P为AB中点，F在BA延长线上且 $PF=PD$，以AF为边作正方形AMEF且M在AD上。原OCR未提供图像，本分析只使用题干确定的共线、垂直、正方形边长关系，不从图像猜额外性质。

## 一、题目场景
- 数学对象：两个正方形 $ABCD$ 与 $AMEF$，线段AB的中点P，BA延长线上的点F，AD上的点M。
- 变量/参数：$AB=AD=2$，$AP=PB=1$，$PD=PF$，$AF=AM$。
- 函数/图形：平面几何构造，核心为直角三角形APD与线段黄金分割。
- 已知条件：P是AB中点；$PF=PD$；F在BA延长线上；以AF为边作正方形AMEF且M在AD上。
- 要求目标：求 $AM,DM$；证明 $AM^2=AD\cdot DM$；指出黄金分割点。

## 二、核心结构
- 表面考点：勾股定理、正方形性质、黄金分割定义。
- 本质考点：由构造得到 $AF=\sqrt5-1$，再识别 $AM$ 是 $AD$ 和 $DM$ 的比例中项；同时在线段BF上识别 $BA$ 是 $BF$ 和 $AF$ 的比例中项。
- 一句话问题模式：用正方形和圆规等长构造出 $\sqrt5-1$，再通过平方关系判断黄金分割点。

## 三、关键转化
- 最关键的转化：在直角三角形APD中算出 $PD=\sqrt5$，利用 $F$ 在BA延长线且 $PF=PD$ 得 $AF=PF-AP=\sqrt5-1$。
- 为什么降低计算量：先得到 $AM=AF$，再用 $DM=AD-AM$，证明黄金关系只需验证一个平方等式。
- 不转化时的低效路径：直接试图从图形美观或黄金比公式判断M、A，容易漏掉F所在延长线导致 $AF$ 方向算错。

## 四、标准路径骨架
1. 先做什么：由正方形和中点得 $AD=AB=2$，$AP=1$。
2. 再做什么：在直角三角形APD中用勾股定理求 $PD=\sqrt{AD^2+AP^2}=\sqrt5$。
3. 建立什么关系：因 $PF=PD$ 且F在BA延长线上，$PF=PA+AF$，所以 $AF=\sqrt5-1$；又 $AM=AF$。
4. 如何求解：$AM=\sqrt5-1$，$DM=AD-AM=3-\sqrt5$；验证 $AM^2=AD\cdot DM$。
5. 需要检查什么：$AM<AD$，所以M确在AD上；黄金分割点要指出在线段AD上M是分割点，在线段BF上A也是分割点；比较哪段是较长段。

## 四点五、标准完整解与验算
- 关键交点/关键量：$AP=1$，$AD=2$，$PD=PF=\sqrt5$，$AF=AM=\sqrt5-1$，$DM=3-\sqrt5$，$BF=BA+AF=\sqrt5+1$。
- 面积/方程/关系式：$PD^2=AP^2+AD^2$；$AM^2=AD\cdot DM$；$AB^2=BF\cdot AF$。
- 完整求解过程：因为 $ABCD$ 为边长2的正方形，P为AB中点，所以 $AD=2$，$AP=1$，且 $\angle DAP=90^\circ$。于是 $PD=\sqrt{AD^2+AP^2}=\sqrt{2^2+1^2}=\sqrt5$。又 $PF=PD=\sqrt5$，F在BA延长线上，所以 $PF=PA+AF$，$AF=\sqrt5-1$。正方形AMEF中 $AM=AF$，故 $AM=\sqrt5-1$，$DM=AD-AM=2-(\sqrt5-1)=3-\sqrt5$。进一步，$AM^2=(\sqrt5-1)^2=6-2\sqrt5$，$AD\cdot DM=2(3-\sqrt5)=6-2\sqrt5$，所以 $AM^2=AD\cdot DM$。因为 $AM>DM>0$ 且 $AM$ 是 $AD$ 与 $DM$ 的比例中项，M是线段AD的黄金分割点。又 $BF=BA+AF=2+\sqrt5-1=\sqrt5+1$，$BF\cdot AF=(\sqrt5+1)(\sqrt5-1)=4=AB^2$，且 $AB>AF>0$，所以A是线段BF的黄金分割点。
- 最终答案：$AM=\sqrt5-1$，$DM=3-\sqrt5$；M是线段AD的黄金分割点；A是线段BF的黄金分割点。
- 排除值：不能把 $AF$ 算成 $\sqrt5+1$，因为F在BA延长线上时 $PF=PA+AF$；不能把D或P误判为黄金分割点，缺少相应比例中项关系。
- 退化情形：$F$ 必须在BA延长线上且 $PF=PD$；若F在另一侧或点序改变，$AF$ 的表达式和黄金点结论会改变。
- 验算：$AM\approx1.236$，$DM\approx0.764$，$AD=2$，确有 $AM>DM$ 且 $AM+DM=2$；$\frac{AM}{AD}=\frac{\sqrt5-1}{2}$；$AB=2$ 是 $BF\approx3.236$ 与 $AF\approx1.236$ 的比例中项。
- 本题最短可靠路径：勾股求 $PD$，由点序求 $AF$，转成 $AM,DM$，用平方关系验证比例中项，再逐条指出黄金分割点。

## 五、出题人逻辑
- 诱导学生硬算的位置：图形中有两个正方形和延长线，容易把黄金分割点只看成M，漏掉A；也容易把 $PF=PD$ 与 $AF$ 的关系方向写反。
- 真正的捷径：抓住 $P$ 是中点，使直角三角形APD的两直角边为1和2，直接得到 $\sqrt5$。
- 训练的可迁移能力：从几何构造中提取根式长度，并用“比例中项平方关系”验证黄金分割，而不是凭图感判断。

## 六、学生卡点预测
- 读题/入手动作卡点：看不出要先在直角三角形APD中求 $PD$；不清楚F在BA延长线导致 $PF=PA+AF$。
- 建模/关系入口卡点：知道 $AM=\sqrt5-1$ 后，不会想到用 $DM=AD-AM$ 和 $AM^2=AD\cdot DM$ 判黄金分割。
- 求解/检查卡点：把 $DM$ 算成 $2-\sqrt5$；漏掉 $A$ 是线段BF的黄金分割点；没有检查较长段是哪一段。

## 七、变式原则
- 核心不变量：构造 $1,2,\sqrt5$ 的直角三角形，再用延长线差值得到 $\sqrt5-1$，最后以比例中项平方关系识别黄金分割点。
- 表层特征：正方形、线段中点、等长构造、延长线、证明黄金分割点。
- 可变维度：正方形边长、要求指出一个或两个黄金分割点、从证明式反推点、隐藏 $PF=PD$ 为圆弧构造。
- 深化阶梯：先求长度；再证明平方关系；再指出一个黄金分割点；再找图中另一个黄金分割点；再改边长为参数。
- 允许的变换：把边长2换成 $2a$；把“求证”改为“判断M是否为黄金分割点”；给出 $AM^2=AD\cdot DM$ 让学生解释线段方向。
- 禁止的变换：改变F所在射线却不重做点序；把P改成非中点同时仍期待同一黄金关系；加入相似三角形证明作为主线。
- 表征切换：几何构造图、长度表、平方关系、黄金比比例。
- 包装方式：圆规截取 $PD$ 到直线BA延长线；两个正方形嵌套。
- 近迁移例子：边长仍为2，只问M是否为AD的黄金分割点并说明哪段较长。
- 远迁移例子：边长为 $2a$ 的同构图形，求 $AM$、$DM$ 并指出黄金分割点。
- 反例/伪变式：若F取在AB延长线的B侧，$PF=PD$ 不再推出 $AF=\sqrt5-1$，不能沿用本题结论。

## 八、计算复杂度预算
- 原题计算层级：一次勾股根式、两次线段差、一个平方验证。
- 允许小步上升到：边长参数化为 $2a$，长度变为 $a(\sqrt5-1)$ 与 $a(3-\sqrt5)$。
- 禁止引入的计算负担：复杂辅助线、多角度追踪、相似三角形联立、多圆交点讨论。
- 必须保留的可见支架：直角三角形APD、F在BA延长线的点序、正方形AMEF给出 $AM=AF$、黄金分割的平方判定。

## 九、推荐讲题任务包
- 建议的本轮教学入口：build_relation。
- 本题讲解目标：会把几何构造转化为长度链，并用比例中项识别一个或多个黄金分割点。
- 不要直接讲的抽象话：不要只说“这是经典黄金分割作图”；必须说明每段长度从哪里来。
- 必须先问的问题：$PF$ 由哪两段组成？$AM$ 为什么等于 $AF$？要证明M是黄金分割点，哪段应是比例中项？
- 关键讲解顺序：读出正方形边长和中点；勾股求 $PD$；由延长线点序求 $AF$；由小正方形求 $AM$；求 $DM$；验证M；再检查线段BF上的A。
- 最适合的具体数值例子：用近似值 $AM\approx1.236$，$DM\approx0.764$，帮助学生确认较长段不是DM。
- 讲到哪里停下来让学生回答：得到 $AM=\sqrt5-1$、$DM=3-\sqrt5$ 后，让学生判断要验证哪个平方关系。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：给同图只要求写出 $AP,AD,PD,PF,AF$ 的长度链。
- 若卡在建模或关系入口，出什么题：给 $AM,DM,AD$，要求判断哪个是比例中项并写平方关系。
- 若卡在求解和检查，出什么题：训练 $(\sqrt5-1)^2=2(3-\sqrt5)$ 和 $(\sqrt5+1)(\sqrt5-1)=4$。
- 若原题已稳，如何小步迁移：只隐藏第（3）问，让学生主动找图中所有黄金分割点。
- 若结构识别已稳，如何深化/抽象/包装：把边长改为 $2a$，要求用参数证明同样的黄金分割关系。
- 禁止出的跑偏变式：让学生用相似三角形大篇幅证明，偏离黄金分割与长度构造主线。

## 十点五、推荐图形请求包（可选）
- 是否需要图：true
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：正方形ABCD，P为AB中点，F在BA延长线上，$PF=PD$，小正方形AMEF，M在AD上。
- 需要突出给学生看的关系：直角三角形APD；$PF=PA+AF$；$AM=AF$；$DM=AD-AM$；M与A两个黄金分割点。
- 图中不能暗示的错误性质：不要把F画到B侧延长线；不要把M画成AD中点；不要暗示 $DM>AM$；不要添加额外相似或角平分关系。
- 图失败时的降级方案：使用文字点序“F-A-P-B 共线，P为AB中点，AD垂直AB”及长度链表。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "正方形与延长线构造黄金分割点",
  "core_transformation": "由 AP=1, AD=2 的直角三角形求 PD=sqrt(5)，再由 PF=PA+AF 得 AF=sqrt(5)-1，并用比例中项平方关系识别黄金分割",
  "solution_skeleton": ["求 AP=1, AD=2, PD=sqrt(5)", "由 PF=PD 且 F 在 BA 延长线上求 AF=AM=sqrt(5)-1，DM=3-sqrt(5)", "验证 AM^2=AD*DM 与 AB^2=BF*AF，指出 M 和 A"],
  "canonical_solution": {
    "key_quantities": ["AP=1", "AD=2", "PD=PF=sqrt(5)", "AF=AM=sqrt(5)-1", "DM=3-sqrt(5)", "BF=sqrt(5)+1"],
    "equation": "AM^2=AD*DM; AB^2=BF*AF",
    "answer_set": ["AM=sqrt(5)-1", "DM=3-sqrt(5)", "M 是 AD 的黄金分割点", "A 是 BF 的黄金分割点"],
    "excluded_values": ["AF=sqrt(5)+1", "DM=2-sqrt(5)", "D 或 P 作为黄金分割点"],
    "degenerate_cases": ["F 不在 BA 延长线上", "P 不是 AB 中点", "M 不在 AD 上"],
    "verification": "AM^2=6-2sqrt(5)=2(3-sqrt(5))=AD*DM；BF*AF=(sqrt(5)+1)(sqrt(5)-1)=4=AB^2",
    "shortest_reliable_path": "勾股求长度链，再用平方关系验证黄金分割点"
  },
  "common_blockers": {
    "read_context_or_find_entry": ["不知道先看直角三角形 APD", "F 在 BA 延长线的点序读错"],
    "build_relation": ["不会由 PF=PD 得 AF=PF-AP", "不会从 AM^2=AD*DM 判断比例中项"],
    "solve_and_check": ["根式差算错", "漏掉 A 是 BF 的黄金分割点", "未检查较长段和较短段"]
  },
  "variation_rules": {
    "core_invariant": "1-2-sqrt(5) 长度构造生成黄金分割，比例中项平方关系用于确认点",
    "surface_features": ["正方形", "中点", "延长线", "等长截取", "黄金分割点判断"],
    "variation_dimensions": ["边长数值", "是否要求找所有黄金点", "是否参数化", "构造条件包装方式"],
    "depth_ladder": ["求长度", "证明平方关系", "指出一个黄金点", "找所有黄金点", "参数化证明"],
    "allowed_transforms": ["边长 2 改为 2a", "只问 M 是否黄金分割", "把 PF=PD 包装为圆规截取"],
    "forbidden_transforms": ["改变 F 的射线却沿用结论", "P 改非中点仍保留黄金关系", "加入无关相似综合"],
    "cognitive_load_budget": "不超过勾股、根式化简和两个平方关系验证",
    "representation_options": ["几何图", "长度链表", "平方关系", "黄金比"],
    "packaging_options": ["作图题", "证明题", "找点题"],
    "near_transfer_examples": ["保留边长2，隐藏第（3）问让学生找黄金点"],
    "far_transfer_examples": ["边长改为 2a，证明 M 仍为 AD 的黄金分割点"],
    "non_examples": ["F 取在 AB 的 B 侧延长线后仍声称 AF=sqrt(5)-1"]
  },
  "complexity_budget": {
    "original_level": "勾股定理加根式平方验证",
    "max_next_step": "边长参数化为 2a",
    "forbidden_load": ["复杂辅助线", "多圆交点分类", "相似形大综合"],
    "required_scaffolds": ["直角三角形 APD", "F-A-P-B 点序", "AM=AF", "比例中项平方关系"]
  },
  "explanation_task_packet": {
    "target_teaching_entries": ["build_relation", "solve_and_check", "transfer"],
    "goal": "从几何构造中建立长度链并识别所有黄金分割点",
    "avoid_abstract_phrases": ["经典作图直接记", "看图可知是黄金分割"],
    "must_ask_first": ["PF 是哪两段相加？", "M 在 AD 上时哪段更长？", "A 在线段 BF 上时哪段是比例中项？"],
    "teaching_sequence": ["读图形关系", "求 PD", "求 AF 与 AM", "求 DM", "验证 M", "再找 A"],
    "concrete_probe_example": "若 AM≈1.236、DM≈0.764，谁是较长段？谁应作为比例中项？",
    "pause_points": ["求出 PD 后", "求出 AM 和 DM 后", "指出 M 后继续找 A 前"]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": ["根据文字点序写 F-A-P-B 共线和 PF=PA+AF"],
    "build_relation_tasks": ["由三段长度判断比例中项"],
    "solve_and_check_tasks": ["根式平方与乘积验算"],
    "transfer_tasks": ["边长 2a 的同构题"],
    "hidden_structure_or_reverse_tasks": ["只给长度链，要求找所有黄金分割点"],
    "forbidden_variations": ["改变 F 位置但不改变结论"]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "synthetic_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "D", "P", "F", "M", "E"],
      "segments": ["AB", "AD", "AP", "PD", "PF", "AF", "AM", "DM", "BF"],
      "curves": [],
      "constraints": ["ABCD square side 2", "P midpoint of AB", "F on ray BA beyond A", "PF=PD", "AMEF square", "M on AD"]
    },
    "teaching_focus": ["right triangle APD", "PF=PA+AF", "AM=AF", "M on AD golden split", "A on BF golden split"],
    "must_not_imply": ["不要把 F 画到 B 侧延长线", "不要把 M 画成 AD 中点", "不要暗示 DM>AM", "不要添加相似或角平分性质"],
    "fallback": "textual_diagram_description"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.plan.assignment.yaml 或 02-student-explanation.assignment.yaml。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。本轮只生成结构分析，供用户审阅。
