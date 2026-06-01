---
name: math-homework-pipeline
description: "端到端调度器：判断当前产物缺哪一步，自动调用对应 skill 或脚本补齐；生成完成后启动独立审核子任务，使用 math-homework-review 给出五项快速质量印象。"
---

# math-homework-pipeline

## 职责

端到端调度器。不直接写题目，不直接写 LaTeX。只判断当前产物缺哪一步，调用对应 skill 或脚本。生成完成后，启动一个独立审核子任务，使用 `math-homework-review` 给用户一个简短质量印象。

本 skill 必须把每次运行当成可审计 workflow：先判定 `run_mode`，再维护 `run_manifest.json`、`build/review-ledger.jsonl`、`preflight.json` 和最终 `review/final-homework-review.json`。

## 触发与跳过

使用本 skill：

- 用户给了一道数学题，要求生成完整作业 PDF
- 用户提到 homework-pipeline 或 pipeline
- 用户说"帮我把这道题做成作业"
- 用户要求端到端生成

跳过本 skill：

- 用户只要求分析结构（使用 `math-structure-analysis`）
- 用户只要求生成 YAML（使用对应 latex-data skill）
- 用户只要求渲染 PDF（使用 `math-assignment-latex`）

## 运行模式

开始任何动作前，必须先判定并记录 `run_mode`。只能使用以下值：

| run_mode | 使用场景 | 必填输入 | 禁止动作 |
| --- | --- | --- | --- |
| `new-homework-run` | 从新题生成完整作业 PDF | 题目、学生程度、小题用时、大题用时、学生名或输出目录 | 不得猜学生程度或用时 |
| `resume-existing-artifact` | 已有 artifact 目录，补齐缺失阶段 | artifact 目录、目标缺口 | 不得重写已有内容，除非用户明确要求 |
| `repair-existing-artifact` | 修复已有产物的编译、排版、内容问题 | artifact 目录、失败现象、允许修改范围 | 不得顺手重构无关 skill |
| `workflow-maintenance` | 修改 skill、脚本、模板、审计流程 | 修改目标、验证方式 | 不得生成学生作业产物 |
| `explanation-only` | 用户只问流程/代码/模板解释 | 用户问题、文件范围 | 不得启动完整 pipeline |

判定后必须初始化或更新 manifest：

```bash
python3 scripts/workflow_gate.py init-manifest \
  --artifact-dir <artifact_dir> \
  --run-mode <run_mode> \
  --goal "<用户目标>" \
  --inputs-json '<结构化输入，可省略>'
```

如果 `workflow-maintenance` 或 `explanation-only` 没有学生 artifact 目录，使用 `.workflow-runs/<YYYY-MM-DD-<topic>>/` 作为 manifest 目录，不要污染 `artifacts/`。

## 输入要求

`new-homework-run` 模式必须提供以下信息（缺一不可，否则先询问再执行）：

1. **数学题目**（完整题干，含图形文字描述）
2. **学生程度**：如"差生"、"中等偏弱"、"中等"、"好"
3. **每道小题用时**：如"2分钟"、"1分钟"、"30秒"
4. **每道大题用时**：如"5分钟"、"3分钟"

agent 不得自行假设用时或学生程度。

非 `new-homework-run` 模式不得机械追问上述四项；必须改为记录 `skip_reason`，说明为什么本轮复用已有 artifact 或只做 workflow 维护。

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
  run_manifest.json                           # 运行 manifest：模式、stage、产物、skip reason、commit
  preflight.json                              # LaTeX 环境检查结果
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
    review-ledger.jsonl                       # YAML gate verdict ledger
    *.log                                     # 编译日志
    exam-zh.cls / exam-zh-*.sty              # 编译器依赖（自动复制，不要手动管理）
  review/
    final-homework-review.md                  # 最终审核报告
    final-homework-review.json                # 最终审核结构化 verdict
