from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
PAPER = "2024-HONGKOU-YIMO"
SRC = "documents/初三/2024届-上海市虹口区-初三一模数学-试卷及参考答案"
ZERO = "sha256:" + "0" * 64


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


items = [
    dict(n=1, typ="choice", pts=4, page="002.png", qbox=[145, 515, 930, 610],
         stem=r"下列函数中，$y$ 是 $x$ 的二次函数的是",
         choices=[r"$y=2x-1$", r"$y=\dfrac{1}{x^2}$", r"$y=2x^2-1$", r"$y=2x^3-1$"], answer="C"),
    dict(n=2, typ="choice", pts=4, page="002.png", qbox=[145, 605, 930, 680],
         stem=r"将抛物线 $y=-3x^2$ 向左平移 $4$ 个单位长度，所得到抛物线的表达式是",
         choices=[r"$y=-3(x+4)^2$", r"$y=-3(x-4)^2$", r"$y=-3x^2+4$", r"$y=-3x^2-4$"], answer="A"),
    dict(n=3, typ="choice", pts=4, page="002.png", qbox=[145, 675, 930, 765],
         stem=r"如图1，在 $\mathrm{Rt}\triangle ABC$ 中，已知 $\angle C=90^\circ$，$\cos A=\dfrac34$，$AC=3$，那么 $BC$ 的长为",
         choices=[r"$\sqrt7$", r"$2\sqrt7$", r"$4$", r"$5$"], answer="A",
         prompts=[("002.png", [190, 880, 330, 1040])]),
    dict(n=4, typ="choice", pts=4, page="002.png", qbox=[145, 755, 930, 885],
         stem=r"如图2，一条细绳系着一个小球在平面内摆动。已知细绳从悬挂点 $O$ 到球心的长度为 $50$ 厘米，小球在左、右两个最高位置时，细绳相应所成的角 $\angle AOB$ 为 $40^\circ$，那么小球在最高位置和最低位置时的高度差为",
         choices=[r"$(50-50\sin40^\circ)$ 厘米", r"$(50-50\cos40^\circ)$ 厘米", r"$(50-50\sin20^\circ)$ 厘米", r"$(50-50\cos20^\circ)$ 厘米"], answer="D",
         prompts=[("002.png", [415, 875, 615, 1040])]),
    dict(n=5, typ="choice", pts=4, page="002.png", qbox=[145, 1045, 930, 1125],
         stem=r"如图3，点 $G$ 是 $\triangle ABC$ 的重心，$GE\parallel AC$ 交 $BC$ 于点 $E$。如果 $AC=12$，那么 $GE$ 的长为",
         choices=["3", "4", "6", "8"], answer="B",
         prompts=[("002.png", [680, 875, 875, 1045])]),
    dict(n=6, typ="choice", pts=4, page="002.png", qbox=[145, 1115, 930, 1290],
         stem="如图4，四边形的顶点在方格纸的格点上，下列方格纸中的四边形与已知四边形相似的是",
         choices=["图 A 所示四边形", "图 B 所示四边形", "图 C 所示四边形", "图 D 所示四边形"], answer="D",
         prompts=[("002.png", [165, 1170, 910, 1325])]),
    dict(n=7, typ="fillin", pts=4, page="002.png", qbox=[145, 1290, 930, 1335],
         stem=r"已知 $x:y=3:2$，那么 $(x-y):x$ 的值为 \fillin。", answer=r"$\dfrac13$"),
    dict(n=8, typ="fillin", pts=4, page="002.png", qbox=[145, 1330, 930, 1395],
         stem=r"如果向量 $\vec a$、$\vec b$ 和 $\vec x$ 满足 $\vec a-\vec x=2(\vec a-\vec b)$，那么 $\vec x=\fillin$。", answer=r"$-\vec a+2\vec b$"),
    dict(n=9, typ="fillin", pts=4, page="003.png", qbox=[150, 165, 925, 225],
         stem=r"已知抛物线 $y=(1-a)x^2+3$ 开口向下，那么 $a$ 的取值范围是 \fillin。", answer=r"$a>1$"),
    dict(n=10, typ="fillin", pts=4, page="003.png", qbox=[150, 215, 925, 260],
         stem=r"如果点 $A(2,1)$ 在抛物线 $y=(x-1)^2+m$ 上，那么 $m$ 的值是 \fillin。", answer="$0$"),
    dict(n=11, typ="fillin", pts=4, page="003.png", qbox=[150, 255, 925, 320],
         stem=r"如果将抛物线 $y=2x^2$ 平移，使顶点移到点 $P(-3,1)$ 的位置，那么所得抛物线的表达式是 \fillin。", answer=r"$y=2(x+3)^2+1$"),
    dict(n=12, typ="fillin", pts=4, page="003.png", qbox=[150, 315, 925, 385],
         stem=r"已知点 $A(-3,y_1)$ 和 $B(1,y_2)$ 都在抛物线 $y=2(x-1)^2-2$ 上，那么 $y_1$ 和 $y_2$ 的大小关系为 $y_1\fillin y_2$（填“$>$”或“$<$”或“$=$”）。", answer="$>$"),
    dict(n=13, typ="fillin", pts=4, page="003.png", qbox=[150, 380, 925, 450],
         stem=r"已知抛物线 $y=-x^2+bx+c$ 如图5所示，那么点 $P(b,c)$ 在第 \fillin 象限。", answer="二",
         prompts=[("003.png", [160, 465, 345, 645])]),
    dict(n=14, typ="fillin", pts=4, page="003.png", qbox=[150, 445, 925, 505],
         stem=r"一个三角形框架模型的边长分别为 $3$ 分米、$4$ 分米和 $5$ 分米，木工要以一根长 $6$ 分米的木条为一边，做与模型相似的三角形，那么做出的三角形中，面积最大的是 \fillin 平方分米。", answer="$24$"),
    dict(n=15, typ="fillin", pts=4, page="003.png", qbox=[150, 660, 925, 705],
         stem=r"如图6，已知 $AD\parallel EF\parallel BC$，$BC=2AD$，$BE=2AE$，$AD=a$，那么用 $a$ 表示 $EF=\fillin$。", answer=r"$\dfrac43a$",
         prompts=[("003.png", [385, 470, 650, 650])]),
    dict(n=16, typ="fillin", pts=4, page="003.png", qbox=[150, 695, 925, 740],
         stem=r"如图7，在平行四边形 $ABCD$ 中，点 $F$ 在边 $AD$ 上，$AF=2FD$，直线 $BF$ 与对角线 $AC$ 相交于点 $E$，交 $CD$ 的延长线于点 $G$，如果 $BE=2$，那么 $EG$ 的长是 \fillin。", answer="$3$",
         prompts=[("003.png", [655, 470, 910, 655])]),
    dict(n=17, typ="fillin", pts=4, page="003.png", qbox=[150, 735, 925, 1060],
         stem=r"定义：如果以一条线段为对角线作正方形，那么称该正方形为这条线段的“对角线正方形”。例如，图8①中正方形 $ABCD$ 即为线段 $AC$ 的“对角线正方形”。如图8②，在 $\mathrm{Rt}\triangle ABC$ 中，$\angle C=90^\circ$，$AC=3$，$BC=4$，点 $P$ 在边 $AB$ 上，如果线段 $PC$ 的“对角线正方形”有两边同时落在 $\triangle ABC$ 的边上，那么 $AP$ 的长是 \fillin。", answer=r"$\dfrac{15}{7}$",
         prompts=[("003.png", [175, 840, 550, 1045])]),
    dict(n=18, typ="fillin", pts=4, page="003.png", qbox=[150, 1055, 925, 1225],
         stem=r"如图9，在 $\triangle ABC$ 中，$AB=AC=5$，$\tan B=\dfrac34$。点 $M$ 在边 $BC$ 上，$BM=3$，点 $N$ 是射线 $BA$ 上一动点，联结 $MN$，将 $\triangle BMN$ 沿直线 $MN$ 翻折，点 $B$ 落在点 $B'$ 处，联结 $B'C$，如果 $B'C\parallel AB$，那么 $BN$ 的长是 \fillin。", answer="$6$",
         prompts=[("003.png", [605, 800, 920, 1045])]),
    dict(n=19, typ="problem", pts=10, page="003.png", qbox=[150, 1215, 925, 1390],
         stem=r"计算：$4\sin^2 30^\circ-\dfrac{\tan45^\circ}{\cos30^\circ-\cos60^\circ}$。", answer=r"$-\sqrt3$",
         steps=[r"原式$=4\times\left(\dfrac12\right)^2-\dfrac{1}{\frac{\sqrt3}{2}-\frac12}=1-(\sqrt3+1)=-\sqrt3$。"]),
    dict(n=20, typ="problem", pts=10, page="004.png", qbox=[150, 175, 925, 385],
         stem=r"画二次函数 $y=ax^2+bx$ 的图像时，在“列表”的步骤中，小明列出如下表格（不完整）。请补全表格，并求该二次函数的解析式。",
         answer=r"表中空格均为 $0$；$y=-x^2+4x$。",
         prompts=[("004.png", [355, 275, 720, 345])],
         solutions=[("006.png", [285, 905, 645, 970])],
         steps=[r"补全表格：当 $x=0$、$4$ 时，$y=0$。",
                r"把 $A(-1,-5)$ 和 $B(2,4)$ 代入 $y=ax^2+bx$，得 $\begin{cases}-5=a-b,\\4=4a+2b.\end{cases}$，解得 $\begin{cases}a=-1,\\b=4.\end{cases}$。因此抛物线的表达式为 $y=-x^2+4x$。"]),
    dict(n=21, typ="problem", pts=10, page="004.png", qbox=[150, 390, 925, 765],
         stem=r"如图10①是某款智能磁吸键盘，如图10②是平板吸附在该款设备上的照片，图10③是图10②的示意图。已知 $BC=8\mathrm{cm}$，$CD=20\mathrm{cm}$，$\angle BCD=63^\circ$。当 $AE$ 与 $BC$ 形成的 $\angle ABC$ 为 $116^\circ$ 时，求 $DE$ 的长。（参考数据：$\sin63^\circ\approx0.90$，$\cos63^\circ\approx0.45$，$\cot63^\circ\approx0.50$；$\sin53^\circ\approx0.80$，$\cos53^\circ\approx0.60$，$\cot53^\circ\approx0.75$）",
         answer="$11$ 厘米",
         prompts=[("004.png", [195, 535, 900, 760])],
         steps=[r"过点 $B$ 作 $BG\perp CD$ 于点 $G$。根据题意，$\angle BEC=\angle ABC-\angle BCD=53^\circ$。",
                r"在 $\mathrm{Rt}\triangle BCG$ 中，$CG=BC\cos\angle BCD=8\times\cos63^\circ=3.6\mathrm{cm}$，$BG=BC\sin\angle BCD=8\times\sin63^\circ=7.2\mathrm{cm}$。",
                r"在 $\mathrm{Rt}\triangle BEG$ 中，$GE=BG\cot\angle BEC=7.2\times\cot53^\circ=5.4\mathrm{cm}$。$\therefore DE=CD-CG-GE=20-3.6-5.4=11\mathrm{cm}$。答：$DE$ 的长为 $11$ 厘米。"]),
    dict(n=22, typ="problem", pts=10, page="004.png", qbox=[150, 770, 925, 1260],
         stem=r"已知线段 $a$、$b$ 和 $\angle MON$。如图11②，小明在射线 $OM$ 上顺次截取 $OA=2a$，$AB=3a$，在射线 $ON$ 上顺次截取 $OC=2b$，$CD=3b$。联结 $AC$、$BC$ 和 $BD$，$AC=4$，$BC=6$。（1）求 $BD$ 的长；（2）小明继续作图，如图11③，分别以点 $B$、$D$ 为圆心，以大于 $\dfrac12BD$ 的长为半径作弧，两弧分别相交于点 $P$、$Q$，联结 $PQ$，分别交 $BD$、$OD$ 于点 $E$、$F$。如果 $BC\perp OD$，求 $EF$ 的长。",
         answer=r"（1）$BD=10$；（2）$EF=\dfrac{15}{4}$。",
         prompts=[("004.png", [145, 940, 960, 1225])],
         steps=[r"（1）$\because OA=2a,\ AB=3a,\ OC=2b,\ CD=3b$，$\therefore\dfrac{OA}{AB}=\dfrac{OC}{CD}$，$\therefore AC\parallel BD$。$\therefore\dfrac{OA}{OB}=\dfrac{AC}{BD}=\dfrac25$。$\because AC=4$，$\therefore BD=10$。",
                r"（2）根据题意，$PQ$ 垂直平分 $BD$，$\therefore BE=DE=\dfrac12BD=5$。$\because BC=6$，$\therefore$ 在 $\mathrm{Rt}\triangle BDC$ 中，$\sin\angle BDC=\dfrac{BC}{BD}=\dfrac35$，$\therefore\tan\angle BDC=\dfrac34$。在 $\mathrm{Rt}\triangle DEF$ 中，$EF=DE\tan\angle BDC=\dfrac52\times\dfrac34=\dfrac{15}{4}$。"]),
    dict(n=23, typ="problem", pts=12, page="005.png", qbox=[150, 160, 925, 430],
         stem=r"如图12，在 $\triangle ABC$ 中，已知点 $D$、$E$ 分别在边 $BC$、$AB$ 上，$EC$ 和 $AD$ 相交于点 $F$，$\angle EDB=\angle ADC$，$DE^2=DF\cdot DA$。（1）求证：$\triangle ABD\sim\triangle ECD$；（2）如果 $\angle ACB=90^\circ$，求证：$FC=\dfrac12EC$。",
         answer="证明见解答。",
         prompts=[("005.png", [610, 170, 910, 420])],
         steps=[r"（1）$\because DE^2=DF\cdot DA$，$\therefore\dfrac{DF}{DE}=\dfrac{DE}{DA}$。又 $\angle ADE=\angle EDF$，$\therefore\triangle EDF\sim\triangle ADE$，$\therefore\angle FED=\angle DEA$。$\because\angle EDB=\angle ADC$，$\therefore\angle ADB=\angle EDC$，$\therefore\triangle ABD\sim\triangle ECD$。",
                r"（2）$\because\triangle ABD\sim\triangle ECD$，$\therefore\angle B=\angle ECB$，$BE=CE$。$\because\angle ACB=90^\circ$，$\therefore\angle ACE+\angle ECB=90^\circ$；在 $\mathrm{Rt}\triangle ABC$ 中，$\angle B+\angle BAC=90^\circ$，$\therefore\angle ACE=\angle BAC$，$\therefore EC=EA$，$\therefore EC=BE=\dfrac12AB$。又 $\triangle ABD\sim\triangle ECD$，$\therefore\dfrac{AB}{EC}=\dfrac{BD}{CD}$。$\because\angle B=\angle ECB,\ \angle EDB=\angle FDC$，$\therefore\triangle EDB\sim\triangle FDC$，$\therefore\dfrac{BE}{FC}=\dfrac{BD}{CD}$。又 $EC=BE$，$\therefore FC=\dfrac12EC$。"]),
    dict(n=24, typ="problem", pts=12, page="005.png", qbox=[150, 425, 925, 850],
         stem=r"如图13，在平面直角坐标系 $xOy$ 中，已知抛物线 $y=x^2+2x+m$ 经过点 $A(-3,0)$，与 $y$ 轴交于点 $C$，联结 $AC$ 交该抛物线的对称轴于点 $E$。（1）求 $m$ 的值和点 $E$ 的坐标；（2）点 $M$ 是抛物线的对称轴上一点且在直线 $AC$ 的上方。①联结 $AM$、$CM$，如果 $\angle AME=\angle MCA$，求点 $M$ 的坐标；②点 $N$ 是抛物线上一点，联结 $MN$，当直线 $AC$ 垂直平分 $MN$ 时，求点 $N$ 的坐标。",
         answer=r"（1）$m=-3$，$E(-1,-2)$；（2）①$M(-1,2\sqrt2)$；②$N(-1-\sqrt2,-2)$。",
         prompts=[("005.png", [645, 620, 910, 835])],
         steps=[r"（1）把 $A(-3,0)$ 代入 $y=x^2+2x+m$，$\therefore0=9-6+m$，解得 $m=-3$。可得对称轴为直线 $x=-1$，可求 $l_{AC}:y=-x-3$，$\therefore E(-1,-2)$。",
                r"（2）①$\because\angle AME=\angle MCA$，又 $\angle MAC=\angle EAM$，$\therefore\triangle MAC\sim\triangle EAM$，$\therefore\dfrac{AM}{AE}=\dfrac{AC}{AM}$。可求 $AE=2\sqrt2,\ AC=3\sqrt2$，$\therefore\dfrac{AM}{2\sqrt2}=\dfrac{3\sqrt2}{AM}$，$\therefore AM=2\sqrt3$。设点 $M$ 坐标为 $(-1,t)$，可得 $2^2+t^2=12$，解得 $t=\pm2\sqrt2$（负舍），$\therefore M(-1,2\sqrt2)$。",
                r"②可得点 $A(-3,0)$，点 $C(0,-3)$，$\therefore AO=OC$，$\therefore\angle AOC=90^\circ$，$\therefore\angle OAC=45^\circ$。$\because AC$ 垂直平分 $MN$，$\therefore EM=EN$，可得 $\angle EMN=\angle MNE=45^\circ$，$\therefore NE\perp ME$，即 $N$ 的纵坐标为 $-2$。把 $y=-2$ 代入 $y=x^2+2x-3$，得 $-2=x^2+2x-3$，解得 $x=-1\pm\sqrt2$。$\because M$ 在直线 $AC$ 上方，$\therefore N(-1-\sqrt2,-2)$。"]),
    dict(n=25, typ="problem", pts=14, page="005.png", qbox=[150, 840, 930, 1480],
         stem=r"如图14①，在 $\mathrm{Rt}\triangle ABC$ 中，$\angle ACB=90^\circ$，$\tan\angle ABC=\dfrac43$，点 $D$ 在边 $BC$ 的延长线上，联结 $AD$，点 $E$ 在线段 $AD$ 上，$\angle EBD=\angle DAC$。（1）求证：$\triangle DBA\sim\triangle DEC$；（2）如图14②，点 $F$ 在边 $CA$ 的延长线上，$DF$ 与 $BE$ 的延长线交于点 $M$。①如果 $AC=2AF$，且 $\triangle DEC$ 是以 $DC$ 为腰的等腰三角形，求 $\tan\angle FDC$ 的值；②如果 $DE=\dfrac{\sqrt5}{2}CD$，$EM=3$，$FM:DM=5:3$，求 $AF$ 的长。",
         answer=r"（1）证明见解答；（2）①$\tan\angle FDC=2$ 或 $\dfrac{36}{7}$；②$AF=8\sqrt5$。",
         prompts=[("005.png", [270, 1090, 920, 1455])],
         steps=[r"（1）$\because\angle DAC=\angle EBD,\ \angle ADC=\angle BDE$，$\therefore\triangle DAC\sim\triangle DBE$，$\therefore\dfrac{DC}{DE}=\dfrac{DA}{DB}$，$\therefore\dfrac{DB}{DE}=\dfrac{DA}{DC}$。又 $\angle ADB=\angle CDE$，$\therefore\triangle DBA\sim\triangle DEC$。",
                r"（2）$\because\triangle DBA\sim\triangle DEC$，$\triangle DEC$ 是以 $DC$ 为腰的等腰三角形，$\therefore\triangle DBA$ 是以 $AD$ 为腰的等腰三角形。①若 $AD=AB$，$\because\angle ACB=90^\circ$，$\therefore DC=BC$。根据题意，设 $DC=BC=3k,\ AC=4k$。$\because AC=2AF$，$\therefore AF=2k,\ CF=6k$。在 $\mathrm{Rt}\triangle DCF$ 中，$\tan\angle FDC=\dfrac{FC}{DC}=2$。②若 $AD=BD$，根据题意设 $BC=3k,\ AC=4k$，则 $AB=5k$。过点 $D$ 作 $DH\perp AB$，垂足为点 $H$，$\therefore BH=\dfrac12AB=\dfrac52k$。在 $\mathrm{Rt}\triangle BDH$ 中，$BD=\dfrac{BH}{\cos\angle ABC}=\dfrac{25}{6}k$，$\therefore DC=\dfrac{25}{6}k-3k=\dfrac76k$。$\because AC=2AF$，$\therefore AF=2k,\ CF=6k$。在 $\mathrm{Rt}\triangle DCF$ 中，$\tan\angle FDC=\dfrac{FC}{DC}=\dfrac{36}{7}$。综上所述，$\tan\angle FDC=2$ 或 $\dfrac{36}{7}$。",
                r"（3）$\because\triangle DAC\sim\triangle DBE,\ DE=\dfrac{\sqrt5}{2}CD$，$\therefore\dfrac{DE}{DC}=\dfrac{DB}{DA}=\dfrac{\sqrt5}{2}$。过点 $D$ 作 $DH\perp AB$，垂足为点 $H$，设 $BD=\sqrt5m,\ AD=2m$。在 $\mathrm{Rt}\triangle BDH$ 中，$BH=BD\cos\angle ABC=\dfrac35\sqrt5m$，$DH=BD\sin\angle ABC=\dfrac45\sqrt5m$。在 $\mathrm{Rt}\triangle ADH$ 中，$AH=\sqrt{AD^2-DH^2}=\dfrac25\sqrt5m$，$\therefore AB=AH+BH=\sqrt5m$。在 $\mathrm{Rt}\triangle ABC$ 中，$BC=AB\cos\angle ABC=\dfrac35\sqrt5m$，$\therefore DC=\dfrac25\sqrt5m$，$\sin\angle DAC=\dfrac{\sqrt5}{5}$。过点 $F$ 作 $FG\parallel ME$ 交 $DA$ 的延长线于点 $G$，$\therefore\dfrac{ME}{FG}=\dfrac{DM}{DF}=\dfrac38$。$\because ME=3$，$\therefore FG=8$。$\because\angle FAG=\angle DAC$，$\therefore\sin\angle FAG=\sin\angle DAC$。在 $\mathrm{Rt}\triangle AFG$ 中，$AF=\dfrac{FG}{\sin\angle DAC}=8\sqrt5$。"]),
]


