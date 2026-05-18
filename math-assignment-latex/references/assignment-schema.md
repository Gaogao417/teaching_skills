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
    layout:
      break_before: bool  # 区块前分页
      avoid_break: bool   # 区块内不分页
    blocks:               # 题目或内容块列表
      - ...
```

---

## block 字段（每道题/每个内容块）

### 通用字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `type` | enum | 是 | 题型：`choice` / `fillin` / `problem` / `short_answer` / `key_idea` / `mistake` / `hint` / `route` / `step` |
| `id` | string | 是 | 唯一标识（如"q1"） |
| `title` | string | 否 | 题目标题 |
| `points` | int | 否 | 分值 |
| `stem` | string | 是 | 题干（支持 `$...$` LaTeX 数学） |
| `visibility` | enum | 否 | 覆盖 section 级 visibility |
| `layout` | object | 否 | `{ break_before, avoid_break }` |

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
  - "步骤一描述"
  - "步骤二描述"
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

1. 所有 `stem`、`explanation`、`content` 字段支持 `$...$` 行内数学和 `$$...$$` 行间数学
2. 普通文本中的 `# % & _ { }` 由渲染器自动转义，不破坏数学模式
3. `id` 全文档唯一
4. 每个 section 至少一个 block
5. `points` 仅对 choice/fillin/problem/short_answer 有效
