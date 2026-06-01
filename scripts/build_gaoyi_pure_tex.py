#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "documents" / "高一" / "topic-archives-pure"
FIGURES_DIR = OUT_DIR / "figures"


FIGURE_CROPS = {
    "vector-kite.png": ("documents/高一/03-AeUS7-mBPoWmDxFx/002.png", (690, 740, 925, 930)),
    "trig-race.png": ("documents/高一/01-yziAF5kAbRtk3MMO/004.png", (660, 920, 925, 1155)),
    "vector-triangle-d.png": ("documents/高一/07-lXolUr-1bu6QRhI1/002.png", (205, 950, 390, 1095)),
    "solid-water-dam.png": ("documents/高一/07-lXolUr-1bu6QRhI1/002.png", (400, 900, 650, 1090)),
    "solid-parallelepiped.png": ("documents/高一/07-lXolUr-1bu6QRhI1/002.png", (650, 915, 925, 1105)),
    "solid-mouhefanggai.png": ("documents/高一/07-lXolUr-1bu6QRhI1/003.png", (705, 345, 925, 610)),
    "solid-cube-e.png": ("documents/高一/07-lXolUr-1bu6QRhI1/003.png", (650, 1060, 930, 1285)),
    "solid-cube-lines.png": ("documents/高一/07-lXolUr-1bu6QRhI1/004.png", (655, 225, 930, 455)),
    "solid-rect-bce.png": ("documents/高一/07-lXolUr-1bu6QRhI1/005.png", (645, 175, 930, 375)),
}


