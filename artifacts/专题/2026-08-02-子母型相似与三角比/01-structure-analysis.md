# 结构分析：子母型相似与三角比互化

## 原题
如图，在 $\triangle ABC$ 中，点 $D$ 在线段 $AC$ 上，$BD\perp BC$，且 $\angle ABD=\angle ACB$。已知 $AD:CD=1:8$，求 $\tan\angle ACB$。

图形文字描述：$A,D,C$ 三点依次共线，连接 $AB,BD,BC$；$BD\perp BC$，$\angle ABD$ 与 $\angle ACB$ 相等。

## 一、题目场景
- 数学对象：母三角形 $\triangle ACB$ 与内嵌子三角形 $\triangle ABD$，以及直角三角形 $\triangle BCD$。
- 变量/参数：共线线段比 $AD:CD$；三角比 $\sin C,\cos C,\tan C$。
- 函数/图形：无函数；核心为子母型相似和直角三角形三角比。
- 已知条件：$A,D,C$ 共线且点序为 $A-D-C$；$BD\perp BC$；$\angle ABD=\angle ACB$；$AD:CD=1:8$。
- 要求目标：求 $\tan\angle ACB$。

## 二、核心结构
### 2.1 表层信息
- 表面考点：相似三角形、共线线段的和差、锐角三角比。
- 题型功能：`composite_problem`
- 是否值得完整 structural analysis：是；题目把“共线线段比”与“三角比”放在两个不同三角形中，必须通过相似关系搭桥。
- 一句话问题模式：先用两个角锁定子母相似，把 $AD:CD$ 转成相似对应边比，再把该边比读成直角三角形中的三角比。

### 2.2 结构表达

#### 判别条件表（概念辨析题用；不适用则写“无”）
无。

#### 情景量表（应用题用；不适用则写“无”）
无。

#### 命题网络（所有题型都写；简单题写简版）
- P1（题设）：$A,D,C$ 三点共线且点序为 $A-D-C$。
- P2（题设）：$\angle ABD=\angle ACB$。
- P3（可推）：$\angle BAD=\angle CAB$。
- P4（可推）：$\triangle ABD\sim\triangle ACB$，对应关系为 $A\leftrightarrow A$、$B\leftrightarrow C$、$D\leftrightarrow B$。
- P5（可推）：$\dfrac{AD}{AB}=\dfrac{AB}{AC}=\dfrac{BD}{BC}$，从而 $AB^2=AD\cdot AC$。
- P6（题设）：$AD:CD=1:8$，且 $AC=AD+CD$。
- P7（计算状态）：$AC=9AD$，故 $AB=3AD$，进而 $\dfrac{BD}{BC}=\dfrac{AD}{AB}=\dfrac13$。
- P8（题设/定义）：$BD\perp BC$，所以在直角三角形 $BCD$ 中，$\tan C=\dfrac{BD}{BC}$。
- P9（目标）：$\tan C=\dfrac13$。
- R1：P1 + P2 -> P3，方法：共线射线重合确定公共顶角。
- R2：P2 + P3 -> P4，方法：两角分别相等（AA）判定三角形相似。
- R3：P4 -> P5，方法：按等角顶点确定对应边并列相似比。
- R4：P5 + P6 -> P7，方法：整段与分段互化，再取正长度平方根。
- R5：P7 + P8 -> P9，方法：在直角三角形中按“对边/邻边”读取正切值。
- 目标：由 P1、P2 先推出 P4，再由 P4、P6 得 P7，最后结合 P8 得 P9。

### 2.3 解题主链
```text
A,D,C 共线 + ∠ABD=∠ACB
-> △ABD∽△ACB
-> AD/AB=AB/AC=BD/BC
-> AD:CD=1:8 -> AC=9AD -> AB=3AD
-> tan C=BD/BC=AD/AB=1/3
```

