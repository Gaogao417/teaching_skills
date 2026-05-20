---
name: math-student-explanation-latex-data
description: "根据结构分析生成讲解内容的 assignment.yaml，保留原 math-student-explanation-html 的教学逻辑，但输出 YAML 而非 HTML。"
version: 0.1.0
triggers:
  - description: "已有 01-structure-analysis.md，需要生成讲解内容 YAML"
  - description: "用户要求生成 explanation assignment.yaml"
  - description: "用户提到 explanation-latex-data 或讲解 YAML"
skip:
  - description: "没有 01-structure-analysis.md（先运行 math-structure-analysis）"
  - description: "用户要求 HTML 输出（使用 math-student-explanation-html）"
  - description: "用户要求练习题（使用 math-practice-latex-data）"
---

# math-student-explanation-latex-data

## 职责

从 `01-structure-analysis.md` 生成 `02-explanation.assignment.yaml`。

保留原 `math-student-explanation-html` 的全部教学逻辑，输出格式从 HTML 改为 YAML。

## 输入

- `artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md`
- 学生画像（可选）
- 教学目标（可选）

## 输出

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.assignment.yaml
```

## 教学逻辑（与 HTML 版一致）

必须包含以下教学元素：

### 原题拆解
- 题目拆解表：已知、要求、关键词、忽略

### 解题路线
- 路线图：2-5 步解题步骤

### 核心思路
- 核心解题思路的提炼

### 标准解法
- 分步骤展示
- 每步有 title, content, 可选 why
- 支持子步骤 substeps

### 边讲边问
- 2-3 个思考题
- 帮助学生主动思考

### 易错提醒
- 常见错误和避坑指南

### 一句话总结
- 核心方法归纳

### 教师备注
- 训练目标
- 预期卡点
- 档位判断

## 关键 block type 说明

explanation 模板支持多种 block type，必须使用正确的 type 才能正确渲染：

### problemcard — 原题展示

用于页面顶部的原题区域，支持 LaTeX 题干和子问题列表。

```yaml
type: "problemcard"
label: "题目"
stem_latex: |
  已知一次函数 $y=kx+b$ 的图像经过点 $A(1,3)$ 和点 $B(-2,-6)$。
  \begin{enumerate}[label=(\arabic*)]
    \item 求这个一次函数的解析式；
    \item 判断点 $C(3,9)$ 是否在这个函数的图像上；
    \item 求该函数图像与 $x$ 轴、$y$ 轴的交点坐标，并计算图像与坐标轴围成的三角形面积。
  \end{enumerate}
```

**不要用** `key_idea` 或 `step` 放原题。`stem_latex` 原样输出 LaTeX，不经过转义。

### reading_tip — 读题提示

轻量楷体提示框，放在原题下方。用 `items` 列表，每条用 `latex` 字段。

```yaml
type: "reading_tip"
items:
  - latex: "先做第（1）问——后面两问都建立在解析式上。"
  - latex: "这道题是「先求式，再代入，再算面积」的递进结构。"
```

### route — 解题路线（虚线框 + 文字箭头）

虚线框内用文字 + `→` 箭头展示解题步骤，自然换行不会溢出页面。

```yaml
type: "route"
steps:
  - latex: "两点代入 $y=kx+b$，列方程组"
  - latex: "解方程组求 $k$、$b$"
  - latex: "代入检验点 $C$"
  - latex: "求坐标轴交点，算面积"
```

### key_idea — 核心思路

轻提示框渲染，用于提炼核心解题思路。

```yaml
type: "key_idea"
content: |
  一次函数有两个未知系数 $k$ 和 $b$。"图像经过一个点"意味着这个点的坐标满足解析式。
  两个点 = 两个方程，刚好解出两个未知数。
