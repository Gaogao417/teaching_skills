#!/usr/bin/env python3
"""ADR-005 T2.2：8 题教学策略重切为小问粒度（15 份 part 级 TA）。

- 每份 = 一个小问 × 一种解法；steps 为该问解法内部的真实认知节点（≥3，
  按官方 reviewed_solution 的路线撰写，不机械三段）；
- 证据 ref 复用整题录音/转写/润色（append-only hash 引用，不重录）；
- 旧整题 TA 由 question_change stale 事件标 Stale（绑定旧 QT 版本的终态）；
- 批准人 = 迁移 agent（代理偏差沿 Phase 3 dogfood 先例登记，供真人教师
  复核替换）。

顺序约束（ADR-005 风险条款）：本脚本必须在 QT v2 re-promote（repromote-v2.py）
之后运行——先 QT 后 TA，不可逆反。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".codex/skills/math-topic-question-bank/scripts"))

import yaml  # noqa: E402

import teaching_approach as ta  # noqa: E402

BANK = Path(__file__).resolve().parent
ROOT = REPO / "artifacts/canonical-authoring"
LEDGER = ROOT / "id-allocations.yaml"
REVIEWER = "migration-agent"


def S(step_id, intent, narration, reasoning, skills, **extra):
    step = {
        "step_id": step_id,
        "intent": intent,
        "narration": narration,
        "expected_student_reasoning": reasoning,
        "skill_ids": skills,
    }
    step.update(extra)
    return step


# 每题：item 目录 + 旧 approach id + part 级内容（part_id=None 表示整题）。
RECUT = {
    "闵行2020/items/Q018": {
        "qt_id": "QT-SMV-001",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": None,
                "title": "翻折不变量 + 余弦定理求 BE",
                "goal": "（承接整题讲法 v3）抓翻折不变量：等角对等边定出 AD=DC，翻折保长保角，在斜三角形里用余弦定理收口求 BE。",
                "entry_signal": "学生看到翻折条件能先列不变量清单，而不是直接硬算 BE。",
                "steps": [
                    S("S1", "读题标注，等角翻译成等边",
                      "标注等腰条件 $AB=AC=4$、$BC=6$；由 $\\angle DAC=\\angle ACD$ 得 $AD=DC$（等角对等边），设 $AD=DC=t$，$BD=6-t$。",
                      "学生看到 $\\angle DAC=\\angle ACD$ 能立刻写出 AD=DC 并设元。",
                      ["SKILL-SMV-001"]),
                    S("S2", "抓翻折不变量，识别母子型结构",
                      "翻折保长保角：$AE=AC=4$、$DE=DC=t$、$\\angle ADE=\\angle ADC$；折叠后的三角形 ADE 与原三角形 ADC 全等，BE 落在 △BDE 中求解。",
                      "学生能列出翻折不变量清单（对应边相等、对应角相等）。",
                      ["SKILL-SMV-008"]),
                    S("S3", "设元列式求 BE",
                      "用勾股关系解出 $t=\\frac{8}{3}$、$BD=\\frac{10}{3}$；再在 △BDE 中求出夹角 $\\angle BDE$ 后用余弦定理，解得 $BE=1$。",
                      "学生能先解出 t 与 BD，再选余弦定理收口，最后得到 $BE=1$。",
                      ["SKILL-SMV-007"],
                      common_errors=["在斜三角形中硬凑勾股"]),
                ],
            },
        ],
    },
    "闵行2020/items/Q023": {
        "qt_id": "QT-SMV-002",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": "1",
                "title": "第(1)问：等积式改比例，配直角相似证垂直",
                "goal": "掌握「等积式 → 比例式 → 配 SAS 相似 → 导角」路线，证得 $CE \\perp AB$。",
                "entry_signal": "学生能把 $AD \\cdot OC = AB \\cdot OD$ 主动改写成比例式。",
                "steps": [
                    S("S1", "等积式改比例",
                      "把 $AD \\cdot OC = AB \\cdot OD$ 交叉改写为 $\\frac{AD}{OD}=\\frac{AB}{OC}$，目标是配出两个直角三角形的公共顶点比例。",
                      "学生能先改比例再找三角形，而不是盯着等积式发呆。",
                      ["SKILL-SMV-003"]),
                    S("S2", "配 SAS 相似",
                      "$BD$ 是 $AC$ 边上的高，$\\angle ADB=\\angle ODC=90^\\circ$，两边成比例且夹角相等，配出 Rt$\\triangle ADB \\sim$ Rt$\\triangle ODC$。",
                      "学生能在图中找到以 D 为公共直角顶点的两个直角三角形。",
                      ["SKILL-SMV-008", "SKILL-SMV-002"]),
                    S("S3", "导角收尾证垂直",
                      "由相似得对应角相等，结合对顶角与互余关系写全导角链，推出 $\\angle AEC=90^\\circ$，即证得 $CE \\perp AB$。",
                      "学生能写全「相似对应角 → 互余 → 垂直」的链条，不跳步。",
                      ["SKILL-SMV-006"],
                      common_errors=["导角链跳步，直接宣布垂直"]),
                ],
            },
            {
                "part_id": "2",
                "title": "第(2)问：角平分线 + 相似转移证等积式",
                "goal": "把目标 $AF \\cdot DE = AG \\cdot BC$ 改写为比例，规划「哪两组相似各贡献哪条边」，两次比例相乘约分收尾。",
                "entry_signal": "学生见等积式目标先改比例式，再规划三角形组。",
                "steps": [
                    S("S1", "目标改写为比例",
                      "目标 $AF \\cdot DE = AG \\cdot BC$ 改写为 $\\frac{AF}{AG}=\\frac{BC}{DE}$，明确要分别「供应」这四条边的相似三角形组。",
                      "学生能说出改写后四条边各自的来源任务。",
                      ["SKILL-SMV-003"]),
                    S("S2", "锁定两组相似",
                      "由 $\\frac{AD}{AB}=\\frac{AE}{AC}$、$\\angle DAE=\\angle BAC$ 得 $\\triangle DAE \\sim \\triangle BAC$（供应 DE 与 BC）；由 $AF$ 平分 $\\angle BAC$ 用角平分线性质（供应 AF 与 AG）。",
                      "学生能分工：第一组相似给哪两条边、角平分线给哪两条边。",
                      ["SKILL-SMV-008", "SKILL-SMV-002"]),
                    S("S3", "比例相乘约分收尾",
                      "两组比例相乘约去中间量，即证 $AF \\cdot DE = AG \\cdot BC$。",
                      "学生能执行「乘 → 约 → 收」并核对方向（分子分母对齐目标）。",
                      ["SKILL-SMV-007", "SKILL-SMV-009"]),
                ],
            },
        ],
    },
    "闵行2020/items/Q025": {
        "qt_id": "QT-SMV-003",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": "1",
                "title": "第(1)问：重心中线 + 外角分解导角",
                "goal": "用「重心 → 中线 → 等腰直角斜边中线垂直」与外角和分解，证 $\\angle DAB = \\angle DCF$。",
                "entry_signal": "学生看到重心条件能联想到三线合一与中线性质。",
                "steps": [
                    S("S1", "重心翻译成中线",
                      "点 $G$ 是 Rt$\\triangle ABC$ 的重心，$CG$ 是中线，交 $AB$ 于 $F$；由 $AC=BC$、$\\angle ACB=90^\\circ$ 知 $CF$ 既是中线也是高，$\\angle AFC=90^\\circ$。",
                      "学生能把「重心」翻译成「中线」，再由等腰直角得到垂直。",
                      ["SKILL-SMV-001", "SKILL-SMV-008"]),
                    S("S2", "外角和分解对齐",
                      "$\\angle DEF=\\angle ADE+\\angle DAE$（外角），$\\angle DEF=\\angle EFC+\\angle ECF$；其中 $\\angle ADE=\\angle EFC=90^\\circ$，两式相减得 $\\angle DAE=\\angle ECF$。",
                      "学生能对同一个角写两条分解式并相减。",
                      ["SKILL-SMV-005"]),
                    S("S3", "收尾书写",
                      "$\\angle DAE$ 即 $\\angle DAB$、$\\angle ECF$ 即 $\\angle DCF$，故 $\\angle DAB = \\angle DCF$ 得证。",
                      "学生能核对角的记号转换（DAE→DAB、ECF→DCF）后落笔。",
                      ["SKILL-SMV-009"]),
                ],
            },
            {
                "part_id": "2",
                "title": "第(2)问：构全等 + 平行导比例建函数式",
                "goal": "作 $BH \\perp CD$ 构造全等转移线段，由 $AD \\parallel BH$ 导比例，解出 $y = \\frac{x^{2} + 4}{x + 2}$（$0 < x \\leq 2$）。",
                "entry_signal": "学生知道函数关系式要「设元 → 找等量 → 消元」。",
                "steps": [
                    S("S1", "构造高线全等转移",
                      "过点 $B$ 作 $BH \\perp CD$ 于点 $H$，可证 $\\triangle CAD \\cong \\triangle BCH$，得 $BH=CD=2$、$CH=AD=x$、$DH=2-x$。",
                      "学生能想到作高构造全等，把 BC 侧的量转到 CD 轴上。",
                      ["SKILL-SMV-001", "SKILL-SMV-008"]),
                    S("S2", "平行导比例",
                      "$AD \\parallel BH$ 得 $\\frac{AD}{BH}=\\frac{DE}{EH}$，即 $\\frac{x}{2}=\\frac{DE}{EH}$；合比得 $\\frac{DH}{EH}=\\frac{x+2}{2}$，解出 $EH=\\frac{4-2x}{x+2}$。",
                      "学生能用合比性质把 DE/EH 转成 DH/EH。",
                      ["SKILL-SMV-003", "SKILL-SMV-007"]),
                    S("S3", "合并成函数并定范围",
                      "$y=CE=CH+HE=x+\\frac{4-2x}{x+2}$，整理得 $y = \\frac{x^{2} + 4}{x + 2}$；由点 $E$ 在边 $CD$ 上得自变量范围 $0 < x \\leq 2$。",
                      "学生能合并分式并说明范围来自 E 的位置约束。",
                      ["SKILL-SMV-007"],
                      common_errors=["范围写成 0<x<2（漏端点）"]),
                ],
            },
            {
                "part_id": "3",
                "title": "第(3)问：以 CG 为腰的等腰分类",
                "goal": "按 $GC=GD$、$CG=CD$ 两类画图列式，结合函数关系式求解并按范围取舍，得 $AD = 1$ 或 $\\sqrt{14}$。",
                "entry_signal": "学生能对「以 CG 为腰」枚举两种等腰可能并分别画图。",
                "steps": [
                    S("S1", "分类起点与图形",
                      "$\\triangle CDG$ 以 $CG$ 为腰 → 两类：$GC=GD$ 与 $CG=CD$；先明确 $CD=2$ 恒定，分类只改变 G 的位置。",
                      "学生能不重不漏列出两类并说明分类依据（腰的两个端点）。",
                      ["SKILL-SMV-009"]),
                    S("S2", "类一 GC=GD",
                      "取 $AC$ 的中点 $M$，联结 $MD$，则 $MD=MC$；联结 $MG$ 则 $MG \\perp CD$ 且直线 $MG$ 经过点 $B$，$BH$ 与 $MG$ 共线；又 $CH=AD$，得 $AD=CH=1$。",
                      "学生能用「到两端等距 → 垂直」识别中垂线结构。",
                      ["SKILL-SMV-005", "SKILL-SMV-001"]),
                    S("S3", "类二 CG=CD 与总结",
                      "$CG=CD=2$；G 为重心，$CF=\\frac{3}{2}CG=3$，等腰直角得 $AC=\\frac{\\sqrt{2}}{2}AB=3\\sqrt{2}$，$AD=\\sqrt{AC^{2}-CD^{2}}=\\sqrt{14}$。综上 $AD = 1$ 或 $\\sqrt{14}$，均满足 $0 < x \\leq 2$。",
                      "学生能代回函数范围检验两解均合法。",
                      ["SKILL-SMV-007"],
                      common_errors=["漏一类，或解后不代回范围"]),
                ],
            },
        ],
    },
    "闵行2020/items/Q007": {
        "qt_id": "QT-SMV-013",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": None,
                "title": "比例中项定义性计算",
                "goal": "巩固比例中项的定义性计算：$b^2=ac$，代入后开平方并按线段取正值。",
                "entry_signal": "学生能默写比例中项定义。",
                "steps": [
                    S("S1", "定义回忆",
                      "比例中项定义：$b^2=ac$（即 $\\frac{a}{b}=\\frac{b}{c}$），本题即求满足 $b^2=4\\times 9$ 的线段 $b$。",
                      "学生能写出两种等价表达并选用平方形式。",
                      ["SKILL-SMV-001"]),
                    S("S2", "代入计算",
                      "代入 $a=4$、$c=9$，$b^2=36$。",
                      "学生能正确完成乘法 4×9=36。",
                      ["SKILL-SMV-007"]),
                    S("S3", "开方取正值",
                      "$b=\\sqrt{36}$，线段长度取正值，得比例中项为 $6$ 厘米。",
                      "学生能说明为什么开方后只取正值（线段长非负且非零）。",
                      ["SKILL-SMV-007"]),
                ],
            },
        ],
    },
    "黄浦2025/items/Q021": {
        "qt_id": "QT-SMV-004",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": None,
                "title": "测高仪 A 字型相似建模（两次实践互证）",
                "goal": "在真实测量情境中把仪器结构翻译成 A 字型相似模型：两次实践分别求还需测量的量与树高表达式，并互相印证。",
                "entry_signal": "学生能把实物图抽象成两条平行线截得的相似三角形。",
                "steps": [
                    S("S1", "读仪器，标注已知量",
                      "标注仪器结构：$AB=40\\,\\mathrm{cm}$、$CD=60\\,\\mathrm{cm}$、$DB=20\\,\\mathrm{cm}$，铅垂保证竖直方向；把「视线—标杆—树」翻译成 A 字型相似模型。",
                      "学生能说出哪两条线平行、截出哪两个三角形。",
                      ["SKILL-SMV-001"]),
                    S("S2", "第一次实践列比例求表达式",
                      "由平行得 A 字型相似，对应边成比例，推出还需测量 $NE=b\\,\\mathrm{cm}$，树高 $MN=(a+b+40)\\,\\mathrm{cm}$（40 为仪器结构补偿量）。",
                      "学生能写出比例式并解出 $MN=(a+b+40)\\,\\mathrm{cm}$，说明每项来源。",
                      ["SKILL-SMV-008", "SKILL-SMV-003"]),
                    S("S3", "第二次实践与结果印证",
                      "换摆放后同理构造相似：还需测量 $EF=c\\,\\mathrm{cm}$，得 $MN=(c+a)\\,\\mathrm{cm}$；与第一次的 $MN=(a+b+40)\\,\\mathrm{cm}$ 互相印证，检查建模一致性。",
                      "学生能独立完成第二次建模并解释两种表达式为何表示同一树高。",
                      ["SKILL-SMV-003", "SKILL-SMV-007"]),
                ],
            },
        ],
    },
    "黄浦2025/items/Q022": {
        "qt_id": "QT-SMV-005",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": "1",
                "title": "第(1)问：角平分线公共角 + 等腰外角配 AA",
                "goal": "用「角平分线给公共角、等腰给外角」组合，AA 判定证 $\\triangle CEA\\sim\\triangle CDB$。",
                "entry_signal": "学生看到角平分线与等腰能分别翻译出等角。",
                "steps": [
                    S("S1", "角平分线给第一组角",
                      "由 $CD$ 平分 $\\angle ACB$ 得 $\\angle ACE=\\angle DCB$，这是 $\\triangle CEA$ 与 $\\triangle CDB$ 的公共等角。",
                      "学生能立刻把角平分线条件翻译成两个三角形的公共等角。",
                      ["SKILL-SMV-008"]),
                    S("S2", "等腰外角配第二组角",
                      "由 $AE=AD$ 得 $\\triangle AED$ 等腰，$\\angle CEA$ 与 $\\angle CDB$ 是其两个外角，均等于 $2\\angle EAD$，故 $\\angle CEA=\\angle CDB$。",
                      "学生能用「等腰 + 外角」补出第二组角。",
                      ["SKILL-SMV-002"]),
                    S("S3", "AA 判定收尾",
                      "两组对应角相等，由 AA 判定证得 $\\triangle CEA\\sim\\triangle CDB$。",
                      "学生能写明判定依据（AA）并核对顶点对应顺序。",
                      ["SKILL-SMV-009"]),
                ],
            },
            {
                "part_id": "2",
                "title": "第(2)问：平行等角传递 + 相似比例收尾",
                "goal": "由 $CF\\parallel AE$ 得新等角并做外角和分解，证 $\\triangle CFB\\sim\\triangle AFC$ 后逐层转移比例，得 $\\frac{BD}{AD}=\\frac{BF}{CF}$。",
                "entry_signal": "学生能把平行条件翻译成等角，并寻找公共角。",
                "steps": [
                    S("S1", "平行给新等角",
                      "由 $CF\\parallel AE$ 得 $\\angle E=\\angle DCF$。",
                      "学生能指出平行线截哪两条线产生这对内错角。",
                      ["SKILL-SMV-005"]),
                    S("S2", "外角和分解 + 公共角配相似",
                      "$\\angle DCF=\\angle DCB+\\angle BCF$，$\\angle E=\\angle CDF=\\angle ACE+\\angle CAD$，相减得 $\\angle BCF=\\angle CAD$；又 $\\angle F=\\angle F$（公共），故 $\\triangle CFB\\sim\\triangle AFC$。",
                      "学生能完成「分解 → 相减 → 公共角」的三步配角。",
                      ["SKILL-SMV-002", "SKILL-SMV-008"]),
                    S("S3", "比例转移收尾",
                      "由 $\\triangle CFB\\sim\\triangle AFC$ 得 $\\frac{BF}{CF}=\\frac{CF}{AF}$，结合第(1)问 $\\triangle CEA\\sim\\triangle CDB$ 的相似比 $\\frac{CE}{CD}=\\frac{CA}{CB}$ 逐层转移，最终证得 $\\frac{BD}{AD}=\\frac{BF}{CF}$。",
                      "学生能规划「先相似比、再平行比」的转移顺序，不硬凑。",
                      ["SKILL-SMV-009", "SKILL-SMV-007"]),
                ],
            },
        ],
    },
    "黄浦2025/items/Q024": {
        "qt_id": "QT-SMV-006",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": "1",
                "title": "第(1)问：作高数值化 + 同正切证等角",
                "goal": "作 $CG\\perp AB$ 把两个角各自数值化（正切都为 2/3），证 $\\angle BAC=\\angle PCF$。",
                "entry_signal": "学生见到 sinB=4/5 能想到作高构造直角三角形。",
                "steps": [
                    S("S1", "作高数值化 BC 侧",
                      "过点 $C$ 作 $CG\\perp AB$，垂足为 $G$；由 $BC=5$、$\\sin B=\\frac{4}{5}$ 得 $BG=3$、$CG=4$；又 $AB=9$，得 $AG=6$。",
                      "学生能由三角函数值还原直角边并算出 AG。",
                      ["SKILL-SMV-001", "SKILL-SMV-008"]),
                    S("S2", "两侧各算正切",
                      "$\\tan\\angle BAC=\\frac{CG}{AG}=\\frac{2}{3}$；$\\angle CPF=90^\\circ$、$\\frac{FP}{PC}=\\frac{2}{3}$，故 $\\tan\\angle PCF=\\frac{2}{3}$。",
                      "学生能在两个不同三角形里分别表达正切。",
                      ["SKILL-SMV-003", "SKILL-SMV-007"]),
                    S("S3", "锐角同一收尾",
                      "$\\angle BAC$ 与 $\\angle PCF$ 均为锐角且正切相等，故 $\\angle BAC=\\angle PCF$。",
                      "学生能说明「锐角 + 三角函数值相等 → 角相等」的依据。",
                      ["SKILL-SMV-009"]),
                ],
            },
            {
                "part_id": "2",
                "title": "第(2)问：等角平移锁相似，余切解 BP",
                "goal": "由平行与第(1)问等角把角平移到 $\\triangle BPC$ 与 $\\triangle PFC$，用余切列比例解出 $BP=\\frac{17}{3}$。",
                "entry_signal": "学生能把「已证等角」当作第二问的现成工具。",
                "steps": [
                    S("S1", "平行 + 等角平移",
                      "$AB\\parallel CD$ 得 $\\angle BAC=\\angle ACD$；结合第(1)问 $\\angle PCF=\\angle BAC$ 得 $\\angle PCF=\\angle ACD$，同减 $\\angle ACP$ 得 $\\angle PCA=\\angle FCD$。",
                      "学生能写出「平行内错角 + 已证等角 → 差角相等」的链条。",
                      ["SKILL-SMV-005", "SKILL-SMV-008"]),
                    S("S2", "相似条件对齐",
                      "$\\triangle APC\\sim\\triangle EFC$ 且 $\\angle PEC=\\angle APE<90^\\circ$，故 $\\angle APC=\\angle EFC$；同加直角得 $\\angle BPC=\\angle PFC$。",
                      "学生能核对待定相似的对应顶点后再用条件。",
                      ["SKILL-SMV-002"]),
                    S("S3", "余切列式解 BP",
                      "$\\cot\\angle BPC=\\cot\\angle PFC$ 得 $\\frac{PG}{CG}=\\frac{2}{3}$，$CG=4$，故 $PG=\\frac{8}{3}$，$BP=BG+PG=3+\\frac{8}{3}=\\frac{17}{3}$。",
                      "学生能用余切（而非正切）使所求边落在分子，解出 $BP=\\frac{17}{3}$。",
                      ["SKILL-SMV-007"],
                      common_errors=["用正切导致求出倒数"]),
                ],
            },
            {
                "part_id": "3",
                "title": "第(3)问：面积比转化 + F 位置两分类",
                "goal": "把 $\\frac{S_{\\triangle HFC}}{S_{\\triangle PHC}}=\\frac{1}{3}$ 转成 $\\frac{FH}{PH}=\\frac{1}{3}$，按 F 在 $PH$ 延长线/线段上两分类，解得 $\\frac{AH}{AC}=\frac{2}{7}$ 或 $\\frac{1}{5}$。",
                "entry_signal": "学生能把面积比转成同高线段比。",
                "steps": [
                    S("S1", "面积比转线段比",
                      "$\\triangle HFC$ 与 $\\triangle PHC$ 共顶点 $C$，底 $FH$、$PH$ 同在直线 $PE$ 上（等高），故 $\\frac{S_{\\triangle HFC}}{S_{\\triangle PHC}}=\\frac{1}{3}$ 即 $\\frac{FH}{PH}=\\frac{1}{3}$。",
                      "学生能识别共顶点、底共线的等高结构并把面积比化成线段比。",
                      ["SKILL-SMV-003", "SKILL-SMV-005"]),
                    S("S2", "类一：F 在 PH 延长线上",
                      "过 $H$ 作 $HM\\perp AB$；$\\angle MPH=\\angle PCG$ 且 $\\angle HMP=\\angle CGP=90^\\circ$，$\\triangle MPH\\sim\\triangle GCP$。此时 $\\frac{PH}{PC}=\\frac{1}{2}$，设 $MH=a$ 得 $GP=2a$、$MP=2$、$AM=\\frac{3}{2}a$，由 $2a+\\frac{3}{2}a+2+3=9$ 得 $a=\\frac{8}{7}$，故 $\\frac{AH}{AC}=\\frac{MH}{CG}=\\frac{2}{7}$。",
                      "学生能用相似把 MH/GP 建立倍数关系并列一元方程。",
                      ["SKILL-SMV-002", "SKILL-SMV-007"]),
                    S("S3", "类二：F 在 PH 上与总结",
                      "此时 $PH=PC$，设 $MH=b$ 得 $GP=b$、$MP=4$、$AM=\\frac{3}{2}b$，由 $b+\\frac{3}{2}b+4+3=9$ 得 $b=\\frac{4}{5}$，故 $\\frac{AH}{AC}=\\frac{1}{5}$。综上 $\\frac{AH}{AC}=\\frac{2}{7}$ 或 $\\frac{1}{5}$。",
                      "学生能完整分两类并把两解分别代回检验。",
                      ["SKILL-SMV-009"],
                      common_errors=["漏掉 F 在延长线上的情形"]),
                ],
            },
        ],
    },
    "黄浦2025/items/Q020": {
        "qt_id": "QT-SMV-048",
        "old_local_id": "t1",
        "approaches": [
            {
                "part_id": "1",
                "title": "第(1)问：8 字相似定比 + 向量分解",
                "goal": "由 $AD\\parallel BC$ 的 8 字型相似定出对角线分比，再分步代入化为 $\\vec{a}$、$\\vec{b}$ 的线性组合。",
                "entry_signal": "学生能在梯形里看出对角线交点分出的两组比。",
                "steps": [
                    S("S1", "平行出 8 字相似",
                      "由 $AD\\parallel BC$ 得 $\\triangle AED \\sim \\triangle CEB$（8 字型），故 $AE:EC=AD:CB=4:5$、$BE:ED=BC:AD=5:4$。",
                      "学生能直接读出对角线被交点 E 分成的两组比。",
                      ["SKILL-SMV-008"]),
                    S("S2", "写向量中间式",
                      "$\\overrightarrow{AE}=\\overrightarrow{AB}+\\overrightarrow{BE}$，其中 $\\overrightarrow{AB}=\\overrightarrow{DB}-\\overrightarrow{DA}$ 分步用 $\\vec{a}$、$\\vec{b}$ 与定比表达。",
                      "学生能先写「向量和」中间式，不直接跳到最终组合。",
                      ["SKILL-SMV-002"]),
                    S("S3", "代入定比收尾",
                      "由定比分解逐步代入，得 $\\overrightarrow{AE}=\\frac{4}{5}\\vec{a}-\\frac{4}{9}\\vec{b}$。",
                      "学生能核对系数来源（4/5 来自 AE:EC，4/9 来自 BE:ED）。",
                      ["SKILL-SMV-007"],
                      common_errors=["两个系数的比分母用反"]),
                ],
            },
            {
                "part_id": "2",
                "title": "第(2)问：构矩形转移直角求正弦",
                "goal": "过 $A$ 作 $AF\\perp BC$ 构造矩形 $ADCF$，把 $\\angle ABC$ 放进 Rt$\\triangle ABF$ 中求 $\\sin\\angle ABC=\\frac{2\\sqrt{5}}{5}$。",
                "entry_signal": "学生能由 $AD\\perp CD$、$AD\\parallel BC$ 想到补出矩形。",
                "steps": [
                    S("S1", "数据准备",
                      "在 Rt$\\triangle ADC$ 中 $AD=4$、$\\tan\\angle DAC=\\frac{1}{2}$，得 $CD=2$。",
                      "学生能由正切与已知直角边解出另一直角边。",
                      ["SKILL-SMV-001", "SKILL-SMV-007"]),
                    S("S2", "构矩形转移",
                      "过点 $A$ 作 $AF\\perp BC$；$\\angle FAD=90^\\circ$ 且 $AD\\perp CD$，四边形 $ADCF$ 是矩形，故 $AF=CD=2$、$FC=AD=4$；$BC=5$ 得 $BF=1$，$AB=\\sqrt{AF^{2}+BF^{2}}=\\sqrt{5}$。",
                      "学生能说明矩形从哪两个垂直条件来，并解出 AB。",
                      ["SKILL-SMV-008", "SKILL-SMV-002"]),
                    S("S3", "直角三角形求正弦",
                      "在 Rt$\\triangle ABF$ 中，对边 $AF=2$、斜边 $AB=\\sqrt{5}$，由 $\\frac{2}{\\sqrt{5}}$ 分母有理化，得 $\\sin\\angle ABC=\\frac{2\\sqrt{5}}{5}$。",
                      "学生能选对对边/斜边并完成分母有理化。",
                      ["SKILL-SMV-007"]),
                ],
            },
        ],
    },
}


def main() -> int:
    applied = ta.apply_question_change_stale(root=ROOT)
    print("stale applied:", applied)
    created: list[str] = []
    for rel, spec in RECUT.items():
        item_dir = BANK / rel
        qt_id = spec["qt_id"]
        payload = ta.load_sidecar(item_dir)
        assert payload is not None, rel
        old = next(
            a for a in payload["approaches"] if a["id"] == spec["old_local_id"]
        )
        for content in spec["approaches"]:
            part_id = content["part_id"]
            already = any(
                a.get("approval")
                and str(a.get("part_id") or "") == (part_id or "")
                for a in payload["approaches"]
            )
            if already:
                print(f"skip（已重切）: {qt_id} part={part_id or '整题'}")
                continue
            new_id = ta.next_local_id(payload)
            entry = ta.new_approach(payload, title=content["title"], author="migration-agent")
            entry["id"] = new_id
            entry["part_id"] = part_id or ""
            entry["goal"] = content["goal"]
            entry["entry_signal"] = content["entry_signal"]
            entry["steps"] = content["steps"]
            entry["steps_origin"] = "manual"
            # 证据 ref 复用整题录音（append-only hash 引用，不重录）。
            entry["evidence"] = {
                "recordings": list(old.get("evidence", {}).get("recordings") or []),
                "polishes": list(old.get("evidence", {}).get("polishes") or []),
                "manual_edit_notes": [
                    "part 级重切（ADR-005）：讲解稿按官方 reviewed_solution 撰写，"
                    "证据 ref 复用整题录音"
                ],
            }
            frozen = ta.freeze_approved_approach(
                entry,
                item_dir,
                reviewer_id=REVIEWER,
                review_note="part 级重切（ADR-005），证据 ref 复用整题录音",
                qt_id=qt_id,
                ledger_path=LEDGER,
                root=ROOT,
                part_id=part_id,
            )
            entry["status"] = "approved"
            entry["approval"] = {
                "reviewer_id": REVIEWER,
                "approved_at": frozen["approval"]["approved_at"],
                "review_note": "part 级重切（ADR-005），代理批准待真人教师复核",
            }
            entry["canonical"] = {
                "artifact_id": frozen["artifact_id"],
                "version": frozen["version"],
                "content_hash": frozen["content_hash"],
                "approved_at": frozen["approval"]["approved_at"],
            }
            payload["approaches"].append(entry)
            ta.save_sidecar(item_dir, payload)
            created.append(
                f"{frozen['artifact_id']}@{frozen['version']} → {qt_id}"
                f"{'#' + part_id if part_id else '（整题）'}"
            )
    for line in created:
        print(line)
    print(f"total: {len(created)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
