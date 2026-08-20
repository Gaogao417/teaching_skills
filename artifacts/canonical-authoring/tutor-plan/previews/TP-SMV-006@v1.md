# TutorPlan 预览：TP-SMV-006@v1

- 题目：QT-SMV-006@v2
- Build：deterministic-rules / plan-build-rules/v1（tutor-plan-build/v1，registry action-runtime-registry/v5@32f7ae75600a）
- 风险标注：答案值出现于 5 个讲解/修复资源（教师判断是否过早泄题）；hint/probe 由发布门禁 fail-closed 拦截
- 最高提示档位：L2；skill annotation：5 个，未锚定节点：5 个
- 待几何绑定的 Action 能力（Phase 5 presenter/内容工序接入）：select-option、mark-segment-values、select-option、enter-equation
- 泄漏自查降级的资源：CP1 voice_seed、CP4 voice_seed、CP7 voice_seed

## Part 1（approach TA-SMV-019@v1）
- 路线 R1（primary）：CP1 → CP2 → CP3；完成：作 $CG\perp AB$ 把两个角各自数值化（正切都为 2/3），证 $\angle BAC=\angle PCF$。
- 路线 R2（alternate）：CP2 → CP3；进入条件：学生已能学生见到 sinB=4/5 能想到作高构造直角三角形。，可直接跳过开场确认；完成：作 $CG\perp AB$ 把两个角各自数值化（正切都为 2/3），证 $\angle BAC=\angle PCF$。

### CP1（可跳过）
- 预期推理：学生能由三角函数值还原直角边并算出 AG。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：过点 $C$ 作 $CG\perp AB$，垂足为 $G$；由 $BC=5$、$\sin B=\frac{4}{5}$ 得 $BG=3$、$CG=4$；又 $AB=9$，得 $AG=6$。
- 提示 L1：先别急着算——这一步的关键是「作高数值化 BC 侧」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「作高数值化 BC 侧」。
- 确认探针：快速确认：作高数值化 BC 侧——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-001：该 checkpoint 对应教学步骤「作高数值化 BC 侧」，预期学生能学生能由三角函数值还原直角边并算出 AG。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-019@v1#S1）

### CP2
- 预期推理：学生能在两个不同三角形里分别表达正切。
- 讲解（explanation）：$\tan\angle BAC=\frac{CG}{AG}=\frac{2}{3}$；$\angle CPF=90^\circ$、$\frac{FP}{PC}=\frac{2}{3}$，故 $\tan\angle PCF=\frac{2}{3}$。
- 提示 L1：先别急着算——这一步的关键是「两侧各算正切」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「两侧各算正切」。
- 确认探针：快速确认：两侧各算正切——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-003：该 checkpoint 对应教学步骤「两侧各算正切」，预期学生能学生能在两个不同三角形里分别表达正切。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-019@v1#S2）
- Skill 标注 SKILL-SMV-007：该 checkpoint 对应教学步骤「两侧各算正切」，预期学生能学生能在两个不同三角形里分别表达正切。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-019@v1#S2）

### CP3
- 预期推理：学生能说明「锐角 + 三角函数值相等 → 角相等」的依据。
- 讲解（explanation）：$\angle BAC$ 与 $\angle PCF$ 均为锐角且正切相等，故 $\angle BAC=\angle PCF$。
- 提示 L1：先别急着算——这一步的关键是「锐角同一收尾」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「锐角同一收尾」。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-009 未在此节点锚定（已在他处使用或粗粒度语境不足）

## Part 2（approach TA-SMV-020@v1）
- 路线 R3（primary）：CP4 → CP5 → CP6；完成：由平行与第(1)问等角把角平移到 $\triangle BPC$ 与 $\triangle PFC$，用余切列比例解出 $BP=\frac{17}{3}$。
- 路线 R4（alternate）：CP5 → CP6；进入条件：学生已能学生能把「已证等角」当作第二问的现成工具。，可直接跳过开场确认；完成：由平行与第(1)问等角把角平移到 $\triangle BPC$ 与 $\triangle PFC$，用余切列比例解出 $BP=\frac{17}{3}$。

### CP4（可跳过）
- 预期推理：学生能写出「平行内错角 + 已证等角 → 差角相等」的链条。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：$AB\parallel CD$ 得 $\angle BAC=\angle ACD$；结合第(1)问 $\angle PCF=\angle BAC$ 得 $\angle PCF=\angle ACD$，同减 $\angle ACP$ 得 $\angle PCA=\angle FCD$。
- 提示 L1：先别急着算——这一步的关键是「平行 + 等角平移」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「平行 + 等角平移」。
- 确认探针：快速确认：平行 + 等角平移——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-005：该 checkpoint 对应教学步骤「平行 + 等角平移」，预期学生能学生能写出「平行内错角 + 已证等角 → 差角相等」的链条。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-020@v1#S1）

