# 立体几何作图工作流

## 1. 目标

立体几何图不是三维软件截图。学生图的目标依次是：

1. 数学关系正确；
2. 题干对象与图上对象一致；
3. 基准面展开、核心夹角清楚、原线和辅助线可区分；
4. 图形风格接近高中教材，能够稳定进入 LaTeX 作业。

因此，三维事实和纸面投影必须分层：

```text
题干与定理条件
  -> diagram_slot.spatial_spec
  -> 三维坐标、关系校验、平面交线求解
  -> GeometryRenderSpec(points3d + projection)
  -> TikZ 三维坐标基 / tikz-3dplot
  -> fragment.tex + preview
  -> spatial gate
  -> resolved assignment.yaml
```

Python 可以为质量审计计算二维投影指标，但最终 fragment 不得消费 Python 预投影的二维点。

## 2. 路由

| 任务 | engine / kind | 默认投影 |
|---|---|---|
| 平面、线面关系，棱柱、棱锥 | `spatial_renderer / spatial_geometry` | `textbook_oblique` |
| 两面相交、二面角 | `spatial_renderer / spatial_geometry` | `hinge_planes` |
| 空间直角坐标系、空间向量 | `spatial_renderer / spatial_geometry` | `orthographic_3d` |
| 柱、锥、球等轴向几何体 | `spatial_renderer / spatial_geometry` | `axial_solid` |
| 普通平面欧氏几何 | `geometric_scene / synthetic_geometry` | 不进入空间图链路 |
| 坐标平面与函数图 | `coordinate_renderer / coordinate_geometry` | pgfplots 坐标轴 |

`textbook_oblique` 使用教材斜二测坐标基：主轴保持、退深轴默认 `45°`、退深比例默认 `1/2`、竖直方向保持。`hinge_planes` 与 `orthographic_3d` 保留三维坐标到 `tikz-3dplot`，但使用不同视角默认值。

## 3. Plan 契约

```yaml
diagram_slot:
  slot_id: "q1.prompt"
  diagram_ref: "q1.prompt"
  variant: "prompt"
  disclosure_policy: "clean"
  required: true
  on_failure: "fail_assignment"
  placement: "diagram_col"
  layout_role: "question_sidecar"
  display_profile: "worksheet_geometry_sidecar"
  engine: "spatial_renderer"
  diagram_kind: "spatial_geometry"
  teaching_intent: "practice_prompt"
  engine_options:
    spatial_spec:
      points3d:
        A: [0, 0, 0]
        B: [4, 0, 0]
        C: [4, 3, 0]
        D: [0, 3, 0]
        E: [0, 0, -1]
        F: [4, 0, -1]
        G: [4, 0, 2]
        H: [0, 0, 2]
      polygons:
        - { id: alpha, points: [A, B, C, D] }
        - { id: beta, points: [E, F, G, H] }
      segments: []
      derived_segments:
        - id: l
          relation: plane_intersection_line
          planes: [alpha, beta]
          role: intersection
      relations:
        - { relation: plane_intersection_line, objects: [alpha, beta, l] }
      labels:
        D: { text: "$\\alpha$", show_point: false }
        H: { text: "$\\beta$", show_point: false }
      projection:
        mode: hinge_planes
      quality_focus:
        base_planes: [alpha]
```

### 对象角色

- `main`：题干或定理中的主线；
- `secondary`：原图中的次要边；
- `intersection`：两平面交线，使用较粗实线；
- `hidden`：被遮挡的原边，使用细虚线；
- `auxiliary`：解题时新增的辅助线，只能出现在 solution/annotated 图；
- `projection`：射影线或背景投影，使用低对比虚线。

颜色不承担数学语义。空间图统一灰阶，由线型和粗细区分对象角色。

`points3d` 可以包含求交、裁剪和遮挡所需的计算点；学生图只显示 `labels` 中显式声明的标签。面名或线名可以挂在已有点或专用辅助坐标上，并设置 `show_point: false`，禁止自动暴露全部三维点。

