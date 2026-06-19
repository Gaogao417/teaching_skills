# Renderer Architecture and Contract

> Status: historical renderer notes from the PNG/SVG period. The active
> renderer is TikZ-only: `final_renderer_spec.json -> rendered/<variant>.fragment.tex
> -> renderer_result.json`, and gate/resolver derive bindable facts with
> `RendererBindingManifest`.

## 0. 核心结论

renderer 只做一件事：

```text
final_renderer_spec.json
  -> PNG / SVG
  -> renderer_result.json
```

renderer 不读取 assignment YAML，不理解 `diagram_slot`，不调用 Wolfram，不调用 LLM，不做 prompt / solution 的业务清洗，也不兼容旧格式。

正式链路中只有一个 active renderer contract。
没有 `v1 -> v2 adapter`。
没有 legacy fallback。
没有 silent normalization。

如果 contract 需要破坏性变更，做法是：

```text
同一个 PR 内同步修改：
  workflow / analytic_workflow producer
  renderer validator
  renderer backend
  tests / fixtures
  artifact builder expectations
```

不是让 renderer 同时读两套格式。

---

## 1. Renderer 在全链路中的位置

完整数据流是：

```text
latex-data
  -> 生成 explanation/practice 的 plan assignment YAML
  -> 只声明 diagram_slot
  -> 不写 image_path
  -> 不写 diagram_col / diagram_row

diagram orchestrator
  -> collect_diagram_jobs.py
  -> run_diagram_batch.py
  -> workflow.py / analytic_workflow.py
  -> render_geometry_spec.py
  -> build_diagram_artifacts.py
  -> check_diagram_gate.py
  -> resolve_assignment_diagrams.py

math-assignment-latex
  -> 只读取 ordinary assignment.yaml 或 resolved.assignment.yaml
  -> render_assignment.py
  -> compile_latex.sh
```

关键边界：

```text
diagram_slot 是“我要一张图”的订单；
image_path / diagram_col / diagram_row 是“我已经有一张图”的排版数据。
```

所以：

```text
plan.assignment.yaml with diagram_slot
  不可直接进入 LaTeX

resolved.assignment.yaml
  可以进入 LaTeX
```

`math-assignment-latex` 不应该适配 `diagram_slot`。它看到 `diagram_slot` 就应该报错，提示先跑 diagram orchestrator 和 resolver。

---

## 2. 目录与路径合同

项目内必须区分两个根目录：

```text
build/diagram/...
  中间产物、请求、日志、调试文件、workflow_result.json、final_renderer_spec.json、renderer_result.json

diagram/jobs/...
  最终 TeX 可引用图片 artifact
```

也就是说：

```text
build/diagram/jobs/{job_id}/final_renderer_spec.json
  renderer 输入

build/diagram/jobs/{job_id}/renderer_result.json
  renderer manifest / debug result

diagram/jobs/{job_id}/rendered/{variant}.png
diagram/jobs/{job_id}/rendered/{variant}.svg
  TeX 可引用图片
```

`renderer_result.image_path`、`diagram_artifacts.image_path`、`resolved.assignment.yaml` 中的 `image_path` 必须指向同一个 public artifact 路径：

```text
diagram/jobs/{job_id}/rendered/{variant}.png
```

不要让 resolver 从 `build/diagram/.../rendered` 猜图。
不要让 artifact builder 重新决定图片路径。
图片路径事实源只能从 `renderer_result.json` 聚合到 `diagram_artifacts.json`。

---

## 3. 单一 Active Contract 规则

正式 renderer 输入合同命名为：

```text
geometry-render-spec
```

正式 renderer 输出合同命名为：

```text
geometry-renderer-result
```

建议不要继续用 `geometry-render-spec/v1`、`geometry-render-spec/v2` 这种命名作为生产链路判断依据，因为它会诱导人写 adapter。

推荐字段：

