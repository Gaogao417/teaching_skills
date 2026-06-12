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
