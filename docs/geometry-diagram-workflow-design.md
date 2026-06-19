# 几何画图闭环工作流设计

> Status: historical design notes. The active output path is TikZ-only:
> `GeometryRenderSpec -> TikzDiagramSpec -> fragment.tex -> renderer_result.json`,
> with gate/resolver consuming `RendererBindingManifest` rather than image
> artifacts.

## 0. 当前实现与测试入口

当前实现层面的主结论：

- `GeometricScene-Builder` 外部仓库不再是默认运行依赖；其 agentic `workflow.py`、Wolfram 包和 prompt skills 已迁入 `scripts/diagram_workflow/geometry_diagram_workflow/`。
- 模型继续负责写 Wolfram `GeometricScene`，workflow 负责注入 skill、执行 Wolfram、抽取坐标、编译 renderer spec、渲染和记录日志。
- solution 图采用二阶段逻辑：先用 prompt job 求原图点坐标，再用 `Join[Thread[basePoints -> baseCoords], auxPoints]` 锁定原点并追加辅助约束，保证 annotated 图不重造构型。

为了缩短调试反馈，当前测试入口从 plan YAML 开始跑到图片产物：

```text
assignment.plan.yaml 中的 diagram_slot 字段
  -> collect_diagram_jobs.py 收集题目级 diagram jobs
  -> 写 build/diagram/jobs/<job_id>/request.json（DiagramJobRequest v2）
  -> run_diagram_batch.py 运行本仓库内置 scripts/diagram_workflow/geometry_diagram_workflow
  -> 生成 final_renderer_spec.json
  -> render_geometry_spec.py 输出 rendered/prompt.png 或 rendered/solution.png
  -> build_diagram_artifacts.py / check_diagram_gate.py 汇总和验收
```

这个测试入口不定义 workflow 的业务职责，也不负责结构分析、题目生成、LaTeX 排版或 PDF 编译。调试几何插图时可运行：

```bash
python3 tests/test_diagram_workflow_e2e.py --out-dir build/e2e-diagram-test
```

## 1. 背景与核心结论

当前有两个相关系统：

- `teaching_skills`：面向教学内容生成，已有结构分析、学生讲解、练习生成、学生诊断等 skill。
- `GeometricScene-Builder`：面向 Wolfram `GeometricScene` 的几何场景生成、渲染、批量 benchmark 与评分分析。

新的需求不是简单“给几何题加一张图”，而是要形成一个可重复、可评价、可重试的画图闭环：

```text
题目信息
  -> agent 生成 GeometricScene 或坐标图 spec
  -> Wolfram 只求解坐标和几何实例
  -> 输出 geometry-render-spec/v1
  -> teaching agent 调本地 renderer 生成 printable PNG
  -> renderer 自检；可选便宜 VLM 或本地 VLM 评价图片是否可用
  -> 若不可用，返回缺陷并补充 renderer/约束
  -> 最多重试 3 次
  -> 输出 final_renderer_spec.json、renderer_result.json、图片、日志和失败原因
```

核心结论：

1. 原 `teaching_skills` 工作流不是画图闭环，它主要闭环在教学文本 artifact 与自检上。
2. 原 `GeometricScene-Builder` 也不是单题自动画图闭环，它更像批量 benchmark lab。
3. 新系统不应废弃原 skills 和 tools，而应把 skills 显式加载为 prompt/context assets。
4. LangGraph 不是刚需。MVP 可以先用 `opencode agent + skills + tools + 简单 Python loop` 组织闭环，成本更低，也更贴近现有仓库。
5. 无论使用 opencode 前端、普通 Python loop 还是 LangGraph，`.opencode/skills` 都必须被显式读取并注入 prompt/context。
6. 推荐把 `GeometricScene-Builder` 升级为“几何画图引擎”，保留原 benchmark 模式，新增单题 agentic diagram workflow。
7. `GeometricScene-Builder` 默认只产 solved renderer spec；Wolfram `Graphics -> PNG` 只保留为可选调试/评估路径。
8. `teaching_skills` 中只有 LaTeX/YAML writer 通过 `math-geometry-diagram-renderer` 处理几何配图；pipeline、HTML writer、LaTeX 渲染器都不直接知道 GSB/renderer 细节。

## 2. 原系统完整度评估

