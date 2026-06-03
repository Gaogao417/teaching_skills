# Function Graph Diagram Contract

本文档定义解析几何/函数图分支的最小 contract。它补充 `docs/diagram-workflow-architecture.md` 和 `docs/diagram-job-schema.md`，不改变综合几何的 `geometric_scene` 主线。

## 1. 适用范围

使用 `diagram_kind: function_graph`：

- 一次函数、二次函数、反比例函数、三角函数等图像。
- 判断点是否在函数图像上。
- 求函数交点、零点、极值、对称轴、面积读图。
- 题目明确要求坐标轴、网格、刻度或函数曲线。

使用 `diagram_kind: coordinate_geometry`：

- 坐标系内的点、线段、直线、圆、多边形。
- 点到直线距离、两点距离、面积、坐标变换。
- 只有解析对象，没有连续函数曲线。

不要把这些任务默认路由到 `geometric_scene`。`GeometricScene` 适合综合几何，不适合作为函数图像和坐标轴渲染的主入口。

## 2. Engine 选择

| 场景 | 推荐 engine | 说明 |
|---|---|---|
| 函数曲线 + 坐标轴 | `wolfram_plot` | Wolfram 校验表达式、采样、计算关键点，可直接导出 Plot PNG/SVG |
| 坐标点/线/多边形 | `coordinate_renderer` | 本地确定性 renderer 画坐标系和对象；可选 Wolfram 校验 |
| 函数图但需要本地统一风格 | `coordinate_renderer` | Wolfram 只产 samples，最终由本地 renderer 画 |
| 综合几何示意 | `geometric_scene` | 不属于函数图分支 |

无论是否由 Wolfram 直接导出图片，都必须写 `final_renderer_spec.json`，记录 `viewport`、`axes`、`functions`、`objects` 或 `samples`。

## 3. DiagramSlot 最小要求

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
    axes:
      x: true
      y: true
      grid: true
      show_ticks: true
    functions:
      - id: "f"
        variable: "x"
        expression_latex: "2x-1"
        expression_wl: "2*x - 1"
        domain:
          min: -2
          max: 6
    objects:
      - type: "point"
        id: "A"
        x: 2
        y: 3
        label: "A"
```

## 4. Workflow 输出要求

`workflow.py` 对函数图输出：

- `workflow_result.json`：状态、失败类型、Wolfram summary、model attempts。
- `final_renderer_spec.json`：可审计的函数图 spec。
- `renderer_result.json`：最终 PNG/SVG 路径，可能来自 Wolfram Plot，也可能来自本地 coordinate renderer。

函数图 `final_renderer_spec.json` 至少满足：

```json
{
  "schema_version": "geometry-render-spec/v1",
  "type": "function_graph",
  "viewport": {"x_min": -2, "x_max": 6, "y_min": -6, "y_max": 12},
  "axes": {"x": true, "y": true, "grid": true, "show_ticks": true},
  "functions": [
    {
      "id": "f",
      "variable": "x",
      "expression_latex": "2x-1",
      "expression_wl": "2*x - 1",
      "domain": {"min": -2, "max": 6}
    }
  ],
  "samples": {
    "f": [[-2, -5], [0, -1], [2, 3], [6, 11]]
  },
  "objects": [
    {"type": "point", "id": "A", "x": 2, "y": 3, "label": "A"}
  ]
}
```

## 5. Clean / Annotated Policy

Prompt 图：

- 只画题干给出的函数、点、坐标轴、必要网格。
- 不用颜色、箭头、文字提前暗示判断结论。
- 不标出未给出的交点、零点、面积阴影或辅助虚线。

Solution 图：

- 可标交点、零点、辅助虚线、面积阴影、对称轴、顶点、单调区间。
- 必须使用 `variant: solution` 和 `disclosure_policy: annotated`。
- 学生版 resolved YAML 不得引用 solution 图。

## 6. 后续实现 TODO

1. `run_diagram_batch.py` 从 plan slot 提取 `analytic_requirements`，写入 `DiagramJobRequest`。
2. `run_diagram_workflow.py` 按 `engine + diagram_kind` 路由 `wolfram_plot` / `coordinate_renderer`，不要 skip `function_graph`。
3. 新增 Wolfram Plot adapter：表达式安全校验、采样、关键点计算、PNG/SVG 导出。
4. 扩展 renderer/gate：检查 viewport 合法、函数/对象引用一致、图片路径可访问。
5. 增加 e2e fixture：一次函数图 + 坐标点，覆盖 S2.5-S2.9。
