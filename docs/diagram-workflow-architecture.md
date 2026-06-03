# Diagram Workflow Architecture

> 目标：把 teaching-skills 中“批量生成 assignment / explanation，但按小题逐个生成 Mathematica 图，再回填到 LaTeX/PDF”的链路梳理成可实现、可审计、职责清晰的工作流。

## 1. 背景与核心矛盾

当前系统的主产物是整份 `assignment.yaml` / explanation YAML：题目、讲解、练习是一次性批量生成的。但 diagram 的真实生产单位不是整份 assignment，而是 assignment 内部每个需要图的位置。一个大题可能没有图，也可能 prompt 图一张、solution 图一张，也可能每个小问一张图。

因此 diagram 工作流的基本矛盾是：

```text
assignment 是批量订单
        ↓
diagram 是 slot/job 级单件生产
        ↓
LaTeX 排版又必须在渲染前知道每个 slot 是否有图、图放哪里、图宽多少
```

解决思路不是“生成一道题时顺手画图”，而是把 assignment 先产生成一个**带 diagram slot 标注的计划文件**，再由 diagram batch 层收集所有 slot，拆成单图 job，逐个或并行调用 `workflow.py` 生成图片，最后把图片 artifact 回填到 resolved YAML，再进入 LaTeX 渲染和 PDF 编译。

核心原则：

```text
assignment generator 负责声明“哪里需要图”
diagram orchestrator 负责把声明拆成单图任务
workflow.py 只负责一个图
artifact manifest 负责把单图结果汇总回 assignment
LaTeX renderer 只负责排版已存在的图片
```

---

## 2. 架构对象模型

### 2.1 层级关系

```text
Assignment
  └── Problem / Section / Block
      └── Subquestion / Answer-space part
          └── DiagramSlot
              └── DiagramJob
                  └── DiagramArtifact
```

### 2.2 关键概念

| 概念 | 语义 | 例子 | 是否可执行 |
|---|---|---|---|
| `DiagramSlot` | assignment 中需要放图的位置；是排版和教学语义单位 | `q3.part1.prompt` | 否 |
| `DiagramJob` | 一次图片生成任务；是 workflow 执行单位 | `q3-part1-prompt` | 是 |
| `DiagramArtifact` | job 生成出的最终图片和元数据 | `diagram/jobs/q3-part1-prompt/rendered/prompt.png` | 否 |
| `diagram_ref` | YAML 中引用 artifact 的稳定引用 | `q3.part1.prompt` | 否 |
| `diagram_job_id` | job 执行 ID；用于路径、日志、manifest | `q3-part1-prompt` | 是 |
| `slot_path` | slot 在 YAML 中的位置，用于 resolver 回填 | `/problems/0/sections/1/blocks/2/answer_space/parts/0/diagram_col` | 否 |

### 2.3 为什么 slot 和 job 不能混用

`slot_id` 表示“这张图放在哪里”；`job_id` 表示“这次生成任务叫什么”。同一个 slot 可能在重试时产生多个 job attempt，同一个 prompt 几何结果也可能被 solution 图复用。因此它们必须分开。

错误做法：

```yaml
diagram_job_id: q3
image_path: diagram/jobs/q3/rendered/prompt.png
```

这个 ID 同时承担题号、slot、job、路径、复用关系，后续必然混乱。

推荐做法：

```yaml
diagram_ref: q3.part1.prompt
slot_id: q3.part1.prompt
job_id: q3-part1-prompt
slot_path: /sections/0/blocks/2/answer_space/parts/0/diagram_col
```

---

## 3. 总体数据流

### 3.1 推荐工作流

```text
S1   math-structure-analysis
     原题 → 01-structure-analysis.md
     锁定数学事实、题目结构、已知/推出边界

S2   latex-data skill
     01-structure-analysis.md → assignment.plan.yaml
     批量生成讲解/练习 YAML，并声明 diagram slots

S2.5 collect_diagram_jobs
     assignment.plan.yaml → diagram_jobs.json
     从 YAML 中收集所有 DiagramSlot，生成可执行 job list

S2.6 run_diagram_batch
     diagram_jobs.json → jobs/<job_id>/...
     按 job 调用 workflow.py + renderer，可并行，可按依赖拓扑排序

S2.7 build_diagram_artifacts
     jobs/<job_id>/renderer_result.json → diagram_artifacts.json
     汇总 image_path、hash、尺寸、状态、失败原因

S2.8 check_diagram_gate
     检查 required 图是否 bindable、clean 图是否不泄题、
     路径是否可访问、hash 是否一致、manifest 是否 stale

S2.9 resolve_assignment_diagrams
     assignment.plan.yaml + diagram_artifacts.json → assignment.resolved.yaml
     把 diagram_ref 解析为 image_path / width / caption 等最终图片对象

S7   math-yaml-review
     plan + resolved YAML 审查

S8   math-assignment-latex
     assignment.resolved.yaml → .tex → .pdf
     只渲染和编译，不生成图

S9   PDF acceptance / math-homework-review
     检查最终 PDF 是否完整、图是否可见、布局是否溢出
```