### 2.1 teaching_skills

现有默认链路：

```text
math-structure-analysis
  -> math-student-explanation-html
  -> math-adaptive-practice-html
```

可选链路：

```text
student response
  -> math-student-response-diagnosis
  -> math-adaptive-practice-html
```

优点：

- 有清晰的教学 artifact 交接。
- `01-structure-analysis.md` 能固定数学事实、canonical solution、学生卡点和变式原则。
- `02-student-explanation.html` 和 `03-adaptive-practice.html` 有明确的输出格式和自检要求。

不足：

- 没有图像生成节点。
- 没有 diagram request/schema。
- 没有图像可用性评价器。
- 没有基于评价反馈的自动重试。
- 坐标系、函数图、合成几何图没有路由区分。

结论：`teaching_skills` 是教学编排层，不是画图执行层。它需要新增“图需求提取”和“图产物消费”能力。

### 2.2 GeometricScene-Builder

原链路更接近：

```text
problems.jsonl + sweep.yaml
  -> run_sweep
  -> results.jsonl + images
  -> human rating
  -> report/analyze
```

优点：

- 有 Wolfram 执行、超时控制、图片输出、结果日志。
- 有 constraint recipes、fail type、人工评分、报告分析。
- 有一批 Wolfram 和 GeometricScene 相关 skills，可作为 agent 生成代码的强约束上下文。

不足：

- `problem-constraint-designer` 明确更像人工指南，不是自动生成器。
- 原评分主要是人工打分，不是在线自动 VLM judge。
- 原目标是比较约束配方，不是为单道题产出最适合教学的图。
- 没有稳定的 renderer spec 输出契约。
- 没有和教学 artifact 的接口。

结论：`GeometricScene-Builder` 的定位需要升级，但不应推倒。它应从 benchmark lab 扩展为 geometry diagram engine。

### 2.3 当前新增 workflow.py 原型

当前已有原型方向：

```text
generate_scene_node
  -> solve_wolfram_node
  -> compile_renderer_spec_node
  -> optional_evaluate_debug_image_node
  -> update_history_node
  -> finalize_node
```

它已经接近新需求，但仍有关键缺口：

- 尚未显式加载 `.opencode/skills`。
- renderer spec 主要由 agent 生成，尚未从真实 Wolfram instance 坐标抽取。
- 合成几何与坐标几何未分流。
- CLI 是入口，但还没有稳定 Python API。
- 评价模型返回的 defects 尚未结构化到 constraint revision policy。

## 3. 推荐架构

推荐分为两层产品能力和一层纯执行内核：

```text
teaching_skills
  教学编排层

GeometricScene-Builder
  画图工作流层

GeometricScene-Builder core
  渲染与 spec 执行内核
```

### 3.1 教学编排层：teaching_skills

职责：

- 判断一道题是否需要图。
- 从结构分析 artifact 中提取图形对象、教学重点、坐标/合成几何倾向。
- 生成 `DiagramRequest`。
- 调用画图引擎。
- 当需要在 assignment YAML 中插入几何图时，调用 `math-geometry-diagram-renderer` 生成最终 PNG。
- 在讲解或练习 YAML 中只消费最终 `diagram.image_path`。
- 当图生成失败时，选择降级策略，例如使用题干文字描述、简单手写 SVG、或保留空图位。

不负责：

- 不直接写 Wolfram `GeometricScene`。
- 不直接调用 Wolfram。
- 不直接调用 VLM。
- 不实现 GeometricScene/约束重试逻辑。

### 3.2 画图工作流层：GeometricScene-Builder

职责：

- 提供 `run_diagram_workflow(request)` Python API。
- 保留 CLI wrapper 用于调试和批处理。
- MVP 使用普通 Python loop 固化画图闭环；LangGraph 只作为后续复杂编排的可选升级。
- opencode agent 前端可以通过提示词、agent、skills 和 tools 低成本驱动同一套闭环。
- 显式加载 `.opencode/skills/<name>/SKILL.md` 注入 prompt。
- 让 agent 生成或修正 `GeometricScene`/坐标图 spec。
- 调用 Wolfram 求解几何实例并抽取坐标。
- 输出 `geometry-render-spec/v1` 的 `final_renderer_spec.json`。
- 可选调用 Wolfram debug PNG 与便宜 VLM/本地 VLM 评价图片。
- 根据 defects 组织重试，最多 3 次。
- 输出完整日志和最终产物。

