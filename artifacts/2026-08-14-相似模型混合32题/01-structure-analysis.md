# 结构分析：反 A 一图四相似——相似证明三步法

## 原题
如图，在 $\triangle ABC$ 中，点 $D$、$E$ 分别在 $AB$、$AC$ 上，且 $\angle ADE=\angle ACB$。连接 $BE$、$CD$，相交于点 $O$。从 $\angle ADE=\angle ACB$ 出发，图中可以依次推出四对相似三角形。

图形文字描述：画三角形 $ABC$，$D$ 在 $AB$ 上、$E$ 在 $AC$ 上，满足 $\angle ADE=\angle ACB$（反 A 形）；连接 $DE$、$BE$、$CD$，$BE$ 与 $CD$ 交于点 $O$。这是经典的"反 A 一图四相似"构型。

## 一、题目场景
- 数学对象：$\triangle ADE$、$\triangle ACB$、$\triangle ADC$、$\triangle AEB$、$\triangle ODB$、$\triangle OEC$、$\triangle ODE$、$\triangle OBC$。
- 已知条件：$D$ 在 $AB$ 上，$E$ 在 $AC$ 上，$\angle ADE=\angle ACB$，$BE$ 与 $CD$ 交于 $O$。
- 要求目标：证明四对相似，并让学生写出"每一次相似推出了什么——是角相等，还是边成比例"。

本专题的首要训练不是"证明四对相似"这个结论本身，而是建立三个固定动作：先找等角、再选判定方法、最后按格式落笔；并且每一组相似推出什么，要明确写出来，供下一组相似复用。

## 二、核心结构
### 2.1 表层信息
- 表面考点：相似三角形的判定（AA、SAS）、对应顶点与对应边、结论的传递（上一组推出的条件供下一组使用）。
- 题型功能：proof_chain
- 是否值得完整 structural analysis：是；理由：四对相似构成一条"结论喂养链"，是训练"找等角 → 选判定 → 写格式"三段式证明书写的最佳载体。
- 一句话问题模式：给出一组角相等（反 A 入口）→ 依次推出四对相似，且每一对都用上一对的结论。

### 2.2 结构表达
#### 命题网络
- P1（题设）：$\triangle ABC$，$D$ 在 $AB$ 上，$E$ 在 $AC$ 上。
- P2（题设）：$\angle ADE=\angle ACB$。
- P3（可推）：$\angle DAE=\angle CAB$（公共角 $A$）。
- P4（可推）：$\triangle ADE\sim\triangle ACB$（AA），对应 $A\leftrightarrow A$、$D\leftrightarrow C$、$E\leftrightarrow B$。
- P5（可推）：$\dfrac{AD}{AC}=\dfrac{AE}{AB}=\dfrac{DE}{CB}$（边成比例）。
- P6（可推）：$\dfrac{AD}{AE}=\dfrac{AC}{AB}$（由 P5 交叉相乘后交换内项）。
- P7（可推）：$\triangle ADC\sim\triangle AEB$（SAS），对应 $A\leftrightarrow A$、$D\leftrightarrow E$、$C\leftrightarrow B$。
- P8（可推）：$\angle ADC=\angle AEB$，$\angle ACD=\angle ABE$（角相等）。
- P9（作图）：$BE$ 与 $CD$ 交于 $O$。
- P10（可推）：$\angle DOB=\angle EOC$、$\angle DOE=\angle BOC$（对顶角）。
- P11（可推）：$\angle ODB=\angle OEC$（P8 中等角的补角相等）。
- P12（可推）：$\triangle ODB\sim\triangle OEC$（AA），对应 $O\leftrightarrow O$、$D\leftrightarrow E$、$B\leftrightarrow C$。
- P13（可推）：$\dfrac{OD}{OE}=\dfrac{OB}{OC}=\dfrac{DB}{EC}$（边成比例）。
- P14（可推）：$\dfrac{OD}{OB}=\dfrac{OE}{OC}$（由 P13 交叉相乘后交换内项）。
- P15（可推）：$\triangle ODE\sim\triangle OBC$（SAS），对应 $O\leftrightarrow O$、$D\leftrightarrow B$、$E\leftrightarrow C$。
- P16（可推）：$\angle ODE=\angle OBC$、$\angle OED=\angle OCB$（角相等）。
- 关系链：
  - R1：P1 + P2 + P3 → P4，方法：两角分别相等（AA）。
  - R2：P4 → P5，方法：相似三角形对应边成比例。
  - R3：P5 → P6，方法：交叉相乘后交换内项。
  - R4：P3 + P6 → P7，方法：两边成比例且夹角相等（SAS）。
  - R5：P7 → P8，方法：相似三角形对应角相等。
  - R6：P9 → P10，方法：对顶角相等。
  - R7：P8 → P11，方法：等角的补角相等。
  - R8：P10 + P11 → P12，方法：两角分别相等（AA）。
  - R9：P12 → P13，方法：对应边成比例。
  - R10：P13 → P14，方法：交叉相乘后交换内项。
  - R11：P10 + P14 → P15，方法：两边成比例且夹角相等（SAS）。
  - R12：P15 → P16，方法：对应角相等。
