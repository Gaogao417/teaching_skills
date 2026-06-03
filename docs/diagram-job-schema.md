# Diagram Job Schema

本文档把 `docs/diagram-workflow-architecture.md` 中的 diagram 数据流收敛成可实现的 Pydantic contract。类型定义落在 `scripts/diagram_contracts.py`。

## 1. 关键数据流

```text
01-structure-analysis.md
  -> assignment.plan.yaml
     - latex-data skill 批量生成题目/讲解
     - 每个需要图的位置只声明 DiagramSlot
     - 不写 image_path，不假装图片已存在

assignment.plan.yaml
  -> build/diagram/diagram_jobs.json
     - collect_diagram_jobs 扫描 DiagramSlot
     - slot_id / diagram_ref / slot_path 保持 YAML 回填定位
     - job_id / request_path / out_dir 成为可执行任务边界

diagram_jobs.json
  -> build/diagram/jobs/<job_id>/request.json
     - run_diagram_batch 按 job graph 调度
     - prompt jobs 可并行
     - solution jobs 必须依赖 reuse_geometry_from 指向的 prompt job

request.json
  -> workflow_result.json + final_renderer_spec.json
     - workflow.py 每次只处理一个 DiagramJobRequest
     - 只消费数学语义、生成引擎、clean/annotated policy
     - 不消费 layout_role / width_hint / image_path

final_renderer_spec.json
  -> renderer_result.json + rendered/*.png
     - render_geometry_spec 只做确定性渲染
     - 输出 PNG/SVG 路径、尺寸、引用检查

jobs/<job_id>/renderer_result.json
  -> build/diagram/diagram_artifacts.json
     - build_diagram_artifacts 汇总可绑定事实
     - diagram_artifacts.json 是 resolver 的唯一图片事实源

assignment.plan.yaml + diagram_artifacts.json
  -> assignment.resolved.yaml
     - resolve_assignment_diagrams 把 DiagramSlot 绑定为 ResolvedDiagramImage
     - 输出现有模板可消费的 diagram_col / diagram_row / type: diagram

assignment.resolved.yaml
  -> .tex -> .pdf
     - math-assignment-latex 只渲染已存在图片
```

## 2. Pydantic 类型边界

| 阶段 | 文件/对象 | Pydantic 类型 | 写入者 | 消费者 |
|---|---|---|---|---|
| plan YAML | `diagram_slot` | `DiagramSlot` | latex-data skills | collector / plan gate |
| batch manifest | `diagram_jobs.json` | `DiagramJobsManifest` / `DiagramJob` | collector | batch runner / gate |
| workflow input | `request.json` | `DiagramJobRequest` | collector / batch runner | `workflow.py` adapter |
| workflow output | `workflow_result.json` | `DiagramJobResult` | `workflow.py` | artifact builder / gate |
| renderer input | `final_renderer_spec.json` | `GeometryRenderSpec` | `workflow.py` | renderer |
| renderer output | `renderer_result.json` | `GeometryRendererResult` | renderer | artifact builder |
| artifact manifest | `diagram_artifacts.json` | `DiagramArtifactsManifest` / `DiagramArtifact` | artifact builder | resolver / gate |
| resolved YAML | image payload | `ResolvedDiagramImage` | resolver | LaTeX templates |
| render gate | gate report | `DiagramGateReport` / `DiagramGateCheck` | check_diagram_gate | pipeline |

## 3. 强制约束

- `slot_id` 表示“图片放在哪里”，`job_id` 表示“一次生成任务”，二者不能混用。
- `diagram_ref` 是 plan/resolved/artifacts 之间的稳定绑定键；默认可等于 `slot_id`。
- `slot_path` 是 JSON Pointer，用于 resolver 在 plan YAML 中定位原 slot。
- `prompt` 图必须是 `disclosure_policy: clean`。
- `required: true` 必须搭配 `on_failure: fail_assignment`。
- `solution` 图必须显式声明 `reuse_geometry_from`，并在 job graph 中依赖对应 prompt job。
- `DiagramJobRequest` 不携带 `layout_role`、`width_hint`、`image_path`。
- `DiagramArtifact.bindable: true` 要求 `status: ok`、`image_path` 非空、`hash` 非空。
- 学生版 resolved YAML 不应引用 `variant: solution` 或 `disclosure_policy: annotated` 的图片；这是 gate 层检查。
- `diagram_kind: synthetic_geometry` 默认搭配 `engine: geometric_scene`，走 Wolfram `GeometricScene` 求实例点位。
- `diagram_kind: coordinate_geometry` 或 `function_graph` 不应强塞进 `GeometricScene`；优先使用 `engine: wolfram_plot` 或 `engine: coordinate_renderer`。
- 函数图和坐标图的数学输入放在 `analytic_requirements`，包括 `viewport`、`axes`、`functions`、`objects`、`annotations` 与 `wolfram_plot_options`。
- `GeometryRenderSpec` 对综合几何要求 `points`；对坐标/函数图要求 `points`、`objects`、`functions`、`curves` 或 `samples` 至少一种可渲染对象。

