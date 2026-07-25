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
- 线段边长或份数标注默认绑定该线段两个端点，位置为“线段中点 + 法向量 × 间距”。`normal_side: clockwise|counterclockwise|auto` 控制从起点到终点的顺时针侧、逆时针侧或自动侧；正式题库图优先显式指定，不沿线方向漂移。线段与水平方向的锐角在 `10°–45°`（含边界）时，数字文字基线沿线段方向，即垂直于法线；旋转角规范到 `-90°–90°` 以保持正读。其余角度保持水平。renderer 使用透明背景和加粗数学字体，不得使用白底、边框或卡片式衬底。
- 分数边长必须渲染成上下式 `\frac{a}{b}`；同一幅逐步图不得在同一线段上重复标注另一套数值。
- `segment_position: auto|offset|legend` 控制线段数字的位置。`auto` 始终保持线段中点这一纵向位置，依次尝试首选法向侧的贴边距离、同侧稍大距离、另一法向侧；两侧均与点名、非目标点或已有数字实质重叠时才降级为 legend。逐步讲解图从本步新增标注向前分配空间，使新解出的数值优先留在对应边中点附近，旧标注只改变法向侧或法向距离，不改变数值与颜色。狭窄区域也可直接声明 `legend`。不提供把数字直接压在线段上的生产模式。
- 逐步比例图的颜色不可由 renderer 重排：题设蓝色、第一模型红色、第二模型绿色；后一步完整保留前一步已有标注的数值、位置模式与颜色。
- `normal_offset_cm` 控制 offset 标注中心到线段的法向距离；默认整数 `0.22cm`、上下分数 `0.30cm`。不得用点名的通用 x/y 偏移模拟法向距离。

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