不负责：

- 不生成学生讲解页。
- 不判断教学节奏。
- 不决定某个学生下一步练什么。

### 3.3 渲染与 spec 执行内核：GSB core

职责：

- 安全校验 Wolfram code。
- 进程隔离执行 Wolfram。
- 超时控制和 fail type 分类。
- 从求解结果抽取真实坐标。
- 将 instance 转为 `geometry-render-spec/v1`。
- 对坐标图执行确定性 spec 输出，不强行路由到 GeometricScene。
- 默认输出 spec、metrics；PNG/SVG 只作为可选 debug 产物。

原则：

- 尽量无 LLM。
- 可单元测试。
- 可复现。
- 所有失败都结构化记录。

## 4. 工作流设计

### 4.1 主流程

```text
DiagramRequest
  -> prepare_request
  -> load_skills_context
  -> route_diagram_type
  -> generate_candidate
  -> solve_candidate
  -> compile_renderer_spec
  -> optional_debug_render_or_evaluate
  -> usable?
       yes -> finalize
       no  -> revise_constraints_or_spec
             -> retry, until max_retries
  -> teaching_renderer_stage
  -> DiagramPackage
```

### 4.2 轻量工作流节点

MVP 不要求 LangGraph。下面这些应先实现为普通 Python 函数和一个简单 retry loop；如果后续需要 checkpoint、人工介入、并发队列或服务化，再把这些函数映射为 LangGraph 节点。

建议步骤：

- `prepare_request`
  - 校验输入 schema。
  - 规范化题目文本、教学重点、对象提示。

- `load_skills_context`
  - 从 GSB 的 `.opencode/skills` 读取技能文档。
  - 按节点装配不同 skill context。

- `route_diagram_type`
  - 判断 `synthetic_geometry`、`coordinate_geometry`、`function_graph`、`hybrid`。
  - 坐标图不要强行走 GeometricScene。
  - 函数图默认走 `wolfram_client` 或 `coordinate_renderer`，不复用合成几何的点位求解逻辑。

- `generate_candidate`
  - 合成几何：agent 生成 `GeometricScene`。
  - 坐标几何：agent 生成解析对象、坐标点、直线/圆等对象和 renderer spec 草案。
  - 函数图：agent 生成函数表达式、定义域、视窗、坐标轴和关键点/交点对象；WolframClient 负责校验表达式、采样和计算关键点。

- `solve_candidate`
  - 合成几何：Wolfram 只求解 `GeometricScene` instance，抽取点坐标和几何对象。
  - 坐标几何：确定性解析坐标对象、视窗、坐标轴和标注。
  - 函数图：WolframClient 计算采样点、交点、零点、极值等可选对象，并返回可渲染 `samples`；最终图片由 Python renderer 生成。

- `compile_renderer_spec`
  - 输出 `final_renderer_spec.json`，schema 为 `geometry-render-spec/v1`。
  - 综合几何包含 `points`、`segments`、`polygons`、`markers`、`labels`、`teaching_focus`。
  - 坐标/函数图包含 `viewport`、`axes`、`objects`、`functions`、`samples`、`teaching_focus`。

- `optional_debug_render_or_evaluate`
  - 仅当 `wolfram_render_image=true` 时，允许 Wolfram debug PNG 和 cheap VLM/local VLM。
  - 默认 `wolfram_render_image=false`，评价阶段走 `spec_only` 成功模式，不要求 vision image。

- `revise_constraints_or_spec`
  - 将缺陷变为下一轮约束。
  - 示例：点重合、角太小、标签放不下、坐标轴范围不合适、视觉上暗示错误性质。

- `finalize`
  - 输出最终 `final_diagram_spec.json`、`final_renderer_spec.json`、scene code、评价结果、attempt logs。
  - `workflow_result.json.final_renderer_spec` 固定指向 `final_renderer_spec.json`。

- `latex_writer_diagram_skill`
  - 仅由 `math-student-explanation-latex-data` 或 `math-adaptive-practice-latex-data` 触发。
  - 调用 `math-geometry-diagram-renderer` 生成 printable PNG。
  - YAML 只插入 `type: diagram` + `image_path`；renderer 细节不进入其它 skills。

