# math-assignment-latex

将教学 DSL (`assignment.yaml`) 渲染为 LaTeX 并编译为 A4 PDF。

## 快速开始

```bash
# 渲染
python math-assignment-latex/scripts/render_assignment.py \
  math-assignment-latex/examples/linear-function.practice.assignment.yaml \
  --out artifacts/linear-function/04-assignment.tex

# 编译
bash math-assignment-latex/scripts/compile_latex.sh \
  artifacts/linear-function/04-assignment.tex
```

## 目录结构

```text
math-assignment-latex/
  SKILL.md                              # Skill 定义
  README.md                             # 本文件
  templates/
    exam-zh-practice.tex.j2             # 练习页模板
    exam-zh-explanation.tex.j2          # 讲解页模板
    exam-zh-homework.tex.j2             # 作业页模板
    exam-zh-solution.tex.j2             # 纯答案页模板
    preamble-exam-zh.tex                # 共享 preamble
  references/
    assignment-schema.md                # DSL Schema 定义
    exam-zh-mapping.md                  # edu-* → LaTeX 映射
    latex-style-guide.md                # 排版规范
    compile-troubleshooting.md          # 编译故障排查
  scripts/
    render_assignment.py                # YAML → LaTeX 渲染器
    validate_assignment.py              # YAML Schema 验证
    sanitize_latex.py                   # LaTeX 文本转义
    compile_latex.sh                    # XeLaTeX 编译脚本
  examples/
    linear-function.practice.assignment.yaml
    linear-function.explanation.assignment.yaml
    expected/
      linear-function.practice.tex      # 预期输出（用于测试）
```

## 依赖

- Python 3.8+, PyYAML, Jinja2
- XeLaTeX (texlive-xetex)
- exam-zh, tcolorbox, needspace 宏包
