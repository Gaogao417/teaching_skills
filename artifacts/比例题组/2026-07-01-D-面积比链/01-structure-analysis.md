# 结构分析：同底同高与面积比链

## 原题
围绕“面积目标 -> 同底/同高 -> 线段比/份数 -> 串联比例”设计面积比链训练。最终综合题必须修正为四边形面积：

在 $\triangle ABC$ 中，点 $D$ 在 $BC$ 上，点 $E$ 在 $AC$ 上，$AD$ 与 $BE$ 交于点 $O$。若 $AO:OD=1:1$，$BO:OE=3:1$，$AE:EC=1:2$，求 $S_{OECD}:S_{\triangle OAB}$。

注意：目标是 $S_{OECD}:S_{\triangle OAB}$，不是 $S_{\triangle OEC}:S_{\triangle OAB}$。

## 一、题目场景
- 数学对象：三角形、边上分点、交点、三角形面积、四边形面积。
- 变量/参数：线段分点比、面积份数。
- 函数/图形：无函数；三角形内部交线构型。
- 已知条件：$AO:OD$、$BO:OE$、$AE:EC$ 等同一直线分点比。
- 要求目标：求 $S_{OECD}:S_{\triangle OAB}$。

## 二、核心结构
### 2.1 表层信息
- 表面考点：三角形面积比。
- 题型功能：`application_modeling`。
- 是否值得完整 structural analysis：是；目标面积是四边形，需要先拆分再串联。
- 一句话问题模式：把四边形面积拆成三角形面积，再用同底/同高把每个面积转成线段比分数。

### 2.2 结构表达
#### 判别条件表（概念辨析题用；不适用则写“无”）
- 必要条件：已知比例必须是同一直线上的分点比，或能控制同底三角形的高比。
- 充分条件：目标四边形可拆成若干三角形，且每个三角形面积能由已知比例串联到同一中间面积。
- 常见干扰项：把 $OECD$ 看成 $\triangle OEC$；把 $AD:BE$ 这种不同方向整段比当作面积比依据。
- 最短检查动作：先写 $S_{OECD}=S_{\triangle OEC}+S_{\triangle OCD}$。

#### 情景量表（应用题用；不适用则写“无”）
| 量 | 类型/单位 | 题设关系 | 未知/已知 |
|---|---|---|---|
| $S_{\triangle OAB}$ | 面积 | 与 $S_{\triangle OAE}$ 共底 $AO$ | 目标参照量 |
| $S_{\triangle OAE}$ | 面积 | 中间面积 | 未知份数 |
| $S_{\triangle OEC}$ | 面积 | 与 $S_{\triangle OAE}$ 同高 | 未知份数 |
| $S_{\triangle OCD}$ | 面积 | 与 $S_{\triangle OAC}$ 共底 $OC$ | 未知份数 |
| $S_{OECD}$ | 面积 | $S_{\triangle OEC}+S_{\triangle OCD}$ | 目标量 |

#### 命题网络（所有题型都写；简单题写简版）
- P1（题设）：$BO:OE=3:1$。
- P2（定理）：$\triangle OAB$ 与 $\triangle OAE$ 共底 $AO$，面积比等于到 $AO$ 的高比。
- P3（可推）：$S_{\triangle OAB}:S_{\triangle OAE}=3:1$。
- R1：P1 + P2 -> P3，方法：共底三角形高比等于同线分点比。
- P4（题设）：$AE:EC=1:2$。
- P5（定理）：$\triangle OAE$ 与 $\triangle OEC$ 同高。
- P6（可推）：$S_{\triangle OAE}:S_{\triangle OEC}=1:2$。
- R2：P4 + P5 -> P6，方法：同高面积比等于底边比。
- P7（题设）：$AO:OD=1:1$。
- P8（定理）：$\triangle OAC$ 与 $\triangle OCD$ 共底 $OC$。
- P9（可推）：$S_{\triangle OAC}:S_{\triangle OCD}=1:1$。
- R3：P7 + P8 -> P9，方法：共底面积比等于高比。
- P10（构造）：$S_{\triangle OAC}=S_{\triangle OAE}+S_{\triangle OEC}$。
- P11（构造）：$S_{OECD}=S_{\triangle OEC}+S_{\triangle OCD}$。
- R4：P3 + P6 + P9 + P10 + P11 -> 目标比，方法：以 $S_{\triangle OAE}$ 为中间面积统一份数。
- 目标：$S_{OECD}:S_{\triangle OAB}=5:3$。