```

### dual_explanation — 主体双栏讲解（核心）

这是讲解页最核心的 block type。左栏放思路点拨，右栏放解题示范。
有子问题时，每个子问题各用一个 `dual_explanation`。

每个小问必须在讲解前带上该小问的题干，使用 `label` + `stem_latex` 字段，
渲染时自动以 `(1)` 题干内容 的 exam 格式呈现（蓝色加粗题号 + 题干文字）。

**不要用** `title: "第（1）问"` 这种写法，改用 `label` + `stem_latex`。

```yaml
type: "dual_explanation"
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
left_title: "思路点拨"
left_items:
  - latex: "把 $A(1,3)$ 代入 $y=kx+b$，你能得到什么方程？"
  - latex: "两个方程，用什么方法消元最快？试试两式直接相减。"
right_title: "解题示范"
right_steps:
  - latex: "代入 $A(1,3)$：$3 = k + b$ \\quad \\textcircled{1}"
  - latex: "代入 $B(-2,-6)$：$-6 = -2k + b$ \\quad \\textcircled{2}"
  - latex: "\\textcircled{1}$-$\\textcircled{2}：$9 = 3k$，所以 $k = 3$"
  - latex: "代回 \\textcircled{1}：$3 = 3 + b$，所以 $b = 0$"
  - latex: "解析式：$y = 3x$"
connection_title: "注意"
connection_items:
  - latex: "$b = 0$！这条直线过原点——后面的第（3）问会用到这个事实。"
```

字段说明：
- `label`：小问题号，如 `(1)`、`(2)`、`(3)`，与原题 enumerate 格式一致
- `stem_latex`：该小问的题干文字（LaTeX），从原题摘出对应小问
- `left_items`：思路点拨或易错提示，列表
- `right_steps`：解题示范步骤，列表
- `connection_title`：衔接标题（如"注意"、"方法"、"关键"）
- `connection_items`：后问如何承接前问的提示

### summary_dual — 底部双栏收束（参考答案 + 方法提炼）

用于讲解页最底部的答案和方法总结。

```yaml
type: "summary_dual"
left_title: "参考答案"
left_items:
  - latex: "$y = 3x$"
  - latex: "$C(3,9)$ 在图像上"
right_title: "方法提炼"
right_items:
  - latex: "待定系数法四步：代入 → 列方程 → 消元 → 回代"
  - latex: "每次求出参数后先看有没有特殊情况（如 $b = 0$）"
```

### mistake — 易错提醒

```yaml
type: "mistake"
title: "套面积公式不看条件"
content: |
  直线与坐标轴围成三角形面积公式 $S = \frac{1}{2}|x_0| \cdot |y_0|$ 的前提是：
  两个交点不重合。本题 $b = 0$，两个交点都是原点。
```

### hint — 边讲边问

```yaml
type: "hint"
content: "如果把点 $B$ 改为 $(-2, -4)$，求出来的 $b$ 还等于 $0$ 吗？"
level: 1
```

### step — 兼容旧格式（优先用上述 type）

只有当上述专用 type 都不适用时才用 `step`。

## YAML 输出格式

```yaml
meta:
  title: "..."
  subtitle: "..."
  grade: "..."
  subject: "..."
  version: "teacher"
  source_artifacts:
    structure_analysis: "artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md"

render:
  template: "exam-zh-explanation"
  paper_size: "a4paper"

