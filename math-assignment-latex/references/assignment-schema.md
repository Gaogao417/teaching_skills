# assignment.yaml Schema

## 概述

`assignment.yaml` 是教学 DSL 的核心，承载从结构分析到 PDF 渲染所需的全部教学语义。
不包含渲染细节，渲染由 Jinja2 模板负责。

## 顶层结构

```yaml
meta:         # 元信息
render:       # 渲染配置
sections:     # 内容区块
```

---

## meta 字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 作业标题 |
| `example_label` | string | 否 | 讲解页左上角例题编号，如 `"例题 2"` |
| `subtitle` | string | 否 | 副标题/标签 |
| `grade` | string | 否 | 年级（如"八年级"） |
| `subject` | string | 否 | 学科（如"数学"） |
| `duration` | string | 否 | 建议用时（如"20分钟"） |
| `total_points` | int | 否 | 总分 |
| `version` | enum | 是 | `student` / `teacher` / `both` |
| `show_answers` | bool | 否 | 即使 student 版也显示答案 |
| `source_artifacts` | object | 否 | 源产物引用 |

### version 规则

```text
student   → 不渲染答案、解析、教师备注
teacher   → 渲染全部
both      → 先 student 内容，\clearpage 后 teacher 附加内容
```

---

## render 字段

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `template` | string | "exam-zh-practice" | 模板名 |
| `paper_size` | string | "a4paper" | 纸张 |
| `show_seal_line` | bool | false | 密封线 |
| `answer_key_position` | string | "after_page_break" | 答案页位置 |

---

## sections 结构

```yaml
sections:
  - id: string            # 区块 ID
    title: string         # 区块标题（如"一、核心练习"）
    type: enum            # practice / explanation / answer_key
    visibility: enum      # student / teacher / both
    blocks:               # 题目或内容块列表
      - ...
```

> **分页规则（模板层自动处理，YAML 无需声明）**
> - `type: "answer_key"` 的 section：渲染模板自动在其前插入 `\clearpage`
> - `visibility: "teacher"` 的 section（讲解页模板）：渲染模板自动在其前插入 `\clearpage`
> - `type: "problem"` / `"short_answer"` 的 block：渲染模板自动加 `\needspace{8\baselineskip}` 防止题干与答题区被截断
> - `type: "dual_explanation"` / `"explanation_dual"`（讲解页）：使用 `paracol` 双栏，内容超出单页时自动跨页续排，无需任何声明
>
> **`layout` 字段已废弃**，不再由 LLM 生成，忽略即可。


---

## block 字段（每道题/每个内容块）

### 通用字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `type` | enum | 是 | 题型或内容块，见下方类型说明 |
| `id` | string | 是 | 唯一标识（如"q1"） |
| `title` | string | 否 | 题目标题 |
| `points` | int | 否 | 分值 |
| `stem` | string | 条件必填 | 题干（支持 `$...$` LaTeX 数学）；题目类 block 可用 `stem_latex` 替代 |
| `stem_latex` | string | 条件必填 | 原样 LaTeX 题干，用于公式较多的题目 |
| `visibility` | enum | 否 | 覆盖 section 级 visibility |
| `layout` | object | 否 | `{ break_before, avoid_break }` |

支持的 block type：

```text
choice / fillin / problem / short_answer
reading_tip / route / dual_explanation / explanation_dual / variation_training
summary_dual / answer_reminder / answer / answers / method_reminder / reminder
mistake / hint / step / problemcard / diagram / diagram_row
```

### 几何插图契约

`assignment-latex` 不从题干自然语言推断是否需要插图；latex-data writer 必须在 YAML 中显式声明。

通用图片对象：

```yaml
image_path: "diagram/rendered/prompt.png"
diagram_job_id: "c1-prompt"
caption: "观察点 D 在 BC 上的位置。"
width: "0.30\\linewidth"
variant: "prompt"             # prompt / solution
disclosure_policy: "clean"    # clean / annotated
reuse_from: ""                # 只有显式复用别题图时填写
```

规则：

- `prompt` / `clean` 图只画题目已知对象和必要顶点标签，不画辅助线、不写推理标注、不泄露答案。
- `solution` / `annotated` 图只用于讲解、解析、教师版，可画辅助线和推理标注。
- 练习题默认每道题一个独立 `diagram_job_id`，独立输出到 `diagram/jobs/<diagram_job_id>/rendered/prompt.png`。
- 多道题引用同一 `image_path` 时，除原题讲义图外，必须显式写 `reuse_from` 说明复用来源；否则 validator 判错。
- 几何大题必须有图；几何题已知条件数大于 3 时默认要有图；题干出现“如图/图中/下图”强制要有图。
- 选择题用 `diagram_col` 或 `prompt_diagram`，模板会把选项强制竖排并把图放右栏。
- 填空题用独立 `diagram_row` block，把同组填空题的所有图并排放在题目后面。
- 大题用 `answer_space.parts[].diagram_col` 或 `answer_space.diagram_col`，模板会把每一问答题区和右侧图栏并排。

### choice 类型