```json
{
  "contract": "geometry-render-spec",
  "contract_revision": "2026-06"
}
```

`contract_revision` 只用于文档和测试定位，不代表 renderer 要双读多版。renderer 只接受当前 active revision。收到别的 revision，直接失败：

```json
{
  "status": "failed",
  "fail_type": "unsupported_renderer_contract"
}
```

规则：

```text
producer outputs current contract;
consumer validates current contract;
no runtime adapter;
no silent fallback;
no legacy normalization.
```

---

## 4. Renderer 输入：`final_renderer_spec.json`

### 4.1 顶层结构

```json
{
  "contract": "geometry-render-spec",
  "contract_revision": "2026-06",

  "job_id": "q01_prompt",
  "variant": "prompt",
  "scene_type": "coordinate_geometry",
  "disclosure_policy": "clean",

  "canvas": {
    "width_px": 720,
    "height_px": 520,
    "dpi": 160,
    "background": "white"
  },

  "plane": {
    "kind": "cartesian",
    "aspect": "equal",
    "viewport": {
      "x": [-6, 6],
      "y": [-4, 4],
      "policy": "fixed"
    },
    "axes": {
      "visible": true,
      "grid": true,
      "ticks": "auto",
      "x_label": "x",
      "y_label": "y"
    }
  },

  "layers": [
    {
      "id": "main",
      "z": 10,
      "objects": []
    }
  ],

  "metadata": {
    "producer": "analytic_workflow.py"
  }
}
```

### 4.2 顶层字段

| 字段                  | 必填 | 说明                                                              |
| ------------------- | -: | --------------------------------------------------------------- |
| `contract`          |  是 | 固定为 `geometry-render-spec`                                      |
| `contract_revision` |  是 | 当前 active revision，例如 `2026-06`                                 |
| `job_id`            |  是 | diagram job id                                                  |
| `variant`           |  是 | `prompt` 或 `solution`                                           |
| `scene_type`        |  是 | `synthetic_geometry` / `coordinate_geometry` / `function_graph` |
| `disclosure_policy` |  是 | `clean` / `annotated`，renderer 只记录，不清洗                          |
| `canvas`            |  是 | 输出画布                                                            |
| `plane`             |  是 | 数学平面                                                            |
| `layers`            |  是 | 待绘制对象                                                           |
| `metadata`          |  否 | 调试信息，不参与渲染语义                                                    |

renderer 不接受这些输入：

```text
assignment.yaml
*.plan.assignment.yaml
*.resolved.assignment.yaml
diagram_jobs.json
diagram_artifacts.json
workflow_result.json
final_diagram_spec.json
gsb-diagram-spec
```

---

## 5. Canvas Contract

```json
{
  "width_px": 720,
  "height_px": 520,
  "dpi": 160,
  "background": "white"
}
```

规则：

```text
width_px > 0
height_px > 0
dpi > 0
background 默认 white
PNG/SVG 由同一个 Matplotlib Figure 输出
```

不要再使用含义不清的：

```text
png_size
size
out_dir as both work dir and public image dir
```

---

## 6. Plane Contract

### 6.1 综合几何

```json
{
  "kind": "plain",
  "aspect": "equal",
  "viewport": {
    "policy": "auto"
  },
  "axes": {
    "visible": false,
    "grid": false
  }
}
```

### 6.2 坐标几何 / 函数图

```json
{
  "kind": "cartesian",
  "aspect": "equal",
  "viewport": {
    "x": [-6, 6],
    "y": [-4, 4],
    "policy": "fixed"
  },
  "axes": {
    "visible": true,
    "grid": true,
    "ticks": "auto",
    "x_label": "x",
    "y_label": "y"
  }
}
```

规则：

```text
viewport 是数学坐标范围，不是像素范围
坐标图默认 aspect 必须是 equal
renderer 可以扩展 viewport 以适配画布比例
renderer 不能拉伸 x/y 单位
综合几何也使用数学坐标，只是隐藏 axes/grid
```

