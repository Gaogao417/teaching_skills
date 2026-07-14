# 结构分析：子母型相似中的相似比与对应边

## 原题
在 $\triangle ABC$ 中，点 $D$ 在线段 $AC$ 上，且 $\angle ABD=\angle ACB$。

1. 判断 $\triangle ABD$ 与 $\triangle ACB$ 的关系，并写出三组对应边；
2. 辨析“$AC/CD$ 就是两个相似三角形的相似比”是否正确；
3. 已知 $AC=9$，$CD=5$，求 $AB$；若再给出 $BC=12$，求 $BD$。

## 一、题目场景
- 数学对象：共用顶点 $A$ 的小三角形 $\triangle ABD$ 与大三角形 $\triangle ACB$。
- 变量/参数：$AC,CD,AD,AB,BC,BD$ 及大、小三角形的相似比。
- 函数/图形：$D$ 在线段 $AC$ 上，线段 $BD$ 把 $\triangle ABC$ 分成两个三角形；其中 $\triangle ABD$ 是待识别的小三角形。
- 已知条件：$D\in AC$，$\angle ABD=\angle ACB$；数值例题中 $AC=9,CD=5,BC=12$。
- 要求目标：确认相似、锁定对应边，区分 $AC/CD$ 与真正相似比，并由整段、差段和一条对应边求另一条边。

本专题的首要训练不是记住子母型公式，而是形成两个固定反应：看到题目给出 $\angle ABD=\angle ACB$，立即在两个候选三角形中寻找第二组等角并判相似；相似成立后，按“等角顶点 -> 对应顶点 -> 对应边”写出三组对应边，再处理线段和差。

## 二、核心结构
### 2.1 表层信息
- 表面考点：两角对应相等判定三角形相似、相似三角形对应边成比例、线段和差。
- 题型功能：`basic_skill`
- 是否值得完整 structural analysis：是；理由：图中 $AC,CD$ 很显眼，但 $CD$ 不是小三角形 $\triangle ABD$ 的边，容易把非对应量误写成相似比。
- 一句话问题模式：看到题设等角 -> 寻找公共顶点处第二组等角 -> 判定子母三角形相似 -> 由角锁定对应边 -> 把整段与差段转成对应边比。

### 2.2 结构表达
#### 判别条件表（概念辨析题用；不适用则写“无”）
- 必要条件：写比例前，两边必须分别来自两个相似三角形，并且位置对应。
- 充分条件：由 $D\in AC$ 得 $\angle BAD=\angle CAB$，再与 $\angle ABD=\angle ACB$ 组成 AA 相似。
- 常见干扰项：把共线段 $CD$ 看成小三角形的边；把 $AC/CD$ 直接称为相似比；只凭图形大小猜对应边。
- 最短检查动作：先写 $\triangle ABD\sim\triangle ACB$，按顶点顺序读出 $A\leftrightarrow A$、$B\leftrightarrow C$、$D\leftrightarrow B$。

#### 情景量表（应用题用；不适用则写“无”）
无。

#### 命题网络（所有题型都写；简单题写简版）
- P1（题设）：$D$ 在线段 $AC$ 上。
- P2（题设）：$\angle ABD=\angle ACB$。
- P3（可推）：$\angle BAD=\angle CAB$。
- P4（可推结论）：$\triangle ABD\sim\triangle ACB$，顶点对应为 $A\leftrightarrow A$、$B\leftrightarrow C$、$D\leftrightarrow B$。
- P5（可推结论）：$AB\leftrightarrow AC$、$AD\leftrightarrow AB$、$BD\leftrightarrow BC$。
- P6（可推结论）：大三角形与小三角形的相似比满足
  $$\frac{AC}{AB}=\frac{AB}{AD}=\frac{BC}{BD}.$$