## 4. 三维条件

`relations` 当前校验：

- `parallel`；
- `perpendicular`；
- `point_on_line`；
- `point_in_plane`；
- `line_in_plane` / `segment_in_plane`；
- `plane_intersection_line`；
- `non_collinear`；
- `angle_between`、`distance_between`、`area_projection`、`volume_height` 的对象存在性。

两个平面相交时优先声明 `derived_segments.relation: plane_intersection_line`，renderer 根据两个平面方程求交线，并裁剪到两个平面多边形的共同可见范围。不要手估交线端点。

## 5. 投影选择

### textbook_oblique

用于教材式关系图和多面体。三维坐标不应预先压扁；例如长、宽为 `4, 3` 的底面仍写 `4, 3`，退深减半由投影完成。

### hinge_planes

用于两个相交平面、二面角和三垂线构型。默认 `theta=50, phi=120`。`quality_focus.angle_checks` 应覆盖二面角平面角或主要垂线夹角。

### orthographic_3d

用于空间坐标与向量，默认 `theta=55, phi=120`。此模式优先保持坐标方向，不追求斜二测外观。

### axial_solid

用于柱、锥等竖直轴明显的几何体。圆形截面仍需使用椭圆/弧对象；不能用多边形冒充圆。

## 6. Gate

空间图除通用 bindable、TikZ、布局和 SVG 检查外，还必须通过：

- `points3d` 一直保留到 final renderer spec；
- final spec 不得携带预投影 `points`；
- 投影 backend 只能是 `tikz_coordinate_basis` 或 `tikz-3dplot`；
- `quality_focus.base_planes` 的展开度不得低于 projection 阈值；
- `quality_focus.angle_checks` 的最小投影夹角不得低于阈值；
- prompt/clean 图不得包含 `role: auxiliary`；
- solution/annotated 图必须通过 `reuse_geometry_from` 复用 prompt 三维构型。

预览仍需人工抽查标签遮挡、点序和题干对象对应。数值 gate 不能替代图义复核。

## 7. 性能记录

每次空间作图在 job 目录输出 `performance_profile.json`。它记录实际 wall-clock 用时，分为：

- `workflow`：读取及校验 request、归一化空间对象、求两面交线、关系校验、投影可读性诊断、写出最终 spec；
- `renderer`：校验 renderer spec、编译 TikZ、写 artifact、XeLaTeX 编译、PNG/SVG 预览导出。

整份作业在 `build/diagram/pipeline_performance.json` 记录 `collect`、`batch`、`gate`、`resolve` 四个阶段。预览中的 `latex_compile`、`png_export`、`svg_export` 是 `renderer.stages` 的子阶段；不要把这些子阶段与 `build_previews` 再次相加。

这些数据用于比较同一投影模板、图元规模或工具链变更前后的性能。它是本机 wall-clock 指标，不包含人工看图时间；`geometric_scene` 的 Agent/Wolfram 耗时仍以其原有工作流事件为准。

## 8. 固定图与新题图

- 定理默写等高度重复构型，先查固定图库；命中同一 theorem id 时直接复用审核过的 fragment。
- 普通题目、截面题和新构型通过 `diagram_slot` 进入正式空间图链路。
- 固定图库和正式链路共享三维事实、对象角色和投影分类，但固定图库不伪装成一次新的 diagram job。
- 固定图只能复用完全相同的数学对象集合；标签、条件或辅助线发生变化时必须新建空间图 job。

## 9. 验证

```bash
./.venv/bin/python -m pytest -q \
  tests/test_diagram_contracts.py \
  tests/test_spatial_diagram_workflow.py \
  tests/test_tikz_renderer.py

./.venv-diagram/bin/python scripts/diagram_workflow/run_assignment_diagrams.py \
  artifacts/<学生>/<日期-主题>/<name>.plan.assignment.yaml
```

正式 assignment 仍按 `collect -> batch -> gate -> resolve` 执行；LaTeX renderer 只消费 resolved TikZ，不在排版阶段重新出图。
