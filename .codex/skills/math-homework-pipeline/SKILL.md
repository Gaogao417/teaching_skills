---
name: math-homework-pipeline
description: "端到端调度器：判断当前产物缺哪一步，自动调用对应 skill 或脚本补齐；生成完成后启动独立审核子任务，使用 math-homework-review 给出含几何插图版式的快速质量印象。"
---

# math-homework-pipeline

## 职责

端到端调度器。不直接写题目，不直接写 LaTeX。只判断当前产物缺哪一步，调用对应 skill 或脚本。生成完成后，启动一个独立审核子任务，使用 `math-homework-review` 给用户一个简短质量印象。

## 触发与跳过

使用本 skill：

- 用户给了一道数学题，要求生成完整作业 PDF
- 用户提到 homework-pipeline 或 pipeline
- 用户说“帮我把这道题做成作业”
- 用户要求端到端生成

跳过本 skill：

- 用户只要求分析结构（使用 `math-structure-analysis`）
- 用户只要求生成 YAML（使用对应 latex-data skill）
- 用户只要求渲染 PDF（使用 `math-assignment-latex`）

## 调度规则

```text
如果没有 01-structure-analysis.md
→ 调用 math-structure-analysis

如果已有结构分析但没有 02-student-explanation.assignment.yaml
→ 调用 math-student-explanation-latex-data

如果已有讲解但没有 03-adaptive-practice.assignment.yaml
→ 调用 math-adaptive-practice-latex-data

如果题目是几何题，且结构分析或 YAML 判定需要插图
→ 先收集每道题的题目级 diagram job：choice/fillin/problem part 各自独立 job_id
→ 并行调用 math-geometry-diagram-renderer，生成 diagram/jobs/<job_id>/rendered/prompt.png 或 solution.png
→ 检查每个 job 的 workflow_events.jsonl 与 round 日志
→ 在讲义/练习 YAML 中插入显式 width 的 diagram_col、diagram_row 或 answer_space.diagram_col

如果已有 assignment.yaml 但没有 .tex
→ 运行 render_assignment.py

如果已有 .tex 但没有 .pdf
→ 运行 compile_latex.sh

如果编译失败
→ 摘要 build.log，反馈最小修复建议

如果 PDF 已生成且含 diagram_col、diagram_row、answer_space.diagram_col 或 diagram block
→ 使用 pdftoppm 或等价工具预览含图页面
→ 检查选择题图栏、填空图行、大题每问图栏是否符合排版契约，caption 是否只写观察动作
→ 必要时回到 YAML 调整 width、diagram_col/diagram_row 位置后重新渲染编译

如果 PDF 已生成且没有阻断错误
→ 启动 subagent 使用 math-homework-review 审核完整 artifact 目录
→ 输出六项快速印象：完整性、数学正确性、结构分析、讲解质量、练习设计、几何插图与版式
```

几何题额外规则：

- 不要把几何题的 `diagram_request_packet.needs_diagram` 轻易写成 `false`；若不用图，必须有明确教学理由。
- YAML writer 必须先做插图判定：几何大题一律需要图；几何题已知条件数大于 3 默认需要图；题干出现“如图/图中/下图”强制需要图。
- 练习题默认每道题单独画图：每个需要图的题必须有唯一 `diagram_job_id`，路径形如 `diagram/jobs/<job_id>/rendered/prompt.png`；多题复用必须显式写 `reuse_from`。
- 选择题用 `diagram_col`，选项竖排且图在右栏；填空题先排题干，再在题后使用 `diagram_row` 同组并排放图；解答题用每问 `answer_space.parts[].diagram_col`，答题区左侧、图栏右侧。
- prompt 图必须 clean：不画辅助线、不写推理标注、不泄露答案；solution 图才允许 annotated 辅助线和解题标注。
- 所有图片字段不允许依赖模板默认宽度。选择题图栏优先 `0.28\\linewidth` 到 `0.32\\linewidth`，填空图行单图优先 `0.20\\linewidth` 到 `0.25\\linewidth`，解答题图栏优先 `0.30\\linewidth` 到 `0.34\\linewidth`。
- 几何图 workflow 使用本仓库内置 `scripts/geometry_diagram_workflow`。缺依赖时，先安装并验证 `scripts/geometry_diagram_workflow/requirements.txt`，不要直接 fallback。

编译前 diagram contract check：

- 查 YAML 中所有几何 choice/fillin/problem/short_answer；若满足上述插图触发规则但没有对应结构化图片字段，先修 YAML。
- choice 只接受 `diagram_col` / `prompt_diagram`；fillin 只接受后置相邻 `diagram_row`；problem/short_answer 只接受 `answer_space.diagram_col` 或 `answer_space.parts[].diagram_col`。
- 如果多个 block 引用同一个 `image_path` 且没有 `reuse_from`，判为 workflow 错误并回退重画。
- `variant: prompt` 必须搭配 `disclosure_policy: clean`；`variant: solution` 必须只出现在讲解、解析或教师版解答中。
- 所有 `image_path` 必须存在且相对最终 `.tex` 可访问。

## 每阶段输出

完成每阶段后输出：

```text
✅ 当前阶段：[阶段名]
📄 产物路径：[文件路径]
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

### Stage 6：快速审核
```
subagent 使用 math-homework-review 审核 artifacts/linear-function/
```

## 失败处理

```text
如果 Stage 1 失败 → 报告题目理解问题，请求人工澄清
如果 Stage 2/3 失败 → 报告教学逻辑问题，回退到 Stage 1 重新分析
如果 Stage 4 失败 → 报告 YAML schema 错误，修复 YAML
如果 Stage 5 失败 → 摘要 build.log，修复模板或 LaTeX 内容
如果 Stage 6 发现明显问题 → 不直接修改产物，指出最可能需要回退的阶段
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
  → Stage 6: 启动 subagent，使用 math-homework-review 做含几何插图版式的快速审核
  → 输出最终报告 + 审核印象
```

## 不做事项

- 不直接生成题目内容
- 不直接写 LaTeX
- 主流程不做教学判断；最终审核判断交给 math-homework-review 子任务
- 不修改现有产物（除非明确要求重新生成）