- P7（题设/计算状态）：$AD=AC-CD$。
- P8（目标）：由 $AC,CD$ 及一条边求其对应边。
- R1：P1 -> P3，方法：共线射线 $AD$ 与 $AC$ 重合，得到公共顶点处的同角。
- R2：P2 + P3 -> P4，方法：两角分别相等判定三角形相似。
- R3：P4 -> P5，方法：按相似三角形书写顺序匹配对应顶点和对应边。
- R4：P5 -> P6，方法：相似三角形对应边成比例。
- R5：P1 -> P7，方法：线段和差 $AC=AD+CD$。
- R6：P6 + P7 -> P8，方法：先用 $AB^2=AC\cdot AD$ 求中间对应边，再按同一相似比求另一组对应边。
- 目标：由 P4、P5 排除 $AC/CD$ 是相似比的误判，再由 P6、P7 完成边长计算。

### 2.3 解题主链
```text
看到 ∠ABD=∠ACB -> 寻找第二组角 -> D在AC上，所以 ∠BAD=∠CAB
-> △ABD∽△ACB -> A↔A，B↔C，D↔B
-> AB↔AC，AD↔AB，BD↔BC
-> AC/AB=AB/AD=BC/BD
+ AD=AC-CD -> 求对应边
```

### 2.4 模型标签
- model_id：`similarity_nested_shared_vertex_correspondence`
- model_name：子母型相似：先定顶点对应，再处理整段与差段
- configuration：已知 $D\in AC$ 与一组角相等，要求识别相似、辨析相似比，并由 $AC,CD$ 和一条边求对应边。
- 可迁移方向：交换已知边和所求边；给出 $AC/CD=t$ 后先转成 $AD/AC=(t-1)/t$；由 $AB^2=AC\cdot AD$ 反求任一量。
- 非同构边界：若没有第二组相等角或其他足以判相似的条件，不能只凭“子母型”外观列比例；若 $D$ 不在线段 $AC$ 上，线段和差关系要随点序重判。

## 二点五、知识点/模型锚点
- 建议讲义标题：子母型相似：$AC/CD$ 为什么不是相似比
- 知识点/模型名称：AA 相似、顶点顺序与对应边、整段减差段、比例链。
- 核心公式/定理：
  - $\triangle ABD\sim\triangle ACB$；
  - $AB\leftrightarrow AC$、$AD\leftrightarrow AB$、$BD\leftrightarrow BC$；
  - $\dfrac{AC}{AB}=\dfrac{AB}{AD}=\dfrac{BC}{BD}$；
  - $AD=AC-CD$，从而 $AB^2=AC\cdot AD$。
- 使用条件：$D$ 在线段 $AC$ 上；已知 $\angle ABD=\angle ACB$；比例式中的分子、分母必须来自对应边。
- 入口信号：大三角形里嵌着一个共用顶点的小三角形，且给出一组跨三角形的角相等。
- 易混边界：$CD$ 只是 $AC$ 上剩余的一段，不是 $\triangle ABD$ 的边，所以 $AC/CD$ 不能直接作为两三角形的相似比。
- 本题如何体现：由 $AC/CD$ 只能先求 $AD/AC$，之后还需开平方才能得到大/小相似比。
- 可作为例题的结构层级：先辨析对应边，再完成一组干净整数计算。

若只知 $AC/CD=t$，因 $AC=t\,CD$，所以
$$AD=AC-CD=(t-1)CD,\qquad \frac{AD}{AC}=\frac{t-1}{t}.$$
又由 $AB^2=AC\cdot AD$，得到
$$\frac{AC}{AB}=\sqrt{\frac{AC}{AD}}=\sqrt{\frac{t}{t-1}}.$$
因此 $AC/CD=t$ 不是相似比；真正的大/小相似比是 $\sqrt{t/(t-1)}$。

## 三、关键转化
- 最关键的转化：把醒目的 $AC/CD$ 拆回 $AD=AC-CD$，再用真正的对应边式 $AC/AB=AB/AD$。
- 为什么降低计算量：比例链直接给出 $AB^2=AC\cdot AD$，不必设多个未知数或重复列比例。
- 不转化时的低效路径：把 $AC/CD$ 当成相似比后计算，会得到与三组对应边不一致的结果；即使偶然数值整齐，也无法通过比例链验算。