### 4.3 重试策略

默认 `max_retries = 3`。

注意这里需要定义清楚是“最多 3 次调整”还是“最多 3 次总尝试”。建议：

```text
max_retries = 3 表示失败后最多修正 3 次
总尝试数最多为 4 次：initial + 3 retries
```

每轮必须保存：

- candidate input
- generated scene/spec
- render result
- image path
- VLM result
- defects
- next feedback

## 5. Skills 集成方式

无论由 opencode agent 前端、普通 Python loop 还是 LangGraph 编排，运行时都不会天然理解 `.opencode/skills`。应实现 skill loader：

```text
load_skill(name)
  -> read .opencode/skills/<name>/SKILL.md
  -> truncate/summarize if too long
  -> inject into node prompt
```

推荐 skill 分配：

### 5.1 生成 GeometricScene

加载：

- `wolfram-geometricscene-reference`
- `wolfram-schema-first-param-types`
- `dimensionless-constraints-library`
- `wolfram-python-integration-patterns`
- `windows-encoding-compatibility`

作用：

- 减少 Wolfram 参数类型错误。
- 避免在 `GeometricScene` 中错误使用坐标向量运算。
- 提供角度下界、边长比、高度比等约束策略。

### 5.2 评价图像

加载：

- `human-rating-loop`
- `tool-output-standards`

作用：

- 把原人工评分经验转为 VLM 评价 rubric。
- 要求返回机器可读 JSON。

### 5.3 输出契约

加载：

- `agent-io-schema`
- `tool-output-standards`

作用：

- 固定 `DiagramRequest`、`DiagramPackage`、`geometry-render-spec/v1` 输出。
- 保证调用方可以稳定消费。

## 6. 数据契约

### 6.1 DiagramRequest

建议 JSON：

```json
{
  "request_id": "p0001-diagram",
  "problem_id": "p0001",
  "problem_text": "在三角形 ABC 中，AB=AC=5，BC=6，求...",
  "structure_artifact_path": "artifacts/xxx/01-structure-analysis.md",
  "grade_or_topic": "初中几何",
  "teaching_focus": [
    "看清等腰三角形的底边和高",
    "突出辅助线 AD"
  ],
  "diagram_intent": "student_explanation",
  "diagram_type": "auto",
  "objects_hint": {
    "points": ["A", "B", "C", "D"],
    "segments": [["A", "B"], ["A", "C"], ["B", "C"], ["A", "D"]],
    "constraints": ["AB=AC", "AD perpendicular BC", "D is midpoint of BC"]
  },
  "coordinate_hint": {
    "required": false,
    "axes": null,
    "x_range": null,
    "y_range": null
  },
  "output_preferences": {
    "image_format": "png",
    "spec_format": "geometry-render-spec/v1",
    "label_language": "zh-CN",
    "allow_schematic_not_to_scale": true,
    "wolfram_render_image": false
  },
  "model_config": {
    "text_model": "openai-compatible-model",
    "vision_model": "cheap-vlm-or-local-vlm",
    "api_key_env": "OPENAI_API_KEY",
    "base_url": "http://localhost:8000/v1"
  },
  "max_retries": 3
}
```

### 6.2 DiagramPackage

建议 JSON：

```json
{
  "status": "ok",
  "request_id": "p0001-diagram",
  "diagram_type": "synthetic_geometry",
  "workflow_result": "diagram/workflow_result.json",
  "diagram_spec_path": "final_diagram_spec.json",
  "renderer_spec_path": "final_renderer_spec.json",
  "renderer_result_path": "renderer_result.json",
  "image_path": "rendered/diagram.png",
  "scene_code_path": "final_geometric_scene.wl",
  "renderer_status": "ok",
  "evaluation": {
    "usable": true,
    "score": 4,
    "defects": [],
    "model": "cheap-vlm-or-local-vlm"
  },
  "attempt_count": 2,
  "attempts": [
    {
      "round_index": 0,
      "status": "failed",
      "defects": ["A and D overlap visually", "altitude label too close to BC"]
    },
    {
      "round_index": 1,
      "status": "ok",
      "defects": []
    }
  ],
  "fallback": null
}
```

失败时：