### 2.4 模型标签
- model_id：`nested_similarity_trig_bridge`
- model_name：子母型相似—共线比—三角比桥接模型
- configuration：已知 $A-D-C$ 共线、$BD\perp BC$、$\angle ABD=\angle ACB$，给定 $AD:CD$ 或某个 $C$ 的三角比，求另一侧量。
- 可迁移方向：$AD:CD\to\tan C/\sin C/\cos C$；$\tan C/\sin C/\cos C\to AD:CD$；由一个三角比反求相似比或共线分点比。
- 非同构边界：若缺少 $BD\perp BC$，相似比不能直接解释为 $C$ 的锐角三角比；若 $D$ 不在线段 $AC$ 内部，$AC=AD+CD$ 的线段和关系需要改变。

## 二点五、知识点/模型锚点
- 建议讲义标题：子母型相似：在“共线比”和“三角比”之间搭桥
- 知识点/模型名称：子母型 AA 相似；相似对应边的平方关系；直角三角形三角比互化。
- 核心公式/定理：
  - $\triangle ABD\sim\triangle ACB$；
  - $\dfrac{AD}{AB}=\dfrac{AB}{AC}=\dfrac{BD}{BC}$；
  - $AB^2=AD\cdot AC$；
  - $\tan C=\dfrac{BD}{BC}=\dfrac{AD}{AB}$。
  - 设 $x=\dfrac{AD}{AC}$，则 $x=\tan^2 C$；又 $\dfrac{AD}{CD}=\dfrac{x}{1-x}$。
- 使用条件：$A,D,C$ 共线且 $D$ 在线段 $AC$ 上；两角保证子母三角形相似；$BD\perp BC$ 保证 $\triangle BCD$ 是直角三角形。
- 入口信号：题图中有“一个小三角形嵌在大三角形中”、共享顶角、另给一组等角，同时所求三角比落在旁边的直角三角形中。
- 易混边界：$CD$ 不是 $\triangle ABD$ 的边，不能直接塞进相似比；$\tan C$ 在 $\triangle BCD$ 中是 $BD/BC$，不是 $AB/BC$；相似对应顺序不能写成 $\triangle ABD\sim\triangle ABC$。
- 本题如何体现：$AD:CD$ 先转成 $AD:AC$，相似给出 $AD:AC=(AD/AB)^2$，再由 $AD/AB=BD/BC$ 接到 $\tan C$。
- 可作为例题的结构层级：条件包装 + 双模型桥接；适合作为讲解例题后接正向与反向练习。

## 三、关键转化
- 最关键的转化：把题面给出的分段比 $AD:CD$ 转为 $AD:AC$，再识别 $\dfrac{AD}{AC}=\left(\dfrac{AD}{AB}\right)^2=\tan^2C$。
- 为什么降低计算量：不必分别求出 $BD,BC$ 的实际长度，只需沿相似比传递比例；正反向都可用同一中间量 $x=AD/AC$。
- 不转化时的低效路径：设多个边长后在 $\triangle BCD$ 中列勾股关系，或误把 $CD$ 当作相似三角形的对应边，既增加未知量又容易列错比例。

## 四、标准路径骨架
1. 先做什么：利用 $A,D,C$ 共线写出 $\angle BAD=\angle CAB$。
2. 再做什么：结合 $\angle ABD=\angle ACB$，判定 $\triangle ABD\sim\triangle ACB$。
3. 建立什么关系：按顶点对应写 $\dfrac{AD}{AB}=\dfrac{AB}{AC}=\dfrac{BD}{BC}$。
4. 如何求解：把 $AD:CD$ 转成 $AD:AC$，用 $AB^2=AD\cdot AC$ 求 $AD/AB$；再在 $\triangle BCD$ 中读出 $\tan C$。反向题则从三角比求 $\tan^2C=AD/AC$，再转为 $AD:CD$。
5. 需要检查什么：相似顺序、$AC=AD+CD$、各线段为正、$C$ 为直角三角形中的锐角；若反求 $AD:CD$，还需确保 $0<\tan^2 C<1$，从而 $D$ 在线段 $AC$ 内。