### 3.2 文件流

```text
artifacts/<student>/<date-topic>/
  01-structure-analysis.md

  build/
    02-student-explanation.plan.assignment.yaml
    03-adaptive-practice.student.plan.assignment.yaml
    03-adaptive-practice.teacher.plan.assignment.yaml

    diagram/
      diagram_jobs.json
      diagram_artifacts.json
      jobs/
        <job_id>/
          request.json
          request.gsb.json
          workflow_result.json
          final_renderer_spec.json
          renderer_result.json
          workflow_events.jsonl
          wrapper_stdout.txt
          wrapper_stderr.txt

    02-student-explanation.resolved.assignment.yaml
    03-adaptive-practice.student.resolved.assignment.yaml
    03-adaptive-practice.teacher.resolved.assignment.yaml
    review-ledger.jsonl

  diagram/
    jobs/
      <job_id>/
        rendered/
          prompt.png
          prompt.svg
          solution.png
          solution.svg

  02-explanation.tex
  02-explanation.pdf
  03-practice-student.tex
  03-practice-student.pdf
  03-practice-teacher.tex
  03-practice-teacher.pdf
```

约定：debug、请求、日志、manifest 放 `build/diagram/`；最终可被 TeX 引用的图片放 artifact 根目录下的 `diagram/jobs/...`。这样 `image_path` 可以稳定写成相对最终 `.tex` 的路径：

```yaml
image_path: "diagram/jobs/q3-part1-prompt/rendered/prompt.png"
```

---

## 4. Skills 职责分工

### 4.1 `math-homework-pipeline`

职责：端到端调度器。它不直接写题、不直接写 LaTeX、不直接画图。它负责维护 run manifest、stage 状态、preflight、review ledger，并调用下游 skill / script。

在 diagram 架构中新增职责：

- 在 Stage 2 之后识别 plan YAML 是否包含 `diagram_slots`。
- 调用 diagram collector / batch runner / resolver。
- 把 diagram stages 写入 `run_manifest.json`。
- 在 render gate 前检查 `diagram_artifacts.json` 和 resolved YAML 是否一致。

不应负责：

- 判断几何图怎么画。
- 调用 Wolfram 细节。
- 手动 patch LaTeX 模板。

建议新增 stages：

```text
S2.5  Diagram job collection
S2.6  Diagram generation batch
S2.7  Diagram artifact build
S2.8  Diagram gate
S2.9  Assignment diagram resolve
```

### 4.2 `math-structure-analysis`

职责：锁定数学事实和教学结构。它应该是 diagram 语义的上游锚点，但不生成图片路径。

推荐新增输出：

```json
"diagram_plan_packet": {
  "needs_diagram": true,
  "diagram_requirement": "required",
  "diagram_kind": "synthetic_geometry",
  "visual_role": "source_problem_figure",
  "given_objects": [],
  "given_constraints": [],
  "derived_objects": [],
  "derived_constraints": [],
  "clean_forbidden": [],
  "solution_allowed_annotations": [],
  "pedagogical_purpose": "帮助学生读清点、线、角关系，而不是提示证明路径"
}
```

不应负责：

- 真实 `image_path`。
- `width: 0.32\linewidth` 这类 TeX 排版细节。
- Wolfram `GeometricScene` 代码。

### 4.3 `math-student-explanation-latex-data`

职责：根据结构分析生成讲解型 `assignment.plan.yaml`。它负责批量生成 explanation 的 blocks，并在需要图的位置声明 diagram slot。

它应该负责：

- 在 `problemcard` / `problem` / `solution` / 独立讲解块中声明 prompt 或 solution diagram slot。
- 指定 diagram 的教学角色：原题图、讲解辅助图、解答标注图。
- 指定 `variant` 与 `disclosure_policy`。
- 指定初始排版意图：右栏、居中、解答图、随小问放置。

不应负责：

- 调用 `workflow.py`。
- 生成真实 PNG。
- 根据失败情况把图降级为 hint。

### 4.4 `math-practice-latex-data`

职责：根据结构分析和学生程度生成练习型 `assignment.plan.yaml`，包括 student / teacher 版本。

它应该负责：

