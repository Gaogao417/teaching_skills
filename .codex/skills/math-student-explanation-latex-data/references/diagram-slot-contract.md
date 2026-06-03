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
  layout_role: "explanation_figure"
  width_hint: "0.42\\linewidth"
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
- `caption` 写学生要观察的动作，不写调试信息。
- plan YAML 不得出现 `image_path`、`diagram_job_id`、`diagram_col`、`diagram_row`、`answer_space.diagram_col` 或最终 `type: diagram` 图片对象。
- 如果图形暂不支持，写 `hint` fallback，不制造空 slot。