```json
{
  "status": "failed",
  "error": "max_retries_exhausted",
  "fallback": {
    "type": "textual_diagram_description",
    "content": "建议教师手动画等腰三角形 ABC，并从 A 向 BC 作高 AD。"
  }
}
```

### 6.3 geometry-render-spec/v1

`geometry-render-spec/v1` 是教学渲染层可消费的中间表达。综合几何不绑定 Wolfram 前端；函数图可以由 WolframClient 计算/采样，最终仍把可审计的 spec 写出来，并由 Python renderer 输出 SVG/PNG。`engine: wolfram_plot` 只保留为兼容 alias。

综合几何最小结构：

```json
{
  "schema_version": "geometry-render-spec/v1",
  "type": "synthetic_geometry",
  "canvas": {
    "width": 640,
    "height": 420,
    "coordinate_system": "diagram"
  },
  "points": {
    "A": [0, 3],
    "B": [-2, 0],
    "C": [2, 0]
  },
  "segments": [
    {"from": "A", "to": "B"},
    {"from": "A", "to": "C"},
    {"from": "B", "to": "C"}
  ],
  "polygons": [
    {"points": ["A", "B", "C"], "fill": "none"}
  ],
  "markers": [
    {"type": "equal_ticks", "segments": [["A", "B"], ["A", "C"]]},
    {"type": "right_angle", "at": "D", "arms": ["A", "B"]}
  ],
  "labels": {
    "A": {"text": "A", "dx": 0, "dy": -24}
  },
  "teaching_focus": [
    "highlight_altitude_AD"
  ]
}
```

坐标图应使用真实数学坐标和 viewport；点、直线、圆、多边形等对象放入 `objects`：

```json
{
  "schema_version": "geometry-render-spec/v1",
  "type": "coordinate_geometry",
  "viewport": {
    "x_min": -2,
    "x_max": 8,
    "y_min": -2,
    "y_max": 8,
    "preserve_aspect": true
  },
  "axes": {
    "x": true,
    "y": true,
    "grid": true
  },
  "objects": [
    {"type": "point", "id": "A", "x": 1, "y": 2, "label": "A"},
    {"type": "line", "id": "l1", "equation": "y=2x+1"},
    {"type": "polygon", "points": ["A", "B", "C"], "fill": "light"}
  ]
}
```

函数图在坐标图基础上增加 `functions` 和可选 `samples`。`expression_latex` 面向审查和题面，`expression_wl` 面向 Mathematica；二者至少一个必须存在。

```json
{
  "schema_version": "geometry-render-spec/v1",
  "type": "function_graph",
  "viewport": {
    "x_min": -2,
    "x_max": 6,
    "y_min": -6,
    "y_max": 12,
    "preserve_aspect": true
  },
  "axes": {
    "x": true,
    "y": true,
    "grid": true,
    "show_ticks": true,
    "x_label": "x",
    "y_label": "y"
  },
  "functions": [
    {
      "id": "f",
      "variable": "x",
      "expression_latex": "2x-1",
      "expression_wl": "2*x - 1",
      "domain": {"min": -2, "max": 6},
      "label": "y=2x-1"
    }
  ],
  "samples": {
    "f": [[-2, -5], [0, -1], [2, 3], [6, 11]]
  },
  "objects": [
    {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"}
  ],
  "teaching_focus": ["读图判断点是否在函数图像上"]
}
```

## 7. 合成几何与坐标几何分流

### 7.1 合成几何

适合：

- 三角形、圆、平行、垂直、角平分线、中线、高线。
- 重点是几何关系，不要求严格坐标轴。

路径：

```text
agent writes GeometricScene
  -> Wolfram RandomInstance
  -> extract point coordinates
  -> compile final_renderer_spec.json
  -> teaching renderer outputs renderer_result.json + rendered/diagram.png
```

### 7.2 坐标几何

适合：

- 平面直角坐标系。
- 函数图像。
- 点坐标、交点、面积、距离。
- 需要坐标轴刻度和网格。

路径：

```text
agent extracts analytic objects
  -> compile geometry-render-spec/v1
  -> deterministic coordinate renderer in teaching stage
  -> optional VLM checks readability
  -> revise viewport/labels/object emphasis
```

重要原则：