```yaml
type: choice
diagram_col:
  image_path: "diagram/jobs/c1-prompt/rendered/prompt.png"
  diagram_job_id: "c1-prompt"
  width: "0.30\\linewidth"
  caption: "参考图"
  variant: "prompt"
  disclosure_policy: "clean"
choices:
  A: "选项文本 $x=1$"
  B: "选项文本 $x=2$"
  C: "选项文本 $x=3$"
  D: "选项文本 $x=4$"
answer: "B"
```

### fillin 类型

```yaml
type: fillin
answer: "填空答案"
fillin_type: line        # line / paren / circle / blank / rectangle
```

填空题插图行示例。注意：`diagram_row` 放在对应填空题 block 后面。

```yaml
blocks:
  - type: fillin
    id: f1
    stem: "如图，求 $x$ 的值。"
    answer: "$5$"
  - type: fillin
    id: f2
    stem: "如图，求 $y$ 的值。"
    answer: "$6$"
  - type: diagram_row
    id: fillin-diagrams-1
    needspace: "18\\baselineskip"
    items:
      - label: "第 1 题"
        image_path: "diagram/jobs/f1-prompt/rendered/prompt.png"
        diagram_job_id: "f1-prompt"
        width: "0.23\\linewidth"
        variant: "prompt"
        disclosure_policy: "clean"
      - label: "第 2 题"
        image_path: "diagram/jobs/f2-prompt/rendered/prompt.png"
        diagram_job_id: "f2-prompt"
        width: "0.23\\linewidth"
        variant: "prompt"
        disclosure_policy: "clean"
```

### problem / short_answer 类型

```yaml
type: problem
label: "题目"
stem_latex: "已知一次函数 $y=kx+b$ ..."
subquestions:
  - latex: "求这个一次函数的解析式；"
  - latex: "求点 $C$ 的坐标。"
answer: "最终答案"
explanation: "解析文本"
solution_steps:
  - title: "步骤标题"
    content: "步骤内容 $formula$"
    why: "为什么这样做"
    formula: "关键公式"
answer_space:
  type: lines            # lines / blank / steps
  height: "25mm"
  diagram_col:
    image_path: "diagram/rendered/prompt.png"
    diagram_job_id: "p1-prompt"
    width: "0.32\\linewidth"
    caption: "参考图"
    variant: "prompt"
    disclosure_policy: "clean"
```

多问大题推荐按每一问声明答题区和右侧图栏：

```yaml
answer_space:
  type: steps
  height: "28mm"
  parts:
    - label: "(1)"
      height: "28mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part1-prompt/rendered/prompt.png"
        diagram_job_id: "p1-part1-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
    - label: "(2)"
      height: "32mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part2-prompt/rendered/prompt.png"
        diagram_job_id: "p1-part2-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
```

### diagram 类型

用于消费本地画图工作流产物。渲染器只负责插入最终图片，不负责生成、评价或重试。

优先用题目内的 `diagram_col` / `diagram_row` / `answer_space.diagram_col` 表达试卷图。`type: diagram` 只用于讲义正文中确实需要独立居中图片的场景。

```yaml
type: diagram
id: fig-main
image_path: "diagram/rendered/prompt.png"
caption: "观察底边 BC 与高 AD 的关系。"
width: "0.82\\linewidth"   # 可选，默认 0.82\linewidth
teaching_focus:
  - "先看底边"
  - "再看高"
```

规则：

- `image_path` 必须相对最终 `.tex` 所在目录可访问，或使用绝对路径。
- 只插入已经存在的最终 PNG；失败时用 `reading_tip` / `hint` 写 fallback。
- `caption` 面向学生观察动作，不写模型名、重试轮次、Wolfram 代码等调试信息。

### reading_tip 类型

用于讲解页题目下方的读题提示框。

```yaml
type: reading_tip
items:
  - latex: "先解决第（1）问，后面两问都建立在第（1）问结果上。"
  - latex: "这是一道“先求式，再代入，再联立”的递进题。"
```

### mistake 类型

```yaml
type: mistake
title: "易错点标题"
content: "易错内容描述"
```

### hint 类型

```yaml
type: hint
content: "提示内容"
level: 1                # 1=轻微, 2=接近答案
```

`hint` 只用于补充提示或 diagram fallback，不用于讲解后的变式题。

### variation_training 类型

用于讲解后的独立变式练习。它必须像一道完整题：有完整题干，并给学生留白作答。

```yaml
type: variation_training
id: var-1
label: "变式 1"
stem_latex: |
  已知一次函数 $y=kx+b$ 的图像经过点 $A(1,3)$ 和点 $B(-2,-4)$。
  \begin{enumerate}[label=(\arabic*)]
    \item 求这个一次函数的解析式；
    \item 求它与两坐标轴围成的三角形面积。
  \end{enumerate}
answer_space:
  height: "36mm"
```

字段规则：

- `label` / `title`：可选，渲染为题目标记，推荐使用 `label: "变式 1"`。
- `stem_latex` / `stem`：必填其一，必须是完整题干，不要只写启发问题。
- `answer_space.height`：必填，控制留白高度。

### route 类型

