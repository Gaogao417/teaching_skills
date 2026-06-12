# 结构分析：初二 xueersi 悬赏题：几何关系与辅助线/图形不变量

## 原题
【悬赏题】★★★☆☆

如图，在直角梯形 ABCD中， $ \angle A B C=\angle B C D=9 0^{\circ} $ ，AB=BC=10，点M在边BC上，使得 $ \triangle A D M $为正三角形，则 $ \triangle A B M $与 $ \triangle D C M $的面积和为___.

- 来源讲义：（数）2020年秋八年级培优体系_教师版_第12讲_四边形中的全等（勤思班）
- 来源定位：page=4；悬赏题
- 主题标签：动点与存在性、几何综合、OCR需复核
- OCR/图形状态：需人工复核：数字可能被拆空格；含图形条件，需对照原图；题干含空格/填空占位；选择项/表格排版可能丢列；题目依赖图形，仅生成 diagram_request_packet，不生成图片。本结构分析只锁定 OCR 文本可见条件，不补造图中缺失条件。

## 一、题目场景
- 数学对象：几何关系与辅助线/图形不变量中的题面对象、变量、图形/函数/方程关系。
- 变量/参数：以原题出现的字母、动点、边长、函数参数或方程参数为准；OCR 不确定处不补造。
- 函数/图形：题面含图或坐标/几何图形，必须按原图复核后再用于学生版。
- 已知条件：见“原题”；若选项、空格、图形信息缺列，以上方 OCR 状态为准。
- 要求目标：完成原题各小问，锁定计算入口、答案范围和验算点。

## 二、核心结构
- 表面考点：动点与存在性、几何综合、OCR需复核。
- 本质考点：把可见条件转化为一个可计算/可证明的关系链。
- 一句话问题模式：先确定入口，再列关系，最后检查范围、图形位置或实际意义。

## 三、关键转化
- 最关键的转化：先锁定题面对象与可见条件；对图形/OCR不完整处标记复核，再进入公式、判别式、函数或辅助线转化。
- 为什么降低计算量：先抓核心关系，能避免在多小问、复杂图形或参数表达中盲目展开。
- 不转化时的低效路径：直接硬算、照图猜性质、把每个小问孤立处理，容易漏范围和退化情况。

## 四、标准路径骨架
1. 先做什么：复述对象、变量、已知条件与目标。
2. 再做什么：判断应使用判别式/韦达/坐标代入/面积公式/辅助线/向量线性组合等哪一个入口。
3. 建立什么关系：把题面条件写成方程、函数关系、几何等量关系或向量表达。
4. 如何求解：按教师版分析或可见关系链完成代数求解/证明。
5. 需要检查什么：定义域、实数根、参数范围、三角形成立、点是否重合、图形边界、实际单位。

## 四点五、标准完整解与验算
- 关键交点/关键量：依据题面和教师版分析锁定；图形题需回源确认图中对象。
- 面积/方程/关系式：见下方教师版分析片段。
- 完整求解过程：

【分析】


过 A作 $ A E\bot C D $ ，交CD延长线于点E，则 $ A E=B C=A B=1 0 $ ，四边形ABCE是正方形；


因为 $ AD=AM $ ；所以 $ Rt\triangle AED\cong Rt\triangle ABM $ ；所以 $ ED=BM $ ， $ CD=CM $ ；


设 $ CD=x $ ，则 $ B M=1 0-x $ ；由勾股定理，得 $ D M^{2}=x^{2}+x^{2} $ ， $ A M^{2}=1 0^{2}+\left(1 0-x\right)^{2} $ ：


所以 $x^{2} + x^{2} = 10^{2} + \left(10 - x\right)^{2}$ ，解得 $x = 10\left(\sqrt{3} - 1\right)$ ；


（亦可过D作垂线）


![](page=5,bbox=[44, 44, 256, 109])


## 本讲巩固


【巩固1】


如图，以平行四边形ABCD两邻边BC、CD为边向外做正 $ \triangle B C E $正 $ \triangle C D F $求证： $ \triangle A E F $为正三角形.


![](page=5,bbox=[179, 570, 569, 892])


【分析】


$$

\because \triangle B C E 、 \triangle C D F \mathrm {为 正 三 角 形}

$$


$$

\therefore B C = B E = C E, C D = D F = C F, \angle C B E = \angle C D F

$$


$ \because $四边形 ABCD为平行四边形


$$