### CP5
- 预期推理：学生能核对待定相似的对应顶点后再用条件。
- 讲解（explanation）：$\triangle APC\sim\triangle EFC$ 且 $\angle PEC=\angle APE<90^\circ$，故 $\angle APC=\angle EFC$；同加直角得 $\angle BPC=\angle PFC$。
- 提示 L1：先别急着算——这一步的关键是「相似条件对齐」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「相似条件对齐」。
- 确认探针：快速确认：相似条件对齐——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-002：该 checkpoint 对应教学步骤「相似条件对齐」，预期学生能学生能核对待定相似的对应顶点后再用条件。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-020@v1#S2）

### CP6
- 预期推理：学生能用余切（而非正切）使所求边落在分子，解出 $BP=\frac{17}{3}$。
- 常见偏差：用正切导致求出倒数
- 讲解（explanation）：$\cot\angle BPC=\cot\angle PFC$ 得 $\frac{PG}{CG}=\frac{2}{3}$，$CG=4$，故 $PG=\frac{8}{3}$，$BP=BG+PG=3+\frac{8}{3}=\frac{17}{3}$。
- 提示 L1：先别急着算——这一步的关键是「余切列式解 BP」。说说你打算怎么找？
- 提示 L2：常见卡点是「用正切导致求出倒数」。回到「余切列式解 BP」，检查还有哪个已知条件没有用上。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-007 未在此节点锚定（已在他处使用或粗粒度语境不足）

## Part 3（approach TA-SMV-021@v1）
- 路线 R5（primary）：CP7 → CP8 → CP9；完成：把 $\frac{S_{\triangle HFC}}{S_{\triangle PHC}}=\frac{1}{3}$ 转成 $\frac{FH}{PH}=\frac{1}{3}$，按 F 在 $PH$ 延长线/线段上两分类，解得 $\frac{AH}{AC}=rac{2}{7}$ 或 $\frac{1}{5}$。
- 路线 R6（alternate）：CP8 → CP9；进入条件：学生已能学生能把面积比转成同高线段比。，可直接跳过开场确认；完成：把 $\frac{S_{\triangle HFC}}{S_{\triangle PHC}}=\frac{1}{3}$ 转成 $\frac{FH}{PH}=\frac{1}{3}$，按 F 在 $PH$ 延长线/线段上两分类，解得 $\frac{AH}{AC}=rac{2}{7}$ 或 $\frac{1}{5}$。

### CP7（可跳过）
- 预期推理：学生能识别共顶点、底共线的等高结构并把面积比化成线段比。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：$\triangle HFC$ 与 $\triangle PHC$ 共顶点 $C$，底 $FH$、$PH$ 同在直线 $PE$ 上（等高），故 $\frac{S_{\triangle HFC}}{S_{\triangle PHC}}=\frac{1}{3}$ 即 $\frac{FH}{PH}=\frac{1}{3}$。
- 提示 L1：先别急着算——这一步的关键是「面积比转线段比」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「面积比转线段比」。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-003/SKILL-SMV-005 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP8
- 预期推理：学生能用相似把 MH/GP 建立倍数关系并列一元方程。
- 讲解（explanation）：过 $H$ 作 $HM\perp AB$；$\angle MPH=\angle PCG$ 且 $\angle HMP=\angle CGP=90^\circ$，$\triangle MPH\sim\triangle GCP$。此时 $\frac{PH}{PC}=\frac{1}{2}$，设 $MH=a$ 得 $GP=2a$、$MP=2$、$AM=\frac{3}{2}a$，由 $2a+\frac{3}{2}a+2+3=9$ 得 $a=\frac{8}{7}$，故 $\frac{AH}{AC}=\frac{MH}{CG}=\frac{2}{7}$。
- 提示 L1：先别急着算——这一步的关键是「类一：F 在 PH 延长线上」。说说你打算怎么找？
- 提示 L2：提示：先写出这一步要用到的已知条件，再看它们如何组合出「类一：F 在 PH 延长线上」。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-002/SKILL-SMV-007 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP9
- 预期推理：学生能完整分两类并把两解分别代回检验。
- 常见偏差：漏掉 F 在延长线上的情形
- 讲解（explanation）：此时 $PH=PC$，设 $MH=b$ 得 $GP=b$、$MP=4$、$AM=\frac{3}{2}b$，由 $b+\frac{3}{2}b+4+3=9$ 得 $b=\frac{4}{5}$，故 $\frac{AH}{AC}=\frac{1}{5}$。综上 $\frac{AH}{AC}=\frac{2}{7}$ 或 $\frac{1}{5}$。
- 提示 L1：先别急着算——这一步的关键是「类二：F 在 PH 上与总结」。说说你打算怎么找？
- 提示 L2：常见卡点是「漏掉 F 在延长线上的情形」。回到「类二：F 在 PH 上与总结」，检查还有哪个已知条件没有用上。
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-009 未在此节点锚定（已在他处使用或粗粒度语境不足）