- 坐标题不要默认强塞进 `GeometricScene`。
- 坐标图的正确性主要靠解析计算和确定性 renderer，而不是随机实例。
- Wolfram 可以作为计算校验器，但不应成为所有坐标图的唯一入口。

### 7.3 函数图

适合：

- 一次函数、二次函数、反比例函数、三角函数等图像。
- 给定点是否在函数图像上。
- 函数交点、零点、极值、单调区间、面积读图。
- 需要坐标轴、网格、刻度和函数曲线同时出现。

推荐路径：

```text
agent extracts functions / viewport / key points
  -> Python calls WolframClient to validate expressions and compute samples/key points
  -> compile function_graph geometry-render-spec/v1
  -> deterministic coordinate renderer outputs SVG/PNG
  -> gate checks axis range, object references, clean/annotated policy
```

重要原则：

- `function_graph` 使用 `engine: wolfram_client` 或 `engine: coordinate_renderer`，不走 `geometric_scene`。
- prompt 图只画题干给出的函数、点、坐标轴和必要网格；不要用颜色或标注提前泄露判断结论。
- solution 图可以额外标零点、交点、辅助虚线、面积阴影或导数/单调性提示，但必须是教师版或讲解版。
- WolframClient 只负责数学计算，不生成 `.wl` 文件，也不把 Mathematica `Plot`/`ListPlot` 图片作为正式产物；`final_renderer_spec.json` 是复核、重渲染和 stale 检查的核心合同。

## 8. 为什么 agent 仍是核心作者

担心是合理的：如果 `GeometricScene-Builder` 只靠固定代码模板生成图，它很可能不如 agent 直接根据 skill 写 `GeometricScene`。

推荐策略：

```text
agent 负责表达意图和生成候选
GSB code 负责执行、校验、求解、spec 输出闭环
teaching renderer 负责最终 PNG 产物和本地自检
skills 负责给 agent 提供领域约束
```

也就是说，GSB 不应变成“固定规则生成器”或“业务 PNG 渲染器”，而应变成“带工具、带评测、带重试的 solved-spec runtime”。

这样可以同时获得：

- agent 的题目理解能力。
- Wolfram 的几何求解能力。
- renderer 的跨平台、可测试产图能力。
- 可选 VLM 的视觉质量反馈。
- 代码层的可复现和安全控制。

## 9. 集成方案比较

### 方案 A：opencode agent/skill + tools 前端编排

```text
opencode agent
  -> read skills
  -> call generate/render/evaluate tools
  -> inspect defects
  -> revise prompt/constraints
  -> stop after max_retries
```

优点：

- 改动最小，最贴近现有 `.opencode/agents`、`.opencode/skills` 和 `.opencode/tools`。
- 适合快速验证 prompt、skill、VLM rubric 和约束修正策略。
- agent 可以直接利用现有 skills，不必先重构为完整 package。
- 对探索阶段很友好，便于人工观察每轮失败原因。

缺点：

- 闭环约束偏软，依赖 agent 严格遵守提示词。
- 批量运行、断点恢复、失败分类和日志一致性不如代码固化。
- 不适合长期作为唯一生产路径。

适用：

- 第一阶段快速验证。
- 小批量人工监督生成。
- 调试 skill 和评价标准。

### 方案 B：简单 Python loop 固化闭环

```text
run_diagram_workflow(request)
  -> load_skills
  -> generate
  -> render
  -> evaluate
  -> revise
  -> retry
  -> finalize
```

优点：

- 不引入 LangGraph，也能强制 `max_retries`、结构化日志和输出契约。
- 比纯 agent 编排稳定，成本又明显低于 LangGraph。
- 容易暴露为 CLI、opencode tool 或 Python API。
- 更适合作为 MVP 主线。

缺点：

- 复杂分支、checkpoint、人工介入和并发队列需要后续自行补。
- 状态可视化不如 LangGraph。

推荐：

- 作为当前 MVP 的主实现。

### 方案 C：CLI artifact 交互

```text
teaching_skills writes request.json
  -> python -m core.workflow --request request.json --out ...
  -> teaching_skills reads workflow_result.json
```

优点：

- 调试清楚。
- 与现有 GSB 工具风格一致。
- 适合跨仓库原型和离线批量生成。

缺点：

- 类型约束弱。
- 进程开销更大。
- teaching 层需要处理文件路径和失败边界。

定位：

