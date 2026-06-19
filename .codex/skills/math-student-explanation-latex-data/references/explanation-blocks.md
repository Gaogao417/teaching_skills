# Explanation Block Reference

只在生成 `exam-zh-explanation` YAML 时读取。本文件是生成讲解 block 的唯一教学字段约束来源，记录讲义单元模板、标题规则、常用 block type 和最小字段。

## 讲义单元模板

Explanation 统一按“知识点/模型单元”组织，不按场景切成两套结构。区别只在讲义规模：

- 单题型：1 个知识点/模型单元，原题作为例题。
- 小专题型：1-3 个知识点/模型单元，每个单元 1-2 个例题。
- 复习型：多个知识点/模型单元，每个单元独立成组。

每个知识点/模型单元固定使用一个 section。section 必须有可见标题：

```yaml
sections:
  - id: "model-1"
    title: "模型一：平行四边形存在性与对角线中点"
    show_title: true
    type: "explanation"
    visibility: "student"
```

单元内推荐结构：

```text
section.title + show_title: true
solution 知识点陈述（按需，但标题仍必须存在）
problemcard + route + dual_explanation 例题 1
problemcard + route + dual_explanation 例题 2（按需）
mistake 易错提醒
method_reminder 方法提醒
```

规则：

- `section.title` 负责学生看到的知识点/模型标题；不要只靠 `problemcard.label` 或 `solution.title` 充当标题。
- 即使不写 `solution` block，也必须保留 `section.title` 和 `show_title: true`。
- `solution` 用全宽 block 写核心结论、公式、使用条件和辨析表；不要用小字号 `step` 写核心公式。
- `problemcard` 放原题或例题题面，`route` 放规范解题动作，`dual_explanation` 放标准解答和左侧小贴士。
- `mistake` 在每个单元末尾列出本单元最容易错的判断；极短单题型讲义可把易错点并入 `dual_explanation.side_items`。
- `method_reminder` 只放本单元做题策略，不承担公式清单功能。
- `step` 只用于短过渡、临时说明或轻提示。
- 若用户要求“每个知识点另起一面”，在该知识点 section 或该知识点第一个 block 上设置 `layout.break_before: true`。

## 标题规则

- 优先使用“模型/知识点编号 + 结构名 + 入口动作/判定对象”，例如：
  - `模型一：平行四边形存在性与对角线中点`
  - `模型二：矩形存在性与直角分类`
  - `模型三：45°方向直线与函数交点`
- 单题型也要有标题，例如：`原题模型：一次函数待定系数与代入检验`。
- 多知识点复习每个 section 一个标题，例如：`知识点一：基本不等式的使用条件`。
- 不用空泛标题，如“知识点讲解”“例题讲解”“公式清单”“解题方法”。
- `solution.title` 写内容型标题，如“核心结论：对角线中点判定平行四边形”“使用条件：等腰直角的 90° 旋转走法”；不要写成“知识点陈述”“公式清单”这类功能名。

## 字段职责

- `section.title`：知识点/模型单元的可见标题，必须配合 `show_title: true`。
- `problemcard.stem_latex`：原题或例题入口，忠实复现题面。
- `solution.title`：内容型小标题，说明本块讲哪条结论、条件或辨析；不是功能名。
- `solution.items[].latex/content_latex`：正常字号的知识点陈述、公式列表、小表格或分组结论。
- `route.steps[].latex`：路线图里的步骤动作标题，同时会成为标准解答步骤标题。
- `route.steps[].content_latex`：对应步骤的标准解答正文，只写 how：必要动作、公式、推导和结论。不要写大段动机、类比、追问或“所以然”解释。
- `route.steps[].diagram_slot`：若某一步需要讲解辅助图，图位放在对应 step 下；例如“作辅助线/补中点”这一步的 annotated 图应跟随该 step，不另起一个 `problemcard`。
- `dual_explanation.label` / `dual_explanation.stem_latex`：现有 schema 要求必填。单问题可用 `label: "例题 1"` 或 `label: "解答"`，`stem_latex` 复述本题要解决的问题；多小问时用真实 `(1)(2)(3)` 小问标签和小问题干。
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

用于全宽知识点/模型陈述，适合放核心结论、公式、使用条件和辨析表。

