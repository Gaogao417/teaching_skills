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
- 教师解析需要逐步图时，可把独立 solution slot 挂在 `solution_steps[].diagram_slot`；每一步仍复用本题 prompt，resolved 后变为该步的 `diagram_col`，学生版派生时必须整体移除。
- 真实图统一交给 `math-geometry-diagram-renderer` 的 collect/batch/gate/resolve 链路。

## 引擎选择

- 普通欧氏几何：`engine: geometric_scene`，`diagram_kind: synthetic_geometry`。
- 坐标轴、坐标点、函数图像或解析几何：`diagram_kind: coordinate_geometry`。
- 点线面、空间多面体、二面角、截面、异面直线：`engine: spatial_renderer`，`diagram_kind: spatial_geometry`，保留 `points3d`。

## 复用和抽题

- solution 图必须复用本题 prompt 几何后再添加辅助对象。
- 抽题脚本只重定位 resolved 资产路径，不重新调用 renderer。
- `ready` 题库中不得残留 `diagram_slot`；TikZ fragment 或图片必须真实存在。

## 逐步边长标注

- 同一张逐步图中，一条边只能出现一次份数/边长标注；颜色层级固定为“题设蓝色、第一组 A/8 字新增红色、第二组 A/8 字新增绿色”。图 3 必须原样保留图 2 的蓝字和红字，只给本步新结果使用绿色；不得给已有边换数或换色。
- 若相似比的一条对应边已有份数，只计算并新增另一条边；若两条都已有份数，不重复标这两条边，但第二组 A/8 字结束时仍须把所求两条边中尚未显示的份数补齐。图 3 必须保留图 2 的全部数字，并明确显示第二组模型得到的最终结果。
- 边长、份数采用工程制图式可读性规则：文字保持水平、使用加粗数学字体和透明背景。位置严格由“线段中点 + 法向量 × 间距”确定；题库逐条使用 `normal_side: clockwise|counterclockwise` 明确选择从起点到终点的顺时针侧或逆时针侧。不得沿线方向漂移，不得给数字加白底、边框或卡片式衬底。
- 分数必须写成 `\frac{a}{b}` 的上下式，不显示为 `a/b` 文本。
- 狭窄区域不把数字硬塞在线段上，显式使用 `segment_position: legend`，在空白区写完整的“边名 = 份数”；可用 `legend_placement: top_left|top_right|bottom_left|bottom_right` 选择图例角落。默认 `segment_position: offset`，仍使用顺/逆法向。
- 若被标整段内部还含有具名分点（本专题中的 `BE` 含 `P`、`BC` 含 `D`），整段数值默认使用 legend，避免被误读成某一小段；个别题的拥挤分段可另加题级 legend override。
- `offset` 模式必须显式保存 `normal_offset_cm`。本专题默认整数为 `0.22cm`、上下分数为 `0.30cm`，使数字贴近对应边但不压线；特殊边可单独覆盖。
- 普通边默认声明 `segment_position: auto`：renderer 先按法向 offset 尝试；若文字框与点名、非目标点或已有数字发生实质重叠，自动降级为 legend。不得仅凭线段短就一律改 legend。