### 2.3 解题主链
```text
确认目标是 OECD -> 拆四边形 -> 选中间面积 OAE -> 串 BO:OE 和 AE:EC -> 求 OAC -> 用 AO:OD 求 OCD -> 合成 OECD
```

### 2.4 模型标签
- model_id：area_ratio_chain_quadrilateral_split
- model_name：四边形面积拆分与面积比链
- configuration：已知三条分点比，求四边形面积与三角形面积之比。
- 可迁移方向：同底同高面积比、面积链、反求分点比。
- 非同构边界：只给 $AD:BE$ 一般不能确定该面积比。

## 二点五、知识点/模型锚点
- 建议讲义标题：面积比链：先拆四边形，再串中间面积
- 知识点/模型名称：同底同高面积比、分点比、四边形面积拆分。
- 核心公式/定理：
  - 同高三角形面积比等于底边比。
  - 同底三角形面积比等于高的比。
  - $S_{OECD}=S_{\triangle OEC}+S_{\triangle OCD}$。
- 使用条件：比较的高必须来自同一直线分点比；各点不重合。
- 入口信号：求面积比，且题面给出 $AO:OD$、$BO:OE$、$AE:EC$ 这类同线比例。
- 易混边界：$OECD$ 是四边形；不能用 $AD:BE$ 直接代替面积链。
- 本题如何体现：目标面积要拆分，两条面积链共享中间面积。
- 可作为例题的结构层级：综合应用型。

## 三、关键转化
- 最关键的转化：$S_{OECD}=S_{\triangle OEC}+S_{\triangle OCD}$。
- 为什么降低计算量：每一块三角形面积都能回到同一个份数系统。
- 不转化时的低效路径：直接盯着四边形，找不到可用的底高关系。

## 四、标准路径骨架
1. 先做什么：确认目标是四边形 $OECD$。
2. 再做什么：把四边形拆成 $\triangle OEC$ 与 $\triangle OCD$。
3. 建立什么关系：用 $S_{\triangle OAE}$ 作为中间面积。
4. 如何求解：依次求 $S_{\triangle OAB}$、$S_{\triangle OEC}$、$S_{\triangle OCD}$ 的份数。
5. 需要检查什么：每一步面积比是否有同底或同高依据。

## 四点五、标准完整解与验算
- 关键交点/关键量：$S_{\triangle OAE}$。
- 面积/方程/关系式：
  \[
  S_{\triangle OAB}:S_{\triangle OAE}=BO:OE=3:1.
  \]
  \[
  S_{\triangle OAE}:S_{\triangle OEC}=AE:EC=1:2.
  \]
  \[
  S_{\triangle OAC}:S_{\triangle OCD}=AO:OD=1:1.
  \]
- 完整求解过程：
  设 $S_{\triangle OAE}=1$ 份，则 $S_{\triangle OAB}=3$ 份，$S_{\triangle OEC}=2$ 份。于是 $S_{\triangle OAC}=1+2=3$ 份。由 $AO:OD=1:1$ 得 $S_{\triangle OCD}=3$ 份。因此
  \[
  S_{OECD}=S_{\triangle OEC}+S_{\triangle OCD}=2+3=5\text{份},
  \]
  所以
  \[
  S_{OECD}:S_{\triangle OAB}=5:3.
  \]
- 最终答案：$5:3$。
- 排除值：线段比为正，各点不重合。
- 退化情形：$O$ 与端点重合时面积链失效。
- 验算：取坐标 $A(0,0)$，$B(0,1)$，$C(1,0)$，$E(\frac13,0)$，$O(\frac14,\frac14)$，可得到 $D(\frac12,\frac12)$，比例相容且目标比为 $5:3$。
- 本题最短可靠路径：以 $S_{\triangle OAE}$ 为中间面积统一份数。

