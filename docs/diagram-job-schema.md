# Diagram Job Schema

本文档把 `docs/diagram-workflow-architecture.md` 中的 diagram 数据流收敛成可实现的 Pydantic contract。类型定义落在 `scripts/diagram_workflow/diagram_contracts.py`。

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
     - 生产链路只写并调用每个 job 的 `request.json`

final_renderer_spec.json
  -> renderer_result.json + rendered/<variant>.fragment.tex
     - render_geometry_spec 只做确定性 TikZ 编译
     - TikZ fragment 是唯一可绑定产物
     - PDF/PNG/SVG 预览只作诊断，不作为绑定合同

jobs/<job_id>/renderer_result.json
  -> RendererBindingManifest
     - renderer_bindings.py 从 jobs + renderer_result 汇总可绑定事实
     - renderer_result.json 是每个 job 的唯一 renderer 事实源

assignment.plan.yaml + RendererBindingManifest
  -> assignment.resolved.yaml
     - resolve_assignment_diagrams 把 DiagramSlot 绑定为 ResolvedDiagramTikz
     - 输出模板可消费的 diagram_col / diagram_row / type: diagram

assignment.resolved.yaml
  -> .tex -> .pdf
     - math-assignment-latex 直接 \input 或内联 TikZ fragment
```

## 2. Pydantic 类型边界

| 阶段 | 文件/对象 | Pydantic 类型 | 写入者 | 消费者 |
|---|---|---|---|---|
| plan YAML | `diagram_slot` | `DiagramSlot` | latex-data skills | collector / plan gate |
| batch manifest | `diagram_jobs.json` | `DiagramJobsManifest` / `DiagramJob` | collector | batch runner / gate |
| workflow input | `request.json` | `DiagramJobRequest` | collector / batch runner | `workflow.py` adapter |
| workflow output | `workflow_result.json` | `DiagramJobResult` | `workflow.py` | renderer binding / gate |
| renderer input | `final_renderer_spec.json` | `GeometryRenderSpec` | `workflow.py` | renderer |
| renderer output | `renderer_result.json` | `GeometryRendererResult` | renderer | renderer binding |
| binding manifest | in-memory / optional `renderer_bindings.json` | `RendererBindingManifest` / `RendererBinding` | `renderer_bindings.py` | resolver / gate |
| resolved YAML | TikZ payload | `ResolvedDiagramTikz` | resolver | LaTeX templates |
| render gate | gate report | `DiagramGateReport` / `DiagramGateCheck` | check_diagram_gate | pipeline |

## 3. 强制约束

- `slot_id` 表示“图片放在哪里”，`job_id` 表示“一次生成任务”，二者不能混用。
- `diagram_ref` 是 plan/resolved/renderer bindings 之间的稳定绑定键；默认可等于 `slot_id`。
- `slot_path` 是 JSON Pointer，用于 resolver 在 plan YAML 中定位原 slot。
- `prompt` 图必须是 `disclosure_policy: clean`。
- `required: true` 必须搭配 `on_failure: fail_assignment`。
- `solution` 图必须显式声明 `reuse_geometry_from`，并在 job graph 中依赖对应 prompt job。
- `DiagramJobRequest` 不携带 `layout_role`、`width_hint`、`image_path`。
- `DiagramJobRequest` v2 是 workflow 的唯一生产输入；batch runner 默认只生成 v2 `request.json`。
- `RendererBinding.bindable: true` 要求 `status: ok`、TikZ source 非空且可访问、`hash` 非空。
- 学生版 resolved YAML 不应引用 `variant: solution` 或 `disclosure_policy: annotated` 的图片；这是 gate 层检查。
- `diagram_kind: synthetic_geometry` 默认搭配 `engine: geometric_scene`，走 Wolfram `GeometricScene` 求实例点位。
- `diagram_kind: coordinate_geometry` 表示坐标平面图，包括只画点/线/多边形，也包括需要画函数曲线的图；函数曲线通过 `analytic_requirements.coordinate_ir.objects[].type=function_curve` 表达，不再在 plan slot 顶层写 `diagram_kind: function_graph`。
- `diagram_kind: spatial_geometry` 搭配 `engine: spatial_renderer`；三维输入写入 `engine_options.spatial_spec`，final renderer spec 必须保留 `points3d` 和 `projection`，不得提前改写成二维 `points`。
- `wolfram_plot` 仅保留为兼容 alias；新 plan 不推荐使用。
- 坐标平面图的数学输入放在 `analytic_requirements.coordinate_ir`，包括 `viewport`、`axes`、`objects` 与 `annotations`；旧 `functions` / `objects` 只作为短期 normalize 入口。
- `coordinate_ir.objects` 是 tagged union，常用类型为 `point`、`function_curve`、`line`、`segment`、`polygon_region`、`derived_point`、`guide_line`、`projection_guide`、`text_label`；函数不得用 plan 层 `polyline` 冒充。
- `GeometryRenderSpec` 对平面综合几何要求 `points`；对空间几何要求 `points3d + projection`；对坐标/函数图要求 `points`、`objects`、`functions`、`curves` 或 `samples` 至少一种可渲染对象。
- 空间图的投影与 gate 细则见 `docs/spatial-geometry-diagram-workflow.md`。

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

### Coordinate Plane DiagramSlot With Functions

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
  engine: "wolfram_client"
  diagram_kind: "coordinate_geometry"
  teaching_intent: "practice_prompt"
  analytic_requirements:
    coordinate_ir:
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
        # optional explicit tick control; labels are rendered as TikZ nodes at axis cs positions.
        # x_ticks: [-2, 0, 2, 4, 6]
        # y_ticks: [-6, -4, -2, 2, 4, 6, 8, 10, 12]
        # x_tick_labels:
        #   - { value: 2 }
        #   - { value: 4, dy_pt: -5 }
        # y_tick_labels:
        #   - { value: 2, dx_pt: -5 }
        #   - { value: 4 }
      objects:
        - type: "function_curve"
          id: "f"
          variable: "x"
          expression_latex: "2x-1"
          expression_wl: "2*x - 1"
          domain_segments:
            - { min: -2, max: 6 }
          label: "y=2x-1"
        - type: "function_curve"
          id: "g"
          variable: "x"
          expression_latex: "-x+4"
          expression_wl: "-x + 4"
          domain_segments:
            - { min: -2, max: 6 }
          label: "y=-x+4"
        - type: "point"
          id: "A"
          x: 2
          y: 3
          label: "A"
        - type: "derived_point"
          id: "P"
          derive: "intersection"
          of: ["f", "g"]
          label: "P"
        - type: "projection_guide"
          id: "P_x"
          point: "P"
          to_axis: "x"
          label_style: { label: "1", dy_pt: -5 }
          style: { dash: "5 4" }
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

### Coordinate Plane DiagramJobRequest With Functions

```json
{
  "schema_version": "diagram-job-request/v2",
  "job_id": "f1-prompt",
  "assignment_id": "2026-06-03-function-practice",
  "problem_id": "f1",
  "slot_id": "f1.prompt",
  "variant": "prompt",
  "disclosure_policy": "clean",
  "engine": "wolfram_client",
  "diagram_kind": "coordinate_geometry",
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
    "coordinate_ir": {
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
      "objects": [
        {
          "type": "function_curve",
          "id": "f",
          "variable": "x",
          "expression_latex": "2x-1",
          "expression_wl": "2*x - 1",
          "domain_segments": [{"min": -2, "max": 6}],
          "label": "y=2x-1",
          "sample_count": 160
        },
        {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"}
      ]
    },
    "wolfram_client_options": {
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

### RendererBinding

```json
{
  "slot_id": "q3.part1.prompt",
  "diagram_ref": "q3.part1.prompt",
  "job_id": "q3-part1-prompt",
  "status": "ok",
  "variant": "prompt",
  "disclosure_policy": "clean",
  "tikz_fragment_path": "build/diagram/jobs/q3-part1-prompt/rendered/prompt.fragment.tex",
  "preview_svg": "build/diagram/jobs/q3-part1-prompt/rendered/prompt.preview.svg",
  "hash": "sha256:...",
  "renderer_result": "build/diagram/jobs/q3-part1-prompt/renderer_result.json",
  "workflow_result": "build/diagram/jobs/q3-part1-prompt/workflow_result.json",
  "final_renderer_spec": "build/diagram/jobs/q3-part1-prompt/final_renderer_spec.json",
  "bindable": true,
  "warnings": []
}
```
