# Practice Diagram Slot Reference

只在练习题需要配图时读取。

## Rules

- 题干出现“如图/图中/下图”时必须声明 `diagram_slot`。
- 几何大题或条件较多、仅靠文字会显著增加读题负担的几何题，应声明 `diagram_slot`。
- 每个需要图的练习题默认使用唯一 `diagram_slot.slot_id`。
- 若复用构型，必须显式写 `reuse_geometry_from`，并保证题干条件完全一致。
- 学生版只声明 `prompt` / `clean` slot。
- 教师版解析若需要辅助线，另声明 `solution` / `annotated` slot，并复用对应 prompt slot。
- 默认声明 `display_profile`，不要在 plan YAML 中手写字号、字体、`diagram_col` 或图片字段。
- 侧栏题图使用 `display_profile: "worksheet_geometry_sidecar"`，默认 resolved 宽度为 `60mm`，点标注为 `44px`；点和标注很密时，在 `visual_requirements.label_density` 写 `dense`，renderer 会使用 `52px` 点标注。
- 只有确有排版理由时才写 `width_hint`；合法值必须是 `60mm`、`7cm`、`42pt`、`2in` 或 `0.32\\linewidth` 这类 LaTeX 尺寸。侧栏图不得低于 `55mm`。
- 长度条件在图上只标数字，如 `7`、`19`；不要要求生成 `CD=19` 这类完整等式标签。
- plan YAML 不得写最终图片字段：不写 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row` 或 `answer_space.diagram_col`。
- collector/resolver 扫描 block 级 `diagram_slot`、`answer_space.diagram_slot`、`answer_space.parts[].diagram_slot`。不要在 plan 阶段手写 `diagram_row.items[]`。
- 坐标平面图使用 `diagram_kind: "coordinate_geometry"`，数学输入写入 `analytic_requirements.coordinate_ir`。
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
  engine: "geometric_scene"
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
  engine: "wolfram_client"
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