PROBLEMS: dict[str, list[str]] = {
    "复数": [
        r"若复数 $z$ 满足 $(1+i)z=i$，则 $z=$\blank.",
        r"若复数 $z$ 满足 $|z|=|z-2-4i|$，则 $|z|+|z+1|$ 的最小值是\blank.",
        r"""若复数 $z_1=a+bi,\ z_2=c+di\ (a,b,c,d\in\mathbb R)$ 在复平面上所对应的向量分别是 $\overrightarrow{OZ_1},\overrightarrow{OZ_2}$，则 $|z_1z_2|$ 与 $\bigl|\overrightarrow{OZ_1}\cdot\overrightarrow{OZ_2}\bigr|$ 的大小关系是（\quad）\\
\longchoices{$|z_1z_2|\le \bigl|\overrightarrow{OZ_1}\cdot\overrightarrow{OZ_2}\bigr|$}{$|z_1z_2|= \bigl|\overrightarrow{OZ_1}\cdot\overrightarrow{OZ_2}\bigr|$}{$|z_1z_2|\ge \bigl|\overrightarrow{OZ_1}\cdot\overrightarrow{OZ_2}\bigr|$}{无法判定}""",
        r"""已知关于 $x$ 的方程 $x^2+2\sqrt3x+m=0\ (m\in\mathbb R)$ 有两个复数根 $x_1,x_2$.\\
(1) 若 $\operatorname{Im}x_1<\operatorname{Im}x_2<1$，求 $m$ 的取值范围；\\
(2) 若 $\dfrac1{|x_1|}+\dfrac1{|x_2|}=1$，求 $m$ 的值.""",
        r"已知虚数 $z$，其实部为 $1$，且 $z+\dfrac2z=m\ (m\in\mathbb R)$，则实数 $m=$\blank.",
        r"""在复平面内，复数 $z=i(1-i)$ 的共轭复数 $\bar z$ 对应的点位于（\quad）\\
\fourchoices{第一象限}{第二象限}{第三象限}{第四象限}""",
        r"""已知复数 $z=1+bi\ (b\in\mathbb R,\ i$ 为虚数单位)，$z$ 在复平面上对应的点在第四象限，且满足 $z^2=4\bar z$.\\
(1) 求实数 $b$ 的值；\\
(2) 若复数 $z$ 是关于 $x$ 的方程 $px^2+2x+q=0\ (p\ne0,\ p,q\in\mathbb R)$ 的一个复数根，求 $p+q$ 的值.""",
        r"若复数 $z$ 满足 $zi=2+i$，$i$ 为虚数单位，则 $z$ 的实部为\blank.",
        r"已知 $i$ 为虚数单位，则 $i+i^2+i^3+i^4+\cdots+i^{2026}=$\blank.",
        r"""$i$ 是虚数单位，复数 $1+2i$ 在复平面内对应的点位于（\quad）\\
\fourchoices{第一象限}{第二象限}{第三象限}{第四象限}""",
        r"""已知复数 $z=\dfrac2{1-i}$，$i$ 为虚数单位.\\
(1) 求 $|z|$；\\
(2) 若复数 $z$ 是关于 $x$ 的方程 $x^2+mx+n=0$ 的一个根，求实数 $m,n$ 的值.""",
        r"若复数 $z=\dfrac{i+1}{i}$（$i$ 为虚数单位），则 $\bar z=$\blank.",
        r"设复数 $z$ 满足 $|z-1|=1$，则 $|z+2-i|$ 的最大值为\blank.",
        r"""已知常数 $a,b\in\mathbb R$，关于 $x$ 的方程 $x^2+ax+b=0$ 在复数集中有两个虚根.\\
(1) 若 $b=1$，求 $a$ 的取值范围；\\
(2) 若其中一个虚根为 $1+i$（$i$ 为虚数单位），求 $a,b$ 的值.""",
        r"若复数 $z$ 满足 $(1+i)z=2$，则 $z$ 的虚部为\blank.",
        r"已知方程 $3x^2-6(m-1)x+m^2+1=0$ 的两个虚根为 $\alpha,\beta$，且 $|\alpha|+|\beta|=2$，则实数 $m=$\blank.",
        r"""下列说法错误的是（\quad）\\
\fourchoices{已知复数 $z_1,z_2$，若 $z_1=\bar z_2$，则 $\bar z_1=z_2$}{已知复数 $z_1,z_2$，若 $|z_1|=|z_2|$，则 $z_1^2=z_2^2$}{若 $|\vec a\cdot\vec b|=|\vec a|\,|\vec b|$，则 $\vec a$ 与 $\vec b$ 共线}{若 $|\vec a|=|\vec b|$，则 $\vec a^{\,2}=\vec b^{\,2}$}""",
        r"""已知复数 $z=1+mi\ (i$ 是虚数单位，$m\in\mathbb R)$，且 $\bar z\,(3+i)$ 为纯虚数.\\
(1) 求实数 $m$；\\
(2) 设复数 $z_1=\dfrac{a-i^{2027}}{z}$，且复数 $z_1$ 对应的点在第二象限，求实数 $a$ 的取值.""",
        r"已知 $i$ 是虚数单位，复数 $z$ 满足 $z(1+\sqrt3\,i)=1$，则 $|z|=$\blank.",
        r"已知 $i$ 是虚数单位，若 $z\in\mathbb C$，且 $|z-2-2i|=3$，则 $|z|$ 的取值范围为\blank.",
    ],
    "平面向量": [
        r"若 $\vec a=(2,1),\ \vec b=(3,4)$，则 $\vec a$ 在 $\vec b$ 方向上的投影是\blank.",
        r"在 $\triangle ABC$ 中，$AC=7,\ BC=4$，点 $D$ 满足 $\overrightarrow{AD}=2\overrightarrow{DB}$，$CD=\sqrt{19}$，则 $BD=$\blank.",
        r"若复数 $z_1=a+bi,\ z_2=c+di$ 在复平面上所对应的向量分别是 $\overrightarrow{OZ_1},\overrightarrow{OZ_2}$，比较 $|z_1z_2|$ 与 $\left|\overrightarrow{OZ_1}\cdot\overrightarrow{OZ_2}\right|$ 的大小.",
        r"""已知平面上的两个向量 $\vec a=(\cos\alpha,\sin\alpha)\ (0\le\alpha<2\pi),\ \vec b=(1,\sqrt3)$.\\
(1) 若 $\vec a$ 与 $\vec b$ 平行，求 $\tan\alpha$ 的值；\\
(2) 若 $\vec a+\vec b$ 与 $5\vec a-2\vec b$ 垂直，求 $\alpha$ 的值.""",
        r"已知向量 $\vec a=(1,\sqrt3),\ \vec b=(a,b)$，其中 $a>0,\ b>0$，求 $\dfrac{\vec a\cdot\vec b}{|\vec b|}$ 的取值范围.",
        r"设单位向量 $\vec a,\vec b$ 的夹角为锐角，若对于任意满足 $|x\vec a+y\vec b|=1,\ xy\ge0$ 的实数对 $(x,y)$，都有 $|3x+y|\le\dfrac{2\sqrt{21}}3$ 成立，则 $\vec a\cdot\vec b$ 的最小值为\blank.",
        r"""已知平面向量 $\vec a=(1,x),\ \vec b=(2x+3,-x)$，$x\in\mathbb R$.\\
(1) 若 $\vec a\perp \vec b$，求 $x$ 的值；\\
(2) 若 $\vec a\parallel\vec b$，求 $|2\vec a-\vec b|$ 的值.""",
        r"已知向量 $\vec a=(1,3),\ \vec b=(m,-1)$，若 $\vec a\perp\vec b$，则 $m=$\blank.",
        r"已知向量 $\vec a=(1,-\sqrt3),\ \vec b=(2,0)$，则 $\vec a$ 在 $\vec b$ 方向上的数量投影为\blank.",
        r"由一个正方形 $ABCD$ 与正三角形 $BDE$（点 $E$ 在 $BD$ 下方）组成一个“风筝骨架”，$O$ 为正方形 $ABCD$ 的中心，点 $P$ 是“风筝骨架”上一点，设 $\overrightarrow{OP}=m\overrightarrow{OA}+n\overrightarrow{OB}\ (m,n\in\mathbb R)$，则 $m+n$ 的最大值是\blank.\diagram{figures/vector-kite.png}{0.28\linewidth}",
        r"""已知 $\vec a,\vec b$ 为单位向量，且 $\vec a$ 与 $\vec b$ 的夹角为 $60^\circ$.\\
(1) 求 $|\vec a-2\vec b|$；\\
(2) 若向量 $2\vec a-\lambda\vec b$ 与 $\lambda\vec a-\vec b$ 的夹角为锐角，求实数 $\lambda$ 的取值范围.""",
        r"已知坐标平面上的三点 $A(2,1),\ B(-3,-2),\ C(3,1)$，则 $\overrightarrow{AB}$ 在 $\overrightarrow{AC}$ 方向上的数量投影为\blank.",
        r"在同一平面上，已知两圆 $\omega_1,\omega_2$ 的圆心均为 $O$，半径分别为 $1,2$，常数 $\lambda\in\mathbb R$. 若在圆 $\omega_1$ 上的点 $A$ 以及在圆 $\omega_2$ 上的点 $B$，对该平面上的任意一个单位向量 $\vec e$，恒有 $\left|\overrightarrow{OA}\cdot\vec e\right|+\left|\overrightarrow{OB}\cdot\vec e\right|\le\lambda$，则 $\lambda$ 的最小值为\blank.",
        r"已知平面向量 $\vec a=(1,3),\ \vec b=(1,-2)$，则 $\vec a$ 在 $\vec b$ 方向上的投影向量为\blank.",
        r"""已知单位向量 $\vec a,\vec b$ 满足 $\sqrt3\,|k\vec a+\vec b|=|\vec a-k\vec b|,\ k>0$.\\
(1) 将 $\vec a\cdot\vec b$ 表示为关于 $k$ 的函数；\\
(2) 求函数 $y=f(k)$ 的最大值及取得最大值时 $\vec a$ 与 $\vec b$ 的夹角.""",
        r"在 $\triangle ABC$ 中，点 $D$ 是线段 $BC$ 上的动点，且 $\overrightarrow{AD}=x\overrightarrow{AB}+y\overrightarrow{AC}$，求 $\dfrac1x+\dfrac1y$ 的最小值.\diagram{figures/vector-triangle-d.png}{0.24\linewidth}",
        r"""已知向量 $\vec a=(\sin x,\sqrt3),\ \vec b=(\cos x,1)$.\\
(1) 若 $\vec a\parallel\vec b$，求 $\dfrac{\sin x+\sqrt3\cos x}{\sqrt3\sin x-\cos x}$ 的值；\\
(2) 设 $f(x)=\left(\vec a-\sqrt3\vec b\right)^2,\ x\in\left[0,\dfrac\pi2\right]$，若关于 $x$ 的不等式 $f(x)\ge m^2-1$ 有解，求实数 $m$ 的取值范围.""",
    ],
    "三角函数": [
        r"函数 $y=\tan x$ 的最小正周期是\blank.",
        r"函数 $y=\sin x$ 的单调增区间是\blank.",
        r"""直线 $2x+y+3=0$ 的倾斜角等于（\quad）\\
\fourchoices{$\arctan2$}{$\arctan(-2)$}{$\pi+\arctan(-2)$}{$\pi-\arctan(-2)$}""",
        r"""已知 $\vec a=(\cos\alpha,\sin\alpha),\ \vec b=(1,\sqrt3)$.\\
(1) 若 $\vec a\parallel\vec b$，求 $\tan\alpha$；\\
(2) 若 $\vec a+\vec b\perp5\vec a-2\vec b$，求 $\alpha$.""",
        r"""某赛道的前一部分为函数 $y=A\sin\omega x\ (A>0,\omega>0),\ x\in[0,4]$ 的图像，最高点为 $S(3,2\sqrt3)$；后一部分为折线段 $MNP$，其中 $P(8,0)$，且 $\angle MNP=120^\circ$.\diagram{figures/trig-race.png}{0.34\linewidth}
(1) 求 $A,\omega$ 的值和 $M,P$ 两点间的距离；\\
(2) 设 $\angle PMN=\theta$，当 $\theta$ 为何值时，折线段赛道 $MNP$ 最长？""",
        r"已知扇形的弧长为 $8$，半径为 $4$，则扇形的面积为\blank.",
        r"已知 $\cos\alpha=-\dfrac8{17}$，且 $\alpha$ 在第二象限，则 $\tan\alpha=$\blank.",
        r"已知角 $\alpha$ 的终边经过点 $P(-4m,3m)\ (m<0)$，则 $2\sin\alpha+\cos\alpha$ 的值是\blank.",
        r"在锐角 $\triangle ABC$ 中，内角 $A,B,C$ 的对边分别为 $a,b,c$，若 $\sqrt2 b\cos A=a\cos C+c\cos A$，求相关边角关系；并在给定条件下求向量表达式的最值.",
        r"已知扇形的弧长和半径都是 $4$，则扇形的面积为\blank.",
        r"已知 $\sin\alpha+\cos\alpha=\dfrac13$，则 $\sin2\alpha=$\blank.",
        r"""已知向量 $\vec a=(1,0),\ \vec b=(\cos\theta,\sin\theta)$，$\theta\in\left[-\dfrac\pi2,\dfrac\pi2\right]$，则 $|\vec a+\vec b|$ 的取值范围是（\quad）\\
\fourchoices{$\left[0,\sqrt2\right]$}{$\left(1,\sqrt2\right]$}{$[1,2]$}{$\left[\sqrt2,2\right]$}""",
        r"函数 $y=\sin2x$ 的最小正周期是\blank.",
        r"已知常数 $\varphi\in\mathbb R$，函数 $f(x)=\sin x+\sqrt3\cos(x+\varphi)$ 为偶函数，则 $\cos2\varphi=$\blank.",
        r"""在 $\triangle ABC$ 中，$\cos A=\dfrac45,\ AC=1$.\\
(1) 若 $AB=2$，求 $BC$ 的长；\\
(2) 若 $\sin C=\dfrac5{13}$，求 $\triangle ABC$ 的面积.""",
        r"对于函数 $y=f(x)$，若数列 $\{a_n\}$ 使得 $\{f(a_n)\}$ 是公比为 $q$ 的等比数列，则称 $\{a_n\}$ 是函数 $f(x)$ 的“关联数列”，$q$ 为“关联常数”. 研究函数 $y=\sin x$ 的关联数列.",
        r"已知 $\alpha$ 是第四象限的角，则点 $P(\tan\alpha,\cos\alpha)$ 在第\blank 象限.",
        r"已知 $\sin\left(\theta+\dfrac\pi6\right)=2\cos\theta$，则 $\tan2\theta=$\blank.",
        r"已知函数 $f(x)=\sin(2x+\varphi)$ 的图像关于原点中心对称，则实数 $\varphi$ 的取值可能是（\quad）",
        r"设函数 $f(x)=m\cos(x+\alpha)+n\cos(x+\beta)$，其中 $m,n,\alpha,\beta$ 为已知实常数，$x\in\mathbb R$，判断相关恒等命题的真假.",
        r"""已知 $\tan\alpha\tan\beta=\tan(\alpha+\beta)$，判断下列象限组合是否可能：\\
（1）$\alpha$ 在第一象限，$\beta$ 在第三象限；（2）$\alpha$ 在第二象限，$\beta$ 在第四象限；（3）$\alpha$ 在第一象限，$\beta$ 在第四象限.""",
        r"""已知函数 $f(x)=\sin kx\cdot\sin^k x+\cos kx\cdot\cos^k x-\cos^k 2x$，其中 $k\in\mathbb N^*$.\\
(1) 当 $k=1$ 时，求方程 $f(x)=1-\dfrac{\sqrt3}{2}$ 的解集；\\
(2) 若 $f(x)$ 是偶函数，当 $k$ 取最小值时，求函数 $g(x)=\dfrac{f(x)}{\tan x}+\sin x+\cos x$ 的取值范围；\\
(3) 若 $f(x)$ 是常数函数，求 $k$ 的值.""",
        r"已知 $f(x)=\sin\left(\omega x+\dfrac\pi4\right)\ (\omega>0)$，如果存在实数 $m$，使得对任意实数 $x$，都有 $f(m)\le f(x)\le f(m+1)$ 成立，则 $\omega$ 的最小值为\blank.",
        r"""已知向量 $\vec a=(\sin x,\sqrt3),\ \vec b=(\cos x,1)$.\\
(1) 若 $\vec a\parallel\vec b$，求 $\dfrac{\sin x+\sqrt3\cos x}{\sqrt3\sin x-\cos x}$ 的值；\\
(2) 设 $f(x)=\left(\vec a-\sqrt3\vec b\right)^2,\ x\in\left[0,\dfrac\pi2\right]$，若关于 $x$ 的不等式 $f(x)\ge m^2-1$ 有解，求实数 $m$ 的取值范围.""",
        r"用一个与圆柱底面不平行的平面去截圆柱可得到一个斜截面. 沿母线剪开并展开后，截口曲线可近似表示为正弦或余弦函数图像. 设圆柱底面半径为 $r$，斜截面与底面所成二面角为 $\theta$，研究展开后曲线的函数模型.",
    ],
    "立体几何": [
        r"一个圆锥的表面积为 $\pi$，母线长为 $\dfrac56$，则其底面半径为\blank.",
        r"已知正三棱锥底面的边长为 $6$，高为 $3$，求该正三棱锥的侧面积.",
        r"如图，甲站在水库底面上的点 $D$ 处，乙站在水坝斜面上的点 $C$ 处. 已知水库底面与水坝斜面所成的二面角为 $150^\circ$，从 $D,C$ 两点到交线的距离分别为 $DA=20\sqrt3\,\mathrm m,\ CB=40\,\mathrm m$，且 $AB=20\,\mathrm m$，求甲乙两人的距离.\diagram{figures/solid-water-dam.png}{0.30\linewidth}",
        r"已知平行六面体 $ABCD-A_1B_1C_1D_1$ 的体积为 $4$，若将其截去三棱锥 $B_1-BD_1C_1$，求剩余几何体的体积.\diagram{figures/solid-parallelepiped.png}{0.34\linewidth}",
        r"如图，正方体 $ABCD-A_1B_1C_1D_1$ 中，四分之一圆柱 $BB_1C_1-AA_1D_1$ 与四分之一圆柱 $AA_1B_1-DD_1C_1$ 的公共部分是八分之一“牟合方盖”. 已知正方体棱长为 $2$，利用祖暅原理求该八分之一“牟合方盖”的体积.\diagram{figures/solid-mouhefanggai.png}{0.28\linewidth}",
        r"""如图，在正方体 $ABCD-A_1B_1C_1D_1$ 中，$E$ 为 $AB$ 的中点，对于下列两个命题：\circnum{1}平面 $BCC_1B_1$ 上存在一条直线，与平面 $A_1C_1E$ 平行；\circnum{2}平面 $BCC_1B_1$ 上存在一条直线，与平面 $A_1C_1E$ 垂直. 则（\quad）\\
\fourchoices{\circnum{1}对，\circnum{2}对}{\circnum{1}对，\circnum{2}错}{\circnum{1}错，\circnum{2}对}{\circnum{1}错，\circnum{2}错}
\diagram{figures/solid-cube-e.png}{0.32\linewidth}""",
        r"""正方体 $ABCD-A'B'C'D'$ 中，直线 $a\subset$ 平面 $ABCD$，直线 $b\subset$ 平面 $DAB'C'$，记该正方体的 $12$ 条棱所在的直线构成的集合为 $\Omega$. 给出下列四个命题：\\
\circnum{1}$\Omega$ 中可能恰有 $2$ 条直线与 $a$ 异面；\quad
\circnum{2}$\Omega$ 中可能恰有 $4$ 条直线与 $a$ 异面；\\
\circnum{3}$\Omega$ 中可能恰有 $8$ 条直线与 $b$ 异面；\quad
\circnum{4}$\Omega$ 中可能恰有 $10$ 条直线与 $b$ 异面.\\
其中，正确命题的个数为（\quad）\\
\fourchoices{$1$}{$2$}{$3$}{$4$}
\diagram{figures/solid-cube-lines.png}{0.30\linewidth}""",
        r"""四边形 $ABCD$ 是矩形，$AD=2,\ DC=1,\ AB\perp$ 平面 $BCE$，$BE=\sqrt3,\ EC=1$，点 $F$ 为线段 $BE$ 的中点.\diagram{figures/solid-rect-bce.png}{0.34\linewidth}
(1) 求证：$EC\perp$ 平面 $ABE$；\\
(2) 求异面直线 $AF$ 与 $DE$ 所成角的大小.""",
        r"用一个与圆柱底面不平行的平面去截圆柱得到斜截面. 设圆柱底面半径为 $r$，斜截面与底面所成二面角为 $\theta$，研究截口曲线展开后的形状，并建立函数模型.",
        r"""如图，圆台 $O_1O$ 的一个轴截面为等腰梯形 $A_1ACC_1$，$AC=2A_1A=2CC_1=4$，$B$ 为底面圆周上异于 $A,C$ 的点.\\
(1) 求该圆台的侧面积 $S$；\\
(2) 若 $P$ 是线段 $BC$ 的中点，求证：$C_1P\parallel$ 平面 $A_1AB$；\\
(3) 若 $AB=BC$，求相关线面角正弦值的最大值.""",
    ],
}