- 对每道练习题或每个小问声明 diagram slot。
- 学生版 slot 使用 `variant: prompt` 和 `disclosure_policy: clean`。
- 教师版可以引用同一 prompt 图，也可以增加 `variant: solution` 的 annotated 图。
- 对“如图/图中/下图”的题，设置 `required: true` 与 `on_failure: fail_assignment`。

不应负责：

- 复用图片路径的临时猜测。
- 把 prompt 图和 solution 图混用。
- 在学生版中输出 derived 标注。

### 4.5 `math-yaml-review`

职责：渲染前审查 YAML。当前它主要负责编译级、渲染级、内容级问题。diagram 架构下应扩展为 plan/resolved 两类审查。

Plan YAML 审查：

- 必须检查题干出现“如图/图中/下图”时是否存在 required diagram slot。
- 必须检查 `variant: prompt` 是否搭配 `disclosure_policy: clean`。
- 必须检查同一小问是否 slot 重复或缺失。

Resolved YAML 审查：

- 必须检查每个 required slot 是否已绑定 `image_path`。
- 必须检查 `image_path` 相对最终 `.tex` 可访问。
- 必须检查 `diagram_ref` / `diagram_job_id` / manifest 一致。

不应负责：

- 修改 YAML。
- 运行 diagram workflow。
- 重新生成图片。

### 4.6 `math-assignment-latex`

职责：把 `assignment.resolved.yaml` 渲染成 LaTeX，并编译 PDF。

它只负责：

```text
assignment.resolved.yaml → Jinja2 template → .tex → XeLaTeX / tectonic → .pdf
```

它不负责：

- 判断是否需要图。
- 生成、重试、评价 diagram。
- 推断 YAML 中缺失的 `image_path`。

### 4.7 `math-homework-review`

职责：最终独立审核完整 artifact 目录，给教师一个简短质量印象。diagram 架构下应把“图是否完整、是否可见、是否影响题意”纳入完整性和讲解质量维度。

不应负责：

- 细查每个 `renderer_spec` 的数学正确性。
- 修复 YAML 或重新生成图。

---

## 5. 代码模块职责分工

### 5.1 当前已有 diagram 相关模块

| 模块 | 当前职责 | 目标职责 | 备注 |
|---|---|---|---|
| `scripts/run_diagram_workflow.py` | 读取单个 `DiagramJobRequest` v2 并调用本地 `geometry_diagram_workflow/core/workflow.py`；只显式支持 `synthetic_geometry` | engine adapter；只负责 request 传递、engine 路由和调用 workflow.py | 不应做 clean policy 的业务修补 |
| `scripts/geometry_diagram_workflow/core/workflow.py` | agentic GeometricScene workflow：文本模型写/revise Wolfram GeometricScene，Wolfram 求解，产出 renderer-friendly spec | 单 job executor；生产输入是一个 `DiagramJobRequest` v2 | 核心图片生成工作流，不扫描或修改 assignment YAML |
| `scripts/render_geometry_spec.py` | `geometry-render-spec/v1` → SVG → PNG，输出 `renderer_result.json` | deterministic renderer；只消费 renderer spec，输出图片 | 不理解 assignment，不改 YAML |
| `scripts/workflow_gate.py` | run manifest、preflight、review ledger、render gate、final review | 增加 diagram stage 记录和 diagram gate | 不直接生成图 |

### 5.2 建议新增模块

| 新模块 | 输入 | 输出 | 职责 |
|---|---|---|---|
| `scripts/collect_diagram_jobs.py` | `assignment.plan.yaml` | `build/diagram/diagram_jobs.json` | 扫描 plan YAML 中的 diagram slots，生成批量 job graph |
| `scripts/run_diagram_batch.py` | `diagram_jobs.json` | per-job output + partial manifest | 按依赖关系运行所有 diagram jobs；控制并发、重试、缓存 |
| `scripts/build_diagram_artifacts.py` | jobs 目录 | `diagram_artifacts.json` | 汇总 renderer_result、image hash、尺寸、状态 |
| `scripts/resolve_assignment_diagrams.py` | `assignment.plan.yaml` + `diagram_artifacts.json` | `assignment.resolved.yaml` | 将 slot/ref 回填为模板可消费的 `image_path` 对象 |
| `scripts/check_diagram_gate.py` | plan + jobs + artifacts + resolved YAML | PASS/BLOCK JSON | 检查 required 图、路径、hash、stale、policy |

### 5.3 LaTeX 相关模块