Matplotlib backend 应使用 `Axes.set_aspect("equal")`；官方定义里，`equal` 等价于 x/y 使用相同缩放，这正好对应数学图“横纵单位一致”的要求。([Matplotlib][3])

---

## 7. Layer Contract

```json
{
  "id": "main",
  "z": 10,
  "objects": []
}
```

推荐 layer：

```text
background
grid
construction
main
highlight
markers
labels
```

规则：

```text
renderer 按 z 从小到大绘制
不要依赖数组顺序隐式表达层级
label 可以挂在 object 上，也可以作为 text object
```

---

## 8. Object Contract

所有几何位置都使用数学坐标。
所有文字偏移、marker 点大小这类排版尺寸必须显式标明单位。

禁止字段：

```text
screen_x
screen_y
screen_radius
pixel_x
pixel_y
radius_px for geometry radius
```

### 8.1 Point

```json
{
  "type": "point",
  "id": "A",
  "xy": [1, 2],
  "label": {
    "text": "A",
    "offset_pt": [5, 5]
  },
  "style": {
    "role": "point"
  }
}
```

### 8.2 Segment

```json
{
  "type": "segment",
  "id": "AB",
  "from": [0, 0],
  "to": [4, 0],
  "style": {
    "role": "main"
  }
}
```

### 8.3 Line

```json
{
  "type": "line",
  "id": "l1",
  "through": [[0, 1], [2, 3]],
  "style": {
    "role": "construction"
  }
}
```

或者：

```json
{
  "type": "line",
  "id": "l2",
  "point": [0, 1],
  "slope": 2
}
```

renderer 不解析字符串方程。
如果要显示 `y=2x+1`，把它放到 `label.text`。

### 8.4 Circle

```json
{
  "type": "circle",
  "id": "c1",
  "center": [0, 0],
  "radius": 2,
  "style": {
    "role": "main"
  }
}
```

`radius` 是数学半径。
Matplotlib 的 `Circle(xy, radius)` 本身就是以中心和半径定义 circle patch；结合 `aspect="equal"`，可以避免当前手写 SVG renderer 中屏幕半径和数学半径混在一起的问题。([Matplotlib][4])

### 8.5 Polygon

```json
{
  "type": "polygon",
  "id": "tri_ABC",
  "points": [[0, 0], [4, 0], [1, 3]],
  "style": {
    "role": "region",
    "fill": true
  }
}
```

### 8.6 Arc

```json
{
  "type": "arc",
  "id": "angle_ABC",
  "center": [0, 0],
  "radius_data": 0.5,
  "theta1_deg": 0,
  "theta2_deg": 60,
  "style": {
    "role": "marker"
  }
}
```

### 8.7 Right Angle Marker

```json
{
  "type": "right_angle_marker",
  "id": "right_A",
  "vertex": [0, 0],
  "arm1": [1, 0],
  "arm2": [0, 1],
  "size_data": 0.25,
  "style": {
    "role": "marker"
  }
}
```

### 8.8 Text

```json
{
  "type": "text",
  "id": "note1",
  "text": "交点",
  "xy": [2, 3],
  "offset_pt": [6, 6],
  "style": {
    "role": "label"
  }
}
```

Matplotlib `Axes.annotate` 支持把文本锚定到数据坐标 `xy`，并用 `xytext` / `textcoords="offset points"` 做排版偏移，所以 label 不需要再通过手写 screen transform 实现。([Matplotlib][5])

---

## 9. Function Graph Contract

函数图必须使用分段曲线，不能再使用顶层 `samples` 直接连线。

