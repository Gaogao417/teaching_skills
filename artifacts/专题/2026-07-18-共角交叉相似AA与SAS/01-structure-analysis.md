# 结构分析：共角交叉相似链中的 AA 与 SAS

## 原题

参照教师手绘图：在 $\triangle ADE$ 中，点 $B,D$ 在射线 $AD$ 上，点 $C,E$ 在射线 $AE$ 上，点序分别为 $A-B-D$ 和 $A-C-E$，$BE$ 与 $CD$ 交于点 $O$。已知

\[
\triangle ABC\sim\triangle AED.
\]

沿下列关系链逐步证明，每个箭头为一个小问：

\[
\triangle ABC\sim\triangle AED
\Longrightarrow
\triangle ACD\sim\triangle ABE
\Longrightarrow
\triangle BOD\sim\triangle COE
\Longrightarrow
\triangle BOC\sim\triangle DOE.
\]

教学时说明：图中四组相似实际上可互相逆推，本讲义先按手绘图的箭头方向训练正向证明。

原始参考图：`/Users/gaochong/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_jfjy52m4e8io21_6e3d/temp/RWTemp/2026-07/3dd471d5143500392b464021b32525cf.png`

## 一、题目场景

- 数学对象：共顶点的大、小两组三角形，以及两条交叉线 $BE,CD$ 在点 $O$ 产生的四个小三角形。
- 变量/参数：无数值参数；以线段比和角相等为主要信息。
- 函数/图形：平面合成几何；$A-B-D$ 共线，$A-C-E$ 共线，$B-O-E$ 共线，$C-O-D$ 共线。
- 已知条件：$\triangle ABC\sim\triangle AED$，对应关系为 $A\leftrightarrow A$，$B\leftrightarrow E$，$C\leftrightarrow D$。
- 要求目标：依次证明其余三组相似，分别训练 SAS、AA、SAS。

## 二、核心结构

### 2.1 表层信息

- 表面考点：相似三角形的判定，对应边比，共角/对顶角，角的和差。
- 题型功能：`proof_model`
- 是否值得完整 structural analysis：是；同一幅图中紧密串联 SAS 与 AA 两种判定，且可提炼为稳定的搜索顺序。
- 一句话问题模式：先利用共顶点角把外层边比“换位”成新的 SAS，再用对顶角和上一组相似的对应角完成 AA，最后把交点周围的边比换位后再做 SAS。

### 2.2 结构表达

#### 判别条件表（概念辨析题用；不适用则写“无”）

- 必要条件：无。
- 充分条件：无。
- 常见干扰项：看到一个相等角就直接写相似；SAS 写了非夹角两边的比；不检查三角形顶点顺序。
- 最短检查动作：SAS 把角顶点圈出并只看它两侧；AA 先写一对确定相等的角，再定向搜第二对。

#### 情景量表（应用题用；不适用则写“无”）

无。

#### 命题网络（所有题型都写）

- P1（题设）：$\triangle ABC\sim\triangle AED$。
- P2（定理）：由 P1 得 $\dfrac{AB}{AE}=\dfrac{AC}{AD}$。
- P3（可推）：交叉相乘后换位，得 $\dfrac{AC}{AB}=\dfrac{AD}{AE}$。
- P4（题设/共线）：$\angle CAD=\angle BAE$，它们都是射线 $AD,AE$ 的夹角。
- P5（目标 1）：$\triangle ACD\sim\triangle ABE$。
- P6（定理）：$\angle BOD=\angle COE$（对顶角）。
- P7（可推）：$\angle BDO=\angle CEO$（由 P5 的对应角与共线关系得到）。
- P8（目标 2）：$\triangle BOD\sim\triangle COE$。
- P9（定理）：由 P8 得 $\dfrac{BO}{CO}=\dfrac{DO}{EO}$，从而 $\dfrac{BO}{DO}=\dfrac{CO}{EO}$。
- P10（定理）：$\angle BOC=\angle DOE$（对顶角）。
- P11（目标 3）：$\triangle BOC\sim\triangle DOE$。
- R1：P1 + P2 -> P3，方法：对应边成比例与比例换位。
- R2：P3 + P4 -> P5，方法：SAS 相似判定。
- R3：P5 + 共线关系 -> P7，方法：对应角传递。
- R4：P6 + P7 -> P8，方法：AA 相似判定。
- R5：P8 -> P9，方法：对应边成比例与比例换位。
- R6：P9 + P10 -> P11，方法：SAS 相似判定。
- 目标：依次由 R2、R4、R6 完成三个箭头。

### 2.3 解题主链

```text
外层相似给边比
-> 共角 A + 夹角两边比（SAS）
-> 上一组对应角 + O 处对顶角（AA）
-> O 周围的对应边比换位 + O 处对顶角（SAS）
```

### 2.4 模型标签

- model_id：`shared-angle-cross-similarity-chain`
- model_name：共角交叉相似链
- configuration：已知两条射线上一组交叉对应的外层相似，要求将相似传递到另一组共角三角形与交点周围的三角形。
- 可迁移方向：射线方向翻转、图形旋转、将已知相似改为直接给出线段积等式，或从内层相似逆推外层相似。
- 非同构边界：若 $B,D$ 或 $C,E$ 不共线，或 $BE,CD$ 不交于同一点 $O$，则共角、对应角传递和对顶角链不再成立。