## 四点五、标准完整解与验算
- 关键交点/关键量：令 $AD=x>0$，则 $CD=8x$，$AC=9x$。
- 面积/方程/关系式：$AB^2=AD\cdot AC=9x^2$。
- 完整求解过程：
  因为 $A,D,C$ 共线，所以 $\angle BAD=\angle CAB$。又 $\angle ABD=\angle ACB$，故 $\triangle ABD\sim\triangle ACB$。于是
  $$
  \frac{AD}{AB}=\frac{AB}{AC}=\frac{BD}{BC}.
  $$
  由 $AD:CD=1:8$，设 $AD=x$，则 $AC=9x$。所以 $AB^2=AD\cdot AC=9x^2$，由边长为正得 $AB=3x$。又 $BD\perp BC$，在 $\mathrm{Rt}\triangle BCD$ 中
  $$
  \tan C=\frac{BD}{BC}=\frac{AD}{AB}=\frac{x}{3x}=\frac13.
  $$
- 最终答案：$\boxed{\tan\angle ACB=\dfrac13}$。
- 排除值：$x>0$；取 $AB=3x$ 而不是 $-3x$。
- 退化情形：$AD=0$、$CD=0$ 或 $D$ 不在线段 $AC$ 内均不属于本题构型。
- 验算：$\tan^2 C=1/9=AD/AC=1/(1+8)$，与分段比一致。
- 本题最短可靠路径：先写相似链 $AD/AB=AB/AC=BD/BC$，再由 $AD:AC=1:9$ 直接得到 $AD/AB=1/3$。

## 五、出题人逻辑
- 诱导学生硬算的位置：看到 $BD\perp BC$ 后立刻想求 $BD,BC$；或围绕 $CD$ 列勾股关系。
- 真正的捷径：相似把 $BD/BC$ 等价替换为 $AD/AB$，而 $AB$ 由 $AB^2=AD\cdot AC$ 一步得到。
- 训练的可迁移能力：在不同三角形之间追踪同一个比值；把分段比、整段比、相似比和三角比串成可逆链条。

## 六、学生卡点预测
- 读题/入手动作卡点：只看到直角三角形 $BCD$，没有先观察子母三角形 $ABD$ 与 $ACB$。
- 建模/关系入口卡点：相似顺序写错；把 $CD$ 直接放进相似比；不知道先将 $AD:CD$ 变成 $AD:AC$。
- 求解/检查卡点：得到 $AB^2=9AD^2$ 后漏掉边长取正；把 $\tan C$ 写成 $AB/BC$；反向题从 $AD/AC$ 转 $AD/CD$ 时忘记“整段减去一段”。

## 七、变式原则
- 核心不变量：$A-D-C$ 共线、$BD\perp BC$、$\angle ABD=\angle ACB$，以及链条 $\dfrac{AD}{AC}=\tan^2 C$。
- 表层特征：给一个共线线段比或一个锐角三角比，求链条另一端的量。
- 可变维度：改变 $AD:CD$ 的数值；把所求从 $\tan C$ 换为 $\sin C$ 或 $\cos C$；把已知与所求互换；将比例写成整段比或分段比。
- 深化阶梯：原题复现（求 $\tan C$）→ 同结构换问法（求 $\sin C$ 或 $\cos C$）→ 反向由三角比求共线比 → 条件包装为判断或填空。
- 允许的变换：选取使结果为简单分数或简单根式的比例；允许用 $\sin^2C+\cos^2C=1$ 和 $\tan C=\sin C/\cos C$ 做一次互化。
- 禁止的变换：同时隐藏相似入口并加入复杂根式运算；改变点序却仍使用 $AC=AD+CD$；去掉垂直条件后仍把 $BD/BC$ 当作 $\tan C$。
- 表征切换：$AD:CD\leftrightarrow AD:AC\leftrightarrow\tan^2C\leftrightarrow\sin C,\cos C$。
- 包装方式：给出 $\sin C$ 或 $\cos C$，要求反求 $AD:CD$；给出一个候选分段比，判断对应三角比是否正确。
- 近迁移例子：已知 $AD:CD=1:7$，求 $\sin C$；已知 $AD:CD=9:7$，求 $\cos C$。
- 远迁移例子：已知 $\tan C=2/5$ 或 $\cos C=\sqrt3/2$，反求 $AD:CD$。
- 反例/伪变式：只改字母但把 $D$ 放到 $AC$ 的延长线上，不再满足原线段和关系；这不是同构换数。