DROP_MARKERS = [
    "求相关边角关系",
    "关联数列",
    "取值可能是",
    "判断相关恒等命题",
    "研究展开后曲线",
    "研究截口曲线",
    "相关线面角",
]


def tex_document(topic: str, problems: list[str]) -> str:
    body = "\n\n".join(rf"\item {problem}" for problem in problems)
    return rf"""\documentclass[UTF8,11pt]{{ctexart}}
\usepackage[a4paper,top=1.8cm,bottom=1.8cm,left=1.7cm,right=1.7cm]{{geometry}}
\usepackage{{amsmath,amssymb}}
\usepackage{{enumitem}}
\usepackage{{multicol}}
\usepackage{{graphicx}}
\setlength{{\parindent}}{{0pt}}
\setlist[enumerate]{{leftmargin=2.2em,itemsep=0.85em,topsep=0.5em}}
\newcommand{{\blank}}{{\underline{{\hspace{{2.8cm}}}}}}
\newcommand{{\diagram}}[2]{{\begin{{center}}\includegraphics[width=#2]{{#1}}\end{{center}}}}
\newcommand{{\circnum}}[1]{{\textcircled{{\scriptsize #1}}}}
\newcommand{{\fourchoices}}[4]{{%
  \begin{{multicols}}{{4}}
  \begin{{enumerate}}[label=\Alph*.,leftmargin=1.6em,itemsep=0pt,topsep=0pt]
  \item #1
  \item #2
  \item #3
  \item #4
  \end{{enumerate}}
  \end{{multicols}}
}}
\newcommand{{\longchoices}}[4]{{%
  \begin{{enumerate}}[label=\Alph*.,leftmargin=2em,itemsep=0.15em,topsep=0.2em]
  \item #1
  \item #2
  \item #3
  \item #4
  \end{{enumerate}}
}}
\pagestyle{{plain}}
\begin{{document}}
\begin{{center}}
{{\LARGE \bfseries 高一数学专题练习：{topic}}}\\[0.4em]
{{\small 题目由原始试卷整理为纯 \TeX{{}} 版，供课堂讲义和学生练习使用。}}
\end{{center}}
\vspace{{0.5em}}
\begin{{enumerate}}
{body}
\end{{enumerate}}
\end{{document}}
"""


def crop_figures() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, (source, box) in FIGURE_CROPS.items():
        image = Image.open(ROOT / source)
        image.crop(box).save(FIGURES_DIR / name)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    crop_figures()
    for topic, problems in PROBLEMS.items():
        problems = [p for p in problems if not any(marker in p for marker in DROP_MARKERS)]
        tex_path = OUT_DIR / f"{topic}.tex"
        tex_path.write_text(tex_document(topic, problems), encoding="utf-8")
        subprocess.run(
            ["tectonic", "--keep-logs", tex_path.name],
            cwd=OUT_DIR,
            text=True,
            check=True,
        )
        for suffix in [".aux", ".log", ".out"]:
            extra = OUT_DIR / f"{topic}{suffix}"
            if extra.exists():
                extra.unlink()
        print(f"{topic}: {len(problems)} problems -> {tex_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