## 二点五、知识点/模型锚点

- 建议讲义标题：共角交叉相似链：SAS 先锁角，AA 先锁一对角
- 知识点/模型名称：SAS 的“夹角—夹边比”搜索法；AA 的“确定角—第二角”搜索法。
- 核心公式/定理：
  - SAS：一角对应相等，且夹该角的两边对应成比例，两三角形相似。
  - AA：两角对应相等，两三角形相似。
- 使用条件：SAS 的相等角必须是两组成比例边的夹角；AA 必须准确确定两对对应角。
- 入口信号：
  - 两个三角形共一个顶点、共用或共线形成同一角 -> 先尝试 SAS。
  - 两条直线交于 $O$ -> 先写对顶角，再找第二对角 -> 尝试 AA。
- 易混边界：“两边成比例+一角相等”不自动是 SAS；必须检查这一角是夹角。“找到对顶角”只完成 AA 的一半。
- 本题如何体现：第 1 问以 $A$ 为夹角；第 2 问以 $O$ 处对顶角为 AA 入口；第 3 问再以 $O$ 处对顶角为 SAS 夹角。
- 可作为例题的结构层级：小专题型，一幅图三个真实小问。

## 三、关键转化

- 最关键的转化：不从“想证哪组相似”空想条件，而是先锁定最稳定的角，再根据判定方法只补剩余条件。
- 为什么降低计算量：SAS 锁角后只需处理四条夹边的一个比例；AA 锁定对顶角后只需追一对角，避免无目的倒角。
- 不转化时的低效路径：罗列所有角、任意写边比，或反复改三角形顶点顺序试错。

## 四、标准路径骨架

1. 先做什么：每问先圈出最稳定的角；第 1 问是共顶点角 $A$，第 2、3 问是 $O$ 处对顶角。
2. 再做什么：判断要走 SAS 还是 AA，并写出尚缺的唯一条件。
3. 建立什么关系：SAS 补夹角两边比；AA 补第二对角。
4. 如何求解：从已知相似提取对应边比或对应角；SAS 时换位比例，AA 时借助共线把对应角移到目标三角形。
5. 需要检查什么：相似式顶点顺序与边比、角对应是否一致。

## 四点五、标准完整解与验算

- 关键交点/关键量：$O=BE\cap CD$；$\angle BOC$ 与 $\angle DOE$、$\angle BOD$ 与 $\angle COE$ 分别为对顶角。
- 面积/方程/关系式：无面积与数值方程；核心关系为比例换位、对应角和共线关系。
- 完整求解过程：
  1. 由 $\triangle ABC\sim\triangle AED$ 得 $\dfrac{AB}{AE}=\dfrac{AC}{AD}$，即 $AB\cdot AD=AC\cdot AE$，所以 $\dfrac{AC}{AB}=\dfrac{AD}{AE}$。又 $\angle CAD=\angle BAE$，故 $\triangle ACD\sim\triangle ABE$（SAS）。
  2. $\angle BOD=\angle COE$。由 $\triangle ACD\sim\triangle ABE$ 得 $\angle ADC=\angle AEB$；又因 $A,B,D$ 共线、$C,O,D$ 共线、$A,C,E$ 共线、$B,O,E$ 共线，所以 $\angle BDO=\angle ADC$，$\angle CEO=\angle AEB$，从而 $\angle BDO=\angle CEO$。故 $\triangle BOD\sim\triangle COE$（AA）。
  3. 由 $\triangle BOD\sim\triangle COE$ 得 $\dfrac{BO}{CO}=\dfrac{DO}{EO}$，交叉相乘后换位得 $\dfrac{BO}{DO}=\dfrac{CO}{EO}$。又 $\angle BOC=\angle DOE$，故 $\triangle BOC\sim\triangle DOE$（SAS）。
- 最终答案：三个箭头均成立。
- 排除值：无。
- 退化情形：点重合、$BE\parallel CD$ 或三角形退化时不在正常题设范围内。
- 验算：三组结论的对应顶点顺序与证明中的角、边一致：$ACD\leftrightarrow ABE$，$BOD\leftrightarrow COE$，$BOC\leftrightarrow DOE$。
- 本题最短可靠路径：每问只写“锁角—补唯一条件—判定”，不额外证明本问不需要的性质。

## 五、出题人逻辑

- 诱导学生硬算的位置：图中三角形数量多，学生容易试图穷举角或写尽所有比例。
- 真正的捷径：每个箭头都有一个“免费角”：$A$ 处共角或 $O$ 处对顶角。
- 训练的可迁移能力：根据最先找到的角选择 SAS/AA，并把已知相似的边比/角信息精准转移给下一组三角形。

## 六、学生卡点预测

- 读题/入手动作卡点：不能先标出两个待证三角形的相同/对顶角，一上来就翻找所有边比。
- 建模/关系入口卡点：SAS 不会围着已知角选边；比例只会原样照抄，不会交叉相乘后换位。
- 求解/检查卡点：AA 找到对顶角就停下；或没有利用共线关系把上一组相似的对应角移到目标三角形。