- CLI 应作为 thin wrapper，而不是唯一正式接口。

### 方案 D：Python package API

```python
from geometric_scene_builder.workflow import run_diagram_workflow

package = run_diagram_workflow(request)
```

优点：

- 类型和异常更容易管理。
- teaching 层集成更自然。
- CLI 和 opencode tool 都可以复用同一套 API。

缺点：

- 需要整理 GSB package 结构。
- 需要处理跨仓库依赖。

推荐：

- MVP 后作为主线集成方式。

### 方案 E：LangGraph

```text
StateGraph
  -> generate
  -> render
  -> evaluate
  -> revise/finalize
```

优点：

- 适合复杂分支、checkpoint、人工介入、长任务恢复和状态追踪。
- 后续服务化、多模型路由、队列化时更有价值。

缺点：

- 当前阶段会增加框架成本。
- 不能自动解决 skills 注入问题，仍需 skill loader。
- 若节点逻辑尚未稳定，过早上 LangGraph 会让调试变重。

定位：

- 后续升级选项，不作为 MVP 必需项。

### 方案 F：本地 HTTP service

```text
POST /diagram-workflow
  -> DiagramPackage
```

优点：

- 易并发。
- 易接本地 VLM。
- 易做缓存和队列。

缺点：

- 现在偏重。
- 需要服务生命周期管理。

适用：

- 后续有多任务队列、本地模型池、Web UI 时。

### 方案 G：把 GSB 合进 teaching_skills

优点：

- 表面上仓库更少。

缺点：

- 教学逻辑和渲染执行耦合。
- Wolfram/VLM/图像日志污染教学仓库。
- 后续难以复用 benchmark。

不推荐。

## 10. 推荐落地路线

### Phase 0：设计文档

产物：

- 本文档。

目标：

- 固定系统边界和数据契约。
- 明确 LangGraph 不是 MVP 必需项。

### Phase 1：opencode 前端验证

在 `GeometricScene-Builder` 中完成：

- 新增或整理 agentic diagram workflow skill。
- 增加 opencode tool：生成候选、渲染候选、评价图片、运行一次完整闭环。
- 让 opencode agent 能按提示词执行：
  - 读取题目信息。
  - 读取 GSB skills。
  - 生成 `GeometricScene` 或坐标图 spec。
  - 调工具求解并输出 renderer spec。
  - 可选调 debug render/VLM 评价。
  - 根据 defects 最多修正 3 次。
- 保留原 `run_sweep`、`build_report`、`launch_rater`。

验收：

- 不引入 LangGraph 也能通过 agent/tool 跑通一题。
- 每轮产物和 defects 有文件日志。

### Phase 2：简单 Python loop 固化闭环

在 `GeometricScene-Builder` 中完成：

- 整理 `run_diagram_workflow(request, out_dir)` Python API。
- CLI wrapper 调同一个 API。
- 实现 skill loader。
- 强制 `max_retries`。
- `workflow_result.json` 中记录 `skills_used`、attempts、defects、final status。
- 修正 Wolfram path normalization。

验收：

- 即使不用 opencode agent 手动接力，也能一条命令跑完整闭环。
- 输出契约稳定。

### Phase 3：合成几何闭环

完成：

- agent 生成 `GeometricScene`。
- Wolfram 求解并抽取坐标。
- 生成 `final_renderer_spec.json`。
- spec-only 成功路径默认不要求 PNG。
- 可选 Wolfram debug PNG/VLM 评价。
- defects 驱动重试。
- 最终输出 `geometry-render-spec/v1`。

验收：

- 一道三角形题能在 1 到 4 次尝试内生成可用图。
- 每轮日志可追踪。
- 失败时有结构化原因。

### Phase 4：坐标图路径

完成：

- 坐标题路由。
- 坐标对象 schema。
- 坐标 `geometry-render-spec/v1`。
- teaching 阶段确定性 renderer。
- 视窗、坐标轴、标签、网格自动调整。
- 可选 VLM 检查坐标轴和对象可读性。

验收：

- 函数交点、三角形面积、点坐标类题目能稳定生成图。
- 坐标轴刻度可读。
- 不把坐标图错误转成随机合成几何图。

### Phase 5：teaching_skills 集成

在 `teaching_skills` 中完成：

