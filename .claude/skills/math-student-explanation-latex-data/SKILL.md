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

- `artifacts/<slug>/01-structure-analysis.md`
- 学生画像（可选）
- 教学目标（可选）

## 输出

```text
artifacts/<slug>/02-student-explanation.assignment.yaml
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

### 教师备注
- 训练目标
- 预期卡点
- 档位判断

## YAML 输出格式

```yaml
meta:
  title: "..."
  subtitle: "..."
  grade: "..."
  subject: "..."
  version: "teacher"
  source_artifacts:
    structure_analysis: "artifacts/<slug>/01-structure-analysis.md"

render:
  template: "exam-zh-explanation"

sections:
  - id: "original"
    title: "原题"
    blocks:
      - type: "key_idea"
        content: "原题文本"

  - id: "breakdown"
    title: "一、先把题目拆开"
    blocks:
      - type: "route"
        steps: [...]

  - id: "route-section"
    title: "二、解题路线"
    blocks:
      - type: "route"
        steps: [...]

  - id: "key-idea"
    title: "三、关键想法"
    blocks:
      - type: "key_idea"
        content: "..."

  - id: "solution"
    title: "四、标准解法"
    blocks:
      - type: "step"
        title: "..."
        content: "..."
        why: "..."
        substeps: [...]

  - id: "mistakes"
    title: "五、易错提醒"
    blocks:
      - type: "mistake"
        title: "..."
        content: "..."

  - id: "questions"
    title: "六、边讲边问"
    blocks:
      - type: "hint"
        content: "..."

  - id: "summary"
    title: "七、一句话总结"
    blocks:
      - type: "key_idea"
        content: "..."

  - id: "teacher-notes"
    title: "教师备注"
    visibility: "teacher"
    layout:
      break_before: true
    blocks:
      - type: "key_idea"
        content: "..."
        teaching:
          teaching_goal: "..."
          expected_blocker: "..."
          mastery_band: "..."
```

## Schema 遵循

必须符合 `math-assignment-latex/references/assignment-schema.md` 定义的 schema。

## 自检

输出前必须检查：
1. 所有 block 都有 id 且唯一
2. 所有 block 都有 type
3. 数学公式使用 `$...$` 和 `$$...$$` 格式
4. version 字段正确设置

## Handoff

生成完毕后说明：

```
下一步：使用 math-assignment-latex 渲染并编译 PDF。

python math-assignment-latex/scripts/render_assignment.py \
  artifacts/<slug>/02-student-explanation.assignment.yaml \
  --out artifacts/<slug>/04-assignment.tex
```