def sol_crop(it):
    n = it["n"]
    if n <= 6:
        return [("006.png", [150, 465, 850, 540])]
    if n <= 10:
        return [("006.png", [150, 550, 880, 625])]
    if n <= 14:
        return [("006.png", [150, 620, 880, 690])]
    if n <= 18:
        return [("006.png", [150, 680, 880, 745])]
    if n == 19:
        return [("006.png", [150, 740, 900, 905])]
    if n == 20:
        return [("006.png", [150, 895, 900, 1145])]
    if n == 21:
        return [("006.png", [150, 1135, 900, 1360])]
    if n == 22:
        return [("007.png", [150, 115, 900, 480])]
    if n == 23:
        return [("007.png", [150, 470, 900, 875])]
    if n == 24:
        return [("007.png", [150, 865, 900, 1527]), ("008.png", [150, 115, 900, 290])]
    return [("008.png", [150, 280, 900, 1435])]


sections = [
    {"id": "choice", "title": "一、选择题", "item_ids": [f"Q{i:03d}" for i in range(1, 7)]},
    {"id": "fillin", "title": "二、填空题", "item_ids": [f"Q{i:03d}" for i in range(7, 19)]},
    {"id": "problem", "title": "三、解答题", "item_ids": [f"Q{i:03d}" for i in range(19, 26)]},
]
dump(ROOT / "paper.yaml", {
    "schema": "math_exam_paper/v1",
    "paper": {"id": PAPER, "title": "虹口区2023学年度第一学期期终学生学习能力诊断测试初三数学试卷", "grade": "九年级", "subject": "数学", "source_archive": SRC},
    "question_bank": "../../question-bank.yaml",
    "sections": sections,
})

