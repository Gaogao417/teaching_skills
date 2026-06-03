# Gate And Output Reference

## Files To Inspect

```text
build/diagram/jobs/<job_id>/request.json
build/diagram/jobs/<job_id>/workflow_events.jsonl
build/diagram/jobs/<job_id>/rounds/round_*/scene_payload.json
build/diagram/jobs/<job_id>/rounds/round_*/render_result.json
build/diagram/jobs/<job_id>/rounds/round_*/vision_result.json
build/diagram/jobs/<job_id>/renderer_result.json
build/diagram/jobs/<job_id>/rendered/prompt.png
build/diagram/jobs/<job_id>/rendered/solution.png
```

## Resolved YAML Shape

resolver 生成的图片对象必须显式设置 `width`。

```yaml
diagram_col:
  image_path: "diagram/jobs/c1-prompt/rendered/prompt.png"
  diagram_job_id: "c1-prompt"
  width: "0.30\\linewidth"
  caption: "观察点 D 在 BC 上的位置。"
  variant: "prompt"
  disclosure_policy: "clean"
```

## Layout Rules

- 讲义原题展示用 clean prompt 图；讲解步骤如需辅助线，另生成 annotated solution 图。
- 选择题用 `diagram_col`，宽度优先 `0.28\\linewidth` 到 `0.32\\linewidth`。
- 填空题先排题干，再在题后用 `diagram_row.items[]`，单图宽度优先 `0.20\\linewidth` 到 `0.25\\linewidth`。
- 解答题用 `answer_space.diagram_col` 或 `answer_space.parts[].diagram_col`，宽度优先 `0.30\\linewidth` 到 `0.34\\linewidth`。
- 试卷中不要再用独立 `type: diagram` block 承载原题图。
- `caption` 写学生要观察的动作，不写调试信息。
- 顶点/关键点标签必须清晰可读。

## Fallback

失败、跳过或图片缺失时，不插入破图字段；改插入简短 `hint` 或 `reading_tip`。

```yaml
type: "hint"
id: "fig-main-fallback"
content: "本题建议先手动画出题干中的三角形和辅助线，再观察底边与高的对应关系。"
level: 1
```
