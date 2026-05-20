---
name: math-yaml-review
description: "审查 assignment.yaml 的内容质量，在渲染前拦截编译级和内容级问题。"
version: 0.1.0
triggers:
  - description: "pipeline 生成了新的 assignment.yaml，需要审查后放行"
  - description: "用户要求审查或 review 一个 assignment.yaml"
  - description: "用户提到 yaml-review 或 YAML 审查"
skip:
  - description: "没有 assignment.yaml 文件可审查"
  - description: "yaml 已经标记为 .reviewed"
  - description: "用户要求直接渲染，跳过审查"
---

# math-yaml-review

## 职责

审查已生成的 `assignment.yaml`，在渲染为 TEX 前拦截质量问题。
发现问题后给出具体修复建议，**不直接修改文件**。

## 输入

- 一个 `*.assignment.yaml` 文件路径
- （可选）对应的 `01-structure-analysis.md` 用于交叉验证答案

## 审查清单

按严重程度排序。每项标明级别：编译级（不修就编不过）→ 渲染级（输出异常）→ 内容级（教学准确性）。

### 1. LaTeX 命令完整性 — 编译级

检测 yaml.safe_load 转义损坏的残留（`_fix_yaml_escapes` 应已修复，此处作为兜底）：

- 搜索包含 tab 字符 (0x09) 的字符串值 → 应为 `\times` / `\to` / `\theta` 等
- 搜索包含裸 `eq` 前面紧跟换行的模式 → 应为 `\neq`
- 搜索包含 `imes` 前面紧跟 tab 的模式 → 应为 `\times`
- 检查 `\Leftrightarrow` 是否被截断为 `eftrightarrow`（U+2028 隐藏字符）

### 2. Markdown 语法残留 — 渲染级

在所有字符串值中检测：

- `**...**` → 应改为 `\textbf{...}`
- `## ` 标题 → 应改为 LaTeX 标题命令
- `` `...` `` 行内代码 → 应改为 `\texttt{...}` 或删除
- `- [ ]` / `- [x]` 复选框 → 不应出现在 LaTeX 内容中

### 3. AI 自我质疑文本 — 内容级

在所有字符串值中检测以下模式（尤其 solutionblock / right_steps 中）：

- "不对"、"不是"、"等等"、"让我重新"、"让我再"
- "重新计算"、"数据可能有误"、"需要确认"
- "让我试试"、"可能有问题"

教师版允许有限的教学提示语气，但不得包含 AI 推理过程的痕迹。

### 4. 答案自洽性 — 内容级

对每个选择题 block：

- 检查 `answer` 或 `\paren[X]` 标注的答案选项
- 在 solutionblock / explanation 中找到最终结论
- 两者必须一致

对每个填空题 block：

- 检查 `answer` 字段
- solutionblock 中应有对应的最终数值

### 5. 空必填字段 — 内容级

- `type: choice` / `type: fillin` → 检查是否有 `choices` / `answer`
- `type: problem` → 检查是否有 `stem` 或 `stem_latex`
- solutionblock 不应为空（教师版）
- `right_steps` 列表不应为空

### 6. 教师信息泄露 — 内容级

当 `meta.version == "student"` 时：

- 检查 visibility != "teacher" 的 block 中是否包含：
  - 学生姓名（通常出现在"XX需要特别注意"等表述中）
  - 教学策略描述（"教学节奏"、"档位判断"）
  - `eduTeacherNote` / `teachernote` 环境

## 输出格式

```
📄 文件：<文件名>

❌ 编译级问题（必须修复才能渲染）
  - L<行号>: <问题描述>
    → 修复：<具体建议>

⚠️ 渲染级问题（输出会异常）
  - L<行号>: <问题描述>
    → 修复：<具体建议>

📝 内容级问题（教学准确性）
  - L<行号>: <问题描述>
    → 修复：<具体建议>

✅ 通过项：<列表>

结论：通过 / 需修复后重新生成
```

## 判定标准

- 存在任何编译级问题 → ❌ 不放行
- 存在 ≥3 个渲染级问题 → ❌ 不放行
- 存在 ≥5 个内容级问题 → ❌ 不放行
- 其他 → ⚠️ 放行但列出建议修复项

## 通过标记

审查通过后，在 build/ 目录下创建空文件：

```
<basename>.reviewed
```

例如 `02-student-explanation.reviewed`。

pipeline 检查此文件决定是否跳过审查。

## 不做事项

- 不修改 YAML 文件（只报告问题）
- 不做数学计算验证（只检查文本层面的自洽性）
- 不替代 check_latex.py（那是渲染后的语法检查）