## 4. 最小对象示例

### DiagramSlot

```yaml
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
  teaching_intent: "practice_prompt"
```

### FunctionGraph DiagramSlot

```yaml
diagram_slot:
  slot_id: "f1.prompt"
  diagram_ref: "f1.prompt"
  variant: "prompt"
  disclosure_policy: "clean"
  required: true
  on_failure: "fail_assignment"
  placement: "diagram_col"
  layout_role: "question_sidecar"
  width_hint: "0.34\\linewidth"
  caption: "函数图像"
  engine: "wolfram_plot"
  diagram_kind: "function_graph"
  teaching_intent: "practice_prompt"
  analytic_requirements:
    viewport:
      x_min: -2
      x_max: 6
      y_min: -6
      y_max: 12
      preserve_aspect: true
    axes:
      x: true
      y: true
      grid: true
      show_ticks: true
      x_label: "x"
      y_label: "y"
    functions:
      - id: "f"
        variable: "x"
        expression_latex: "2x-1"
        expression_wl: "2*x - 1"
        domain:
          min: -2
          max: 6
        label: "y=2x-1"
    objects:
      - type: "point"
        id: "A"
        x: 2
        y: 3
        label: "A"
```

### DiagramJob

```json
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
  "teaching_intent": "practice_prompt",
  "request_path": "build/diagram/jobs/q3-part1-prompt/request.json",
  "out_dir": "build/diagram/jobs/q3-part1-prompt",
  "public_image_dir": "diagram/jobs/q3-part1-prompt/rendered",
  "depends_on": [],
  "content_hash": "sha256:..."
}
```

### DiagramJobRequest

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
    "clean_forbidden": ["不要画辅助线 AH"],
    "solution_allowed_annotations": []
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

### FunctionGraph DiagramJobRequest

```json
{
  "schema_version": "diagram-job-request/v2",
  "job_id": "f1-prompt",
  "assignment_id": "2026-06-03-function-practice",
  "problem_id": "f1",
  "slot_id": "f1.prompt",
  "variant": "prompt",
  "disclosure_policy": "clean",
  "engine": "wolfram_plot",
  "diagram_kind": "function_graph",
  "teaching_intent": "practice_prompt",
  "problem_context": {
    "stem_latex": "画出函数 $y=2x-1$ 的图像，并判断点 $A(2,3)$ 是否在图像上。",
    "grade_or_topic": "一次函数图像"
  },
  "semantic_constraints": {
    "given_objects": ["y=2x-1", "A(2,3)"],
    "given_constraints": ["A is the test point"],
    "clean_forbidden": ["不要标出判断结论", "不要用颜色暗示 A 一定在图像上"]
  },
  "analytic_requirements": {
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
        "label": "y=2x-1",
        "sample_count": 160
      }
    ],
    "objects": [
      {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"}
    ],
    "wolfram_plot_options": {
      "aspect_ratio": "Automatic",
      "plot_range_padding": "Scaled[0.04]"
    }
  },
  "visual_requirements": {
    "show_labels": true,
    "show_given_markers": true,
    "show_axes": true,
    "preferred_orientation": "square",
    "caption": "函数图像"
  },
  "engine_options": {
    "max_retries": 2,
    "wolfram_timeout_s": 20,
    "wolfram_hard_timeout_s": 40,
    "model_config": {}
  }
}
```

### FunctionGraph GeometryRenderSpec

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

### DiagramArtifact

```json
{
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
```