```yaml
type: route
steps:
  - latex: "由 $A$、$B$ 两点求解析式"
  - latex: "代入 $x=2$ 求点 $C$"
  - latex: "联立两条直线求点 $M$"
```

`exam-zh-explanation` 会将 `route.steps` 渲染为虚线框内文字 + `→` 箭头，自然换行不会溢出。

### dual_explanation / explanation_dual 类型

用于讲解页主体双栏。每个真实题目/真实小问一个 `dual_explanation`：`side_items` 是题目级/小问级“提示与易错”，`solution_step_ids` 引用 `route.steps[].id` 作为“解答”的分步。思路导航和解答步骤标题必须同源，不要另写一套步骤标题。后续小问依赖前问时，用 `connection_items` 收束。

原题只有一问时，只写一个 `dual_explanation`，用 `solution_step_ids` 引用全部必要 route step；不要把讲解步骤拆成伪小问。

每个 `dual_explanation` 必须带 `label` + `stem_latex`，讲解前自动以 exam 格式复现该题/小问题干。`stem_latex` 必须是真实题干，不写“为什么……”“怎样……”这类讲解提问。
不要用 `title: "第（X）问"`，改用 `label` + `stem_latex`。

`route.steps[]` 可带 `id` 和 `content_latex/content`；带 `id` 的 route step 可被 `dual_explanation.solution_step_ids` 引用。解答渲染时使用 route step 的 `latex/text/title` 作为 step 标题，使用 `content_latex/content` 作为正文。
`side_items[]` 必须是对象，推荐 `kind: hint | mistake | note`，并包含 `title` 与 `content_latex` / `content` / `latex`。
旧格式 `left_items/right_steps` 不再合法。

```yaml
type: route
id: route
steps:
  - id: solve-by-points
    latex: "两点代入 $y=kx+b$，列方程组"
    content_latex: "把 $A(0,2)$、$B(4,0)$ 分别代入，得到两个方程。"
  - id: solve-parameters
    latex: "解方程组求 $k$、$b$"
    content_latex: "由方程组求得 $k=-\\dfrac12$，$b=2$。"
```

```yaml
type: dual_explanation
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
side_title: "提示与易错"
side_items:
  - kind: hint
    title: "入口"
    content_latex: "已知两个点，优先想到用待定系数法求 $k,b$。"
  - kind: mistake
    title: "负号"
    content_latex: "代入 $B(4,0)$ 时，不要漏掉移项后的负号。"
solution_title: "解答"
solution_step_ids:
  - solve-by-points
  - solve-parameters
connection_title: "后两问如何承接"
connection_items:
  - latex: "把 $x=2$ 代入解析式，求点 $C$。"
```

### summary_dual / answer_reminder 类型

用于讲解页底部答案和方法提醒。

```yaml
type: summary_dual
left_title: "答案"
left_items:
  - latex: "$y=-\\dfrac{1}{2}x+2$"
  - latex: "$C(2,1)$"
right_title: "方法提醒"
right_items:
  - latex: "先做基础问，再做依赖前面结果的后续问。"
```

### answer / answers 类型

轻量答案块。可用 `items` 或 `content`。

```yaml
type: answer
title: "答案"
items:
  - latex: "$C(2,1)$"
```

### method_reminder / reminder 类型

轻量方法提醒块。

```yaml
type: method_reminder
items:
  - latex: "先看递进关系，再决定书写顺序。"
```

### step 类型

```yaml
type: step
title: "步骤标题"
content: "步骤内容"
why: "原因说明"
substeps:
  - "子步骤一"
```

---

## teaching 字段（可选，附加在任意 block 上）

```yaml
teaching:
  teaching_goal: "训练目标描述"
  expected_blocker: "预期卡点"
  mastery_band: "B"           # A/B/C/D/E/F
  upgrade_rule: "升级条件"
  downgrade_rule: "降级条件"
  complexity_note: "复杂度说明"
```

教师版渲染时输出，学生版不渲染。

---

## hints 字段

```yaml
hints:
  - content: "提示 1：指向动作"
  - content: "提示 2：接近答案"
```

---

## answer_space 字段

```yaml
answer_space:
  type: lines        # lines / blank / steps
  height: "25mm"
  step_count: 4      # type=steps 时
  diagram_col:       # 可选；把图放进答题区右侧，不单独占用题面纵向空间
    image_path: "diagram/jobs/p1-prompt/rendered/prompt.png"
    diagram_job_id: "p1-prompt"
    width: "0.32\\linewidth"
    caption: "原题图"
    variant: "prompt"
    disclosure_policy: "clean"
```

---

## 约束

1. 所有 `stem`、`stem_latex`、`explanation`、`content`、`latex` 字段支持 `$...$` 行内数学和 `$$...$$` 行间数学
2. 普通文本中的 `# % & _ { }` 由渲染器自动转义，不破坏数学模式
3. `id` 全文档唯一
4. 每个 section 至少一个 block
5. `points` 仅对 choice/fillin/problem/short_answer 有效
6. 不要把中文标点放进数学模式：写 `$A$、$B$`，不要写 `$A、B$`
