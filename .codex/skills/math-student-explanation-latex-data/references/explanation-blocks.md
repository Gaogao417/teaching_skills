# Explanation Block Reference

只在生成 `exam-zh-explanation` YAML 时读取。本文件是生成讲解 block 的唯一教学字段约束来源，记录常用 block type、两种讲解模式和最小字段。

## 模式选择

### 单题讲解模式

用于用户给出具体原题、要求讲解原题，或 `01-structure-analysis.md` 明确围绕一道原题展开时。

推荐结构：

```text
problemcard 原题
route 解题路线
dual_explanation 主体讲解
summary_dual 答案与方法收束
```

单题讲解模式下，不默认生成独立的 `reading_tip`、`mistake`、`variation_training` 或 `hint` block。若标准步骤里出现了讲 why、讲“所以然”的长解释，应移到 `dual_explanation.side_items`，作为小贴士提问或易混提醒。

### 知识点复习模式

用于用户要求“复习、专题、期末复习、薄弱点、知识点讲义”等按知识点组织的讲义。

每个知识点固定结构：

```text
solution 知识点陈述 / 公式清单
problemcard + route + dual_explanation 例题 1
problemcard + route + dual_explanation 例题 2（按需要）
mistake 易错提醒
method_reminder 方法提醒
```

规则：

- 用全宽 `solution` block 写知识点陈述、公式清单和辨析表，正常字号展示；不要用小字号 `step` 写核心公式。
- 例题仍沿用单题讲解模式的旧结构：`problemcard` 放题面，`route` 放路线，`dual_explanation` 放标准解答和左侧小贴士。
- `mistake` 在每个知识点末尾独立列出本知识点最容易错的判断。
- `method_reminder` 只放本知识点做题策略，不承担公式清单功能。
- `step` 只用于短过渡、临时说明或轻提示。
- 若用户要求“每个知识点另起一面”，在该知识点 section 或该知识点第一个 block 上设置 `layout.break_before: true`。

## 字段职责

- `problemcard.stem_latex`：原题或例题入口，忠实复现题面。
- `solution.title`：知识点复习模式中写成“知识点陈述”“公式清单”等；单题兼容用法中也可写“解答”。
- `solution.items[].latex/content_latex`：正常字号的知识点陈述、公式列表、小表格或分组结论。
- `route.steps[].latex`：路线图里的步骤动作标题，同时会成为标准解答步骤标题。
- `route.steps[].content_latex`：对应步骤的标准解答正文，只写 how：必要动作、公式、推导和结论。不要写大段动机、类比、追问或“所以然”解释。
- `route.steps[].diagram_slot`：若某一步需要讲解辅助图，图位放在对应 step 下；例如“作辅助线/补中点”这一步的 annotated 图应跟随该 step，不另起一个 `problemcard`。
- `dual_explanation.label` / `dual_explanation.stem_latex`：现有 schema 要求必填。单问题可用 `label: "解答"` 或 `label: "例题 1"`，`stem_latex` 复述本题要解决的问题；多小问时用真实 `(1)(2)(3)` 小问标签和小问题干。
- `dual_explanation.solution_step_ids`：引用 route step，决定本题/本小问的标准解答包含哪些步骤。
- `dual_explanation.side_items`：放小贴士提问和易混提醒，用来讲 why 和“所以然”。每条要短，优先写成能让学生思考的提问或判断句。
- `connection_items`：放必要的承接说明；不要把步骤正文已经能表达清楚的内容重复写一遍。

不要把教学步骤伪装成小问。题目只有一问时，只写一个 `dual_explanation`，并用 `label` / `stem_latex` 标出本题解答入口；题目有真实 `(1)(2)(3)` 小问时，才写多个 `dual_explanation`。

## Step Brevity Rule

生成 assignment YAML 后，必须复查每个 `route.steps[].content_latex`：

