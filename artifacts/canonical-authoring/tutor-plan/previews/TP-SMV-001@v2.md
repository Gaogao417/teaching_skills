# TutorPlan 预览：TP-SMV-001@v2

- 题目：QT-SMV-001@v2
- Build：deterministic-rules / plan-build-rules/v1（tutor-plan-build/v1，registry action-runtime-registry/v5@32f7ae75600a）
- 风险标注：答案值出现于 1 个讲解/修复资源（教师判断是否过早泄题）；hint/probe 由发布门禁 fail-closed 拦截
- 最高提示档位：L2；skill annotation：2 个，未锚定节点：1 个
- 待几何绑定的 Action 能力（Phase 5 presenter/内容工序接入）：select-option、mark-segment-values、enter-equation

## Part 1（approach TA-SMV-009@v1）
- 路线 R1（primary）：CP1 → CP2 → CP3；完成：（承接整题讲法 v3）抓翻折不变量：等角对等边定出 AD=DC，翻折保长保角，在斜三角形里用余弦定理收口求 BE。
- 路线 R2（alternate）：CP2 → CP3；进入条件：学生已能学生看到翻折条件能先列不变量清单，而不是直接硬算 BE。，可直接跳过开场确认；完成：（承接整题讲法 v3）抓翻折不变量：等角对等边定出 AD=DC，翻折保长保角，在斜三角形里用余弦定理收口求 BE。

### CP1（可跳过）
- 预期推理：学生看到 $\angle DAC=\angle ACD$ 能立刻写出 AD=DC 并设元。
- 开场（voice_seed）：我们先看这道题：（承接整题讲法 v3）抓翻折不变量：等角对等边定出 AD=DC，翻折保长保角，在斜三角形里用余弦定理收口求 BE。（（承接整题讲法 v3）抓翻折不变量：等角对等边定出 AD=DC，翻折保长保角，在斜三角形里用余弦定理收口求 BE。）
- 讲解（explanation）：标注等腰条件 $AB=AC=4$、$BC=6$；由 $\angle DAC=\angle ACD$ 得 $AD=DC$（等角对等边），设 $AD=DC=t$，$BD=6-t$。
- 提示 L1：读题标注，等角翻译成等边
- 提示 L2：检查还有哪个已知条件没有用上
- 确认探针：快速确认：读题标注，等角翻译成等边——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-001：该 checkpoint 对应教学步骤「读题标注，等角翻译成等边」，预期学生能学生看到 $\angle DAC=\angle ACD$ 能立刻写出 AD=DC 并设元。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-009@v1#S1）

### CP2
- 预期推理：学生能列出翻折不变量清单（对应边相等、对应角相等）。
- 讲解（explanation）：翻折保长保角：$AE=AC=4$、$DE=DC=t$、$\angle ADE=\angle ADC$；折叠后的三角形 ADE 与原三角形 ADC 全等，BE 落在 △BDE 中求解。
- 提示 L1：抓翻折不变量，识别母子型结构
- 提示 L2：检查还有哪个已知条件没有用上
- 未锚定原因：v2 skill_ids 仅作 provisional hint：SKILL-SMV-008 未在此节点锚定（已在他处使用或粗粒度语境不足）

### CP3
- 预期推理：学生能先解出 t 与 BD，再选余弦定理收口，最后得到 $BE=1$。
- 常见偏差：在斜三角形中硬凑勾股
- 讲解（explanation）：用勾股关系解出 $t=\frac{8}{3}$、$BD=\frac{10}{3}$；再在 △BDE 中求出夹角 $\angle BDE$ 后用余弦定理，解得 $BE=1$。
- 提示 L1：设元列式求 BE
- 提示 L2：常见卡点：在斜三角形中硬凑勾股
- 确认探针：快速确认：设元列式求 BE——你能指出它在图或题干中对应的具体对象吗？
- Skill 标注 SKILL-SMV-007：该 checkpoint 对应教学步骤「设元列式求 BE」，预期学生能学生能先解出 t 与 BD，再选余弦定理收口，最后得到 $BE=1$。；此处证据可直接支持该 skill 的判定。（证据 TA-SMV-009@v1#S3）