\therefore \angle A B C = \angle C D A = 6 0 ^ {\circ}, A D = B C, A B = C D

$$


$$

\therefore \angle E C F = 2 4 0 ^ {\circ} - \angle B C D = 6 0 ^ {\circ} + 1 8 0 ^ {\circ} - \angle B C D = 6 0 ^
{\circ} + \angle A D C = \angle A B E = \angle F D A,

$$


且 BE = AD = CE ， AB = DF = CF


$$

\therefore \triangle A B E \cong \triangle F D A \cong \triangle F C E (S. A. S)

$$


$$

\therefore A E = F A = F E

$$


$ \therefore \triangle A E F $为正三角形


【巩固2】


如图，点M、N分别在正方形ABCD的边BC、CD上，已知 $ \triangle M C N $的周长等于正方形ABCD周长的一半，求 $ \angle M A N $的度数


![](page=5,bbox=[199, 1745, 504, 2044])


【分析】


$ M N=B M+D N $ ，延长CD至 $ M^{\prime} $ ，使 $ M^{\prime} D=B M $ ，联结 $ A M^{\prime} $


证明 $ \triangle ADM^{\prime}\cong \triangle ABM $ ， $ \triangle AM^{\prime}N\cong \triangle AMN $


则得 $ \angle M A N=\angle M^{\prime} A N=\frac{1}{2}\angle M^{\prime} A M=4 5^{\circ}. $


![](page=6,bbox=[43, 44, 256, 109])


## 【巩固3】


如图，将边长为 8cm的正方形 ABCD折叠，使点 D落在 BC边的中点 E处，点 A落在 F处，折痕为 MN，则线段 CN的长是___.


![](page=6,bbox=[181, 600, 614, 984])


【分析】 3cm


## 【巩固4】


已知：如图，在梯形ABCD中，AD//BC，AB=DC.点E，F，G分别在AB，BC，CD上，AE=GF=GC. (1)求证：四边形AEFG是平行四边形；


(2) 当 $ \angle FGC=2\angle EFB $时，求证：四边形 AEFG是矩形.


![](page=6,bbox=[197, 1526, 675, 1823])


【分析】


(1) 因为在梯形ABCD中， $ AB=DC $ ；所以 $ \angle B=\angle C $


因为 $ G F=G C $ ；所以 $ \angle G F C=\angle C $ ；所以 $ \angle B=\angle G F C $ ；所以 $ A E / / G F $


因为 $ A E=G F $ ；所以四边形AEFG是平行四边形.


(2) 因为 $ \angle FGC+\angle GFC+\angle C=180^{\circ} $ $ \angle GFC=\angle C $ $ \angle FGC=2\angle EFB $


所以 $ \angle E F B+\angle G F C=9 0^{\circ} $ ；因为 $ \angle E F G+\angle E F B+\angle G F C=1 8 0^{\circ} $


所以 $ \angle EFG=90^{\circ} $ ；所以四边形 AEFG是矩形.


![](page=7,bbox=[44, 44, 256, 109])


## 课后延伸

- 最终答案：以教师版分析片段中的答案为准；若片段只给结论，需下一阶段补全逐步验算。
- 排除值：OCR/图形未复核前，保留潜在排除值。
- 退化情形：需检查点重合、边界位置、图形方向或函数交点退化。
- 验算：把结果代回原条件；应用题检查单位和实际意义；几何/函数题检查图形位置与定义域。
- 本题最短可靠路径：以教师版【分析】片段为标准解证据；若片段只给答案，则下一阶段生成学生讲解前应回源补全推导。

## 五、出题人逻辑
- 诱导学生硬算的位置：多条件、多小问、参数或图形对象同时出现时，学生容易先展开计算。
- 真正的捷径：抓住一个核心不变量或关键关系式，再推进各小问。
- 训练的可迁移能力：读题建模、选择入口、列式/证明、检查边界。

## 六、学生卡点预测
- 读题/入手动作卡点：看见长题面或图形后不知道先整理对象。
- 建模/关系入口卡点：不会判断该用哪条公式、定理、函数性质或辅助线。
- 求解/检查卡点：求出答案后漏掉范围、退化、实际意义或图形位置验证。