## 八、计算复杂度预算
- 原题计算层级：一次分段转整段、一次平方关系、一次简单分数化简。
- 允许小步上升到：一次三角比互化或一次反向分段比变换；结果限简单分数或常见根式。
- 禁止引入的计算负担：反三角函数近似、复杂二次方程、多层根式有理化、无关的边角全解。
- 必须保留的可见支架：图中清楚标出 $A-D-C$ 的点序、$BD\perp BC$ 和相等角；前两题保留“先找相似”的短提示，后两题提示降为“先求 $AD/AC$”。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先问“$\tan C$ 在哪个直角三角形里？$BD/BC$ 又能否在相似三角形里找到等价比？”
- 本题讲解目标：让学生形成可逆桥梁 $AD:CD\to AD:AC\to\tan^2C$，而非记住某一个数值答案。
- 不要直接讲的抽象话：不要开场只说“利用相似和三角函数综合求解”；应落实到“先对角、再对边、最后换比”。
- 必须先问的问题：$\triangle ABD$ 与哪个三角形相似？顶点如何对应？$CD$ 是小三角形的边吗？
- 关键讲解顺序：锁定相似 → 写完整对应比 → 从 $AD:CD$ 得 $AD:AC$ → 发现平方关系 → 把 $AD/AB$ 读成 $\tan C$。
- 最适合的具体数值例子：原题 $AD:CD=1:8$，因 $AC=9AD$，平方开方后得到 $AB=3AD$，计算最干净。
- 讲到哪里停下来让学生回答：写出 $AD/AB=AB/AC=BD/BC$ 后，暂停让学生自己把 $AD:CD=1:8$ 接到 $\tan C$。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：给图并只要求写出相似三角形及对应边，不做计算。
- 若卡在建模或关系入口，出什么题：给 $AD:CD$，要求先填 $AD:AC$ 和 $\tan^2 C$，再求一个三角比。
- 若卡在求解和检查，出什么题：选能得到简单 $\sin C$、$\cos C$ 的比例，并要求写出三角比互化过程。
- 若原题已稳，如何小步迁移：由 $AD:CD$ 分别求 $\sin C$、$\cos C$，避免四题都停留在正切。
- 若结构识别已稳，如何深化/抽象/包装：给 $\tan C$ 或 $\cos C$，反求 $AD:CD$，明确先求 $x=AD/AC$ 再做 $x:(1-x)$。
- 禁止出的跑偏变式：要求求出所有边长和角度；加入圆、面积或坐标系等无关新模型。

## 十点五、推荐图形请求包（可选）
- 是否需要图：是。
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`、`practice_prompt`、`teacher_reference`
- 需要出现的对象：点 $A,B,C,D$；线段 $AB,AC,BD,BC$；$A-D-C$ 的点序；$BD\perp BC$；$\angle ABD$ 与 $\angle ACB$ 的等角标记。
- 需要突出给学生看的关系：小三角形 $ABD$ 嵌在大三角形 $ACB$ 中；直角三角形 $BCD$ 与相似链共享 $BD,BC$ 的比例。
- 图中不能暗示的错误性质：不要暗示 $AB=AC$、$D$ 是中点、$AB\perp BC$ 或额外平行关系；prompt 图不显示相似结论、比例或答案。
- 图失败时的降级方案：本图为理解构型的必需图，失败时停止 resolve，不用纯文字替代。

## 十一点、模型规则入库草案（可选）
暂不入库。本题属于纯平面几何中的相似—三角比桥接模型，当前 v0 typed relation 库只覆盖一次函数、坐标面积和坐标存在性。

下一步建议：先使用 math-model-rule-ingestion 将本结构分析中的模型规则规范化为 canonical relations；随后 math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 可并行消费结构分析和模型库关系。工作流：math-structure-analysis → math-model-rule-ingestion →（math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 并行）→ math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
