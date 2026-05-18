---
name: math-assignment-latex
description: "将 assignment.yaml 渲染为 exam-zh LaTeX 并编译为 PDF。不做教学判断，不生成题目内容。"
version: 0.1.0
triggers:
  - description: "用户已有 assignment.yaml，需要渲染为 LaTeX 或编译 PDF"
  - description: "用户提到 math-assignment-latex 或 assignment 渲染"
  - description: "用户要求从 YAML 生成作业 PDF"
skip:
  - description: "用户没有 assignment.yaml（需要先运行 latex-data skill 生成）"
  - description: "用户要求生成题目内容而非渲染"
  - description: "用户要求 HTML 输出（使用 math-student-explanation-html）"
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
