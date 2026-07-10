# Spatial Geometry Reference

## Route

空间点线面、棱柱棱锥、二面角、异面直线距离等使用：

```yaml
engine: "spatial_renderer"
diagram_kind: "spatial_geometry"
```

输入放在 `engine_options.spatial_spec`。必须先声明三维坐标与关系，再选纸面投影；不得提供预投影二维 `points`。

## Projection

- `textbook_oblique`: 一般教材关系图、棱柱、棱锥；45 度退深、默认减半。
- `hinge_planes`: 两面相交、二面角、三垂线；默认 `theta=50, phi=120`。
- `orthographic_3d`: 空间坐标系、空间向量。
- `axial_solid`: 柱、锥、球等轴向几何体；圆形截面必须使用圆弧/椭圆语义。

三维坐标不预压扁。长宽为 4、3 的底面仍写 4、3，退深比例由投影层完成。

## Required Spatial Fields

```yaml
engine_options:
  spatial_spec:
    points3d: {...}
    segments: [...]
    polygons: [...]
    labels: {...}
    relations: [...]
    projection: { mode: textbook_oblique }
    quality_focus:
      base_planes: [alpha]
      angle_checks:
        - { id: AOB, vertex: O, arms: [A, B] }
```

平面交线使用 `derived_segments`：

```yaml
derived_segments:
  - id: l
    relation: plane_intersection_line
    planes: [alpha, beta]
    role: intersection
```

renderer 会求两个平面的交线并裁剪到共同可见区域。

只渲染 `labels` 显式声明的标签。用于计算和裁剪的点不得自动出现在学生图中；面名、线名使用 `show_point: false`。

## Roles

- `main`, `secondary`, `intersection`, `hidden` 是原图对象；
- `auxiliary` 只允许出现在 solution/annotated 图；
- `projection` 是低对比射影线或背景投影。

空间图使用灰阶，线型和粗细承担语义，不用多色编码关系。

## Gate

- final spec 保留 `points3d`，且 `points` 为空；
- backend 只能是 `tikz_coordinate_basis` 或 `tikz-3dplot`；
- 基准面展开度、核心投影夹角通过 projection 阈值；
- prompt/clean 不含 `auxiliary`；
- solution/annotated 通过 `reuse_geometry_from` 复用 prompt 三维构型；
- gate 后仍人工抽查标签遮挡、点序和题干对象对应。

完整设计见 `docs/spatial-geometry-diagram-workflow.md`。