- 目标：按"找等角 → 选判定 → 写格式"的顺序，证明四对相似，并明确每一对推出的结论。

### 2.3 解题主链
第一步 $\angle ADE=\angle ACB$ 加公共角 $A$，得 $\triangle ADE\sim\triangle ACB$（AA），推出边比 $AD/AC=AE/AB$；交换内项得 $AD/AE=AC/AB$，得 $\triangle ADC\sim\triangle AEB$（SAS），推出角 $\angle ADC=\angle AEB$；取补角得 $\angle ODB=\angle OEC$，加对顶角 $\angle DOB=\angle EOC$，得 $\triangle ODB\sim\triangle OEC$（AA），推出边比 $OD/OE=OB/OC$；交换内项得 $OD/OB=OE/OC$，得 $\triangle ODE\sim\triangle OBC$（SAS），推出角 $\angle ODE=\angle OBC$、$\angle OED=\angle OCB$。

### 2.4 模型标签
- model_id：similarity_reverse_a_four_chain
- model_name：反 A 一图四相似（AA/SAS 交替的结论喂养链）
- configuration：一个三角形中，一条边上的点和另一条边上的点连线满足跨角相等，进而把对角线的两个交点处的对顶角/补角转成四对相似。
- 可迁移方向：换角的位置（改为 $\angle AED=\angle ABC$ 同样可推出四对）；隐去其中一对相似让学生补全；只给部分结论反推入口条件。
- 非同构边界：若题设角不能和公共角组成 AA，或交点 $O$ 不在两条线段内部，则不能机械套用四对相似。

## 二点五、知识点/模型锚点
- 建议讲义标题：反 A 一图四相似：找等角、选判定、写格式
- 知识点/模型名称：相似判定（AA、SAS）与对应关系、结论的传递链。
- 核心公式/定理：
  - AA：两角分别相等 ⇒ 两三角形相似，推出三组对应边成比例。
  - SAS：两边成比例且夹角相等 ⇒ 两三角形相似，推出其余对应角相等。
- 使用条件：写相似时必须先把对应顶点对齐（$\triangle ADE\sim\triangle ACB$ 的对应是 $D\leftrightarrow C$、$E\leftrightarrow B$，交叉对应）。
- 入口信号：图上同时出现公共角（顶点 $A$）和对顶角（交点 $O$），且有一条跨三角形等角把两者串起来。
- 易混边界：反 A 形 $\triangle ADE\sim\triangle ACB$ 的对应是交叉的（$D$ 对 $C$、$E$ 对 $B$），不是顺排（$D$ 对 $B$、$E$ 对 $C$）；$DE$ 不平行于 $BC$。
- 本题如何体现：$\angle ADE=\angle ACB$ 锁定 $D\leftrightarrow C$，公共角 $A$ 锁定 $A\leftrightarrow A$，于是 $E\leftrightarrow B$。
- 可作为例题的结构层级：一图承载四对相似、判定方法 AA/SAS 交替，适合训练"三段式证明书写 + 结论喂养"。

## 三、关键转化
- 最关键的转化：把"上一组相似推出的结论"改写成"下一组相似需要的条件"（边比交换内项、等角取补角）。
- 为什么降低计算量：四对相似全部靠 AA/SAS 判定，不涉及边长数值，只需把结论逐级传递。
- 不转化时的低效路径：每对相似都从头找角，不利用上一对结论，导致重复劳动和对应关系混乱。

## 四、标准路径骨架
1. 先做什么：由 $\angle ADE=\angle ACB$ 和公共角 $A$，用 AA 证 $\triangle ADE\sim\triangle ACB$。
2. 再做什么：写出它推出的边比 $\dfrac{AD}{AC}=\dfrac{AE}{AB}$，交换内项得 $\dfrac{AD}{AE}=\dfrac{AC}{AB}$。
3. 建立什么关系：用 SAS 证 $\triangle ADC\sim\triangle AEB$，写出它推出的角 $\angle ADC=\angle AEB$。
4. 如何求解：取补角得 $\angle ODB=\angle OEC$，加对顶角用 AA 证 $\triangle ODB\sim\triangle OEC$。
5. 需要检查什么：每一步的"推出什么"（角相等还是边成比例）都写清，且下一对正好用上。

## 四点五、标准完整解与验算
- 关键交点/关键量：公共顶点 $A$、对角线交点 $O$。
- 完整求解过程：
  ① $\triangle ADE\sim\triangle ACB$（AA：$\angle DAE=\angle CAB$ 公共角，$\angle ADE=\angle ACB$ 已知）⇒ $\dfrac{AD}{AC}=\dfrac{AE}{AB}$。
  ② 由①得 $\dfrac{AD}{AE}=\dfrac{AC}{AB}$，又 $\angle DAC=\angle EAB$，故 $\triangle ADC\sim\triangle AEB$（SAS）⇒ $\angle ADC=\angle AEB$。
  ③ 由 $O$ 为 $BE$、$CD$ 交点，$\angle DOB=\angle EOC$（对顶角）；又 $\angle ODB=180^\circ-\angle ADC=180^\circ-\angle AEB=\angle OEC$，故 $\triangle ODB\sim\triangle OEC$（AA）⇒ $\dfrac{OD}{OE}=\dfrac{OB}{OC}$。
  ④ 由③得 $\dfrac{OD}{OB}=\dfrac{OE}{OC}$，又 $\angle DOE=\angle BOC$（对顶角），故 $\triangle ODE\sim\triangle OBC$（SAS）⇒ $\angle ODE=\angle OBC$、$\angle OED=\angle OCB$。