- `math-structure-analysis` 增加可选 `diagram_request_packet`。
- 新增 `math-geometry-diagram-renderer`，只给 LaTeX/YAML writer 使用。
- `math-student-explanation-latex-data` 可在需要几何配图时调用该 skill，并只插入最终 `diagram.image_path`。
- `math-adaptive-practice-latex-data` 可在练习题确需配图时调用该 skill，并确保图片不泄露答案。
- 图失败时有降级显示策略。

### Phase 6：评测与回归

完成：

- 几何题小集合。
- 坐标题小集合。
- VLM 判分日志。
- 人工抽检对比。
- benchmark 模式继续可用。

### Phase 7：可选 LangGraph 升级

只有当出现以下需求时再升级：

- 长任务 checkpoint 和恢复。
- 人工介入节点。
- 多模型路由。
- 并发队列。
- 服务化状态追踪。

升级方式：

- 复用 Phase 2 中已经稳定的 Python 函数。
- 将 `generate`、`render`、`evaluate`、`revise`、`finalize` 映射为 LangGraph 节点。
- 保持 `DiagramRequest` 和 `DiagramPackage` 不变。

## 11. 文件组织建议

### teaching_skills

```text
docs/
  geometry-diagram-workflow-design.md

artifacts/<problem-slug>/
  01-structure-analysis.md
  build/diagram/jobs/<job_id>/request.json
  02-student-explanation.html
```

### GeometricScene-Builder

```text
core/
  workflow.py              # simple Python loop + CLI wrapper
  diagram_request.py
  skill_loader.py
  coordinate_renderer.py
  spec_export.py
  wolfram_render.py

.opencode/tools/
  geo-tools.ts             # run_diagram_workflow plus existing benchmark tools

.opencode/skills/
  agentic-geometry-workflow/
    SKILL.md

examples/
  workflow_request_triangle.json
  workflow_request_coordinate.json
```

## 12. 评价标准

VLM 评价不应尝试完整证明数学正确性，主要负责视觉可用性：

- 图中对象是否与题目匹配。
- 是否退化。
- 关键点、线、角、区域是否可见。
- 标签是否可放置、可读。
- 坐标轴和刻度是否可读。
- 图是否暗示了题目没有给出的特殊性质。
- 讲解重点是否被突出。

建议评分：

```text
5：可直接用于学生讲解
4：小瑕疵，但可用
3：基本对象可见，但需要人工调整
2：明显误导或难读
1：不可用或渲染失败
```

默认 `usable = score >= 4`。

## 13. 安全与稳定性

Wolfram code 必须限制：

- 禁止文件写入、删除、进程执行、网络访问。
- 禁止 `Get` 加载非白名单路径。
- 每轮有 soft timeout 和 hard watchdog timeout。
- Wolfram worker 独立进程执行。
- 只允许输出到 workflow 指定目录。

模型调用必须限制：

- API key 只从环境变量读取。
- 结果必须是 JSON。
- 无效 JSON 进入结构化失败。
- 每轮 prompt 和 response 存档，便于复盘。

## 14. 开放问题

仍需确认：

1. 坐标图是否需要支持函数解析式直接绘制。
2. VLM 评价用云端 cheap model 还是本地 model，默认 base_url 如何配置。
3. `max_retries=3` 是否按“3 次修正”解释。
4. teaching HTML 中图片是内嵌 base64，还是使用相对路径。
5. 何时需要从简单 Python loop 升级到 LangGraph。
6. SVG/PDF 是否需要成为 renderer 的正式输出格式；当前默认交付为 PNG。

## 15. 最小可验收版本

MVP 应满足：

- `teaching_skills` 能通过 collector/batch 产生 `DiagramJobRequest` v2。
- GSB 能读取 v2 request，并完成合成几何图闭环。
- MVP 不要求 LangGraph；可以由 opencode agent/tool 或简单 Python loop 驱动。
- 最多 3 次修正。
- 成功时输出：
  - `final_diagram_spec.json`
  - `final_renderer_spec.json`
  - `renderer_result.json`
  - `rendered/diagram.png`
  - `final_geometric_scene.wl`
  - `workflow_result.json`
- 失败时输出：
  - 每轮失败原因。
  - 最终 fallback 建议。
- 原 benchmark tools 不被删除，仍可运行。