## 七、变式原则

- 核心不变量：两条共顶点射线+两条交叉线+“对应边比换位”与“对应角沿共线关系传递”。
- 表层特征：大三角形内有 $BC$ 与两条交叉线 $BE,CD$。
- 可变维度：整图旋转/翻转；改变已知的相似组；将相似条件改为线段积相等；要求逆向证明。
- 深化阶梯：
  1. 原题复现：按三个箭头补全理由。
  2. 同结构换问法：只给出中间一组相似，逆推外层或内层。
  3. 条件包装：把 $\triangle ABC\sim\triangle AED$ 换成 $AB\cdot AD=AC\cdot AE$。
  4. 结构部分隐藏：不提示目标三角形，要求找出图中所有相似组。
- 允许的变换：只变一个主维度，并保留共线和交点结构。
- 禁止的变换：同时加入平行、圆、等腰等新知识，使原有 SAS/AA 入口不再是主线。
- 表征切换：从相似式切换到边比表、角对应表或箭头流程图。
- 包装方式：只给出两条线段乘积相等，要求学生自己决定从哪一组共角三角形入手。
- 近迁移例子：已知 $AB\cdot AD=AC\cdot AE$，证明 $\triangle ACD\sim\triangle ABE$。
- 远迁移例子：已知 $\triangle BOD\sim\triangle COE$，逆向证明 $\triangle ABC\sim\triangle AED$。
- 反例/伪变式：只把一组线段改成整数长度，但同时破坏 $A-B-D$、$A-C-E$ 共线；这已不是同一命题网络。

## 八、计算复杂度预算

- 原题计算层级：无数值计算；两个 SAS 箭头各做一次比例换位，AA 箭头只做对应角传递。
- 允许小步上升到：用简单整数比先求一条线段，再证明相似。
- 禁止引入的计算负担：根式、三角函数、面积系统或坐标化证明。
- 必须保留的可见支架：每问明示“先找角”；SAS 把夹角两侧边写在同一个比例中；AA 显式写出第二对角的来源。

## 九、推荐讲题任务包

- 建议的本轮教学入口：先把三个箭头分成三问，每问第一句都是“先找最稳定的角”。
- 本题讲解目标：学生能说出并执行两个口令：“SAS：先找角，再证夹边比”；“AA：先找一对角，再找另一对角”。
- 不要直接讲的抽象话：“这是经典模型，背下四组相似”。
- 必须先问的问题：“这两个待证三角形中，哪一对角不用计算就一定相等？”
- 关键讲解顺序：第 1 问示范 SAS 搜索；第 2 问用“对顶角+上一问对应角”快速完成 AA；第 3 问让学生自己迁移回 SAS。
- 最适合的具体数值例子：本讲解不需要数值；若追加口算，可用 $AB:AE=2:3$、$AC:AD=2:3$ 演示比例换位。
- 讲到哪里停下来让学生回答：第 1 问找到角 $A$ 后，让学生写夹边比；第 2 问写出对顶角后，让学生补第二对角；第 3 问写出对顶角后，让学生把已知边比换位。

## 十、推荐练题任务包

- 若卡在读题/入手动作，出什么题：只给两组待证三角形，要求圈出共角或对顶角，不写完整证明。
- 若卡在建模或关系入口，出什么题：给出一个已知比例，只要求整理成目标夹边比。
- 若卡在求解和检查，出什么题：给出错序的相似式和边比，要求根据角对应修正顶点顺序。
- 若原题已稳，如何小步迁移：将第 3 组相似作为已知，逆向证明第 2 组。
- 若结构识别已稳，如何深化/抽象/包装：把已知相似改成一个线段积等式，要求学生先自己确定目标三角形。
- 禁止出的跑偏变式：同时混入圆幂定理、角平分线或复杂长度计算，排挤本节的 SAS/AA 搜索动作。

## 十点五、推荐图形请求包（可选）

- 是否需要图：是。
- 图形类型：`synthetic_geometry`
- 用图意图：`student_explanation`
- 需要出现的对象：外层 $\triangle ADE$，内点 $B,C$，线段 $BC,BE,CD,DE$，交点 $O$，并准确保持 $A-B-D$、$A-C-E$、$B-O-E$、$C-O-D$ 的共线关系。
- 需要突出给学生看的关系：点 $A$ 周围两组三角形共用同一个大角；点 $O$ 周围有两组对顶角。
- 图中不能暗示的错误性质：不要画成等腰、直角、平行或轴对称；不在 prompt 图上写相似结论或边比。
- 图失败时的降级方案：保留题干中的共线文字描述，让学生先手绘点序与两条交叉线。

## 十一、模型规则入库草案（可选）

暂不入库。本题属于几何证明模型，当前 v0 模型规则库不覆盖该类型。

下一步建议：先使用 math-model-rule-ingestion 将本结构分析中的模型规则规范化为 canonical relations；随后 math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 可并行消费结构分析和模型库关系。工作流：math-structure-analysis → math-model-rule-ingestion →（math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 并行）→ math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
