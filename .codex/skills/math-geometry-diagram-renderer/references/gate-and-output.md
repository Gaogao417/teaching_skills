# Gate And Output Reference

## Files To Inspect

```text
build/diagram/jobs/<job_id>/request.json
build/diagram/jobs/<job_id>/workflow_events.jsonl
build/diagram/jobs/<job_id>/rounds/round_*/scene_payload.json
build/diagram/jobs/<job_id>/rounds/round_*/render_result.json
build/diagram/jobs/<job_id>/rounds/round_*/vision_result.json
build/diagram/jobs/<job_id>/renderer_result.json
build/diagram/jobs/<job_id>/rendered/prompt.fragment.tex
build/diagram/jobs/<job_id>/rendered/solution.fragment.tex
build/diagram/jobs/<job_id>/rendered/*.preview.pdf
build/diagram/jobs/<job_id>/rendered/*.preview.png
build/diagram/jobs/<job_id>/rendered/*.preview.svg
```

## Resolved YAML Shape

resolver 生成的 TikZ 对象必须显式设置 `width`。`tikz_path` 是最终
LaTeX 可直接 `\input` 的 fragment；preview 文件只用于人工抽查。

```yaml
diagram_col:
  kind: "tikz"
  tikz_path: "diagram/jobs/c1-prompt/rendered/prompt.fragment.tex"
  diagram_job_id: "c1-prompt"
  width: "60mm"
  caption: "观察点 D 在 BC 上的位置。"
  variant: "prompt"
  disclosure_policy: "clean"
```

## Layout Rules

- 讲义原题展示用 clean prompt 图；讲解步骤如需辅助线，另生成 annotated solution 图。
- 选择题和解答题侧栏图使用 `display_profile: "worksheet_geometry_sidecar"`，resolved 宽度默认 `60mm`；侧栏绝对宽度低于 `55mm` 会被 gate 阻断。
- 填空题先排题干，再在题后用 `diagram_row.items[]`，单图宽度优先 `0.20\\linewidth` 到 `0.25\\linewidth`。
- 居中讲解图使用 `display_profile: "worksheet_geometry_center"`，resolved 宽度默认 `70mm`；居中图低于 `68mm` 会被 gate 阻断。
- 试卷中不要再用独立 `type: diagram` block 承载原题图。
- `caption` 写学生要观察的动作，不写调试信息。
- 顶点/关键点标签必须清晰可读：默认点标注 `44px`，密集图 `52px`，正常字重，serif italic 点名。
- 长度条件在图上只保留数字，如 `7`、`19`；不要输出 `AB=7`、`CD=19` 这类完整等式标签。

## Fallback

失败、跳过或 TikZ fragment 缺失时，不插入破图字段；改插入简短 `hint` 或 `reading_tip`。

```yaml
type: "hint"
id: "fig-main-fallback"
content: "本题建议先手动画出题干中的三角形和辅助线，再观察底边与高的对应关系。"
level: 1
```

## Spatial Gate

立体几何 job 还要检查：final spec 保留 `points3d`、不存在预投影 `points`、投影 backend 合法、基准面展开度和核心夹角达标、prompt 图不含 `role: auxiliary`。详细规则见 `spatial-geometry.md`。