```json
{
  "type": "function_curve",
  "id": "f",
  "label": {
    "text": "y=\\frac{1}{x}"
  },
  "segments": [
    {
      "domain": [-5, -0.05],
      "samples": [[-5, -0.2], [-4, -0.25], [-1, -1]]
    },
    {
      "domain": [0.05, 5],
      "samples": [[0.05, 20], [1, 1], [5, 0.2]]
    }
  ],
  "asymptotes": [
    {
      "type": "vertical",
      "x": 0
    }
  ],
  "style": {
    "role": "function"
  }
}
```

规则：

```text
不允许顶层 samples
不允许 renderer 根据 expression 自行采样
不允许 renderer 解析函数表达式
不连续函数必须由 analytic workflow 拆成多个 segment
每个 segment 独立绘制，不跨 segment 连线
渐近线、零点、交点、特殊点必须由 workflow 显式输出
```

renderer 可以用 Matplotlib `LineCollection` 绘制多个 segment；Matplotlib 文档说明 `LineCollection` 可一次绘制多条线，这正适合函数多段曲线，避免跨间断点误连。([Matplotlib][6])

---

## 10. Style Contract

style 以“教学角色”为主，而不是让上游到处写像素细节。

```json
{
  "style": {
    "role": "main",
    "stroke": "#111827",
    "stroke_width_pt": 1.4,
    "linestyle": "solid",
    "fill": false
  }
}
```

推荐 role：

```text
main
construction
highlight
auxiliary
region
function
axis
grid
marker
label
point
```

规则：

```text
role 用于 renderer 默认样式
stroke / fill / linewidth 可覆盖
所有尺寸单位必须显式：pt / px / data
不允许含糊字段：size / width / radius_px
```

坐标轴、tick、grid 应交给 Matplotlib backend 处理。Matplotlib ticker API 提供 locator 机制，例如 `MaxNLocator` 会根据范围生成 tick 值，这比继续维护手写 `tick_step/tick_values` 更稳定。([Matplotlib][7])

---

## 11. Renderer 输出：`renderer_result.json`

成功结果：

```json
{
  "contract": "geometry-renderer-result",
  "contract_revision": "2026-06",

  "status": "ok",
  "job_id": "q01_prompt",
  "variant": "prompt",
  "renderer": "matplotlib-geometry-renderer",

  "renderer_spec": "build/diagram/jobs/q01_prompt/final_renderer_spec.json",
  "image_path": "diagram/jobs/q01_prompt/rendered/prompt.png",
  "preview_svg": "diagram/jobs/q01_prompt/rendered/prompt.svg",

  "checks": {
    "contract_valid": true,
    "references_valid": true,
    "aspect_equal": true,
    "image_exists": true,
    "svg_exists": true,
    "public_image_dir_used": true
  },

  "warnings": []
}
```

失败结果：

```json
{
  "contract": "geometry-renderer-result",
  "contract_revision": "2026-06",

  "status": "failed",
  "job_id": "q01_prompt",
  "variant": "prompt",
  "renderer": "matplotlib-geometry-renderer",

  "fail_type": "invalid_renderer_spec",
  "message": "function_curve f has no segments",

  "renderer_spec": "build/diagram/jobs/q01_prompt/final_renderer_spec.json",
  "image_path": "",
  "preview_svg": "",

  "checks": {
    "contract_valid": false,
    "references_valid": false,
    "image_exists": false,
    "svg_exists": false
  },

  "warnings": []
}
```

推荐 `fail_type`：

```text
unsupported_renderer_contract
invalid_renderer_spec
unsupported_scene_type
invalid_viewport
invalid_object_reference
invalid_function_segments
public_image_dir_missing
png_export_failed
svg_export_failed
matplotlib_render_failed
```

---

## 12. Renderer CLI Contract

推荐 CLI：

```bash
python3 scripts/diagram_workflow/render_geometry_spec.py \
  --renderer-spec build/diagram/jobs/q01_prompt/final_renderer_spec.json \
  --work-dir build/diagram/jobs/q01_prompt \
  --public-image-dir diagram/jobs/q01_prompt/rendered \
  --variant prompt
```

参数含义：

