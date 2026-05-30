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
  - description: "用户要求练习题（使用 math-adaptive-practice-latex-data）"
---

# math-student-explanation-latex-data

## 职责

从 `01-structure-analysis.md` 生成 `02-student-explanation.assignment.yaml`。

保留原 `math-student-explanation-html` 的全部教学逻辑，输出格式从 HTML 改为 YAML。

## 输入

- `artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md`
- 学生画像（可选）
- 教学目标（可选）

## 输出

```text
artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.assignment.yaml
```

## 教学逻辑（与 HTML 版一致）

必须包含以下教学元素：

### 原题拆解
- 题目拆解表：已知、要求、关键词、忽略

### 解题路线
- 路线图：2-5 步解题步骤

### 关键想法
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

### 图形辅助（可选）
- 如果结构分析的 `diagram_request_packet.needs_diagram: true`，先使用 `math-geometry-diagram-renderer` 生成配套图片。
- 原题展示只能用 `prompt` / `clean` 图：只画题干已知对象和必要顶点标签，不画辅助线、不写推理标注、不泄露答案。
- 讲解步骤中如需辅助线、垂足、角标、相等标记或推理标注，另生成 `solution` / `annotated` 图，不要改造原题图。
- 讲义正文可用 `type: diagram` 居中展示图片；题目型试卷中的选择/填空/解答题图栏由 practice YAML 使用 `diagram_col` / `diagram_row` / `answer_space.diagram_col`。
- 如果图形生成失败、跳过或暂不支持，用 `hint` block 写 fallback 文本，不插入破图

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

### diagram — 图形包插图

用于插入 `math-geometry-diagram-renderer` 产出的最终 PNG。只插入最终可用图，不暴露生成过程。

```yaml
type: "diagram"
id: "fig-main"
image_path: "diagram/rendered/prompt.png"
caption: "先观察底边 BC 与高 AD 的关系。"
variant: "prompt"
disclosure_policy: "clean"
teaching_focus:
  - "先看底边"
  - "再作高"
```

规则：
- `image_path` 必须相对当前 YAML/最终 `.tex` 所在目录可访问
- `caption` 写学生要观察的动作，不写“模型生成”“第几轮成功”等调试信息
- 只有 PNG 文件真实存在时才生成 `diagram` block；否则改用 `hint` 写 fallback 或教师手动画图建议
- 原题图必须写 `variant: "prompt"` 和 `disclosure_policy: "clean"`；辅助线讲解图必须写 `variant: "solution"` 和 `disclosure_policy: "annotated"`
- 坐标图/函数图如果 renderer skill 明确不支持，不强行插图

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
  - id: "route-equations"
    latex: "两点代入 $y=kx+b$，列方程组"
    content_latex: "代入两个已知点，得到关于 $k,b$ 的两个方程。"
  - id: "route-solve"
    latex: "解方程组求 $k$、$b$，写出解析式"
    content_latex: "解出 $k,b$ 后，写出一次函数解析式。"
  - id: "route-check"
    latex: "代入检验点 $C$"
    content_latex: "把点 $C$ 的横坐标代入解析式，比较纵坐标。"
  - id: "route-area"
    latex: "求坐标轴交点，算面积"
    content_latex: "分别令 $y=0$、$x=0$ 求交点，再判断能否围成三角形。"
```

### key_idea — 关键想法

轻提示框渲染，用于提炼核心解题思路。

```yaml
type: "key_idea"
content: |
  一次函数有两个未知系数 $k$ 和 $b$。"图像经过一个点"意味着这个点的坐标满足解析式。
  两个点 = 两个方程，刚好解出两个未知数。
```

### dual_explanation — 主体双栏讲解（核心）

这是讲解页最核心的 block type。每个小问一个 `dual_explanation`：
`side_items` 固定放本小问的“提示与易错”，`solution_step_ids` 引用 `route.steps[].id` 展示解答。
思路导航怎么分步，解答就怎么分步；不要再为解答另写一套步骤标题。
有子问题时，每个子问题各用一个 `dual_explanation`。

每个小问必须在讲解前带上该小问的题干，使用 `label` + `stem_latex` 字段，
渲染时自动以 `(1)` 题干内容 的 exam 格式呈现（蓝色加粗题号 + 题干文字）。

**不要用** `title: "第（1）问"` 这种写法，改用 `label` + `stem_latex`。

```yaml
type: "dual_explanation"
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
side_title: "提示与易错"
side_items:
  - kind: "hint"
    title: "入口"
    content_latex: "把 $A(1,3)$ 和 $B(-2,-6)$ 分别代入 $y=kx+b$。"
  - kind: "mistake"
    title: "负号"
    content_latex: "代入 $B(-2,-6)$ 时，$kx$ 是 $-2k$，不要写成 $2k$。"