## 七、变式原则
- 核心不变量：保持“几何关系与辅助线/图形不变量”这一核心结构不变，只改变一个表层维度。
- 表层特征：动点与存在性、几何综合、OCR需复核。
- 可变维度：换数、换问法、换表征、条件包装。
- 深化阶梯：原题复现 → 同结构换数 → 同结构换问法 → 同结构换表征 → 条件包装 → 结构部分隐藏 → 反向构造。
- 允许的变换：只改变一个主维度，保留核心入口和计算层级。
- 禁止的变换：加入无关新知识点，或让图形/OCR 条件成为猜测。
- 表征切换：文字、代数式、坐标图像、几何图形、表格。
- 包装方式：把关键条件藏入情境、图形描述或参数限制。
- 近迁移例子：同结构换干净数字，要求学生复现入口和检查。
- 远迁移例子：保留不变量，把代数关系迁移到函数/几何/向量表达。
- 反例/伪变式：改变了核心入口或引入超纲计算的题，不算本题有效变式。

## 八、计算复杂度预算
- 原题计算层级：初二培优核心例题；一到两个关键转化。
- 允许小步上升到：增加一个边界讨论、一个同构表征切换或一个轻量参数。
- 禁止引入的计算负担：高次复杂运算、多重分类叠加、超纲定理、未给图却强依赖隐含图形条件。
- 必须保留的可见支架：对象表、关键关系、范围/退化检查。

## 九、推荐讲题任务包
- 建议的本轮教学入口：read_context/find_entry；先复核题面完整性。
- 本题讲解目标：能解释关键关系从哪里来，并完成结果检查。
- 不要直接讲的抽象话：“数形结合”“综合运用”“灵活转化”。
- 必须先问的问题：题中确定了哪些量？要求什么？哪些条件限制范围？
- 关键讲解顺序：对象整理 → 入口选择 → 关系式 → 求解/证明 → 验算。
- 最适合的具体数值例子：取原题一个小问或缩小数字，保留同一入口。
- 讲到哪里停下来让学生回答：写出关键关系式前、求出候选答案后、检查排除值前。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：同题型短题，只要求圈对象、已知、目标。
- 若卡在建模或关系入口，出什么题：给出半成品关系链，让学生补关键等式/辅助线理由。
- 若卡在求解和检查，出什么题：给出已列关系式，训练求解和验算。
- 若原题已稳，如何小步迁移：同结构换数或轻微换问法。
- 若结构识别已稳，如何深化/抽象/包装：把关键条件换成图像、表格或情境句。
- 禁止出的跑偏变式：增加无关知识点、复杂高次计算或依赖未给图形性质。

