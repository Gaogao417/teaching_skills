---
name: math-assignment-latex
description: "将已定稿或 reviewed 的 assignment.yaml 渲染为 exam-zh LaTeX 并编译为 PDF。Use when: 用户已有可直接渲染的 assignment.yaml，需要渲染 LaTeX、编译 PDF 或检查 LaTeX。Skip when: 用户没有 assignment.yaml、要求生成或审改讲解/练习内容、要求打开 explanation/practice review UI，或要求 HTML 输出。本 skill 不做教学判断，不生成题目内容，也不编排 review。"
---

# math-assignment-latex

## 职责

把已有 `*.assignment.yaml` 渲染成 `.tex` 并编译 PDF：

```text
assignment.yaml -> Jinja2 template -> .tex -> PDF
```

本 skill 不做教学判断、不生成题目内容、不生成几何图，也不负责打开或编排 review UI。讲义 review 属于
`math-student-explanation-latex-data`，练习 review 属于 `math-adaptive-practice-latex-data`。若 YAML 仍含
`diagram_slot`，先使用 `math-geometry-diagram-renderer` 生成 `*.resolved.assignment.yaml`。

## 输入

- `02-student-explanation.assignment.yaml` 或 `02-student-explanation.resolved.assignment.yaml`
- `03-adaptive-practice.student.assignment.yaml` / `.teacher.assignment.yaml`
- 任意合法的 `*.assignment.yaml`

## 路径约定

- 编译必须以最终 `.tex` 所在目录作为 working directory。`compile_latex.sh` 会自动 `cd` 到该目录；编辑器或其它工具也必须等价配置，例如 LaTeX Workshop 使用 `cwd: "%DIR%"`。
- YAML、渲染出的 `.tex`、最终 PDF 默认放在同一个 artifact 目录；构建日志和中间文件可以进入该目录下的 `build/` 或 `.latex-workshop/`。
- `image_path` / `tikz_path` 必须相对最终 `.tex` 所在目录可访问，或使用绝对路径。不要按仓库根目录写相对路径。
- 如果同名 `.tex` 旁存在对应 `*.assignment.yaml`，`compile_latex.sh` 会优先从该 YAML 重新渲染再编译，所以长期内容修改应落在 YAML，而不是只改生成的 `.tex`。

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