| 模块 | 职责 | 与 diagram 的关系 |
|---|---|---|
| `math-assignment-latex/scripts/render_assignment.py` | 读取 assignment YAML，按 `render.template` 选择 Jinja2 模板，输出 `.tex` | 只消费 resolved YAML 中的 `image_path` / `width` / `caption` |
| `math-assignment-latex/scripts/compile_latex.sh` | 使用 XeLaTeX / tectonic 编译 `.tex` 为 PDF；可自动从对应 YAML 重新 render | 不生成图片；只要求 `\includegraphics` 路径可访问 |
| `math-assignment-latex/templates/exam-zh-practice.tex.j2` | 练习页模板 | 支持选择题右栏图、diagram row、答题区右侧图、独立 diagram block |
| `math-assignment-latex/templates/exam-zh-explanation.tex.j2` | 讲解页模板 | 支持 problemcard/problem 右栏图和独立居中 diagram block |
| `math-assignment-latex/templates/preamble-exam-zh*.tex` | LaTeX 宏与样式 | 定义 `\diagramcolfigure`、`\diagramrowitem`、`\answerareawithdiagramcol` 等宏的样式边界 |
| `math-assignment-latex/references/assignment-schema.md` | assignment DSL schema | 应升级为 plan/resolved 两阶段 diagram contract |

---

## 6. 两阶段 YAML contract

### 6.1 `assignment.plan.yaml`

`assignment.plan.yaml` 是题目/讲解的计划文件。它描述“哪里需要图、图的教学用途、图影响排版的位置”，但不假装图片已经存在。

示例：

```yaml
meta:
  title: "几何练习"
  version: "student"
  assignment_id: "2026-05-28-geometry-practice"
render:
  template: "exam-zh-practice"
sections:
  - id: "s1"
    type: "practice"
    blocks:
      - type: "problem"
        id: "q3"
        stem_latex: "如图，$AB=AC$，点 $D$ 在 $BC$ 上……"
        answer_space:
          type: "steps"
          parts:
            - label: "(1)"
              height: "28mm"
              diagram_slot:
                slot_id: "q3.part1.prompt"
                diagram_ref: "q3.part1.prompt"
                variant: "prompt"
                disclosure_policy: "clean"
                required: true
                on_failure: "fail_assignment"
                placement: "answer_space.parts[].diagram_col"
                layout_role: "answer_area_sidecar"
                width_hint: "0.32\\linewidth"
                caption: "原题图"
                engine: "geometric_scene"
                diagram_kind: "synthetic_geometry"
                source_problem_ref: "q3"
```

说明：

- `diagram_slot` 是 plan 阶段字段，不直接被现有模板消费。
- 现有模板仍消费 `diagram_col`、`diagram_row`、`type: diagram` 里的 `image_path`。
- resolver 负责把 `diagram_slot` 转成 resolved YAML 中的 `diagram_col`。

### 6.2 `assignment.resolved.yaml`

`assignment.resolved.yaml` 是渲染输入。它必须只引用已经生成好的图片。

示例：

```yaml
answer_space:
  type: "steps"
  parts:
    - label: "(1)"
      height: "28mm"
      diagram_col:
        image_path: "diagram/jobs/q3-part1-prompt/rendered/prompt.png"
        diagram_ref: "q3.part1.prompt"
        diagram_job_id: "q3-part1-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
        artifact_hash: "sha256:..."
```

规则：

- `resolved.yaml` 可以由 `plan.yaml` 自动生成，不建议手写。
- `resolved.yaml` 进入 `math-assignment-latex`。
- `image_path` 必须相对最终 `.tex` 所在目录可访问，或是绝对路径。

---

## 7. Diagram batch contract

### 7.1 `diagram_jobs.json`

由 `collect_diagram_jobs.py` 生成，是 batch 层的总订单。

```json
{
  "schema_version": "diagram-jobs/v1",
  "assignment_id": "2026-05-28-geometry-practice",
  "source_assignment": "build/03-adaptive-practice.student.plan.assignment.yaml",
  "jobs": [
    {
      "job_id": "q3-part1-prompt",
      "slot_id": "q3.part1.prompt",
      "diagram_ref": "q3.part1.prompt",
      "slot_path": "/sections/0/blocks/2/answer_space/parts/0/diagram_slot",
      "problem_id": "q3",
      "variant": "prompt",
      "disclosure_policy": "clean",
      "required": true,
      "on_failure": "fail_assignment",
      "engine": "geometric_scene",
      "diagram_kind": "synthetic_geometry",
      "request_path": "build/diagram/jobs/q3-part1-prompt/request.json",
      "out_dir": "build/diagram/jobs/q3-part1-prompt",
      "public_image_dir": "diagram/jobs/q3-part1-prompt/rendered",
      "depends_on": [],
      "content_hash": "sha256:..."
    }
  ]
}
```

### 7.2 Job graph 与并行

- `variant: prompt` 的图通常可以并行运行。
- `variant: solution` 的图如果要复用 prompt 几何，必须显式声明 `reuse_geometry_from`，并依赖对应 prompt job 完成。
- `run_diagram_batch.py` 不应让 `workflow.py` 一次处理多个 job。batch 并行在外层，`workflow.py` 保持单 job executor。

