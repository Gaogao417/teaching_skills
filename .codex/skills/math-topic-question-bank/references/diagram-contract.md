# Question Bank Diagram Contract

本题库沿用仓库 diagram-slot 和 renderer 边界。

## 版本职责

- 学生图：`prompt` + `clean`，只含题干已知对象和必要标签。
- 教师图：至少复用学生 prompt 构型；需要辅助线、垂足、角标或关键关系时，另加 `solution` + `annotated`。
- `diagram_requirement: prompt_only` 表示教师解析不需要单独解答图。
- `diagram_requirement: prompt_and_solution` 表示教师 resolved assignment 中必须同时存在 prompt 与 solution 图。

## Plan 边界

- plan YAML 只写 `diagram_slot`，不写 `image_path`、`diagram_col`、`diagram_row`、`diagram_job_id` 或手写 TikZ。
- prompt slot 的 `slot_id` 使用 `<item-id>.prompt`。
- solution slot 的 `slot_id` 使用 `<item-id>.solution`，并显式复用 prompt 构型。
- 真实图统一交给 `math-geometry-diagram-renderer` 的 collect/batch/gate/resolve 链路。

## 引擎选择

- 普通欧氏几何：`engine: geometric_scene`，`diagram_kind: synthetic_geometry`。
- 坐标轴、坐标点、函数图像或解析几何：`diagram_kind: coordinate_geometry`。
- 点线面、空间多面体、二面角、截面、异面直线：`engine: spatial_renderer`，`diagram_kind: spatial_geometry`，保留 `points3d`。

## 复用和抽题

- solution 图必须复用本题 prompt 几何后再添加辅助对象。
- 抽题脚本只重定位 resolved 资产路径，不重新调用 renderer。
- `ready` 题库中不得残留 `diagram_slot`；TikZ fragment 或图片必须真实存在。