## 四、标准路径骨架
1. 先做什么：由 $D\in AC$ 写出 $\angle BAD=\angle CAB$。
2. 再做什么：结合 $\angle ABD=\angle ACB$，判定 $\triangle ABD\sim\triangle ACB$。
3. 建立什么关系：按顺序写出 $AB\leftrightarrow AC$、$AD\leftrightarrow AB$、$BD\leftrightarrow BC$，列 $AC/AB=AB/AD=BC/BD$。
4. 如何求解：先算 $AD=AC-CD$，由 $AB^2=AC\cdot AD$ 求 $AB$；再用 $BC/BD=AC/AB$ 求 $BD$。
5. 需要检查什么：所列比例是否全部是对应边；边长是否为正；数值是否满足三组比例相等。

## 四点五、标准完整解与验算
- 关键交点/关键量：$AD=AC-CD=9-5=4$。
- 面积/方程/关系式：本题不使用面积；核心关系为 $AC/AB=AB/AD=BC/BD$。
- 完整求解过程：
  由 $D$ 在线段 $AC$ 上，得 $\angle BAD=\angle CAB$。又因 $\angle ABD=\angle ACB$，所以 $\triangle ABD\sim\triangle ACB$。

  顶点对应为 $A\leftrightarrow A$、$B\leftrightarrow C$、$D\leftrightarrow B$，故
  $$\frac{AC}{AB}=\frac{AB}{AD}=\frac{BC}{BD}.$$
  已知 $AC=9,CD=5$，所以 $AD=9-5=4$。由
  $$\frac{9}{AB}=\frac{AB}{4}$$
  得 $AB^2=36$。边长取正值，所以 $AB=6$。

  若 $BC=12$，则
  $$\frac{12}{BD}=\frac{9}{6}=\frac32,$$
  解得 $BD=8$。
- 最终答案：$AB=6$；若 $BC=12$，则 $BD=8$。
- 排除值：$AB,BD$ 为边长，舍去负根；一般式中需 $t=AC/CD>1$，才能保证 $D$ 在线段 $AC$ 上且 $AD>0$。
- 退化情形：$CD=AC$ 时 $AD=0$，小三角形退化，不能使用相似三角形比例；$CD\ge AC$ 不符合 $D$ 在线段 $AC$ 内且三角形非退化的设定。
- 验算：$AC/AB=9/6=3/2$，$AB/AD=6/4=3/2$，$BC/BD=12/8=3/2$，三组比例一致。
- 本题最短可靠路径：判相似并锁对应边 -> $AD=AC-CD$ -> $AB^2=AC\cdot AD$ -> 同比求 $BD$。

## 五、出题人逻辑
- 诱导学生硬算的位置：题面同时出现 $AC$ 与 $CD$，诱导学生把这两个量直接拼成相似比。
- 真正的捷径：相似三角形名称顺序本身已经编码了对应关系；先写对应边，再决定哪些已知量需要转换。
- 训练的可迁移能力：不看“图上挨得近不近”，只按角和顶点顺序确定对应边；把非三角形边转换为三角形边后再列比例。

## 六、学生卡点预测
- 读题/入手动作卡点：看见“子母型”却不知道利用公共顶点角；误以为 $CD$ 是小三角形的一条边。
- 建模/关系入口卡点：能判相似，但把相似式写成 $AC/CD$；或把 $AD$ 错配给 $BC$。
- 求解/检查卡点：由 $AB^2=36$ 写成 $AB=\pm6$ 而忘记边长取正；求出 $BD$ 后不检查三组比是否一致。

## 七、变式原则
- 核心不变量：$D\in AC$、两角判相似、对应顺序 $A\leftrightarrow A$、$B\leftrightarrow C$、$D\leftrightarrow B$。
- 表层特征：一个大三角形内嵌一个共顶点小三角形，$AC$ 被 $D$ 分成 $AD,CD$。
- 可变维度：边长数值、给定的对应边组、所求边、是否用 $AC/CD=t$ 包装条件。
- 深化阶梯：先直接给 $AC,CD$；再给 $AC/CD$；再交换已知与所求；最后判断某个比是否是真正相似比。
- 允许的变换：换干净正数；由给 $BC$ 求 $BD$ 改为给 $BD$ 求 $BC$；由给 $AC,CD$ 改为给 $AC/CD=t$。
- 禁止的变换：删除相似判定所需条件却仍要求使用比例；把 $D$ 移到 $AC$ 延长线上而不明确改变线段关系；把 $AC/CD$ 直接命名为相似比。
- 表征切换：由图形题切换为“相似三角形顺序 + 线段和差”的文字题，或用比例链填空。
- 包装方式：先问“下面哪个比是真正相似比”，再进行边长计算。
- 近迁移例子：已知 $AC=16,CD=7$，先求 $AD$，再由 $AB^2=AC\cdot AD$ 求 $AB$。
- 远迁移例子：已知 $AC/CD=t$ 与 $BC$，用含 $t$ 的式子表示 $BD$。
- 反例/伪变式：只保留一个角相等且不给其他相似条件，却仍要求列出同样的比例链；这已破坏核心命题网络。