map_items = []
for it in items:
    iid = f"Q{it['n']:03d}"
    pages = [f"{SRC}/{p}" for p, _ in sol_crop(it)]
    if it["n"] <= 18:
        start = f"{it['n']}."
        end = f"{it['n'] + 1}." if it["n"] < 18 else "三、解答题"
    else:
        start = f"{it['n']}. 解："
        end = f"{it['n'] + 1}. 解：" if it["n"] < 25 else "<END_OF_SOURCE>"
    map_items.append({
        "item_id": iid,
        "question_number": it["n"],
        "question_pages": [f"{SRC}/{it['page']}"],
        "official_solution": {"pages": list(dict.fromkeys(pages)), "start_anchor": start, "end_anchor": end},
    })
dump(ROOT / "paper-map.yaml", {"schema": "math_exam_paper_map/v1", "paper_id": PAPER, "items": map_items})

for it in items:
    iid = f"Q{it['n']:03d}"
    idir = ROOT / "items" / iid
    role_crops = {"question_evidence": [], "prompt": [], "solution": [], "official_solution": []}

    def add(role, source, box, idx):
        suffix = "" if role == "question_evidence" else f"-{idx:02d}"
        base = "source-question" if role == "question_evidence" else role.replace("_", "-")
        role_crops[role].append({
            "source": f"{SRC}/{source}", "source_sha256": ZERO, "box_px": box, "whiteout_px": [],
            "output": f"assets/{base}{suffix}.png", "output_sha256": ZERO,
        })

    add("question_evidence", it["page"], it["qbox"], 1)
    for idx, (p, box) in enumerate(it.get("prompts", []), 1):
        add("prompt", p, box, idx)
    for idx, (p, box) in enumerate(it.get("solutions", []), 1):
        add("solution", p, box, idx)
    for idx, (p, box) in enumerate(sol_crop(it), 1):
        add("official_solution", p, box, idx)

    section_title = "一、选择题" if it["n"] <= 6 else ("二、填空题" if it["n"] <= 18 else "三、解答题")
    source = {
        "schema": "math_exam_item_source/v1", "item_id": iid, "source_key": f"{PAPER}-Q{it['n']:02d}",
        "paper_id": PAPER, "question_number": it["n"], "question_type": it["typ"], "points": it["pts"],
        "section_title": section_title, "source_directory": SRC, "crops": role_crops,
        "transcription": {"question_status": "author_pass", "official_solution_status": "author_pass",
                          "independent_review": "review_pass", "human_review": "pending",
                          "prompt_status": "author_pass", "prompt_review_notes": []},
        "content_hash": ZERO,
    }
    dump(idir / "source.yaml", source)

    block = {"type": it["typ"], "id": iid, "points": it["pts"], "stem_latex": it["stem"], "answer": it["answer"]}
    if it["typ"] == "choice":
        block["choices"] = it["choices"]
        block["clue"] = f"答案：{it['answer']}。"
    elif it["typ"] == "fillin":
        block["clue"] = f"答案：{it['answer']}。"
    else:
        block["solution_steps"] = [{"title": f"步骤 {idx}", "content": text} for idx, text in enumerate(it["steps"], 1)]
        if it.get("solutions"):
            block["solution_steps"][0]["diagram_col"] = {
                "image_path": "assets/solution-01.png", "width": "58mm",
                "variant": "solution", "disclosure_policy": "teacher_only",
            }
    if it.get("prompts"):
        block["diagram_col"] = {
            "image_path": "assets/prompt-01.png", "width": "0.92\\linewidth",
            "variant": "prompt", "disclosure_policy": "clean",
        }
    block["source_solution_images"] = [
        {"image_path": crop["output"], "width": "0.96\\linewidth", "variant": "source_solution",
         "disclosure_policy": "teacher_only", "label": f"官方原解答第{idx}页"}
        for idx, crop in enumerate(role_crops["official_solution"], 1)
    ]
    assignment = {
        "meta": {"title": f"虹口区2023学年度第一学期期终初三数学第{it['n']}题", "grade": "九年级",
                 "subject": "数学", "total_points": it["pts"], "version": "teacher", "show_answers": True,
                 "source_artifacts": {"source_record": "source.yaml"}},
        "render": {"template": "exam-zh-practice", "paper_size": "a4paper", "answer_key_position": "inline"},
        "sections": [{"id": "question", "title": section_title, "type": "practice", "visibility": "both", "blocks": [block]}],
    }
    dump(idir / "teacher.resolved.assignment.yaml", assignment)