```yaml
type: "solution"
id: "model-1-knowledge"
title: "核心结论：对角线中点判定平行四边形"
items:
  - latex: '\textbf{固定顺序：} 若四边形 $ABCD$ 是平行四边形，则 $A+C=B+D$。'
  - latex: '\textbf{构成题：} 若只说 $A,B,C,D$ 构成平行四边形，要分别讨论三组对角点。'
  - content_latex: |
      \begin{tabular}{p{0.32\linewidth}p{0.58\linewidth}}
      题面说法 & 入口动作\\
      平行四边形 $ABCD$ & 顺序固定，直接找 $A,C$ 与 $B,D$ 两组对角点\\
      四点构成平行四边形 & 顺序未固定，三种对角情况都要列
      \end{tabular}
```

不要把核心公式写进 `step` 或只放在 `method_reminder`。`solution.items` 可用 `latex` 写短句，也可用 `content_latex` 写分组列表或小表格。

## problemcard

用于页面顶部原题或例题展示。

```yaml
type: "problemcard"
id: "orig"
label: "例题 1"
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
label: "例题 1"
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

用于每个知识点/模型单元末尾的独立易错提醒。

```yaml
type: "mistake"
id: "model-1-mistake"
title: "易错提醒"
content_latex: |
  平行四边形存在性最容易漏的是“构成”题的三种对角情况。做题时先写清三组对角点，再分别列式。
```

极短单题型讲义中，易错点可以写入 `dual_explanation.side_items`；只有用户明确要求汇总易错，或题目确实需要页末集中提醒时，才使用独立 `mistake`。

## method_reminder

用于每个知识点/模型单元末尾的方法总结。

```yaml
type: "method_reminder"
id: "model-1-method"
title: "方法提醒"
items:
  - latex: "固定顺序 $ABCD$：直接找两组对角点。"
  - latex: "无固定顺序：三种候选对角情况都要写。"
```

`method_reminder` 不写大段公式清单；公式清单和使用条件放入前面的 `solution` block。

## summary_dual

用于底部答案和方法收束；可在单题型讲义末尾使用，专题型通常用每个单元的 `method_reminder` 收束。

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

## Minimal YAML Shape: 单题型

```yaml
meta:
  title: "一次函数待定系数讲解"
  subtitle: "学生讲义"
  grade: "八年级"
  subject: "数学"
  version: "student"
  source_artifacts:
    structure_analysis: "artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md"

render:
  template: "exam-zh-explanation"
  paper_size: "a4paper"

sections:
  - id: "original-model"
    title: "原题模型：一次函数待定系数与代入检验"
    show_title: true
    type: "explanation"
    visibility: "student"
    blocks:
      - type: "problemcard"
        id: "orig"
        label: "例题 1"
        stem_latex: "..."
```

## Minimal YAML Shape: 多单元讲义

```yaml
meta:
  title: "特殊四边形坐标存在性专题"
  subtitle: "学生讲义"
  grade: "八年级"
  subject: "数学"
  version: "student"

render:
  template: "exam-zh-explanation"
  paper_size: "a4paper"

sections:
  - id: "model-1"
    title: "模型一：平行四边形存在性与对角线中点"
    show_title: true
    type: "explanation"
    visibility: "student"
    layout:
      break_before: true
    blocks:
      - type: "solution"
        id: "model-1-knowledge"
        title: "核心结论：对角线中点判定平行四边形"
        items:
          - latex: '固定顺序 $ABCD$ 中，若 $A,C$ 为对角点，则 $A+C=B+D$。'

      - type: "problemcard"
        id: "model-1-example-1"
        label: "例题 1"
        stem_latex: "..."

      - type: "route"
        id: "model-1-route-1"
        steps:
          - id: "model-1-route-1-fixed"
            latex: "固定顺序找对角点"
            content_latex: "先判断题目是否固定为 $ABCD$，再确定两组对角点。"
          - id: "model-1-route-1-formula"
            latex: "代入对角线中点公式"
            content_latex: "由 $A+C=B+D$ 求出未知点坐标。"

      - type: "dual_explanation"
        id: "model-1-sol-1"
        label: "例题 1"
        stem_latex: "求平行四边形中未知点的坐标。"
        side_title: "小贴士"
        side_items:
          - kind: "hint"
            title: "先看顺序"
            content_latex: "题目写成 $ABCD$，顺序已经固定；只说“构成”时顺序没有固定。"
        solution_title: "解答"
        solution_step_ids:
          - "model-1-route-1-fixed"
          - "model-1-route-1-formula"

      - type: "mistake"
        id: "model-1-mistake"
        title: "易错提醒"
        content_latex: "只说四点构成平行四边形时，不能只写一种对角情况。"

      - type: "method_reminder"
        id: "model-1-method"
        title: "方法提醒"
        items:
          - latex: "固定顺序先找指定对角点；无固定顺序要分类。"
```
