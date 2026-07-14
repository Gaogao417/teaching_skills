# 审核稿｜根据两条已知比选择辅助线：练习提案

> 审核状态：`draft`
> 三题分别使用不同的“比例线三角形”和不同辅助线；批准后才生成学生/教师 YAML。

## 共同原始构型

在 \(\triangle ABC\) 中，点 \(D\) 在线段 \(BC\) 上，点 \(E\) 在线段 \(AC\) 上，线段 \(AD\) 与 \(BE\) 相交于点 \(P\)。每题从

\[
AE:EC,\quad AP:PD,\quad BP:PE,\quad BD:DC
\]

中给出两个比，求另一个比。

学生首先填写：两条已知比例线、所求比例线、三条线围成的三角形、应过哪个顶点作哪条边的平行线。随后题目给出完成辅助线后的第二张图，学生从图中找两组相似并计算。

---

## 第 1 题｜围 \(\triangle AEP\)，求 \(BP:PE\)

### 学生题干

已知

\[
AE:EC=1:2,\qquad AP:PD=3:4,
\]

求 \(BP:PE\)。

（1）指出三条比例线围成的三角形。
（2）补全辅助线：过点 ____ 作 ____ \(\parallel\) ____，交直线 ____ 于点 \(F\)。
（3）写出图中的两组相似三角形，并求 \(BP:PE\)。

### 正确构造

三个比位于 \(AC,AD,BE\) 上，围成 \(\triangle AEP\)。过 \(A\) 作

\[
AF\parallel EP,
\]

交直线 \(BC\) 于 \(F\)。

两组相似为

\[
\triangle ACF\sim\triangle ECB,qquad
\triangle ADF\sim\triangle PDB.
\]

### 标准答案

\[
\boxed{BP:PE=6:1}
\]

### 教师验算

设 \(x=AE/EC=1/2\)，\(y=AP/PD=3/4\)。则

\[
\frac{BP}{PE}=\frac{1+x}{y-x}
=\frac{3/2}{1/4}=6.
\]

### 图槽审核卡 Q1

- **第一张图：** 只有原始构型，强调 \(AC,AD,BE\) 三条比例线和 \(\triangle AEP\)。
- **第二张图：** \(AF\parallel EP\)，且 \(F=AF\cap BC\)；不能把 \(F\) 放在任意边上。
- **必须支持：** \(A,C,E\) 共线；\(A,D,P\) 共线；\(B,E,P\) 共线；\(B,D,C,F\) 共线。
- **解答图：** 分两步突出 \(ACF/ECB\) 与 \(ADF/PDB\)。

---

## 第 2 题｜围 \(\triangle ECB\)，求 \(AE:EC\)

### 学生题干

已知

\[
BP:PE=3:1,\qquad BD:DC=2:1,
\]

求 \(AE:EC\)。

（1）指出三条比例线围成的三角形。
（2）补全辅助线，并写出它与哪条直线相交。
（3）写出两组相似三角形并求解。

### 正确构造

三个比位于 \(BE,BC,AC\) 上，围成 \(\triangle ECB\)。过 \(E\) 作

\[
EF\parallel CB,
\]

交直线 \(AD\) 于 \(F\)。

两组相似为

\[
\triangle AEF\sim\triangle ACD,qquad
\triangle PEF\sim\triangle PBD.
\]

### 标准答案

\[
\boxed{AE:EC=2:1}
\]

### 教师验算

设 \(z=BP/PE=3\)，\(w=BD/DC=2\)。由

\[
w=\frac{xz}{x+1}
\]

得

\[
x=\frac{w}{z-w}=\frac2{3-2}=2.
\]

### 图槽审核卡 Q2

- **第一张图：** 强调 \(BE,BC,AC\) 围成的 \(\triangle ECB\)。
- **第二张图：** \(EF\parallel CB\)，且 \(F=EF\cap AD\)。
- **必须支持：** \(A,F,P,D\) 共线；不得让 \(F\) 悬空或落到 \(BE\) 上。
- **解答图：** 分别突出 \(AEF/ACD\) 与 \(PEF/PBD\)。

---

## 第 3 题｜围 \(\triangle PDB\)，求 \(BD:DC\)

### 学生题干

已知

\[
AP:PD=2:1,\qquad BP:PE=3:1,
\]

求 \(BD:DC\)。

（1）指出三条比例线围成的三角形。
（2）说明应过哪个顶点作哪条边的平行线。
（3）写出两组相似三角形并求解。

### 正确构造

三个比位于 \(AD,BE,BC\) 上，围成 \(\triangle PDB\)。过 \(P\) 作

\[
PF\parallel DB,
\]

交直线 \(AC\) 于 \(F\)。

两组相似为

\[
\triangle APF\sim\triangle ADC,qquad
\triangle EPF\sim\triangle EBC.
\]

### 标准答案

\[
\boxed{BD:DC=5:3}
\]

### 教师验算

设 \(y=AP/PD=2\)，\(z=BP/PE=3\)。则

\[
\frac{BD}{DC}=\frac{yz-1}{y+1}
=\frac{6-1}{3}=\frac53.
\]

### 图槽审核卡 Q3

- **第一张图：** 强调 \(AD,BE,BC\) 围成的 \(\triangle PDB\)。
- **第二张图：** \(PF\parallel DB\)，且 \(F=PF\cap AC\)。
- **必须支持：** \(A,E,F,C\) 共线；辅助线不得固定为上一题的方向。
- **解答图：** 分别突出 \(APF/ADC\) 与 \(EPF/EBC\)。

## 审核清单

- [ ] 三题是否确实使用三种不同围三角形方案？
- [ ] 是否接受“先让学生选择辅助线，再给完成构造的图”这一题面结构？
- [ ] 每题是否都使用两条已知比，并求第三条比例线上的比？
- [ ] 三题辅助点 \(F\) 的相交对象是否明确且几何闭合？
- [ ] 是否需要再加第 4 题覆盖 \(\triangle ACD\)，还是讲解例题覆盖即可？