| 参数                   | 必填 | 含义                               |
| -------------------- | -: | -------------------------------- |
| `--renderer-spec`    |  是 | 输入 `final_renderer_spec.json`    |
| `--work-dir`         |  是 | 写 `renderer_result.json`、日志、调试信息 |
| `--public-image-dir` |  是 | 写 TeX 可引用 PNG/SVG                |
| `--variant`          |  是 | `prompt` 或 `solution`            |
| `--strict`           |  否 | warning 是否升级为 failure            |

不再推荐：

```text
--out-dir 作为唯一目录
--png-size
```

因为它们不能表达：

```text
debug/work dir
public image dir
```

这两个不同概念。

---

## 13. Renderer 模块架构

建议拆成：

```text
scripts/
  render_geometry_spec.py

scripts/renderer/
  __init__.py
  contracts.py
  validate.py
  viewport.py
  styles.py
  matplotlib_backend.py
  result.py
```

### 13.1 `render_geometry_spec.py`

只负责：

```text
parse CLI
read final_renderer_spec.json
validate contract
call MatplotlibGeometryRenderer
write renderer_result.json
exit 0 / 1
```

不负责：

```text
SVG 手写绘图
math -> screen transform
tick/grid 手写逻辑
旧格式兼容
业务清洗
assignment resolve
```

### 13.2 `contracts.py`

定义当前唯一 active contract 的类型。

可以用 Pydantic，也可以先用 dataclass + 显式 validator。关键不是工具，而是：

```text
renderer 只能接受当前 contract
```

### 13.3 `validate.py`

负责 fail-fast validation：

```text
contract == geometry-render-spec
contract_revision == 当前 active revision
job_id present
variant in {prompt, solution}
scene_type valid
canvas valid
plane valid
layers valid
objects supported
all coordinates finite
no screen-space geometry fields
no legacy fields
function_curve has segments
```

必须拒绝：

```text
diagram_slot
diagram_col
diagram_row
gsb-diagram-spec
final_diagram_spec
screen_x
screen_y
screen_radius
top-level samples
equation string as only geometry definition
```

### 13.4 `viewport.py`

负责：

```text
auto bounds
math padding
expand viewport to canvas aspect
never distort x/y units
```

核心原则：

```text
可以留白；
可以扩展数学视野；
不能拉伸坐标单位。
```

### 13.5 `styles.py`

负责教学图默认风格：

```text
role -> stroke/fill/linewidth/fontsize/marker
```

不要让 workflow 到处写具体绘图细节。

### 13.6 `matplotlib_backend.py`

负责：

```text
create Figure/Axes
set aspect equal
set viewport
draw axes/grid/ticks
draw primitives
draw function segments
draw labels
save PNG/SVG
```

不负责：

```text
函数采样
求交点
求零点
判断间断点
调用 Wolfram
disclosure policy 清洗
```

### 13.7 `result.py`

负责统一构造：

```text
ok renderer_result
failed renderer_result
relative/absolute path normalization
public_image_dir consistency check
```

---

## 14. Workflow 与 Renderer 的边界

`workflow.py` / `analytic_workflow.py` 必须直接输出当前 renderer contract：

```text
build/diagram/jobs/{job_id}/final_renderer_spec.json
```

它们负责：

```text
把题意变成数学对象
调用 Wolfram / wolframclient 做数学求解
输出点、线、圆、多边形、函数分段、渐近线、特殊点
执行 prompt / solution disclosure policy
保证 prompt 图不泄题
保证 solution 图有必要标注
```

它们不应把这些事丢给 renderer：

```text
删除 marker
删除 polygon
改写 label
解析函数表达式
补采样
判断是否泄题
```

renderer 只画 spec。spec 里有什么，renderer 就画什么；spec 不合法，renderer 就失败。

---

## 15. Artifact Builder 与 Resolver 的边界

`build_diagram_artifacts.py` 只读：