## 五、出题人逻辑
- 诱导学生硬算的位置：把四边形当成不可拆对象，或误算成 $\triangle OEC$。
- 真正的捷径：先拆 $OECD$，再找中间面积。
- 训练的可迁移能力：面积目标反推底高关系。

## 六、学生卡点预测
- 读题/入手动作卡点：把 $OECD$ 看漏一个点。
- 建模/关系入口卡点：不会把 $S_{\triangle OAC}$ 写成 $S_{\triangle OAE}+S_{\triangle OEC}$。
- 求解/检查卡点：多个比例串联时份数基准不统一。

## 七、变式原则
- 核心不变量：四边形拆分后，每块面积都能用同底/同高关系回到同一份数系统。
- 表层特征：点名、分点比、目标面积对象。
- 可变维度：数字、目标从三角形改为四边形、反求某个分点比。
- 深化阶梯：同高面积比 -> 共底面积比 -> 两比例串联 -> 四边形拆分。
- 允许的变换：小整数分点比，保证构型相容。
- 禁止的变换：只给 $AD:BE$ 求目标面积比。
- 表征切换：文字条件、面积符号、份数表。
- 包装方式：把中间面积藏在四边形目标里。
- 近迁移例子：$BD:DC$ 求 $S_{\triangle ABD}:S_{\triangle ACD}$。
- 远迁移例子：给目标面积比，补一个分点比。
- 反例/伪变式：$AD:BE=2:3$，求 $S_{OECD}:S_{\triangle OAB}$，一般不充分。

## 八、计算复杂度预算
- 原题计算层级：三条小整数比例，一次面积加法。
- 允许小步上升到：简单分数比例。
- 禁止引入的计算负担：坐标大计算、相似证明、三角函数。
- 必须保留的可见支架：四边形拆分式和中间面积。

## 九、推荐讲题任务包
- 建议的本轮教学入口：先纠正目标对象是 $OECD$。
- 本题讲解目标：会拆四边形并串联面积比。
- 不要直接讲的抽象话：不要只说“用面积法”。
- 必须先问的问题：$OECD$ 可以拆成哪两个三角形？
- 关键讲解顺序：拆四边形 -> 找 $OAE$ -> 求 $OEC$ 和 $OAB$ -> 求 $OCD$ -> 合并。
- 最适合的具体数值例子：$AO:OD=1:1$，$BO:OE=3:1$，$AE:EC=1:2$。
- 讲到哪里停下来让学生回答：设 $S_{\triangle OAE}=1$ 后，让学生补出其他面积份数。

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：直接同高面积比。
- 若卡在建模或关系入口，出什么题：共底三角形用同线分点比求面积比。
- 若卡在求解和检查，出什么题：两比例共享中间面积。
- 若原题已稳，如何小步迁移：四边形面积拆分。
- 若结构识别已稳，如何深化/抽象/包装：反求某个分点比。
- 禁止出的跑偏变式：只给不同方向整段比。

## 十点五、推荐图形请求包（可选）
- 是否需要图：是。
- 图形类型：`synthetic_geometry`
- 用图意图：学生讲解与练习题题面均配图，帮助学生看清 $D,E,O$ 的位置与 $OECD$ 四边形。
- 需要出现的对象：$\triangle ABC$，$D$ 在 $BC$，$E$ 在 $AC$，$AD$ 与 $BE$ 交于 $O$。
- 需要突出给学生看的关系：$OECD$ 拆成 $\triangle OEC$ 和 $\triangle OCD$。
- 图中不能暗示的错误性质：不要画成特殊等腰或直角。
- 图失败时的降级方案：不得直接编译无图版本，应回到 diagram workflow 修复图位。

## 十一点、模型规则入库草案（可选）
暂不入库。原因：几何面积比链不属于当前 v0 模型规则库范围。

下一步建议：先使用 math-model-rule-ingestion 将本结构分析中的模型规则规范化为 canonical relations；随后 math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 可并行消费结构分析和模型库关系。工作流：math-structure-analysis → math-model-rule-ingestion →（math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 并行）→ math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
