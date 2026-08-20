# TutorPlan 预览：TP-SMV-002@v2

- 题目：QT-SMV-002@v2
- Build：deterministic-rules / plan-build-rules/v1（tutor-plan-build/v1，registry action-runtime-registry/v5@32f7ae75600a）
- 风险标注：答案值出现于 5 个讲解/修复资源（教师判断是否过早泄题）；hint/probe 由发布门禁 fail-closed 拦截
- 最高提示档位：L2；skill annotation：3 个，未锚定节点：3 个
- 待几何绑定的 Action 能力（Phase 5 presenter/内容工序接入）：select-option、select-option、convert-collinear、enter-equation
- 泄漏自查降级的资源：CP1 voice_seed、CP4 voice_seed

## Part 1（approach TA-SMV-010@v1）
- 路线 R1（primary）：CP1 → CP2 → CP3；完成：掌握「等积式 → 比例式 → 配 SAS 相似 → 导角」路线，证得 $CE \perp AB$。
- 路线 R2（alternate）：CP2 → CP3；进入条件：学生已能学生能把 $AD \cdot OC = AB \cdot OD$ 主动改写成比例式。，可直接跳过开场确认；完成：掌握「等积式 → 比例式 → 配 SAS 相似 → 导角」路线，证得 $CE \perp AB$。

### CP1（可跳过）
- 预期推理：学生能先改比例再找三角形，而不是盯着等积式发呆。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：把 $AD \cdot OC = AB \cdot OD$ 交叉改写为 $\frac{AD}{OD}=\frac{AB}{OC}$，目标是配出两个直角三角形的公共顶点比例。
- 提示 L1：等积式改比例
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：等积式改比例——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-003：该 checkpoint 对应教学步骤「等积式改比例」，预期学生能学生能先改比例再找三角形，而不是盯着等积式发呆。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-010@v1#S1）

### CP2
- 预期推理：学生能在图中找到以 D 为公共直角顶点的两个直角三角形。
- 讲解（explanation）：$BD$ 是 $AC$ 边上的高，$\angle ADB=\angle ODC=90^\circ$，两边成比例且夹角相等，配出 Rt$\triangle ADB \sim$ Rt$\triangle ODC$。
- 提示 L1：配 SAS 相似
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：配 SAS 相似——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-002：该 checkpoint 对应教学步骤「配 SAS 相似」，预期学生能学生能在图中找到以 D 为公共直角顶点的两个直角三角形。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-010@v1#S2）

### CP3
- 预期推理：学生能写全「相似对应角 → 互余 → 垂直」的链条，不跳步。
- 常见偏差：导角链跳步，直接宣布垂直
- 讲解（explanation）：由相似得对应角相等，结合对顶角与互余关系写全导角链，推出 $\angle AEC=90^\circ$，即证得 $CE \perp AB$。
- 提示 L1：导角收尾证垂直
- 提示 L2：常见卡点：导角链跳步，直接宣布垂直
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-006 未在此节点锚定（已在他处使用或粗粒度语境不足）

## Part 2（approach TA-SMV-011@v1）
- 路线 R3（primary）：CP4 → CP5 → CP6；完成：把目标 $AF \cdot DE = AG \cdot BC$ 改写为比例，规划「哪两组相似各贡献哪条边」，两次比例相乘约分收尾。
- 路线 R4（alternate）：CP5 → CP6；进入条件：学生已能学生见等积式目标先改比例式，再规划三角形组。，可直接跳过开场确认；完成：把目标 $AF \cdot DE = AG \cdot BC$ 改写为比例，规划「哪两组相似各贡献哪条边」，两次比例相乘约分收尾。

### CP4（可跳过）
- 预期推理：学生能说出改写后四条边各自的来源任务。
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：目标 $AF \cdot DE = AG \cdot BC$ 改写为 $\frac{AF}{AG}=\frac{BC}{DE}$，明确要分别「供应」这四条边的相似三角形组。
- 提示 L1：目标改写为比例
- 提示 L2：检查还有哪个已知条件没有用上
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-003 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP5
- 预期推理：学生能分工：第一组相似给哪两条边、角平分线给哪两条边。
- 讲解（explanation）：由 $\frac{AD}{AB}=\frac{AE}{AC}$、$\angle DAE=\angle BAC$ 得 $\triangle DAE \sim \triangle BAC$（供应 DE 与 BC）；由 $AF$ 平分 $\angle BAC$ 用角平分线性质（供应 AF 与 AG）。
- 提示 L1：锁定两组相似
- 提示 L2：检查还有哪个已知条件没有用上
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-008/SKILL-SMV-002 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP6
- 预期推理：学生能执行「乘 → 约 → 收」并核对方向（分子分母对齐目标）。
- 讲解（explanation）：两组比例相乘约去中间量，即证 $AF \cdot DE = AG \cdot BC$。
- 提示 L1：比例相乘约分收尾
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：比例相乘约分收尾——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-007：该 checkpoint 对应教学步骤「比例相乘约分收尾」，预期学生能学生能执行「乘 → 约 → 收」并核对方向（分子分母对齐目标）。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-011@v1#S3）