- 简洁：每步通常只保留 1 个核心动作；能用一行公式说明的，不写成讲义段落。
- 严谨：公式、等量关系、取值范围、点序或符号判断必须完整，不能为了短而漏条件。
- 规范：使用标准数学表述，如“由中位线定理得”“代入得”“解得”“因此”，少用口语化解释。
- 分工：右栏解答步骤讲“怎么做”；左栏 `side_items` 讲“为什么想到这一步”“这里为什么不能那样做”“下一步先观察什么”。

如果发现 `content_latex` 中出现下面内容，应移动到 `side_items`：

- “为什么先……”
- “看到……要想到……”
- “这一步的本质是……”
- “容易错在……”
- “你可以先问自己……”

## solution

知识点复习模式中，用于全宽知识点陈述和公式清单。

```yaml
type: "solution"
id: "knowledge-card"
title: "知识点陈述与公式清单"
items:
  - latex: '\textbf{基本结论：} 对 $a,b\ge0$，有 $a+b\ge2\sqrt{ab}$。'
  - latex: '\textbf{使用条件：} 一正、二定、三相等。'
  - content_latex: |
      \begin{tabular}{p{0.32\linewidth}p{0.58\linewidth}}
      形式 & 适用提醒\\
      $a+b\ge2\sqrt{ab}$ & 已知和或积时优先观察\\
      $\frac{x}{y}+\frac{y}{x}\ge2$ & 先确认 $x,y$ 同号且分母不为 $0$
      \end{tabular}
```

不要把核心公式写进 `step` 或只放在 `method_reminder`。`solution.items` 可用 `latex` 写短句，也可用 `content_latex` 写分组列表或小表格。

## problemcard

用于页面顶部原题或例题展示。

```yaml
type: "problemcard"
id: "orig"
label: "题目"
stem_latex: |
  已知一次函数 $y=kx+b$ 的图像经过点 $A(1,3)$ 和点 $B(-2,-6)$。
  \begin{enumerate}[label=(\arabic*)]
    \item 求这个一次函数的解析式；
    \item 判断点 $C(3,9)$ 是否在这个函数的图像上。
  \end{enumerate}
```

不要用 `step` 放原题。`stem_latex` 原样输出 LaTeX，不转义。

## route

用文字步骤展示解题路线。

```yaml
type: "route"
id: "route"
steps:
  - id: "route-equations"
    latex: "两点代入 $y=kx+b$"
    content_latex: "代入两个已知点，得到关于 $k,b$ 的两个方程。"
  - id: "route-solve"
    latex: "解方程组求 $k$、$b$"
    content_latex: "解出 $k,b$ 后写出解析式。"
```

如果某一步本身就是“补辅助线/作图/标关键点”，把讲解图位挂在该 step 下：

```yaml
  - id: "route-add-helper"
    latex: "补取中点 $M$"
    content_latex: "取 $M$ 为 $AB$ 的中点。"
    diagram_slot:
      slot_id: "explanation.solution.annotated"
      diagram_ref: "explanation.solution.annotated"
      variant: "solution"
      disclosure_policy: "annotated"
      reuse_geometry_from: "explanation.orig.prompt"
      required: true
      on_failure: "fail_assignment"
      placement: "step_diagram"
      layout_role: "solution_annotation"
      display_profile: "worksheet_geometry_center"
      caption: "补 $M$ 后看两条中位线。"
      engine: "coordinate_renderer"
      diagram_kind: "coordinate_geometry"
      teaching_intent: "explanation_solution"
```

## dual_explanation

主体讲解 block。每个真实题目/真实小问一个 `dual_explanation`，解答步骤通过 `solution_step_ids` 引用 `route.steps[].id`。

如果题目只有一问，标准讲解也只写一个 `dual_explanation`，但仍按 schema 写 `label` 和 `stem_latex`：

```yaml
type: "dual_explanation"
id: "sol-main"
label: "解答"
stem_latex: "求这个一次函数的解析式。"
side_title: "小贴士"
side_items:
  - kind: "hint"
    title: "先想什么"
    content_latex: "为什么这一步要先找到两个已知点？"
solution_title: "解答"
solution_step_ids:
  - "route-equations"
  - "route-solve"
connection_title: "注意"
connection_items:
  - latex: "求出的参数要回代检查。"
```