sections:
  - id: "original"
    title: "原题"
    type: "explanation"
    visibility: "both"
    blocks:
      - type: "problemcard"
        id: "orig"
        label: "题目"
        stem_latex: |
          已知一次函数 $y=kx+b$ 的图像经过点 $A(1,3)$ 和点 $B(-2,-6)$。
          \begin{enumerate}[label=(\arabic*)]
            \item 求这个一次函数的解析式；
            \item 判断点 $C(3,9)$ 是否在这个函数的图像上；
          \end{enumerate}

  - id: "breakdown"
    title: "一、先把题目拆开"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "reading_tip"
        id: "rt1"
        items:
          - latex: "先做第（1）问——后面两问都建立在解析式上。"
          - latex: "这道题是「先求式，再代入，再算面积」的递进结构。"

  - id: "route-section"
    title: "二、思路导航"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "route"
        id: "route"
        steps:
          - latex: "两点代入 $y=kx+b$"
          - latex: "解方程组求 $k$、$b$"
          - latex: "代入检验点 $C$"
          - latex: "求坐标轴交点"

  - id: "key-idea"
    title: "三、核心思路"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "key_idea"
        id: "ki"
        content: |
          核心解题思路...

  - id: "solution"
    title: "四、标准解法"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      # 每个子问题用一个 dual_explanation，带 label + stem_latex 复现题干
      - type: "dual_explanation"
        id: "sol-part1"
        label: "(1)"
        stem_latex: "求这个一次函数的解析式；"
        left_title: "思路点拨"
        left_items:
          - latex: "..."
        right_title: "解题示范"
        right_steps:
          - latex: "..."
        connection_title: "注意"
        connection_items:
          - latex: "..."

      - type: "dual_explanation"
        id: "sol-part2"
        label: "(2)"
        stem_latex: "判断点 $C(3,9)$ 是否在这个函数的图像上；"
        left_title: "思路点拨"
        left_items:
          - latex: "..."
        right_title: "解题示范"
        right_steps:
          - latex: "..."

  - id: "summary"
    title: "总结"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "summary_dual"
        id: "summary-block"
        left_title: "参考答案"
        left_items:
          - latex: "..."
        right_title: "方法提炼"
        right_items:
          - latex: "..."

  - id: "mistakes"
    title: "易错提醒"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "mistake"
        id: "m1"
        title: "易错点标题"
        content: "..."

  - id: "questions"
    title: "边讲边问"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "hint"
        id: "q1"
        content: "思考题..."
        level: 1
      - type: "hint"
        id: "q2"
        content: "思考题..."
        level: 2

  - id: "teacher-notes"
    title: "教师备注"
    type: "explanation"
    visibility: "teacher"
    blocks:
      - type: "key_idea"
        id: "tn1"
        content: |
          学生画像和教学节奏说明...
        teaching:
          teaching_goal: "..."
          expected_blocker: "..."
          mastery_band: "B"
          upgrade_rule: "升级条件"
          downgrade_rule: "降级条件"
```

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md` 定义的 schema。

## 自检

输出前必须检查：
1. 所有 block 都有 id 且唯一
2. 所有 block 都有 type，且使用正确的 type（不要用 `step` 替代 `dual_explanation`）
3. 原题用 `problemcard` + `stem_latex`，不要用 `key_idea`
4. 每个子问题的解法各用一个 `dual_explanation`，必须带 `label`（如 `(1)`）和 `stem_latex`（该小问题干），不要用 `title: "第（X）问"`
5. 数学公式使用 `$...$` 和 `$$...$$` 格式。特别注意：逻辑推理符号（如 `\because`, `\therefore`）必须强制置于数学环境内（即 `$\because$`，`$\therefore$`），不得以纯文本形式出现。
6. `stem_latex` 中的 LaTeX 命令不转义（原样输出）
7. block scalar（`|`）字段中的 LaTeX 命令用单反斜杠 `\frac`（不是 `\\frac`）；双引号字符串中的 `\\frac` 会被 YAML 解析为 `\frac` 所以是正确的
8. 每个 section 都有 `type: "explanation"` 和 `visibility`
9. 底部答案用 `summary_dual`，不要用 `key_idea`
10. 可读性保障：
    - 对于列表字段（如 `left_items`, `right_steps`, `items` 等），**严禁**在单个 item 的字符串内部使用换行符（如 `\n\n` 或 `\\`）。如果需要分步，请将其拆分为多个独立的 item 数组元素，模板会自动进行列表排版。
    - 对于纯长文本段落字段（如 `explanation`, `content`），如果有复杂的推导、多步方程或分类讨论，务必使用换行符进行清晰的段落划分，避免文字堆砌挤成一团。
11. 文件名严格绑定：输出文件名必须严格命名为 `02-explanation.assignment.yaml`，以匹配编译管线的自动挂载策略。

## Handoff

生成完毕后说明：

```
下一步：使用 math-assignment-latex 渲染、检查并编译 PDF。

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.assignment.yaml \
  --out artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.tex

python math-assignment-latex/scripts/check_latex.py artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.tex

bash math-assignment-latex/scripts/compile_latex.sh artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.tex
```