---

## 8. `workflow.py` 输入输出格式

### 8.1 当前问题

`workflow.py` 是核心图片生成工作流，但其输入格式目前没有清晰分层。尤其是 `diagram_intent` 容易同时表示教学意图和几何类型。目标 contract 必须分离以下概念：

```text
teaching_intent     这张图服务哪种教学场景
engine              用哪个生成引擎
diagram_kind        图的数学/视觉类型
variant             prompt / solution
policy              clean / annotated
layout              TeX 排版，不属于 workflow.py
```

当前 engine/kind 边界：

| `diagram_kind` | 推荐 `engine` | 说明 |
|---|---|---|
| `synthetic_geometry` | `geometric_scene` | 综合几何，Wolfram `GeometricScene` 求实例点位 |
| `coordinate_geometry` | `wolfram_client` / `coordinate_renderer` | 坐标系内的点、线、圆、多边形；用 WolframClient 计算关系，Python renderer 出图 |
| `function_graph` | `wolfram_client` / `coordinate_renderer` | 函数图像、坐标轴、网格、交点、零点、关键点 |
| `hybrid` | 由 orchestrator 拆 job | 同一题同时需要综合几何示意和函数/坐标图时，拆成多个 slot/job |
| `auto` | collector/workflow 路由 | 只在上游不确定时临时使用；进入执行前应收敛为明确 kind |

### 8.2 `DiagramJobRequest` v2

`workflow.py` 只接受单个 job request。

```json
{
  "schema_version": "diagram-job-request/v2",
  "job_id": "q3-part1-prompt",
  "assignment_id": "2026-05-28-geometry-practice",
  "problem_id": "q3",
  "slot_id": "q3.part1.prompt",
  "variant": "prompt",
  "disclosure_policy": "clean",

  "engine": "geometric_scene",
  "diagram_kind": "synthetic_geometry",
  "teaching_intent": "practice_prompt",

  "problem_context": {
    "stem_latex": "如图，$AB=AC$，点 $D$ 在 $BC$ 上……",
    "subquestion_latex": "证明……",
    "grade_or_topic": "等腰三角形"
  },

  "semantic_constraints": {
    "given_objects": ["A", "B", "C", "D"],
    "given_constraints": ["AB=AC", "D on BC"],
    "derived_objects": [],
    "derived_constraints": [],
    "clean_forbidden": ["不要画辅助线 AH", "不要标注 BD=DC"],
    "solution_allowed_annotations": []
  },

  "analytic_requirements": {
    "viewport": {},
    "axes": {},
    "functions": [],
    "objects": [],
    "annotations": [],
    "wolfram_client_options": {}
  },

  "visual_requirements": {
    "show_labels": true,
    "show_given_markers": true,
    "show_axes": false,
    "preferred_orientation": "landscape",
    "caption": "原题图"
  },

  "reuse": {
    "reuse_geometry_from": "",
    "base_job_dir": ""
  },

  "engine_options": {
    "seed": 42,
    "max_retries": 3,
    "wolfram_timeout_s": 30,
    "wolfram_hard_timeout_s": 60,
    "model_config": {}
  }
}
```

字段边界：

- `layout_role`、`width`、`image_path` 不进入 `workflow.py`。
- `workflow.py` 可以知道 `caption` 作为视觉意图，但不负责最终 LaTeX caption 排版。
- `reuse_geometry_from` 只表达几何复用，不表达图片路径复用。
- `analytic_requirements` 只在 `coordinate_geometry` / `function_graph` 中承载坐标轴、视窗、函数、点、直线、采样和兼容保留的 Wolfram plot 选项；综合几何可以为空。
- 解析几何推荐路径是 Python 调 WolframClient 做数学计算，再由 Python renderer 输出 SVG/PNG；`wolfram_plot` 只作为兼容 alias。

### 8.3 `workflow.py` 内部职责

`workflow.py` 应该执行：

```text
DiagramJobRequest
  → route by engine + diagram_kind
  → synthetic_geometry: text model produces GeometricScene payload
  → coordinate/function: text model or parser produces analytic payload
  → validate Wolfram code / expression safety
  → Wolfram solves GeometricScene or validates/samples analytic graph
  → compile final_renderer_spec.json
  → optional debug render / vision feedback
  → workflow_result.json
```

`workflow.py` 不应该执行：

- 扫描 assignment YAML。
- 修改 assignment YAML。
- 选择 LaTeX template。
- 决定图失败时是否改成 hint。
- 生成最终 `assignment.resolved.yaml`。

### 8.4 `DiagramJobResult`

