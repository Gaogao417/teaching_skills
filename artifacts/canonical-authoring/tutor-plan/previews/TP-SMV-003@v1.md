# TutorPlan 预览：TP-SMV-003@v1

- 题目：QT-SMV-003@v2
- Build：deterministic-rules / plan-build-rules/v1（tutor-plan-build/v1，registry action-runtime-registry/v5@32f7ae75600a）
- 风险标注：答案值出现于 6 个讲解/修复资源（教师判断是否过早泄题）；hint/probe 由发布门禁 fail-closed 拦截
- 最高提示档位：L2；skill annotation：6 个，未锚定节点：4 个
- 待几何绑定的 Action 能力（Phase 5 presenter/内容工序接入）：select-option、convert-collinear、enter-equation、select-option
- 泄漏自查降级的资源：CP1 voice_seed、CP4 voice_seed、CP7 voice_seed

## Part 1（approach TA-SMV-012@v1）
- 路线 R1（primary）：CP1 → CP2 → CP3；完成：用「重心 → 中线 → 等腰直角斜边中线垂直」与外角和分解，证 $\angle DAB = \angle DCF$。
- 路线 R2（alternate）：CP2 → CP3；进入条件：学生已能学生看到重心条件能联想到三线合一与中线性质。，可直接跳过开场确认；完成：用「重心 → 中线 → 等腰直角斜边中线垂直」与外角和分解，证 $\angle DAB = \angle DCF$。

### CP1（可跳过）
- 预期推理：学生能把「重心」翻译成「中线」，再由等腰直角得到垂直。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：点 $G$ 是 Rt$\triangle ABC$ 的重心，$CG$ 是中线，交 $AB$ 于 $F$；由 $AC=BC$、$\angle ACB=90^\circ$ 知 $CF$ 既是中线也是高，$\angle AFC=90^\circ$。
- 提示 L1：先别急着算——这一步的关键是「重心翻译成中线」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「重心翻译成中线」。
- 确认探针：快速确认：重心翻译成中线——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-001：该 checkpoint 对应教学步骤「重心翻译成中线」，预期学生能学生能把「重心」翻译成「中线」，再由等腰直角得到垂直。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-012@v1#S1）

### CP2
- 预期推理：学生能对同一个角写两条分解式并相减。
- 讲解（explanation）：$\angle DEF=\angle ADE+\angle DAE$（外角），$\angle DEF=\angle EFC+\angle ECF$；其中 $\angle ADE=\angle EFC=90^\circ$，两式相减得 $\angle DAE=\angle ECF$。
- 提示 L1：先别急着算——这一步的关键是「外角和分解对齐」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「外角和分解对齐」。
- 确认探针：快速确认：外角和分解对齐——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-005：该 checkpoint 对应教学步骤「外角和分解对齐」，预期学生能学生能对同一个角写两条分解式并相减。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-012@v1#S2）

### CP3
- 预期推理：学生能核对角的记号转换（DAE→DAB、ECF→DCF）后落笔。
- 讲解（explanation）：$\angle DAE$ 即 $\angle DAB$、$\angle ECF$ 即 $\angle DCF$，故 $\angle DAB = \angle DCF$ 得证。
- 提示 L1：先别急着算——这一步的关键是「收尾书写」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「收尾书写」。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-009 未在此节点锚定（已在他处使用或粗粒度语境不足）

## Part 2（approach TA-SMV-013@v1）
- 路线 R3（primary）：CP4 → CP5 → CP6；完成：作 $BH \perp CD$ 构造全等转移线段，由 $AD \parallel BH$ 导比例，解出 $y = \frac{x^{2} + 4}{x + 2}$（$0 < x \leq 2$）。
- 路线 R4（alternate）：CP5 → CP6；进入条件：学生已能学生知道函数关系式要「设元 → 找等量 → 消元」。，可直接跳过开场确认；完成：作 $BH \perp CD$ 构造全等转移线段，由 $AD \parallel BH$ 导比例，解出 $y = \frac{x^{2} + 4}{x + 2}$（$0 < x \leq 2$）。

### CP4（可跳过）
- 预期推理：学生能想到作高构造全等，把 BC 侧的量转到 CD 轴上。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：过点 $B$ 作 $BH \perp CD$ 于点 $H$，可证 $\triangle CAD \cong \triangle BCH$，得 $BH=CD=2$、$CH=AD=x$、$DH=2-x$。
- 提示 L1：先别急着算——这一步的关键是「构造高线全等转移」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「构造高线全等转移」。
- 确认探针：快速确认：构造高线全等转移——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-008：select 类证据在 recognize/plan 间共享（capability-skill-map gap note）；以本 checkpoint 语境（构造高线全等转移）作为该 skill 的低置信线索。（证据 TA-SMV-013@v1#S1）

