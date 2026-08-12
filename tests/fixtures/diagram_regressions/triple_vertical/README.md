# 三垂直相似 — diagram regression fixture

Regression fixture for the diagram workflow failure that blocked the
2026-08-12 三垂直相似比例中项 assignment at 12/13: the p2 prompt
(正方形 `ABCD`, `E` midpoint of `BC`, `EF⊥AE`) failed audit with
`invalid_point_label` because the scene-authoring agent emitted aggregated
Wolfram-style label strings instead of per-point `{"A": {"text": "A"}}` labels.

## Files

- `p2-square-midpoint.plan.assignment.yaml` — single-problem assignment for the
  p2-focused regression (P8-A). Runs exactly one job (`p2-prompt`).
- `full-student.plan.assignment.yaml` — 13-problem student assignment
  (3 choice + 3 fillin + 7 problem) for the full-chain regression (P8-B).
- `full-teacher.plan.assignment.yaml` — teacher counterpart with
  `answer` / `solution_steps` / `teaching` block fields.
- `expected/p2-required-markers.json` — canonical p2 `required_visible_annotations`
  marker list + their audit signatures (computed via the real `_marker_signature`),
  including the stem-required right angle at `E` (arms `A`, `F`).
- `expected/assignment-summary.json` — authoritative 13-job summary
  (`job_id`, `engine`, `diagram_kind`, `required`, …) produced by `collect_jobs`.

## What changed vs the source artifact

Both full plans add the missing stem-required marker to p2's
`visual_requirements.required_visible_annotations.markers`:

```yaml
- {type: right_angle, vertex: E, arms: [A, F]}   # EF⊥AE
```

The stem ("过 $E$ 作 $EF\perp AE$") implies a right angle at `E`; the original
artifact omitted it, so the audit never required it. The four square-corner right
angles, the four-side `equal_ticks`, and the `BE=EC` `equal_ticks` are preserved.

## Coverage

- 三垂直母图 `AB·DE = BC·CD` (c1, f1, p3, p4, p5, p6)
- 压缩交叉模型 `BC² = AB·CD` (p1)
- 平方根型 `a = d` (c2, f2, p3)
- 比例中项型 `b = c` (f3)
- 三垂直包装进正方形 (p2)
- 坐标系迁移 (p7, `coordinate_geometry` via `coordinate_renderer`)
- choice / fillin / problem block types
