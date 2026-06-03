---
name: math-assignment-latex
description: "将已有 assignment.yaml 渲染为 exam-zh LaTeX 并编译为 PDF。Use when: 用户已有 assignment.yaml，需要渲染为 LaTeX、编译 PDF、检查 LaTeX 或从 YAML 生成作业 PDF。Skip when: 用户没有 assignment.yaml、要求生成题目内容、要求结构分析/讲解/练习内容，或要求 HTML 输出。本 skill 不做教学判断，不生成题目内容。"
---

# math-assignment-latex

## 职责

```text
assignment.yaml → Jinja2 模板 → .tex → tectonic/XeLaTeX → .pdf
```

本 skill **不做**以下事情：

- 不做教学判断（那是 structure-analysis 的事）
- 不生成题目内容（那是 latex-data skill 的事）
- 不直接写完整 .tex 页面（通过模板渲染）

## 输入

- `artifacts/<slug>/02-student-explanation.assignment.yaml`
- 或 `artifacts/<slug>/03-adaptive-practice.assignment.yaml`
- 或任意合法的 `*.assignment.yaml`

如果 YAML 使用几何插图，确认所有 `diagram_col` / `diagram_row` / `answer_space.diagram_col` / `type: diagram` 的 `image_path` 相对最终 `.tex` 所在目录可访问；本 skill 只按结构化字段排版图片，不判断题目是否该有图，也不生成图片。

## 输出

```text
artifacts/<slug>/04-assignment.tex    # 渲染后的 LaTeX 源码
artifacts/<slug>/04-assignment.pdf    # 编译后的 PDF（优先使用 tectonic；有 xelatex 时也可用）
artifacts/<slug>/build.log            # 编译日志
```

## 步骤

### 1. 验证 YAML

```bash
python3 math-assignment-latex/scripts/validate_assignment.py <input.yaml>
```

检查 schema 合法性、必需字段、id 唯一性。
所有插图对象必须包含 `image_path`。几何题应由 latex-data writer 显式写入：

- 选择题：`diagram_col` 或 `prompt_diagram`，渲染为左侧题干和竖直选项、右侧图栏。
- 填空题：`type: diagram_row`，渲染为同组填空题前的并排插图行。
- 解答题：`answer_space.diagram_col` 或 `answer_space.parts[].diagram_col`，渲染为答题区和右侧图栏并排。
- 讲义正文：只有确实需要独立居中图时才使用 `type: diagram`。

### 2. 渲染 LaTeX

```bash
python3 math-assignment-latex/scripts/render_assignment.py <input.yaml> --out <output.tex>
```

根据 `render.template` 选择 Jinja2 模板，将 YAML 渲染为 .tex。

### 3. 编译 PDF

```bash
bash math-assignment-latex/scripts/compile_latex.sh <output.tex>
```

脚本自动选择引擎：优先 `xelatex`，否则使用 `tectonic`。当前本地环境没有 `xelatex`，使用 `tectonic` 编译。

### 4. 报告结果

```text
✅ 编译成功 → 输出 PDF 路径
❌ 编译失败 → 输出 build.log 摘要 + 最小修复建议
```

## 版本控制

根据 `meta.version` 决定渲染内容：

```text
student  → 不渲染答案、解析、教师备注
teacher  → 渲染全部
both     → 先 student，\clearpage 后 teacher 附加
```

## 前置依赖

```text
Python 3.8+ (PyYAML, Jinja2)
tectonic 或 XeLaTeX (texlive-xetex)
exam-zh 宏包 (texlive-latex-extra 或 CTAN)
tcolorbox 宏包
needspace 宏包
```