### CP5
- 预期推理：学生能用合比性质把 DE/EH 转成 DH/EH。
- 讲解（explanation）：$AD \parallel BH$ 得 $\frac{AD}{BH}=\frac{DE}{EH}$，即 $\frac{x}{2}=\frac{DE}{EH}$；合比得 $\frac{DH}{EH}=\frac{x+2}{2}$，解出 $EH=\frac{4-2x}{x+2}$。
- 提示 L1：先别急着算——这一步的关键是「平行导比例」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「平行导比例」。
- 确认探针：快速确认：平行导比例——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-003：该 checkpoint 对应教学步骤「平行导比例」，预期学生能学生能用合比性质把 DE/EH 转成 DH/EH。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-013@v1#S2）
- Skill 标注 SKILL-SMV-007：该 checkpoint 对应教学步骤「平行导比例」，预期学生能学生能用合比性质把 DE/EH 转成 DH/EH。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-013@v1#S2）

### CP6
- 预期推理：学生能合并分式并说明范围来自 E 的位置约束。
- 常见偏差：范围写成 0<x<2（漏端点）
- 讲解（explanation）：$y=CE=CH+HE=x+\frac{4-2x}{x+2}$，整理得 $y = \frac{x^{2} + 4}{x + 2}$；由点 $E$ 在边 $CD$ 上得自变量范围 $0 < x \leq 2$。
- 提示 L1：先别急着算——这一步的关键是「合并成函数并定范围」。说说你打算怎么找？
- 提示 L2：常见卡点是「范围写成 0<x<2（漏端点）」。回到「合并成函数并定范围」，检查还有哪个已知条件没有用上。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-007 未在此节点锚定（已在他处使用或粗粒度语境不足）

## Part 3（approach TA-SMV-014@v1）
- 路线 R5（primary）：CP7 → CP8 → CP9；完成：按 $GC=GD$、$CG=CD$ 两类画图列式，结合函数关系式求解并按范围取舍，得 $AD = 1$ 或 $\sqrt{14}$。
- 路线 R6（alternate）：CP8 → CP9；进入条件：学生已能学生能对「以 CG 为腰」枚举两种等腰可能并分别画图。，可直接跳过开场确认；完成：按 $GC=GD$、$CG=CD$ 两类画图列式，结合函数关系式求解并按范围取舍，得 $AD = 1$ 或 $\sqrt{14}$。

### CP7（可跳过）
- 预期推理：学生能不重不漏列出两类并说明分类依据（腰的两个端点）。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：$\triangle CDG$ 以 $CG$ 为腰 → 两类：$GC=GD$ 与 $CG=CD$；先明确 $CD=2$ 恒定，分类只改变 G 的位置。
- 提示 L1：先别急着算——这一步的关键是「分类起点与图形」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「分类起点与图形」。
- 确认探针：快速确认：分类起点与图形——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-009：select 类证据在 recognize/plan 间共享（capability-skill-map gap note）；以本 checkpoint 语境（分类起点与图形）作为该 skill 的低置信线索。（证据 TA-SMV-014@v1#S1）

### CP8
- 预期推理：学生能用「到两端等距 → 垂直」识别中垂线结构。
- 讲解（explanation）：取 $AC$ 的中点 $M$，联结 $MD$，则 $MD=MC$；联结 $MG$ 则 $MG \perp CD$ 且直线 $MG$ 经过点 $B$，$BH$ 与 $MG$ 共线；又 $CH=AD$，得 $AD=CH=1$。
- 提示 L1：先别急着算——这一步的关键是「类一 GC=GD」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「类一 GC=GD」。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-005/SKILL-SMV-001 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP9
- 预期推理：学生能代回函数范围检验两解均合法。
- 常见偏差：漏一类，或解后不代回范围
- 讲解（explanation）：$CG=CD=2$；G 为重心，$CF=\frac{3}{2}CG=3$，等腰直角得 $AC=\frac{\sqrt{2}}{2}AB=3\sqrt{2}$，$AD=\sqrt{AC^{2}-CD^{2}}=\sqrt{14}$。综上 $AD = 1$ 或 $\sqrt{14}$，均满足 $0 < x \leq 2$。
- 提示 L1：先别急着算——这一步的关键是「类二 CG=CD 与总结」。说说你打算怎么找？
- 提示 L2：常见卡点是「漏一类，或解后不代回范围」。回到「类二 CG=CD 与总结」，检查还有哪个已知条件没有用上。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-007 未在此节点锚定（已在他处使用或粗粒度语境不足）