```

**规则**：
- 顶层只放交付物：`.md`、`.tex`、`.pdf`
- 所有中间产物（`.assignment.yaml`）放入 `build/`
- 编译产物（`.log`、`.cls`、`.sty`）也放入 `build/`
- `render_assignment.py --out` 输出到专题顶层；`.assignment.yaml` 本身在 `build/`
- 每个 stage 状态必须写入 `run_manifest.json`
- review/gate verdict 必须写入 `build/review-ledger.jsonl`

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
Step 0: 判定 run_mode，并写入 run_manifest.json

如果 run_mode == workflow-maintenance 或 explanation-only
→ 不执行学生作业生成阶段
→ 只完成用户要求的维护/解释任务，并在 manifest 中记录 skip_reason

Step -1: LaTeX preflight
→ 运行 scripts/workflow_gate.py preflight
→ 如果状态为 BLOCKED_ENVIRONMENT：停止渲染/编译，报告缺失依赖
→ 如果 pdftoppm 缺失：允许继续编译，但 PDF 视觉验收记为 SKIPPED

如果没有 01-structure-analysis.md
→ 调用 math-structure-analysis

如果已有结构分析但没有 02-student-explanation.assignment.yaml
→ 调用 math-student-explanation-latex-data
→ 重新生成 YAML 时，必须删除旧 .reviewed 标记：
  python3 scripts/workflow_gate.py invalidate-review <yaml_path>

如果已有 02-student-explanation.assignment.yaml 但没有对应的 .reviewed
→ 调用 math-yaml-review 审查
→ 审查不通过：写 BLOCK 到 build/review-ledger.jsonl，报告问题，等待修复后重新生成
→ 审查通过：写 PASS 到 build/review-ledger.jsonl，并创建 .reviewed 标记，继续

如果已有讲解但没有 03-adaptive-practice.assignment.yaml
→ 调用 math-adaptive-practice-latex-data
→ 重新生成 YAML 时，必须删除旧 .reviewed 标记

如果已有 03-adaptive-practice.*.assignment.yaml 但没有对应的 .reviewed
→ 对每个 yaml 调用 math-yaml-review 审查
→ 审查不通过：写 BLOCK 到 build/review-ledger.jsonl，报告问题，等待修复后重新生成
→ 审查通过：写 PASS 到 build/review-ledger.jsonl，并创建 .reviewed 标记，继续

如果已有 assignment.yaml（且已 .reviewed）但没有 .tex
→ 先运行 scripts/workflow_gate.py check-render-gate --artifact-dir <dir> --artifact <yaml>
→ gate 不通过：停止渲染，报告缺失 PASS verdict 或 marker 过期
→ 运行 render_assignment.py

如果已有 .tex 但没有 .pdf
→ 运行 compile_latex.sh

如果编译失败
→ 摘要 build.log，反馈最小修复建议

如果所有 PDF 编译成功
→ 执行 PDF 验收：学生版答案泄露、禁用组件、明显跨页断裂、教师版答案区完整性
→ 如果视觉工具缺失：在 manifest 中记录 SKIPPED 和原因
→ git add 该专题目录下的交付物（.md/.tex/.pdf）
→ git commit -m "[artifacts] <学生名>/<话题>: <简述>"
→ 若本回合也修改了 skill/脚本/模板，另做一次 [workflow] commit

如果 PDF 已生成且没有阻断错误
→ 启动 subagent 使用 math-homework-review 审核完整 artifact 目录
→ 必须生成 review/final-homework-review.md 和 review/final-homework-review.json
→ 输出五项快速印象：完整性、数学正确性、结构分析、讲解质量、练习设计
→ 没有 final-homework-review.json 时，不得宣称 pipeline 完成
```

### Git Commit 格式

完成编译后必须 git commit。commit message 开头用方括号标注变更类别：

```text
[artifacts] <学生名>/<话题>: <简述>
[documents] <scope>: <简述>
[workflow] <scope>: <简述>
```

例：
- `[artifacts] 陆子辰/两圆位置关系: 讲解与练习`
- `[documents] 高一/wechat: 下载文章图片与 OCR 输入`
- `[workflow] feat(latex): solution block 替代 dual_explanation`

artifacts commit 只 add 该专题目录（`.md/.tex/.pdf`，`build/` 已被 `.gitignore` 排除）。
documents commit 只 add 文档采集、下载、OCR 输入输出相关文件（如 `documents/`）。
workflow commit 只 add 修改过的 skill/脚本/模板文件。
三类变更不要混在同一次 commit 中。

### Review 标记规则

审查通过后，在 build/ 目录下创建空文件作为标记：

```text
02-student-explanation.reviewed                        → 对应 02-student-explanation.assignment.yaml
03-adaptive-practice.student.reviewed                  → 对应 03-adaptive-practice.student.assignment.yaml
03-adaptive-practice.teacher.reviewed                  → 对应 03-adaptive-practice.teacher.assignment.yaml
```

重新生成 YAML 时自动删除对应的 `.reviewed` 标记。

标记必须和 `build/review-ledger.jsonl` 中当前 YAML hash 的 PASS/PASS_WITH_NOTES verdict 对应。只存在 `.reviewed` 文件但没有 ledger 记录，不得放行渲染。

## 每阶段输出

完成每阶段后输出：

```text
✅ 当前阶段：[阶段名]
📄 产物路径：[文件路径]
🧾 Manifest：[run_manifest.json 更新状态]
➡️  下一步：[命令或说明]
⚠️  需要人工检查：是/否
```

最终审核阶段输出：

```text
✅ 当前阶段：Stage 6 作业审核
📄 审核对象：[artifact 目录]
🧑‍🏫 审核方式：subagent + math-homework-review
📝 审核印象：[通过 / 基本可用但需小修 / 建议回退重做]
➡️  下一步：[放行给学生 / 修复具体阶段 / 回退重新生成]
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

### Stage 6：快速审核
```
subagent 使用 math-homework-review 审核 artifacts/陆子辰/2026-05-19-一次函数面积/
```

## 失败处理

```text
如果 Stage 1 失败 → 报告题目理解问题，请求人工澄清
如果 Stage 2/3 失败 → 报告教学逻辑问题，回退到 Stage 1 重新分析
如果 Stage 4 失败 → 报告 YAML schema 错误，修复 YAML
如果 Stage 5 失败 → 摘要 build.log，修复模板或 LaTeX 内容
如果 Stage 6 发现明显问题 → 不直接修改产物，指出最可能需要回退的阶段
如果 preflight BLOCKED_ENVIRONMENT → 不继续渲染/编译，报告缺失依赖
如果 review ledger 缺失或 marker 过期 → 不继续渲染，重新运行 math-yaml-review
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
  → Stage 6: 启动 subagent，使用 math-homework-review 做五项快速审核
  → 输出最终报告 + 审核印象
```

## 不做事项

- 不直接生成题目内容
- 不直接写 LaTeX
- 主流程不做教学判断；最终审核判断交给 math-homework-review 子任务
- 不修改现有产物（除非明确要求重新生成）