```json
{
  "schema_version": "diagram-job-result/v2",
  "job_id": "q3-part1-prompt",
  "status": "ok",
  "fail_type": "",
  "message": "",
  "request": "request.json",
  "workflow_events": "workflow_events.jsonl",
  "scene_payload": "scene_payload.json",
  "final_renderer_spec": "final_renderer_spec.json",
  "wolfram": {
    "success": true,
    "solve_time_s": 1.42,
    "seed": 42
  },
  "model": {
    "text_model_used": "...",
    "attempts": []
  },
  "policy_warnings": []
}
```

---

## 9. Renderer 与 artifact contract

### 9.1 `final_renderer_spec.json`

由 `workflow.py` 产出，供 renderer 消费。

综合几何示例：

```json
{
  "schema_version": "geometry-render-spec/v1",
  "job_id": "q3-part1-prompt",
  "variant": "prompt",
  "disclosure_policy": "clean",
  "type": "synthetic_geometry",
  "points": {
    "A": [0, 2],
    "B": [-2, 0],
    "C": [2, 0]
  },
  "segments": [
    {"from": "A", "to": "B"},
    {"from": "A", "to": "C"},
    {"from": "B", "to": "C"}
  ],
  "polygons": [],
  "markers": [
    {"type": "equal_ticks", "segments": [["A", "B"], ["A", "C"]]}
  ],
  "labels": {
    "A": {"text": "A", "dx": 0, "dy": -24}
  },
  "teaching_focus": ["读清等腰条件"]
}
```

函数图示例：

```json
{
  "schema_version": "geometry-render-spec/v1",
  "job_id": "f1-prompt",
  "variant": "prompt",
  "disclosure_policy": "clean",
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

### 9.2 `renderer_result.json`

由 `render_geometry_spec.py` 产出。

```json
{
  "schema_version": "geometry-renderer-result/v1",
  "job_id": "q3-part1-prompt",
  "status": "ok",
  "renderer": "teaching-svg-geometry-renderer",
  "diagram_variant": "prompt",
  "disclosure_policy": "clean",
  "renderer_spec": "final_renderer_spec.json",
  "image_path": "diagram/jobs/q3-part1-prompt/rendered/prompt.png",
  "preview_svg": "diagram/jobs/q3-part1-prompt/rendered/prompt.svg",
  "width_px": 720,
  "height_px": 520,
  "checks": {
    "references_valid": true,
    "svg_exists": true,
    "image_exists": true
  }
}
```

### 9.3 `diagram_artifacts.json`

全局 manifest，是 resolver 的唯一输入来源。

```json
{
  "schema_version": "diagram-artifacts/v1",
  "assignment_id": "2026-05-28-geometry-practice",
  "source_jobs": "build/diagram/diagram_jobs.json",
  "artifacts": {
    "q3.part1.prompt": {
      "slot_id": "q3.part1.prompt",
      "job_id": "q3-part1-prompt",
      "status": "ok",
      "variant": "prompt",
      "disclosure_policy": "clean",
      "image_path": "diagram/jobs/q3-part1-prompt/rendered/prompt.png",
      "preview_svg": "diagram/jobs/q3-part1-prompt/rendered/prompt.svg",
      "width_px": 720,
      "height_px": 520,
      "aspect_ratio": 1.3846,
      "hash": "sha256:...",
      "renderer_result": "build/diagram/jobs/q3-part1-prompt/renderer_result.json",
      "workflow_result": "build/diagram/jobs/q3-part1-prompt/workflow_result.json",
      "final_renderer_spec": "build/diagram/jobs/q3-part1-prompt/final_renderer_spec.json",
      "bindable": true,
      "warnings": []
    }
  }
}
```

---

## 10. 关键字段语义

| 字段 | 所属 contract | 语义 | 谁写入 | 谁消费 |
|---|---|---|---|---|
| `assignment_id` | plan/jobs/request/artifacts | 本次作业的稳定 ID | pipeline / latex-data | 所有下游 |
| `block.id` / `problem_id` | assignment | 题目或 block ID | latex-data | collector / review |
| `slot_id` | plan/jobs/artifacts | assignment 中某个图位的稳定 ID | latex-data / collector | jobs / resolver |
| `slot_path` | jobs | slot 在 plan YAML 中的 JSON Pointer | collector | resolver |
| `diagram_ref` | plan/resolved/artifacts | YAML 和 manifest 之间的稳定引用 | latex-data / collector | resolver / renderer gate |
| `diagram_job_id` / `job_id` | jobs/request/result | 单次生成任务 ID | collector | orchestrator / workflow / renderer |
| `variant` | slot/request/spec/artifact | `prompt` 或 `solution` | latex-data | policy / renderer / template |
| `disclosure_policy` | slot/request/spec/artifact | `clean` 或 `annotated` | latex-data | workflow / gate |
| `required` | slot/jobs | 图缺失是否阻断 assignment | latex-data | diagram gate |
| `on_failure` | slot/jobs | 失败策略：`fail_assignment` / `omit_diagram` / `textual_fallback` | latex-data | orchestrator / resolver |
| `placement` | slot | 图最终应该绑定到哪个 YAML 位置 | latex-data | resolver |
| `layout_role` | slot | 排版角色：右栏、答题区侧栏、并排图行、居中图 | latex-data | resolver / template |
| `width_hint` | slot | plan 阶段的 TeX 宽度建议 | latex-data | resolver |
| `width` | resolved YAML | 模板实际使用的 TeX 宽度 | resolver | LaTeX template |
| `image_path` | resolved/artifact | 最终 PNG 路径，必须相对 `.tex` 可访问 | artifact builder / resolver | template / compiler |
| `engine` | jobs/request | 图片生成引擎，如 `geometric_scene` / `wolfram_client` / `coordinate_renderer`；`wolfram_plot` 为兼容 alias | collector | orchestrator |
| `diagram_kind` | jobs/request | 图类型，如 `synthetic_geometry` / `coordinate_geometry` / `function_graph` / `hybrid` | latex-data / collector | workflow adapter |
| `analytic_requirements` | slot/request | 坐标/函数图的 viewport、axes、functions、objects 和 WolframClient 计算输入 | latex-data / collector | workflow |
| `reuse_geometry_from` | request/jobs | solution 图复用哪个 prompt job 的几何点位 | latex-data / collector | orchestrator / workflow |
| `content_hash` | jobs/artifacts | 用于判断 job 是否 stale | collector | cache / gate |
| `artifact_hash` | resolved/artifacts | 最终 PNG hash | artifact builder | resolver / gate |

---

## 11. LaTeX 模板如何消费 diagram

现有模板消费的是 resolved YAML 中的图片对象，而不是 plan 阶段的 `diagram_slot`。

### 11.1 选择题右栏图

Resolved YAML：

```yaml
type: choice
diagram_col:
  image_path: "diagram/jobs/c1-prompt/rendered/prompt.png"
  width: "0.30\\linewidth"
  caption: "参考图"