solution_title: "解答"
solution_step_ids:
  - "route-equations"
  - "route-solve"
connection_title: "注意"
connection_items:
  - latex: "$b = 0$！这条直线过原点——后面的第（3）问会用到这个事实。"
```

字段说明：
- `label`：小问题号，如 `(1)`、`(2)`、`(3)`，与原题 enumerate 格式一致
- `stem_latex`：该小问的题干文字（LaTeX），从原题摘出对应小问
- `side_title`：侧栏标题，默认 `"提示与易错"`
- `side_items`：小问级侧栏提示列表；每项必须是 object，包含 `kind: "hint" | "mistake" | "note"`、`title`、`content_latex` / `content` / `latex`
- `solution_title`：解答栏标题，默认 `"解答"`
- `solution_step_ids`：引用 `route.steps[].id`，解答步骤标题和正文都来自对应 route step；不再允许 `right_steps: [{title/content_latex: ...}]`
- `connection_title`：衔接标题（如"注意"、"方法"、"关键"）
- `connection_items`：后问如何承接前问的提示

### summary_dual — 底部双栏收束（答案 + 方法提醒）

用于讲解页最底部的答案和方法总结。

```yaml
type: "summary_dual"
left_title: "答案"
left_items:
  - latex: "$y = 3x$"
  - latex: "$C(3,9)$ 在图像上"
right_title: "方法提醒"
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

### step — 其他内容块（不用于主体讲解）

只有当上述专用 type 都不适用时才用 `step`。不要用 `step` 表示每个小问的标准解法；小问讲解必须使用 `route.steps[].id + dual_explanation.solution_step_ids`。

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
    layout:
      break_before: false
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
    title: "二、解题路线"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "route"
        id: "route"
        steps:
          - id: "route-equations"
            latex: "两点代入 $y=kx+b$"
            content_latex: "..."
          - id: "route-solve"
            latex: "解方程组求 $k$、$b$"
            content_latex: "..."
          - id: "route-check"
            latex: "代入检验点 $C$"
            content_latex: "..."
          - id: "route-intercepts"
            latex: "求坐标轴交点"
            content_latex: "..."

  - id: "key-idea"
    title: "三、关键想法"
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
        side_title: "提示与易错"
        side_items:
          - kind: "hint"
            title: "入口"
            content_latex: "..."
          - kind: "mistake"
            title: "易错点"
            content_latex: "..."
        solution_title: "解答"
        solution_step_ids:
          - "route-equations"
          - "route-solve"
        connection_title: "注意"
        connection_items:
          - latex: "..."

      - type: "dual_explanation"
        id: "sol-part2"
        label: "(2)"
        stem_latex: "判断点 $C(3,9)$ 是否在这个函数的图像上；"
        side_title: "提示与易错"
        side_items:
          - kind: "hint"
            title: "入口"
            content_latex: "..."
        solution_title: "解答"
        solution_step_ids:
          - "route-check"

  - id: "summary"
    title: "总结"
    type: "explanation"
    visibility: "student"
    show_title: false
    blocks:
      - type: "summary_dual"
        id: "summary-block"
        left_title: "答案"
        left_items:
          - latex: "..."
        right_title: "方法提醒"
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
```

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md` 定义的 schema。

## 自检

输出前必须检查：
1. 所有 block 都有 id 且唯一
2. 所有 block 都有 type，且使用正确的 type（不要用 `step` 替代 `dual_explanation`）
3. 原题用 `problemcard` + `stem_latex`，不要用 `key_idea`
4. 每个子问题的解法各用一个 `dual_explanation`，必须带 `label`（如 `(1)`）和 `stem_latex`（该小问题干），不要用 `title: "第（X）问"`
5. 若使用 `diagram` block，图片路径相对 YAML/最终 `.tex` 可访问；原题图必须 clean，辅助线图必须另用 solution/annotated；失败时使用 fallback，不留空图
6. 数学公式使用 `$...$` 和 `$$...$$` 格式
7. `stem_latex` 中的 LaTeX 命令不转义（原样输出）
8. block scalar（`|`）字段中的 LaTeX 命令用单反斜杠 `\frac`（不是 `\\frac`）；双引号字符串中的 `\\frac` 会被 YAML 解析为 `\frac` 所以是正确的
9. 每个 section 都有 `type: "explanation"` 和 `visibility`
10. 底部答案用 `summary_dual`，不要用 `key_idea`

## Handoff

生成完毕后说明：

```
下一步：使用 math-assignment-latex 渲染、检查并编译 PDF。

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<学生名>/YYYY-MM-DD-<内容>/02-student-explanation.assignment.yaml \
  --out artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.tex

python math-assignment-latex/scripts/check_latex.py artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.tex

bash math-assignment-latex/scripts/compile_latex.sh artifacts/<学生名>/YYYY-MM-DD-<内容>/02-explanation.tex
```