```text
build/diagram/jobs/{job_id}/renderer_result.json
```

它输出：

```text
diagram_artifacts.json
```

`diagram_artifacts.json` 是 resolver 的唯一图片事实源。

artifact builder 不应该：

```text
重新决定 image_path
扫描 rendered 目录猜测图片
从 final_renderer_spec 推断图片路径
修补 renderer_result
```

resolver 输入：

```text
plan.assignment.yaml
diagram_artifacts.json
```

resolver 输出：

```text
resolved.assignment.yaml
```

resolver 负责：

```text
找到 diagram_slot
根据 artifacts 找到 image_path
把 diagram_slot 替换为 diagram_col / diagram_row
删除所有 diagram_slot
```

---

## 16. LaTeX 层边界

`math-assignment-latex` 只能吃：

```text
ordinary assignment.yaml
resolved.assignment.yaml
```

它必须拒绝：

```text
plan.assignment.yaml with diagram_slot
```

建议报错文案：

```text
This assignment YAML contains unresolved diagram_slot.
Run the diagram orchestrator and resolve_assignment_diagrams.py before rendering LaTeX.
```

LaTeX 层可以接受：

```yaml
diagram_col:
  image_path: diagram/jobs/q01_prompt/rendered/prompt.png
  caption: ""
  width: 0.42\textwidth
```

或：

```yaml
diagram_row:
  images:
    - image_path: diagram/jobs/q01_prompt/rendered/prompt.png
      caption: 原图
    - image_path: diagram/jobs/q01_solution/rendered/solution.png
      caption: 解答图
```

但 LaTeX 层不应该知道：

```text
final_renderer_spec.json
renderer_result.json
workflow_result.json
diagram_slot
```

---

## 17. No Adapter Policy

正式生产链路中禁止：

```text
adapt_v1_to_v2
normalize_old_request
parse_gsb_diagram_spec
sanitize_clean_prompt_spec
guess_legacy_samples
accept_assignment_yaml_in_renderer
```

也不要把这些逻辑换个名字藏进：

```text
normalize.py
compat.py
legacy.py
```

允许存在的只有两类逻辑：

```text
validation:
  当前 contract 是否合法

render preparation:
  当前 contract 内部的默认样式补全、viewport 计算
```

注意：默认样式补全不是 adapter。
adapter 是跨 contract 理解旧格式；这件事禁止放进 renderer。

---

## 18. Disclosure Policy

`disclosure_policy` 是 workflow/gate 的合同，不是 renderer 的行为。

renderer 可以记录：

```json
{
  "disclosure_policy": "clean"
}
```

但 renderer 不得：

```text
删除 equal tick
删除 polygon
删除 marker
删除 label
改写 text
判断是否泄题
```

原因：

```text
renderer 只知道“要画什么”；
workflow/gate 才知道“这张图是否适合给学生看”。
```

---

## 19. Matplotlib Backend 的实现原则

renderer 重构不是把 SVG 字符串换成 Matplotlib 字符串，而是把坐标系统交给 Matplotlib。

必须满足：

```text
所有 object 用 data coordinates 传给 Matplotlib
不再写 world -> screen transform
不再手写 tick/grid/axis
不再手写 SVG -> PNG converter
PNG/SVG 从同一个 Figure 输出
坐标图默认 ax.set_aspect("equal")
圆用 matplotlib.patches.Circle
label 用 Axes.annotate
tick/grid 用 Matplotlib ticker
function segments 用 LineCollection 或等价分段绘制
```

当前 renderer 中 `SvgCoordinateRenderer` 仍然自己做 `_plot_transform`、`screen_xy`、`tick_step`、`tick_values`、`draw_axes`、`draw_functions`，这些都应该从正式 backend 中消失。([GitHub][2])

---

## 20. 测试要求

### Renderer contract tests

