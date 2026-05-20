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
key_idea / reading_tip / route / dual_explanation / explanation_dual
summary_dual / answer_reminder / answer / answers / method_reminder / reminder
mistake / hint / step / problemcard
```

### choice 类型

```yaml
type: choice
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
```

### key_idea 类型

```yaml
type: key_idea
content: "关键想法内容"
```

在 `exam-zh-explanation` 模板中，`key_idea` 会以轻提示框渲染；新讲义页优先使用语义更明确的 `reading_tip`。

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

用于讲解页主体双栏。左栏放思考引导和易错提示，右栏放规范讲解；后续小问依赖前问时，用 `connection_items` 收束。

每个子问题必须带 `label` + `stem_latex`，讲解前自动以 exam 格式复现该小问题干。
不要用 `title: "第（X）问"`，改用 `label` + `stem_latex`。

```yaml
type: dual_explanation
label: "(1)"
stem_latex: "求这个一次函数的解析式；"
left_title: "思考引导 / 易错提示"
left_items:
  - latex: "已知两个点，优先想到用待定系数法求 $k,b$。"
  - latex: "点 $A(0,2)$ 在 $y$ 轴上，代入后可以直接得到 $b$。"
right_title: "规范讲解"
right_steps:
  - latex: "把 $A(0,2)$ 代入 $y=kx+b$，得 $b=2$。"
  - latex: "把 $B(4,0)$ 代入 $y=kx+b$，得 $0=4k+2$，所以 $k=-\\dfrac{1}{2}$。"
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
```

---

## 约束

1. 所有 `stem`、`stem_latex`、`explanation`、`content`、`latex` 字段支持 `$...$` 行内数学和 `$$...$$` 行间数学
2. 普通文本中的 `# % & _ { }` 由渲染器自动转义，不破坏数学模式
3. `id` 全文档唯一
4. 每个 section 至少一个 block
5. `points` 仅对 choice/fillin/problem/short_answer 有效
6. 不要把中文标点放进数学模式：写 `$A$、$B$`，不要写 `$A、B$`
