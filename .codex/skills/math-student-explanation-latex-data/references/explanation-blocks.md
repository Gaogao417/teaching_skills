# Explanation Block Reference

只在生成 `exam-zh-explanation` YAML 时读取。本文件记录常用 block type 和最小字段。

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

## reading_tip

轻量读题提示。

```yaml
type: "reading_tip"
id: "rt1"
items:
  - latex: "先做第（1）问，后面两问都建立在解析式上。"
```

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

主体讲解 block。每个小问一个 `dual_explanation`，解答步骤通过 `solution_step_ids` 引用 `route.steps[].id`。

```yaml
type: "dual_explanation"
id: "sol-part1"
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
side_title: "提示与易错"
side_items:
  - kind: "hint"
    title: "入口"
    content_latex: "把两个已知点分别代入 $y=kx+b$。"
solution_title: "解答"
solution_step_ids:
  - "route-equations"
  - "route-solve"
connection_title: "注意"
connection_items:
  - latex: "求出的参数要回代检查。"
```

不要使用旧结构 `right_steps`。不要用 `title: "第（1）问"` 替代 `label` + `stem_latex`。

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

## mistake

```yaml
type: "mistake"
id: "m1"
title: "易错点标题"
content: "说明常见错误和避坑动作。"
```

## variation_training

讲解后的短小动作确认。每个 block 只检查一个关键动作。

```yaml
type: "variation_training"
id: "check-1"
label: "随堂检查"
stem_latex: "把点 $A(1,3)$ 代入 $y=kx+b$，写出对应等式。"
answer_space:
  height: "14mm"
```

## hint

用于补充提示或 diagram fallback。

```yaml
type: "hint"
id: "fig-main-fallback"
content: "本题建议教师在黑板上补画题目草图。"
level: 1
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
