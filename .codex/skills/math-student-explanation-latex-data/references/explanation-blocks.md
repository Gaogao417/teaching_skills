# Explanation Block Reference

只在生成 `exam-zh-explanation` YAML 时读取。本文件是生成讲解 block 的唯一教学字段约束来源，记录常用 block type 和最小字段。

## 字段职责

- `problemcard.stem_latex`：原题入口，忠实复现题面。
- `route.steps[].latex`：路线图里的步骤动作标题，同时会成为标准解答步骤标题。
- `route.steps[].content_latex`：对应步骤的标准解答正文。
- `dual_explanation.label` / `dual_explanation.stem_latex`：只在原题有多个真实小问时使用，用来标出真实小问和小问题干；原题只有一问时不写。
- `dual_explanation.solution_step_ids`：引用 route step，决定本题/本小问的标准解答包含哪些步骤。
- `connection_items`：放必要的承接说明；不要默认补提示、易错或追问。

不要把教学步骤伪装成小问。原题只有一问时，只写一个 `dual_explanation`，且不写 `label` 和 `stem_latex`；原题有真实 `(1)(2)(3)` 小问时，才写多个 `dual_explanation`。

不默认生成 `reading_tip`、`mistake`、`variation_training` 或 `hint` block。易错点、变式训练和额外提示由教师后续手动补充。

## problemcard

用于页面顶部原题展示。

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

## dual_explanation

主体讲解 block。每个真实题目/真实小问一个 `dual_explanation`，解答步骤通过 `solution_step_ids` 引用 `route.steps[].id`。

如果原题只有一问，标准讲解也只写一个 `dual_explanation`：

```yaml
type: "dual_explanation"
id: "sol-main"
solution_title: "解答"
solution_step_ids:
  - "route-equations"
  - "route-solve"
connection_title: "注意"
connection_items:
  - latex: "求出的参数要回代检查。"
```

如果原题明确有多个小问，才按真实小问拆分：

```yaml
type: "dual_explanation"
id: "sol-part1"
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
solution_step_ids:
  - "route-equations"
  - "route-solve"
```

不要使用旧结构 `right_steps`。多小问时不要用 `title: "第（1）问"` 替代 `label` + `stem_latex`。不要把 `stem_latex` 写成“为什么先……”“怎样……”这类讲解提问；必要引导放在 `route.steps[].content_latex` 或 `connection_items`。

## summary_dual

底部答案和方法收束。

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

## Minimal YAML Shape

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