如果题目明确有多个小问，才按真实小问拆分：

```yaml
type: "dual_explanation"
id: "sol-part1"
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
solution_step_ids:
  - "route-equations"
  - "route-solve"
```

不要使用旧结构 `right_steps`。不要用 `title: "第（1）问"` 替代 `label` + `stem_latex`。不要把 `stem_latex` 写成“为什么先……”“怎样……”这类讲解提问；必要引导放在 `route.steps[].content_latex`、`side_items` 或 `connection_items`。

## mistake

知识点复习模式中，用于每个知识点末尾的独立易错提醒。

```yaml
type: "mistake"
id: "knowledge-mistake"
title: "易错提醒"
content_latex: |
  基本不等式不能直接对一正一负的两项使用；使用前先检查取值范围，再检查等号能否取到。
```

单题讲解模式中，优先把易错点写入 `dual_explanation.side_items`；只有用户明确要求汇总易错，或题目确实需要页末集中提醒时，才使用独立 `mistake`。

## method_reminder

知识点复习模式中，用于每个知识点末尾的方法总结。

```yaml
type: "method_reminder"
id: "knowledge-method"
title: "方法提醒"
items:
  - latex: "先看条件是否满足，再决定能不能套公式。"
  - latex: "遇到最值题，最后必须检查等号成立条件。"
```

`method_reminder` 不写大段公式清单；公式清单放入前面的 `solution` block。

## summary_dual

单题讲解模式底部答案和方法收束。

```yaml
type: "summary_dual"
id: "summary-block"
left_title: "答案"
left_items:
  - latex: "$y = 3x$"
right_title: "方法提醒"
right_items:
  - latex: "待定系数法：代入、列方程、消元、回代。"
```

## Minimal YAML Shape: 单题讲解模式

```yaml
meta:
  title: "..."
  subtitle: "..."
  grade: "..."
  subject: "数学"
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
        stem_latex: "..."
```

## Minimal YAML Shape: 知识点复习模式

```yaml
meta:
  title: "高一薄弱点复习"
  subtitle: "学生讲义"
  grade: "高一"
  subject: "数学"
  version: "student"

render:
  template: "exam-zh-explanation"
  paper_size: "a4paper"

sections:
  - id: "topic-1"
    title: "基本不等式"
    type: "explanation"
    visibility: "student"
    layout:
      break_before: true
    blocks:
      - type: "solution"
        id: "topic-1-knowledge"
        title: "知识点陈述与公式清单"
        items:
          - latex: '对 $a,b\ge0$，$a+b\ge2\sqrt{ab}$，等号当且仅当 $a=b$ 时成立。'

      - type: "problemcard"
        id: "topic-1-example-1"
        label: "例题 1"
        stem_latex: "..."

      - type: "route"
        id: "topic-1-route-1"
        steps:
          - id: "topic-1-route-1-check"
            latex: "检查使用条件"
            content_latex: "先确认参与基本不等式的量均为非负。"
          - id: "topic-1-route-1-equality"
            latex: "检查等号条件"
            content_latex: "令两项相等，判断是否能取到。"

      - type: "dual_explanation"
        id: "topic-1-sol-1"
        label: "例题 1"
        stem_latex: "求该式的最小值。"
        side_title: "小贴士"
        side_items:
          - kind: "hint"
            title: "先看条件"
            content_latex: "这一步为什么必须先确认非负？"
        solution_title: "解答"
        solution_step_ids:
          - "topic-1-route-1-check"
          - "topic-1-route-1-equality"

      - type: "mistake"
        id: "topic-1-mistake"
        title: "易错提醒"
        content_latex: "不能只写最小值，还要检查等号成立条件。"

      - type: "method_reminder"
        id: "topic-1-method"
        title: "方法提醒"
        items:
          - latex: "基本不等式题按“条件、定值、等号”三步检查。"
```