```text
valid synthetic geometry renders
valid coordinate geometry renders
valid function graph renders
unsupported contract rejected
assignment YAML rejected
diagram_slot rejected
gsb-diagram-spec rejected
screen_radius rejected
top-level samples rejected
function_curve without segments rejected
non-finite coordinate rejected
```

### Geometry correctness tests

```text
circle uses data radius
coordinate aspect is equal
viewport expands instead of distorting
function segments are not connected across gaps
labels use offset_pt without changing anchor point
```

### Path contract tests

```text
renderer_result.image_path points to public_image_dir
renderer_result.preview_svg points to public_image_dir
artifact builder preserves renderer_result.image_path
resolver uses diagram_artifacts only
resolved YAML contains no diagram_slot
LaTeX rejects unresolved plan YAML
```

---

## 21. 迁移顺序

### Phase 1：先硬化 YAML 边界

```text
validate_assignment.py 拒绝 diagram_slot
render_assignment.py 拒绝 diagram_slot
resolver 保证 resolved YAML 不含 diagram_slot
```

### Phase 2：硬化 diagram job contract

```text
collector 只负责 slot -> job
batch 只负责 job -> request
workflow 只负责 request -> final_renderer_spec
renderer 只负责 final_renderer_spec -> image/result
artifact builder 只负责 renderer_result -> diagram_artifacts
```

### Phase 3：替换 renderer backend

```text
引入 Matplotlib backend
移除手写 SVG coordinate renderer
移除 SVG -> PNG converter 依赖
统一 public_image_dir
统一 renderer_result.image_path
```

### Phase 4：删除 legacy 输出

```text
workflow_result.json 不再正式指向 final_diagram_spec
final_diagram_spec.json 不再作为生产产物
run_diagram_workflow.py 不再 normalize 老 request
wrapper 不再清洗 prompt spec
```

---

## 22. 最终状态

最终系统应该是：

```text
latex-data
  -> plan.assignment.yaml
  -> diagram_slot only

collector
  -> diagram_jobs.json

batch
  -> per-job request.json

workflow / analytic_workflow
  -> final_renderer_spec.json

renderer
  -> diagram/jobs/{job_id}/rendered/{variant}.png
  -> diagram/jobs/{job_id}/rendered/{variant}.svg
  -> renderer_result.json

artifact builder
  -> diagram_artifacts.json

resolver
  -> resolved.assignment.yaml

math-assignment-latex
  -> TeX/PDF
```

最核心的工程纪律：

```text
plan YAML 不能渲染；
resolved YAML 才能渲染；

diagram_slot 不能进 LaTeX；
image_path 不能出现在 plan YAML；

renderer 不做 adapter；
renderer 只吃当前 active renderer contract；

build/diagram 是调试区；
diagram/jobs 是 TeX 可引用图区；

prompt/solution policy 在 workflow/gate；
renderer 只画图，不做业务判断。
```

[1]: https://github.com/Gaogao417/teaching_skills/tree/main/scripts "teaching_skills/scripts at main · Gaogao417/teaching_skills · GitHub"
[2]: https://raw.githubusercontent.com/Gaogao417/teaching_skills/main/scripts/diagram_workflow/render_geometry_spec.py "raw.githubusercontent.com"
[3]: https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.set_aspect.html "matplotlib.axes.Axes.set_aspect — Matplotlib 3.10.9 documentation"
[4]: https://matplotlib.org/stable/api/_as_gen/matplotlib.patches.Circle.html "matplotlib.patches.Circle — Matplotlib 3.10.9 documentation"
[5]: https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.annotate.html "matplotlib.axes.Axes.annotate — Matplotlib 3.10.9 documentation"
[6]: https://matplotlib.org/stable/gallery/shapes_and_collections/line_collection.html "Plot multiple lines using a LineCollection — Matplotlib 3.10.9 documentation"
[7]: https://matplotlib.org/stable/api/ticker_api.html "matplotlib.ticker — Matplotlib 3.10.9 documentation"
