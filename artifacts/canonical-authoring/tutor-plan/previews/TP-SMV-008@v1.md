# TutorPlan 预览：TP-SMV-008@v1

- 题目：QT-SMV-048@v2
- Build：deterministic-rules / plan-build-rules/v1（tutor-plan-build/v1，registry action-runtime-registry/v5@32f7ae75600a）
- 风险标注：答案值出现于 3 个讲解/修复资源（教师判断是否过早泄题）；hint/probe 由发布门禁 fail-closed 拦截
- 最高提示档位：L2；skill annotation：4 个，未锚定节点：2 个
- 待几何绑定的 Action 能力（Phase 5 presenter/内容工序接入）：select-option、enter-equation
- 泄漏自查降级的资源：CP4 voice_seed

## Part 1（approach TA-SMV-022@v1）
- 路线 R1（primary）：CP1 → CP2 → CP3；完成：由 $AD\parallel BC$ 的 8 字型相似定出对角线分比，再分步代入化为 $\vec{a}$、$\vec{b}$ 的线性组合。
- 路线 R2（alternate）：CP2 → CP3；进入条件：学生已能学生能在梯形里看出对角线交点分出的两组比。，可直接跳过开场确认；完成：由 $AD\parallel BC$ 的 8 字型相似定出对角线分比，再分步代入化为 $\vec{a}$、$\vec{b}$ 的线性组合。

### CP1（可跳过）
- 预期推理：学生能直接读出对角线被交点 E 分成的两组比。
- 开场（voice_seed）：我们先看第1问：由 $AD\parallel BC$ 的 8 字型相似定出对角线分比，再分步代入化为 $\vec{a}$、$\vec{b}$ 的线性组合。（设 $\overrightarrow{BC}=\vec{a}$，$\overrightarrow{BD}=\vec{b}$，试用 $\vec{a}$、$\vec{b}$ 的线性组合表示向量 $\overrightarrow{AE}$；）
- 讲解（explanation）：由 $AD\parallel BC$ 得 $\triangle AED \sim \triangle CEB$（8 字型），故 $AE:EC=AD:CB=4:5$、$BE:ED=BC:AD=5:4$。
- 提示 L1：平行出 8 字相似
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：平行出 8 字相似——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-008：select 类证据在 recognize/plan 间共享（capability-skill-map gap note）；以本 checkpoint 语境（平行出 8 字相似）作为该 skill 的低置信线索。（证据 TA-SMV-022@v1#S1）

### CP2
- 预期推理：学生能先写「向量和」中间式，不直接跳到最终组合。
- 讲解（explanation）：$\overrightarrow{AE}=\overrightarrow{AB}+\overrightarrow{BE}$，其中 $\overrightarrow{AB}=\overrightarrow{DB}-\overrightarrow{DA}$ 分步用 $\vec{a}$、$\vec{b}$ 与定比表达。
- 提示 L1：写向量中间式
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：写向量中间式——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-002：该 checkpoint 对应教学步骤「写向量中间式」，预期学生能学生能先写「向量和」中间式，不直接跳到最终组合。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-022@v1#S2）

### CP3
- 预期推理：学生能核对系数来源（4/5 来自 AE:EC，4/9 来自 BE:ED）。
- 常见偏差：两个系数的比分母用反
- 讲解（explanation）：由定比分解逐步代入，得 $\overrightarrow{AE}=\frac{4}{5}\vec{a}-\frac{4}{9}\vec{b}$。
- 提示 L1：代入定比收尾
- 提示 L2：常见卡点：两个系数的比分母用反
- 确认探针：快速确认：代入定比收尾——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-007：该 checkpoint 对应教学步骤「代入定比收尾」，预期学生能学生能核对系数来源（4/5 来自 AE:EC，4/9 来自 BE:ED）。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-022@v1#S3）

## Part 2（approach TA-SMV-023@v1）
- 路线 R3（primary）：CP4 → CP5 → CP6；完成：过 $A$ 作 $AF\perp BC$ 构造矩形 $ADCF$，把 $\angle ABC$ 放进 Rt$\triangle ABF$ 中求 $\sin\angle ABC=\frac{2\sqrt{5}}{5}$。
- 路线 R4（alternate）：CP5 → CP6；进入条件：学生已能学生能由 $AD\perp CD$、$AD\parallel BC$ 想到补出矩形。，可直接跳过开场确认；完成：过 $A$ 作 $AF\perp BC$ 构造矩形 $ADCF$，把 $\angle ABC$ 放进 Rt$\triangle ABF$ 中求 $\sin\angle ABC=\frac{2\sqrt{5}}{5}$。

### CP4（可跳过）
- 预期推理：学生能由正切与已知直角边解出另一直角边。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：在 Rt$\triangle ADC$ 中 $AD=4$、$\tan\angle DAC=\frac{1}{2}$，得 $CD=2$。
- 提示 L1：数据准备
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：数据准备——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-001：该 checkpoint 对应教学步骤「数据准备」，预期学生能学生能由正切与已知直角边解出另一直角边。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-023@v1#S1）

### CP5
- 预期推理：学生能说明矩形从哪两个垂直条件来，并解出 AB。
- 讲解（explanation）：过点 $A$ 作 $AF\perp BC$；$\angle FAD=90^\circ$ 且 $AD\perp CD$，四边形 $ADCF$ 是矩形，故 $AF=CD=2$、$FC=AD=4$；$BC=5$ 得 $BF=1$，$AB=\sqrt{AF^{2}+BF^{2}}=\sqrt{5}$。
- 提示 L1：构矩形转移
- 提示 L2：检查还有哪个已知条件没有用上
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-008/SKILL-SMV-002 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP6
- 预期推理：学生能选对对边/斜边并完成分母有理化。
- 讲解（explanation）：在 Rt$\triangle ABF$ 中，对边 $AF=2$、斜边 $AB=\sqrt{5}$，由 $\frac{2}{\sqrt{5}}$ 分母有理化，得 $\sin\angle ABC=\frac{2\sqrt{5}}{5}$。
- 提示 L1：直角三角形求正弦
- 提示 L2：检查还有哪个已知条件没有用上
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-007 未在此节点锚定（已在他处使用或粗粒度语境不足）
