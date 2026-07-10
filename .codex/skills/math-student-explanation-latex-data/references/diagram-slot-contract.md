# Diagram Slot Contract

只在 explanation YAML 需要声明几何图时读取。plan 阶段只声明图位，真实图片由 `math-geometry-diagram-renderer` 生成。

## Plan 阶段允许字段

```yaml
diagram_slot:
  slot_id: "explanation.orig.prompt"
  diagram_ref: "explanation.orig.prompt"
  variant: "prompt"
  disclosure_policy: "clean"
  required: true
  on_failure: "fail_assignment"
  placement: "block_center"
  layout_role: "center_block"
  display_profile: "worksheet_geometry_center"
  caption: "先观察底边 BC 与顶点 A 的位置关系。"
  engine: "geometric_scene"
  diagram_kind: "synthetic_geometry"
  teaching_intent: "explanation_prompt"
  semantic_constraints:
    given_objects: ["A", "B", "C"]
    given_constraints: ["AB=AC"]
```

## Rules

- `slot_id` 必须唯一。
- 原题图使用 `variant: "prompt"` 和 `disclosure_policy: "clean"`。
- 辅助线讲解图使用 `variant: "solution"` 和 `disclosure_policy: "annotated"`，并显式写 `reuse_geometry_from`。
- 给已有讲义补图时，必须回到本 writer 重新生成 plan YAML；不得把普通 assignment 机械转换成 plan YAML。
- 若辅助图对应某个解答动作，如“作辅助线”“补中点”“连接某线段”，优先把 `diagram_slot` 写在对应 `route.steps[]` 下，并使用 `placement: "step_diagram"`；不要单独制造一个“辅助图” `problemcard`。
- `caption` 写学生要观察的动作，不写调试信息。
- 默认只写 `display_profile`，不要手写字号、字体或图片宽度。侧栏原题图用 `worksheet_geometry_sidecar`，默认 resolved 宽度为 `60mm`；居中讲解图用 `worksheet_geometry_center`，默认 resolved 宽度为 `70mm`。
- 只有确有排版理由时才写 `width_hint`；合法值必须是 `60mm`、`7cm`、`42pt`、`2in` 或 `0.32\\linewidth` 这类 LaTeX 尺寸。侧栏图不得低于 `55mm`。
- 长度条件交给 renderer 以数字形式标注，如 `7`、`19`，不要在图中要求生成 `CD=19` 这类冗长标签。
- plan YAML 不得出现 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row`、`answer_space.diagram_col` 或最终 `type: diagram` 图片对象。
- 普通欧氏几何（如三角形、平行线、相似、角平分线、共线线段比例）默认使用 `engine: "geometric_scene"` 与 `diagram_kind: "synthetic_geometry"`。
- 只有题目明确涉及坐标轴、坐标点、函数图像、解析式、交点/读图或坐标平面面积时，才使用 `diagram_kind: "coordinate_geometry"`。
- 空间点线面、棱柱棱锥、二面角、异面直线距离等使用 `engine: "spatial_renderer"` 与 `diagram_kind: "spatial_geometry"`，三维输入写入 `engine_options.spatial_spec`。一般关系图用 `textbook_oblique`，两面相交用 `hinge_planes`，空间坐标/向量用 `orthographic_3d`。
- 空间图必须声明 `points3d`、`segments`/`polygons`、结构化 `relations`、`projection` 和 `quality_focus`。两个平面相交时用 `derived_segments.relation: plane_intersection_line`，不要手估交线端点。
- 空间 prompt 图不得声明 `role: auxiliary`；讲解辅助线放在 solution/annotated slot，并复用 prompt 构型。
- 如果图形暂不支持，不补额外提示 block，也不制造空 slot。
- 必需图使用 `required: true` 和 `on_failure: "fail_assignment"` 让流程显式失败；非必需图直接跳过图位。
