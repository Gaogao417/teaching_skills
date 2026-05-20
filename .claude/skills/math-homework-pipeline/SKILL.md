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

## 输入要求

用户触发 pipeline 时，**必须**提供以下信息（缺一不可，否则先询问再执行）：

1. **数学题目**（完整题干，含图形文字描述）
2. **学生程度**：如"差生"、"中等偏弱"、"中等"、"好"
3. **每道小题用时**：如"2分钟"、"1分钟"、"30秒"
4. **每道大题用时**：如"5分钟"、"3分钟"

agent 不得自行假设用时或学生程度。

## 路径规范

### 目录命名

```
artifacts/<学生名>/<YYYY-MM-DD-<subject>>/
```

- `<学生名>`：学生姓名（如 `陆子辰`、`荣璟羽`）
- `<YYYY-MM-DD-<subject>>`：日期 + 中文话题词，如 `2026-05-19-垂径定理`
- 同一话题的多道题放同一目录

### 目录结构

```
artifacts/<学生名>/<YYYY-MM-DD-<subject>>/
  01-structure-analysis.md                    # 结构分析
  02-explanation.tex                          # 交付物：讲解 TEX
  02-explanation.pdf                          # 交付物：讲解 PDF
  03-practice-student.tex                    # 交付物：练习学生版 TEX
  03-practice-student.pdf                    # 交付物：练习学生版 PDF
  03-practice-teacher.tex                    # 交付物：练习教师版 TEX
  03-practice-teacher.pdf                    # 交付物：练习教师版 PDF
  build/
    02-student-explanation.assignment.yaml    # 中间产物：讲解 YAML
    03-adaptive-practice.student.assignment.yaml  # 中间产物：练习学生版 YAML
    03-adaptive-practice.teacher.assignment.yaml  # 中间产物：练习教师版 YAML
    *.log                                     # 编译日志
    exam-zh.cls / exam-zh-*.sty              # 编译器依赖（自动复制，不要手动管理）
```

**规则**：
- 顶层只放交付物：`.md`、`.tex`、`.pdf`
- 所有中间产物（`.assignment.yaml`）放入 `build/`
- 编译产物（`.log`、`.cls`、`.sty`）也放入 `build/`
- `render_assignment.py --out` 输出到专题顶层；`.assignment.yaml` 本身在 `build/`

### 产物文件名

```
01-structure-analysis.md          # 每道题一个，或整份讲义一个
02-student-explanation.assignment.yaml    → build/
03-adaptive-practice.student.assignment.yaml → build/
03-adaptive-practice.teacher.assignment.yaml → build/
```

讲义模式（多题）：`02-student-explanation.assignment.yaml` 中使用 `problems` 数组，
每道题一个元素，渲染时自动分页。

单题模式：`problems` 数组只有一个元素。

### 学生姓名

学生姓名出现在目录路径中（`artifacts/<学生名>/`），也记录在 YAML 的 `meta.student.name` 字段中。

## 调度规则

```text
如果没有 01-structure-analysis.md
→ 调用 math-structure-analysis

如果已有结构分析但没有 02-student-explanation.assignment.yaml
→ 调用 math-student-explanation-latex-data

如果已有 02-student-explanation.assignment.yaml 但没有对应的 .reviewed
→ 调用 math-yaml-review 审查
→ 审查不通过：报告问题，等待修复后重新生成
→ 审查通过：创建 .reviewed 标记，继续

如果已有讲解但没有 03-adaptive-practice.assignment.yaml
→ 调用 math-adaptive-practice-latex-data

如果已有 03-adaptive-practice.*.assignment.yaml 但没有对应的 .reviewed
→ 对每个 yaml 调用 math-yaml-review 审查
→ 审查不通过：报告问题，等待修复后重新生成
→ 审查通过：创建 .reviewed 标记，继续

如果已有 assignment.yaml（且已 .reviewed）但没有 .tex
→ 运行 render_assignment.py

如果已有 .tex 但没有 .pdf
→ 运行 compile_latex.sh

如果编译失败
→ 摘要 build.log，反馈最小修复建议
```

### Review 标记规则

审查通过后，在 build/ 目录下创建空文件作为标记：

```text
02-student-explanation.reviewed                        → 对应 02-student-explanation.assignment.yaml
03-adaptive-practice.student.reviewed                  → 对应 03-adaptive-practice.student.assignment.yaml
03-adaptive-practice.teacher.reviewed                  → 对应 03-adaptive-practice.teacher.assignment.yaml
```

重新生成 YAML 时自动删除对应的 `.reviewed` 标记。

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
用户给一道数学题和学情信息，如：
- 题目："一次函数 $y=kx+b$ 的图像经过点 $(2,5)$ 和 $(-1,-1)$，求 $k$ 和 $b$。"
- 学生程度：中等偏弱
- 小题用时：2 分钟
- 大题用时：5 分钟

### Stage 1：结构分析
```
artifacts/陆子辰/2026-05-19-一次函数面积/01-structure-analysis.md
```

### Stage 2：讲解 YAML
```
artifacts/陆子辰/2026-05-19-一次函数面积/build/02-student-explanation.assignment.yaml
```

### Stage 3：练习 YAML
```
artifacts/陆子辰/2026-05-19-一次函数面积/build/03-adaptive-practice.student.assignment.yaml
artifacts/陆子辰/2026-05-19-一次函数面积/build/03-adaptive-practice.teacher.assignment.yaml
```

### Stage 4：渲染 LaTeX
```
artifacts/陆子辰/2026-05-19-一次函数面积/02-explanation.tex
artifacts/陆子辰/2026-05-19-一次函数面积/03-practice-student.tex
artifacts/陆子辰/2026-05-19-一次函数面积/03-practice-teacher.tex
```

### Stage 5：编译 PDF
```
artifacts/陆子辰/2026-05-19-一次函数面积/02-explanation.pdf
artifacts/陆子辰/2026-05-19-一次函数面积/03-practice-student.pdf
artifacts/陆子辰/2026-05-19-一次函数面积/03-practice-teacher.pdf
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
      学生程度差，小题2分钟，大题5分钟。

Agent：
  → 检查输入：题目 ✓ 学生程度 ✓ 小题用时 ✓ 大题用时 ✓
  → 确定输出目录：artifacts/<学生名>/<YYYY-MM-DD-一次函数>/（根据学生姓名、当日日期和话题自动生成）
  → Stage 1: 调用 math-structure-analysis
  → Stage 2: 调用 math-student-explanation-latex-data
  → Stage 3: 调用 math-adaptive-practice-latex-data（传入学情信息）
  → Stage 4: python render_assignment.py ...
  → Stage 5: bash compile_latex.sh ...
  → 输出最终报告
```

## 不做事项

- 不直接生成题目内容
- 不直接写 LaTeX
- 不做教学判断
- 不修改现有产物（除非明确要求重新生成）
