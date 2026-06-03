---
name: math-assignment-latex
description: "将已有 assignment.yaml 渲染为 exam-zh LaTeX 并编译为 PDF。Use when: 用户已有 assignment.yaml，需要渲染为 LaTeX、编译 PDF、检查 LaTeX 或从 YAML 生成作业 PDF。Skip when: 用户没有 assignment.yaml、要求生成题目内容、要求结构分析/讲解/练习内容，或要求 HTML 输出。本 skill 不做教学判断，不生成题目内容。"
---

# math-assignment-latex

## 职责

把已有 `*.assignment.yaml` 渲染成 `.tex` 并编译 PDF：

```text
assignment.yaml -> Jinja2 template -> .tex -> PDF
```

本 skill 不做教学判断、不生成题目内容、不生成几何图。若 YAML 仍含 `diagram_slot`，先使用 `math-geometry-diagram-renderer` 生成 `*.resolved.assignment.yaml`。

## 输入

- `02-student-explanation.assignment.yaml` 或 `02-student-explanation.resolved.assignment.yaml`
- `03-adaptive-practice.student.assignment.yaml` / `.teacher.assignment.yaml`
- 任意合法的 `*.assignment.yaml`

## 工作流

先验证 YAML：

```bash
python3 math-assignment-latex/scripts/validate_assignment.py <input.yaml>
```

再渲染 LaTeX：

```bash
python3 math-assignment-latex/scripts/render_assignment.py <input.yaml> --out <output.tex>
```

检查并编译：

```bash
python3 math-assignment-latex/scripts/check_latex.py <output.tex>
bash math-assignment-latex/scripts/compile_latex.sh <output.tex>
```

## 参考

- Schema: `math-assignment-latex/references/assignment-schema.md`
- 模板映射: `math-assignment-latex/references/exam-zh-mapping.md`
- LaTeX 风格: `math-assignment-latex/references/latex-style-guide.md`
- 编译排错: `math-assignment-latex/references/compile-troubleshooting.md`

只在需要具体字段、模板映射或排错时读取对应 reference。

## 输出

报告生成的 `.tex`、`.pdf` 和 `build.log` 路径。编译失败时摘要 `build.log` 中最相关的错误，并给出最小修复建议。
