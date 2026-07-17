# Practice Diagram Slot Reference

只在练习题需要配图时读取。

## Rules

- 题干出现“如图/图中/下图”时必须声明 `diagram_slot`。
- 几何大题或条件较多、仅靠文字会显著增加读题负担的几何题，应声明 `diagram_slot`。
- 每个需要图的练习题默认使用唯一 `diagram_slot.slot_id`。
- 若复用构型，必须显式写 `reuse_geometry_from`，并保证题干条件完全一致。
- 给普通 assignment 补图时，必须回到本 writer 重新生成 plan YAML；不得把已经生成的普通 assignment 机械转换成 plan YAML。
- 学生版只声明 `prompt` / `clean` slot。
- 教师版解析若需要辅助线，另声明 `solution` / `annotated` slot，并复用对应 prompt slot。
- `prompt/clean` 默认只显示题干几何对象和必要顶点标签；长度、比例、相等、角度等题干条件用于约束构型，不自动成为可见标注。只有 `visual_requirements.required_visible_annotations` 明确列出时才要求在原题图中显示。讲解标记放在教师版 `solution/annotated` 图中。
- 默认声明 `display_profile`，不要在 plan YAML 中手写字号、字体、`diagram_col` 或图片字段。
- 侧栏题图使用 `display_profile: "worksheet_geometry_sidecar"`，默认 resolved 宽度为 `60mm`，点标注为 `44px`；点和标注很密时，在 `visual_requirements.label_density` 写 `dense`，renderer 会使用 `52px` 点标注。
- 只有确有排版理由时才写 `width_hint`；合法值必须是 `60mm`、`7cm`、`42pt`、`2in` 或 `0.32\\linewidth` 这类 LaTeX 尺寸。侧栏图不得低于 `55mm`。
- `solution/annotated` 中明确要求显示的长度只标数字，如 `7`、`19`；不要生成 `CD=19` 这类完整等式标签。学生 `prompt/clean` 不因题干给出长度就自动显示数字。
- plan YAML 不得写最终图片字段：不写 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row` 或 `answer_space.diagram_col`。
- collector/resolver 扫描 block 级 `diagram_slot`、`answer_space.diagram_slot`、`answer_space.parts[].diagram_slot`。不要在 plan 阶段手写 `diagram_row.items[]`。
- `diagram_kind` 是 plan-stage 必填语义。writer 不选择 `engine`；Host 在 Agent 启动前生成不可变的 `DiagramExecutionPlan`。旧 YAML 中的 `engine` 只由兼容层读取。
- 普通欧氏几何（如三角形、平行线、相似、角平分线、共线线段比例）使用 `diagram_kind: "synthetic_geometry"`；Host 强制路由到 `geometric_scene + symbolic_only`。
- 坐标平面图使用 `diagram_kind: "coordinate_geometry"`，数学输入写入 `analytic_requirements.coordinate_ir`。
- 只有题目明确涉及坐标轴、坐标点、函数图像、解析式、交点/读图或坐标平面面积时，才使用 `coordinate_geometry`。
- 立体几何题使用 `diagram_kind: "spatial_geometry"`；Host 路由到 `spatial_renderer`。一般线面/多面体优先 `textbook_oblique`，两面相交或二面角用 `hinge_planes`，空间坐标/向量用 `orthographic_3d`。
- `engine_options.spatial_spec` 必须保留三维 `points3d`，声明结构化 `relations`、`projection` 和 `quality_focus`；不得由 writer 先投影成二维点。
- 两平面交线通过 `derived_segments.relation: plane_intersection_line` 求解。学生 prompt 图不得包含 `role: auxiliary`，教师 solution 图必须复用对应 prompt 构型。
- 函数图像必须写 `type: "function_curve"`，包含 `expression_latex` 或 `expression_wl`，并写 `domain_segments`；不要用 `polyline` 冒充函数图像。
- `polyline` 只用于题面明确给出的折线或低层渲染结果，不承载函数解析式。

## Minimal Slot

```yaml
diagram_slot:
  slot_id: "c1.prompt"
  diagram_ref: "c1.prompt"
  variant: "prompt"
  disclosure_policy: "clean"
  required: true
  on_failure: "fail_assignment"
  placement: "diagram_col"
  layout_role: "question_sidecar"
  display_profile: "worksheet_geometry_sidecar"
  caption: "观察点 D 在边 BC 上的位置。"
  diagram_kind: "synthetic_geometry"
  teaching_intent: "practice_prompt"
  semantic_constraints:
    given_objects: ["A", "B", "C", "D"]
    given_constraints: ["D on BC", "AB=AC"]
```

## Coordinate Plane Slot

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
  display_profile: "worksheet_geometry_sidecar"
  caption: "函数图像"
  diagram_kind: "coordinate_geometry"
  teaching_intent: "practice_prompt"
  analytic_requirements:
    coordinate_ir:
      viewport:
        x_min: -4
        x_max: 5
        y_min: -6
        y_max: 5
        preserve_aspect: true
      axes:
        x: true
        y: true
        grid: false
        show_ticks: true
        x_label: "x"
        y_label: "y"
        # 可选：控制坐标轴刻度线和刻度数字；不写时由 pgfplots 自动生成。
        # x_ticks: [-4, -2, 2, 4]
        # y_ticks: [-6, -4, -2, 2, 4]
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
          expression_latex: "x-2"
          expression_wl: "x - 2"
          domain_segments:
            - { min: -4, max: 5 }
          label: "$y=x-2$"
          sample_count: 80
        - type: "function_curve"
          id: "g"
          variable: "x"
          expression_latex: "\\frac{3}{x}"
          expression_wl: "3/x"
          domain_segments:
            - { min: -4, max: -0.5 }
            - { min: 0.5, max: 5 }
          label: "$y=\\frac{3}{x}$"
          sample_count: 80
        - type: "point"
          id: "A"
          x: 3
          y: 1
          label: "A"
        - type: "point"
          id: "B"
          x: -1
          y: -3
          label: "B"
        # 可选：用派生交点读横/纵坐标时，不要手写垂足点；用 projection_guide。
        # - type: "derived_point"
        #   id: "P"
        #   derive: "intersection"
        #   of: ["f", "g"]
        #   label: "P"
        # - type: "projection_guide"
        #   id: "P_x"
        #   point: "P"
        #   to_axis: "x"        # 读交点横坐标；to_axis: "y" 则读纵坐标
        #   label_style: { label: "1", dy_pt: -5 }
        #   style: { dash: "5 4" }
```