```

模板行为：题干和选项在左侧 minipage，图在右侧 `\diagramcolfigure`。

### 11.2 填空题并排图行

Resolved YAML：

```yaml
- type: diagram_row
  id: fillin-diagrams-1
  items:
    - label: "第 1 题"
      image_path: "diagram/jobs/f1-prompt/rendered/prompt.png"
      width: "0.23\\linewidth"
```

模板行为：用 `\diagramrowitem` 将多张图并排放在题组后面。

### 11.3 大题答题区右侧图

Resolved YAML：

```yaml
answer_space:
  type: steps
  parts:
    - label: "(1)"
      height: "28mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part1-prompt/rendered/prompt.png"
        width: "0.32\\linewidth"
```

模板行为：用 `\answerareawithdiagramcol` 把答题区和右侧图栏并排。

### 11.4 独立居中图

Resolved YAML：

```yaml
- type: diagram
  id: fig-main
  image_path: "diagram/jobs/main-prompt/rendered/prompt.png"
  width: "0.82\\linewidth"
  caption: "观察底边 BC 与高 AD 的关系。"
```

模板行为：居中 `\includegraphics`。

---

## 12. Gate 与失败策略

### 12.1 状态机

每个 job 可以有如下状态：

```text
planned
collected
running
ok
failed
skipped
bound
```

每个 slot 的最终状态：

```text
resolved       已绑定 image_path
missing        没有 artifact
failed         job 失败
omitted        optional 图被省略
fallback       optional 图被文本 fallback 替代
blocked        required 图失败，assignment 不可渲染
```

### 12.2 失败策略

| 场景 | required | on_failure | 结果 |
|---|---:|---|---|
| 题干出现“如图/图中/下图” | true | `fail_assignment` | 图失败则阻断渲染 |
| 几何大题依赖图读条件 | true | `fail_assignment` | 图失败则阻断渲染 |
| 讲解页补充观察图 | false | `omit_diagram` | 图失败则省略该图 |
| 讲解页辅助提示图 | false | `textual_fallback` | 图失败可生成 reading_tip/hint，但必须由 plan 声明 |
| 教师版 solution annotated 图 | 视情况 | `omit_diagram` 或 `fail_assignment` | 不得影响学生版 prompt 图 |

禁止：后处理脚本在没有 plan 授权的情况下，把 required 图自动降级为 hint 或 reading_tip。

### 12.3 必要 gate

渲染前必须通过：

1. 所有 `required: true` 的 slot 都在 `diagram_artifacts.json` 中 `status: ok` 且 `bindable: true`。
2. `image_path` 文件存在且非空。
3. `content_hash` 与当前 plan YAML 内容一致，不 stale。
4. `variant: prompt` 的图必须是 `disclosure_policy: clean`。
5. 学生版 resolved YAML 不得引用 `variant: solution` 或 `disclosure_policy: annotated` 的图片。
6. `image_path` 相对最终 `.tex` 所在目录可访问。
7. PDF 编译后必须做基础视觉检查：图不空白、不越界、不严重压缩。

---

## 13. 当前模块需要调整的地方

### 13.1 `workflow.py` 输入格式重构

重点不是增加字段，而是拆开过载字段：

| 当前风险 | 目标拆分 |
|---|---|
| `diagram_intent` 同时像教学意图又像图类型 | `teaching_intent` + `diagram_kind` |
| request 混入 layout / image path | workflow request 只保留数学与视觉生成信息 |
| solution 图复用靠路径猜测 | `reuse_geometry_from` 显式进入 job graph |
| clean policy 靠 wrapper 后处理 | `semantic_constraints.clean_forbidden` + 独立 gate |

### 13.2 旧 assignment 反扫入口已移除

从 assignment YAML 反向扫描 diagram 并生成 job 的入口已移除。目标架构中，扫描 YAML 是 `collect_diagram_jobs.py` 的职责；gate 只消费：

```text
assignment.plan.yaml
diagram_jobs.json
diagram_artifacts.json
assignment.resolved.yaml
```

gate 应回答：“计划中要求的图是否都已经可绑定、可渲染、符合 policy？”而不是重新跑生成流程。

### 13.3 后处理插图入口已移除

后处理脚本不再构造 package，也不再插入 YAML/HTML fallback。生产链路只使用：

```text
resolve_assignment_diagrams.py
```

只做 artifact → resolved YAML 的确定性绑定。

### 13.4 `assignment-schema.md` 升级

当前 schema 中 diagram 对象直接包含 `image_path`。目标上应分为：

- plan 阶段：`diagram_slot`，声明需求和排版意图。
- resolved 阶段：`diagram_col` / `diagram_row` / `type: diagram`，包含真实 `image_path`。

这样不会在图片尚未生成时，让 YAML 假装图片已经存在。

---

## 14. 推荐落地顺序

### Step 1：先定义 schema，不动 workflow

新增文档：

```text
docs/diagram-workflow-architecture.md
docs/diagram-job-schema.md
```

先明确：slot/job/artifact/plan/resolved 的字段语义。

### Step 2：实现 collector + resolver

先不改 `workflow.py`，只做：

```text
assignment.plan.yaml → diagram_jobs.json
assignment.plan.yaml + fake diagram_artifacts.json → assignment.resolved.yaml
```

用 fake artifact 验证 LaTeX 模板排版链路。

### Step 3：把现有 `run_diagram_workflow.py` 接到 batch runner

让 batch runner 调现有 wrapper。此时仍可使用旧 request 字段，但由 collector 统一生成。

### Step 4：重构 `workflow.py` request v2

引入 `DiagramJobRequest` v2 作为生产唯一输入；`run_diagram_batch.py` 只写并调用每个 job 的 `request.json`。

### Step 5：把 diagram gate 接入 `math-homework-pipeline`

在 `render_assignment.py` 前加：

```text
check_diagram_gate.py
```

没有通过 required diagram gate，不允许进入 LaTeX render。

### Step 6：清理旧 fallback

删除旧 request builder、assignment 反扫入口和后处理插图入口；生产链路只保留 `DiagramJobRequest` v2。

---

## 15. 最终目标状态

完成后，系统的职责边界应当是：

```text
structure-analysis
  负责数学事实和 diagram 语义边界

latex-data skills
  负责批量题目和 diagram slots

collector
  负责 slot → jobs

batch orchestrator
  负责 jobs → per-job workflow outputs

workflow.py
  负责一个图的数学生成

renderer
  负责 spec → PNG/SVG

artifact manifest
  负责 job results 的统一事实源

resolver
  负责 plan YAML → resolved YAML

math-assignment-latex
  负责 resolved YAML → TeX/PDF

review/gate
  负责每阶段是否放行
```

一句话总结：

> Diagram 系统不应该寄生在 assignment YAML、LaTeX 模板或后处理脚本里；它应该拥有自己的 slot/job/artifact/manifest 层。assignment 批量声明图，diagram batch 单件生产图，resolver 再把图片绑定回 assignment。这样才能同时解决“题目批发”和“图逐个生成”的矛盾。