## 十点五、推荐图形请求包（可选）
- 是否需要图：true
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：原题所有点、线段、函数图像/几何对象；需回源复核图中相对位置。
- 需要突出给学生看的关系：关键等量、垂直/平行、交点、动点路径或函数交点。
- 图中不能暗示的错误性质：不要暗示题中未给出的等腰、直角、平行、点重合或比例关系。
- 图失败时的降级方案：用文字图形描述替代，明确所有对象与关系。

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "几何关系与辅助线/图形不变量",
  "core_transformation": "先锁定题面对象与可见条件；对图形/OCR不完整处标记复核，再进入公式、判别式、函数或辅助线转化。",
  "solution_skeleton": [
    "识别对象、变量、已知条件和目标",
    "选择最短入口：判别式/韦达/坐标代入/辅助线/向量基底/面积表达",
    "列式求解并检查定义域、退化、图形或实际意义"
  ],
  "canonical_solution": {
    "key_quantities": [
      "题面给定量",
      "待求量",
      "中间关系式"
    ],
    "equation": "见本文件“标准完整解与验算”中的教师版分析片段。",
    "answer_set": [
      "见教师版分析片段或答案句"
    ],
    "excluded_values": [
      "OCR/图形条件未复核前，不排除存在额外限制"
    ],
    "degenerate_cases": [
      "图形位置、点重合、边界位置需按原图复核"
    ],
    "verification": "后续讲解阶段应按教师版分析重算并补充验算。",
    "shortest_reliable_path": "沿教师版分析中的关键转化展开，避免另起复杂分类。"
  },
  "common_blockers": {
    "read_context_or_find_entry": [
      "把多小问当成零散计算，未先识别同一结构",
      "依赖图形但未先确认图中位置关系"
    ],
    "build_relation": [
      "不知道该用判别式、韦达、坐标代入、面积表达、辅助线还是向量基底",
      "把结论直接代入，缺少等量关系来源"
    ],
    "solve_and_check": [
      "求出数值后不检查定义域、根的存在性、三角形边界或实际范围",
      "OCR 数字/选项不复核导致答案漂移"
    ]
  },
  "variation_rules": {
    "core_invariant": "保持“几何关系与辅助线/图形不变量”这一核心结构不变，只改变一个表层维度。",
    "surface_features": [
      "动点与存在性",
      "几何综合",
      "OCR需复核"
    ],
    "variation_dimensions": [
      "换干净数字",
      "轻微换问法",
      "换表征：文字/图像/解析式/表格",
      "条件包装"
    ],
    "depth_ladder": [
      "原题复现",
      "同结构换数",
      "同结构换问法",
      "同结构换表征",
      "条件包装",
      "结构部分隐藏",
      "反向构造"
    ],
    "allowed_transforms": [
      "保留核心入口和计算层级",
      "只改变一个主维度",
      "保留必要范围检查"
    ],
    "forbidden_transforms": [
      "同时换知识点和计算负担",
      "把图形题改到需要新定理",
      "引入超出初二体系的技巧"
    ],
    "cognitive_load_budget": "下一阶段练习不应比原题多一个以上主要计算层级。",
    "representation_options": [
      "文字题面",
      "坐标/函数图像",
      "几何图形描述",
      "代数式/方程组"
    ],
    "packaging_options": [
      "把关键等量关系藏入情境",
      "把已知与所求轻微互换",
      "把图形条件改写成文字条件"
    ],
    "near_transfer_examples": [
      "保留题型和入口，仅替换数值或点的位置"
    ],
    "far_transfer_examples": [
      "保留不变量，把代数关系迁移到函数/几何表达"
    ],
    "non_examples": [
      "为了追求难度加入无关新知识点，导致训练目标偏移"
    ]
  },
  "complexity_budget": {
    "original_level": "初二培优讲义核心例题；以一到两个关键转化为主。",
    "max_next_step": "允许增加一个边界讨论或一个表征切换。",
    "forbidden_load": [
      "复杂高次运算",
      "多重分类叠加",
      "超纲定理",
      "未给图却强依赖图形隐含条件"
    ],
    "required_scaffolds": [
      "先列对象表",
      "标出关键等量关系",
      "保留范围/退化检查"
    ]
  },
  "explanation_task_packet": {
    "target_teaching_entries": [
      "read_context",
      "find_entry",
      "build_relation"
    ],
    "goal": "让学生能说出题目核心结构、第一步入口、关系式来源和答案检查点。",
    "avoid_abstract_phrases": [
      "数形结合",
      "综合运用",
      "灵活转化"
    ],
    "must_ask_first": [
      "题目中哪些量是确定的？",
      "要求目标对应哪个等量关系？",
      "有没有范围、符号或图形位置限制？"
    ],
    "teaching_sequence": [
      "复述题面对象",
      "确定核心入口",
      "列出关键关系",
      "完成计算",
      "检查范围和退化"
    ],
    "concrete_probe_example": "把原题数字缩小或取其中一小问，让学生先完成同结构入口。",
    "pause_points": [
      "关系式写出前",
      "代入求解前",
      "答案验算前"
    ]
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": [
      "给出同题型短题，只要求圈出对象、已知和目标"
    ],
    "build_relation_tasks": [
      "保留原题数值，让学生补全关键等式或辅助线理由"
    ],
    "solve_and_check_tasks": [
      "给出已列好的关系式，训练求解与范围检查"
    ],
    "transfer_tasks": [
      "同结构换数或换问法一题"
    ],
    "hidden_structure_or_reverse_tasks": [
      "反向给答案或性质，要求构造参数/说明条件是否充分"
    ],
    "forbidden_variations": [
      "不加入本讲未覆盖的新定理或复杂计算"
    ]
  },
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "synthetic_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": [
        "按原题点名与图中对象标注"
      ],
      "segments": [
        "按原题线段、边、垂线、平行线或函数图像标注"
      ],
      "curves": [],
      "constraints": [
        "必须回源复核原图位置关系"
      ]
    },
    "teaching_focus": [
      "突出关键等量关系或位置关系",
      "避免误导学生读出题中没有给出的特殊性质"
    ],
    "must_not_imply": [
      "不要暗示未给出的等腰/直角/平行/点重合关系",
      "坐标比例或长度比例不能误导结论"
    ],
    "fallback": "textual_diagram_description"
  }
}
```

下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.plan.assignment.yaml 或 02-student-explanation.assignment.yaml。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