- 最终答案：四对相似依次为 $\triangle ADE\sim\triangle ACB$、$\triangle ADC\sim\triangle AEB$、$\triangle ODB\sim\triangle OEC$、$\triangle ODE\sim\triangle OBC$。
- 排除值/退化情形：三角形非退化；$D$、$E$ 不与 $A$、$B$、$C$ 重合；交点 $O$ 在两条线段内部。
- 验算：判定方法交替为 AA、SAS、AA、SAS；"用 AA 证推边比、用 SAS 证推角"的规律一致。

## 五、出题人逻辑
- 诱导学生硬算的位置：四对相似容易让学生分别从头找角，忽视结论之间的传递。
- 真正的捷径：①的边比喂给②的 SAS，②的角喂给③的 AA，③的边比喂给④的 SAS——"上一组推出的，正是下一组要用的"。
- 训练的可迁移能力：找等角 → 选判定 → 写格式的三段式证明书写，以及"证明写完要清点推出了什么"。

## 六、学生卡点预测
- 读题/入手动作卡点：看到 $\angle ADE=\angle ACB$ 没意识到这是在提示"反 A 相似"，找不到公共角 $A$。
- 建模/关系入口卡点：写 $\triangle ADE\sim\triangle ACB$ 时对应顶点排错（写成 $D\leftrightarrow B$），导致对应边全错。
- 求解/检查卡点：③ 的 $\angle ODB=\angle OEC$ 不知从何而来（忘了用②的等角取补角）。

## 七、变式原则
- 核心不变量：公共角 $A$ + 一条跨角相等 + 对角线交点 $O$ 的对顶角，串成四对相似。
- 表层特征：$\angle ADE=\angle ACB$ 的入口位置、四对相似被隐去几对、对应顶点是否给全。
- 深化阶梯：完整四对 → 隐去一对让学生补 → 隐去"推出什么"让学生补 → 交换入口角为 $\angle AED=\angle ABC$ 重推。
- 禁止的变换：把 $DE$ 改成平行于 $BC$（那会退化成 A 字型 + 八字型，不是反 A 四相似）。

## 八、计算复杂度预算
- 原题计算层级：纯证明，无数值计算，只有比例式交换内项。
- 允许小步上升到：加入具体边长，要求由某对相似求出某条边。
- 禁止引入的计算负担：根式、面积比、周长比。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先圈出 $\angle ADE=\angle ACB$，追问"这组等角加上哪个公共角，能先判出第一对相似？"
- 本题讲解目标：形成"找等角 → 选判定 → 写格式"的条件反射，且每证完一对就写清"推出了什么（角相等还是边成比例）"。
- 不要直接讲的抽象话：不要只说"对应边成比例"，必须把每一对相似推出的具体结论写出来。
- 必须先问的问题：$\angle ADE$ 的顶点是 $D$，与它相等的 $\angle ACB$ 的顶点是 $C$——所以 $D$ 对应谁？
- 关键讲解顺序：找公共角 → AA 判第一对 → 写对应边比 → 交换内项 → SAS 判第二对 → 写对应角 → 取补角 → AA 判第三对 → 写边比 → 交换内项 → SAS 判第四对。
- 讲到哪里停下来让学生回答：证完①后停下，让学生写出"①推出了什么"以及②的 SAS 需要哪两条边成比例。

## 十、推荐图形请求包
- 是否需要图：是；反 A 一图四相似的点序、公共角 $A$、对顶角 $O$ 必须可见。
- 图形类型：synthetic_geometry
- 用图意图：student_explanation
- 需要出现的对象：点 $A,B,C,D,E,O$；三角形 $ABC$；线段 $DE$、$BE$、$CD$；角标记 $\angle ADE$ 与 $\angle ACB$。
- 需要突出给学生看的关系：$D$ 在 $AB$ 上、$E$ 在 $AC$ 上；$\angle ADE=\angle ACB$；$BE$ 与 $CD$ 交于 $O$。
- 图中不能暗示的错误性质：不要画成 $DE\parallel BC$（那是 A 字型）；不要画成等腰三角形；不要标出四对相似结论或比例式。
- 图失败时的降级方案：必需图失败则阻断 assignment，不用文字占位替代。

## 十一点、模型规则入库草案（可选）
本结构属于基础欧氏几何相似模型的证明链，可作为 canonical relation 候选：入口条件（公共角 + 跨角相等）→ 四对相似（AA/SAS 交替）→ 结论喂养链。

工作流：math-structure-analysis → math-student-explanation-latex-data（含 diagram_slot）→ math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
