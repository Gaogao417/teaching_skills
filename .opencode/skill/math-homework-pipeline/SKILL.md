---
name: math-homework-pipeline
description: "端到端调度器：判断当前产物缺哪一步，自动调用对应 skill 或脚本补齐。"
version: 0.1.0
triggers:
  - description: "用户给了一道数学题，要求生成完整作业 PDF"
  - description: "用户提到 homework-pipeline 或 pipeline"
  - description: "用户说：帮我把这道题做成作业"
  - description: "用户要求端到端生成"
skip:
  - description: "用户只要求分析结构（使用 math-structure-analysis）"
  - description: "用户只要求生成 YAML（使用对应 latex-data skill）"
  - description: "用户只要求渲染 PDF（使用 math-assignment-latex）"
---

# math-homework-pipeline

## 职责

端到端调度器。不直接写题目，不直接写 LaTeX。只判断当前产物缺哪一步，调用对应 skill 或脚本。

## 调度规则

```text
如果没有 01-structure-analysis.md
→ 调用 math-structure-analysis

如果已有结构分析但没有 02-student-explanation.assignment.yaml
→ 调用 math-student-explanation-latex-data

如果已有讲解但没有 03-adaptive-practice.assignment.yaml
→ 调用 math-adaptive-practice-latex-data

如果已有 assignment.yaml 但没有 .tex
→ 运行 render_assignment.py

如果已有 .tex 但没有 .pdf
→ 运行 compile_latex.sh

如果编译失败
→ 摘要 build.log，反馈最小修复建议
```

## 每阶段输出

完成每阶段后输出：

```text
✅ 当前阶段：[阶段名]
📄 产物路径：[文件路径]
➡️  下一步：[命令或说明]
⚠️  需要人工检查：是/否
```

## 完整 pipeline 示例

### 输入
用户给一道数学题，如："一次函数 $y=kx+b$ 的图像经过点 $(2,5)$ 和 $(-1,-1)$，求 $k$ 和 $b$。"

### Stage 1：结构分析
```
artifacts/linear-function/01-structure-analysis.md
```

### Stage 2：讲解 YAML
```
artifacts/linear-function/02-student-explanation.assignment.yaml
```

### Stage 3：练习 YAML
```
artifacts/linear-function/03-adaptive-practice.assignment.yaml
```

### Stage 4：渲染 LaTeX
```
artifacts/linear-function/04-assignment.tex
```

### Stage 5：编译 PDF
```
artifacts/linear-function/04-assignment.pdf
artifacts/linear-function/build.log
```

## 失败处理

```text
如果 Stage 1 失败 → 报告题目理解问题，请求人工澄清
如果 Stage 2/3 失败 → 报告教学逻辑问题，回退到 Stage 1 重新分析
如果 Stage 4 失败 → 报告 YAML schema 错误，修复 YAML
如果 Stage 5 失败 → 摘要 build.log，修复模板或 LaTeX 内容
```

## 使用示例

```
用户：帮我把这道题做成作业：函数 y=2x-1 的图像经过哪个点？

Agent：
  → 检查 artifacts 目录：无现有产物
  → Stage 1: 调用 math-structure-analysis
  → Stage 2: 调用 math-student-explanation-latex-data
  → Stage 3: 调用 math-adaptive-practice-latex-data
  → Stage 4: python render_assignment.py ...
  → Stage 5: bash compile_latex.sh ...
  → 输出最终报告
```

## 不做事项

- 不直接生成题目内容
- 不直接写 LaTeX
- 不做教学判断
- 不修改现有产物（除非明确要求重新生成）