## 八、计算复杂度预算
- 原题计算层级：一次减法、一次平方根（设计成完全平方数）、一次一元比例计算。
- 允许小步上升到：含参数 $t$ 的根式相似比 $\sqrt{t/(t-1)}$，但不与复杂根式化简同时出现。
- 禁止引入的计算负担：无理数分母有理化、多层分式方程、与本模型无关的面积或三角函数计算。
- 必须保留的可见支架：相似三角形书写顺序、三组对应边、$AD=AC-CD$、边长取正。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先圈出题设 $\angle ABD=\angle ACB$，追问“已经有一组角相等，两个候选三角形在 $A$ 点还能找到哪一组角？”
- 本题讲解目标：学生看到角相等会主动寻找第二组角和相似三角形；相似成立后能按角的顶点写出三组对应边，并据此否定“$AC/CD$ 就是相似比”。
- 不要直接讲的抽象话：不要只说“找准对应边”；必须让学生逐个说出顶点对应和边对应。
- 必须先问的问题：$\triangle ABD$ 中有没有边 $CD$？
- 关键讲解顺序：公共角 -> AA 相似 -> 顶点对应 -> 三组边对应 -> 线段和差 -> 数值计算 -> 比例验算。
- 最适合的具体数值例子：$AC=9,CD=5$，则 $AD=4,AB=6$；再给 $BC=12$，求得 $BD=8$。
- 讲到哪里停下来让学生回答：写出 $\triangle ABD\sim\triangle ACB$ 后暂停，让学生独立完成三组对应边；写出 $AD=4$ 后再停，让学生选用哪一组比例。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：只要求补出公共角并写出相似三角形的正确顺序。
- 若卡在建模或关系入口，出什么题：给出四个比，判断哪些是对应边比，并说明 $AC/CD$ 为什么不是。
- 若卡在求解和检查，出什么题：给 $AC,CD$ 求 $AB$，要求最后验算 $AC/AB=AB/AD$。
- 若原题已稳，如何小步迁移：给 $AC/CD=t$ 与 $BC$，求 $BD$ 的表达式。
- 若结构识别已稳，如何深化/抽象/包装：反向给出相似比与 $CD$，求 $AC$ 或判断条件是否能唯一确定边长。
- 禁止出的跑偏变式：加入无关平行线、角平分线或面积条件，使练习变成另一个模型。

## 十点五、推荐图形请求包（可选）
- 是否需要图：是。
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：$\triangle ABC$、点 $D$ 在线段 $AC$ 上、线段 $BD$，并清楚显示小三角形 $\triangle ABD$ 嵌在大三角形中。
- 需要突出给学生看的关系：题设图只标点和等角符号；学生应能看清 $AC=AD+CD$，但不预先画出对应边箭头。
- 图中不能暗示的错误性质：不要画成 $BD\parallel BC$、不要暗示等腰或直角、不要把 $D$ 画成 $AC$ 中点、不要让 $CD$ 看起来像 $\triangle ABD$ 的边。
- 图失败时的降级方案：必需图失败则停止该讲义的图形 resolve，不以手写 TikZ 或错误构型替代。

## 十一点、模型规则入库草案（可选）
暂不入库：本题属于普通欧氏几何相似模型，当前 v0 模型规则库不覆盖几何证明模型。

下一步建议：先使用 math-model-rule-ingestion 将本结构分析中的模型规则规范化为 canonical relations；随后 math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 可并行消费结构分析和模型库关系。工作流：math-structure-analysis → math-model-rule-ingestion →（math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 并行）→ math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
