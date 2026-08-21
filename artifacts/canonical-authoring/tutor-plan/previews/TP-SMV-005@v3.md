# TutorPlan 预览：TP-SMV-005@v3

- 题目：QT-SMV-005@v2
- Build：deterministic-rules / plan-build-rules/v1（tutor-plan-build/v1，registry action-runtime-registry/v5@32f7ae75600a）
- 风险标注：答案值出现于 5 个讲解/修复资源（教师判断是否过早泄题）；hint/probe 由发布门禁 fail-closed 拦截
- 最高提示档位：L2；skill annotation：4 个，未锚定节点：2 个
- 待几何绑定的 Action 能力（Phase 5 presenter/内容工序接入）：select-option、pair-segments、enter-equation
- 泄漏自查降级的资源：CP1 voice_seed、CP4 voice_seed

## Part 1（approach TA-SMV-017@v2）
- 路线 R1（primary）：CP1 → CP2 → CP3；完成：用「角平分线给公共角、等腰给外角」组合，AA 判定证 $\triangle CEA\sim\triangle CDB$。
- 路线 R2（alternate）：CP2 → CP3；进入条件：学生已能学生看到角平分线与等腰能分别翻译出等角。，可直接跳过开场确认；完成：用「角平分线给公共角、等腰给外角」组合，AA 判定证 $\triangle CEA\sim\triangle CDB$。

### CP1（可跳过）
- 预期推理：学生能立刻把角平分线条件翻译成两个三角形的公共等角。
- 常见偏差：平分线两侧的角与三角形顶点对应错
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：由 $CD$ 平分 $\angle ACB$ 得 $\angle ACE=\angle DCB$，这是 $\triangle CEA$ 与 $\triangle CDB$ 的公共等角。
- 提示 L1：角平分线给第一组角
- 提示 L2：常见卡点：平分线两侧的角与三角形顶点对应错
- 确认探针：快速确认：角平分线给第一组角——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-008：select 类证据在 recognize/plan 间共享（capability-skill-map gap note）；以本 checkpoint 语境（角平分线给第一组角）作为该 skill 的低置信线索。（证据 TA-SMV-017@v2#S1）

### CP2
- 预期推理：学生能用「等腰 + 外角」补出第二组角。
- 常见偏差：把外角当成底角本身
- 讲解（explanation）：由 $AE=AD$ 得 $\triangle AED$ 等腰，$\angle CEA$ 与 $\angle CDB$ 是其两个外角，均等于 $2\angle EAD$，故 $\angle CEA=\angle CDB$。
- 提示 L1：等腰外角配第二组角
- 提示 L2：常见卡点：把外角当成底角本身
- 确认探针：快速确认：等腰外角配第二组角——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-002：该 checkpoint 对应教学步骤「等腰外角配第二组角」，预期学生能学生能用「等腰 + 外角」补出第二组角。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-017@v2#S2）

### CP3
- 预期推理：学生能写明判定依据（AA）并核对顶点对应顺序。
- 常见偏差：顶点对应关系写错；只证一组角相等就下相似结论
- 讲解（explanation）：两组对应角相等，由 AA 判定证得 $\triangle CEA\sim\triangle CDB$。
- 提示 L1：AA 判定收尾
- 提示 L2：常见卡点：顶点对应关系写错
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-009 未在此节点锚定（已在他处使用或粗粒度语境不足）

## Part 2（approach TA-SMV-018@v2）
- 路线 R3（primary）：CP4 → CP5 → CP6；完成：由 $CF\parallel AE$ 得新等角并做外角和分解，证 $\triangle CFB\sim\triangle AFC$ 后逐层转移比例，得 $\frac{BD}{AD}=\frac{BF}{CF}$。
- 路线 R4（alternate）：CP5 → CP6；进入条件：学生已能学生能把平行条件翻译成等角，并寻找公共角。，可直接跳过开场确认；完成：由 $CF\parallel AE$ 得新等角并做外角和分解，证 $\triangle CFB\sim\triangle AFC$ 后逐层转移比例，得 $\frac{BD}{AD}=\frac{BF}{CF}$。

### CP4（可跳过）
- 预期推理：学生能指出平行线截哪两条线产生这对内错角。
- 常见偏差：平行等角认错位置（内错角与同位角混淆）
- 开场（voice_seed）：回到题干，把已知条件与要求的目标各列一遍，再对照图形找它们的联系。
- 讲解（explanation）：由 $CF\parallel AE$ 得 $\angle E=\angle DCF$。
- 提示 L1：平行给新等角
- 提示 L2：常见卡点：平行等角认错位置（内错角与同位角混淆）
- 确认探针：快速确认：平行给新等角——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-005：该 checkpoint 对应教学步骤「平行给新等角」，预期学生能学生能指出平行线截哪两条线产生这对内错角。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-018@v2#S1）

### CP5
- 预期推理：学生能完成「分解 → 相减 → 公共角」的三步配角。
- 常见偏差：外角和分解相减时对应项错位
- 讲解（explanation）：$\angle DCF=\angle DCB+\angle BCF$，$\angle E=\angle CDF=\angle ACE+\angle CAD$，相减得 $\angle BCF=\angle CAD$；又 $\angle F=\angle F$（公共），故 $\triangle CFB\sim\triangle AFC$。
- 提示 L1：外角和分解 + 公共角配相似
- 提示 L2：常见卡点：外角和分解相减时对应项错位
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-002/SKILL-SMV-008 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP6
- 预期推理：学生能规划「先相似比、再平行比」的转移顺序，不硬凑。
- 常见偏差：平行线截得的比例上下位写反；不用第一问结论另起炉灶
- 讲解（explanation）：由 $\triangle CFB\sim\triangle AFC$ 得 $\frac{BF}{CF}=\frac{CF}{AF}$，结合第(1)问 $\triangle CEA\sim\triangle CDB$ 的相似比 $\frac{CE}{CD}=\frac{CA}{CB}$ 逐层转移，最终证得 $\frac{BD}{AD}=\frac{BF}{CF}$。
- 提示 L1：比例转移收尾
- 提示 L2：常见卡点：平行线截得的比例上下位写反
- 确认探针：快速确认：比例转移收尾——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-007：该 checkpoint 对应教学步骤「比例转移收尾」，预期学生能学生能规划「先相似比、再平行比」的转移顺序，不硬凑。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-018@v2#S3）
