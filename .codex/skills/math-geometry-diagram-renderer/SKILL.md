---
name: math-geometry-diagram-renderer
description: "为 LaTeX/YAML writer 生成几何题配套 TikZ 图。仅在 math-student-explanation-latex-data 或 math-adaptive-practice-latex-data 已声明 diagram_slot、且结构分析/题目判定需要插图时使用；本 skill 负责真实 collect/batch/JobPackageGate/resolve/ResolvedAssignmentGate 链路。不要在 math-assignment-latex 渲染阶段直接触发。"
---

# math-geometry-diagram-renderer

## 职责

读取 plan YAML 中的 `diagram_slot`，运行真实 collect/batch/JobPackageGate/resolve/ResolvedAssignmentGate 链路，生成可渲染的 `*.resolved.assignment.yaml`。本 skill 不判断题目是否需要图，不修改 LaTeX 模板，不编译最终作业 PDF。

latex-data skill 只负责声明图位和教学语义；`diagram_kind` 必填，`engine` 由 Host 的确定性 `DiagramExecutionPlan` 在 Agent 启动前锁定。当前含 `engine` 的 DiagramSlot v1 仍由兼容层读取，但 Agent、repair 与人工返修都不得修改 engine。本 skill 负责确认 TikZ fragment 真实存在、两层 gate 通过、resolved YAML 可绑定。PDF/PNG/SVG 只作为调试预览与受控视觉判断输入。

## 输入

- 当前 artifact 目录或一个 `*.plan.assignment.yaml`
- plan YAML 中的 `diagram_slot`
- `01-structure-analysis.md` 中的 `推荐图形请求包` 只作为语义复核背景；真实 collect/batch/resolve 输入来自 plan YAML 的 `diagram_slot`

支持平面合成几何、立体几何、坐标几何和函数图的确定性 TikZ compiler。workflow 仍负责几何事实和函数采样，TikZ backend 只负责编译绘图。

立体几何声明 `diagram_kind: spatial_geometry`：Host route policy 锁定 `engine: spatial_renderer`。三维关系在 Python 层校验，`points3d` 保留到 TikZ compiler，最终按 `textbook_oblique`、`hinge_planes`、`orthographic_3d` 或 `axial_solid` 投影。不得先投成二维 `points` 再交给 TikZ。详细契约见 `references/spatial-geometry.md`。

## 图形类型

- `prompt` / `clean`: 原题图，只画题干已知对象和必要顶点标签；不画辅助线、不写推理标注、不泄露答案。题干中的长度、比例、相等、角度等条件默认只用于约束构型，不重复写到图上。只有独立的 `visual_requirements.required_visible_annotations` 明确声明时，才把某项条件画成可见文字或标记；`problem_text`、`source_problem_text` 和 `semantic_constraints.given_constraints` 本身都不是可见标注清单。
- `solution` / `annotated`: 讲解图或教师版答案图，可画辅助线、垂足、角标、相等标记和关键推理标注。视觉审核在此 variant 才检查明确要求的教学标记是否清楚、是否与讲解步骤一致。

`prompt/clean` 的视觉审核重点是图形是否退化、题干对象/点序/共线与相交关系是否错误，以及顶点标签是否严重偏离、遮挡或指向错误。不得因为图上没有重复题干中的数值、等式、角度文字而要求返修，也不要为轻微风格差异消耗 candidate budget。

solution 图必须复用 prompt 图构型，不让 Python 成为第二套几何求解器。这个边界同样适用于 prompt：
Python 可以选择少量版面锚点和确定性种子，但题设中的在线点、内外分点、交点、垂足、中点等构造点必须由
`GeometricScene` 原生约束求出，不能先算坐标再写成 `P == {x,y}`。`scene_payload` 应声明
`point_roles.anchors`、`point_roles.constructed`、`point_roles.auxiliary`。需要写辅助约束时读取
`references/solution-reuse-contract.md`。

## 工作流

优先使用一键脚本：

```bash
./.venv-diagram/bin/python scripts/diagram_workflow/run_assignment_diagrams.py \
  artifacts/<学生名>/YYYY-MM-DD-<内容>/<name>.plan.assignment.yaml
```

常用选项：

```bash
./.venv-diagram/bin/python scripts/diagram_workflow/run_assignment_diagrams.py <plan.yaml> --out <resolved.yaml> --max-workers 4
./.venv-diagram/bin/python scripts/diagram_workflow/run_assignment_diagrams.py <plan.yaml> --dry-run
```

## 运行进度与用户汇报

真实 `geometric_scene` job 会启动 Codex SDK subagent，禁止把一键脚本当成
一个可以沉默等待到结束的黑盒命令。

- 启动命令时先使用约 10 秒的短 yield；命令仍在运行时保留 session id，
  后续每 30--45 秒轮询一次，不得执行超过 60 秒的阻塞等待。
- stderr 中的 `GSB_EVENT` 是用户进度的事实来源。阶段变化时立即发一条
  commentary；即使阶段没有变化，也必须在 60 秒内向用户汇报一次当前
  job、阶段、累计用时和距最近 SDK 事件的时间。
- `agent.thread.started` / `agent.turn.started` 表示 subagent 已真正进入模型；
  `agent.stage.started/completed` 会给出 `wolfram_render`、`tikz_compile`、
  `preview_render`、`audit`、`finalize_round` 等阶段；`agent.heartbeat` 表示
  父进程仍存活。
- heartbeat 的 `health=quiet` 表示 120 秒没有新的 SDK 生命周期事件，
  `health=suspected_stall` 表示 300 秒没有新事件。此时要明确告诉用户并
  检查进程与 `workflow_events.jsonl`，不能继续只说“正在画图”。
- 模型入口错误、网络/API 错误、Wolfram 失败、预览失败、audit 重试和硬
  超时必须分别汇报，不能统称为几何失败或网络问题。
- 进度汇报只转述操作阶段和健康状态；不得暴露 subagent 的 reasoning
  正文、完整命令、工具参数、密钥或原始命令输出。

建议用户消息格式：

```text
第 2/6 图 q2-prompt｜Wolfram 求解｜已运行 01:40｜最近事件 18 秒前｜运行正常
```

job 完成后立即报告本 job 用时和是否发生内部修复轮次，再进入下一 job。

默认阶段在同一 Python 进程内依次调用库函数运行。每个 job 由唯一 owner
完成 solve/spec/render/audit/visual/finalize，Batch 不再二次调用 TikZ renderer。
脚本内部顺序为：

```text
collect_diagram_jobs.py
run_diagram_batch.py + per-job JobPackageGate
resolve_assignment_diagrams.py
ResolvedAssignmentGate
```

批处理内部按 `DiagramExecutionPlan` 路由：`renderer_spec` 与 analytic
（`coordinate_renderer` / `wolfram_client` / `wolfram_plot`）走进程内；
`geometric_scene` 合成几何仍保持子进程隔离，避免 LLM/Wolfram 运行时
污染主进程。TikZ 编译器默认进程内调用，仅预览仍通过 TeX/pdf 子进程。

调试或临时回退旧式四子进程链路时加 `--process-isolation`：
`collect` / `batch` / compatibility gate / `resolve` 各自作为独立 Python 解释器运行。
单阶段脚本也继续保留，可独立运行用于定位问题。

不要跳过 gate，除非正在调试脚本本身。`JobPackageGate` 在 cache/store/bind 前运行；
student disclosure、layout、diagram_ref/hash/path 一致性必须在 resolve 后由
`ResolvedAssignmentGate` 检查。

`build_diagram_artifacts.py` 只保留为调试 dump 工具，可从 jobs 和
`renderer_result.json` 生成 `renderer_bindings.json` 供人工检查；它不是主链路
必需步骤。

## 语义复核

gate 通过后仍要抽查图义；不要只看 `usable=true`。

- 题干若写点序或位置关系，预览图中的点序必须一致。
- 题干显式给出的长度、比例、相等、垂直、平行、共线等条件，必须能在 scene 或 renderer spec 中找到对应表达。
- prompt 图不得包含推理得到但题干未给出的结论标注。
- 若图形可渲染但点序、比例或题干对象明显不符，不得写入最终 YAML；保留失败日志并重跑该 job。

详细检查文件见 `references/gate-and-output.md`。

## Wolfram scene 编写

生成或审查 `GeometricScene[...]`、`scene_payload`、`hypotheses_wl` 时，必须全文读取
`references/wolfram-geometricscene-authoring.md`。共线/在线/交点使用 `Element[point, region]`；
不要使用自然语言伪 DSL，也不要用 `GeometricAssertion[..., "Collinear"]` 代替点对线或线段的隶属关系。
普通综合几何默认不手动指定点坐标。需要控制版面时，优先只给一条基准边添加
`GeometricAssertion[Line[{B, C}], "Horizontal"]`，必要时再加 `"Rightward"`，其余位置交给
边长、角、垂直、平行、共线等原生几何约束求解。严禁把同一三角形的三个顶点全部固定坐标后，
又重复加入边长或角度条件；这会把版面选择误变成额外数学条件，并可能与题设冲突。

`point_roles.anchors` 记录题设的基础点，但“属于 anchors”不表示必须写坐标；anchors 也应默认保持
符号化。只有确有必要消除平移自由度时，才允许给极少量 anchor 写坐标。已经由题设的度量、隶属或
构造关系确定的点必须保持符号化；
`constructed` 与 `auxiliary` 点必须各有足够的隶属、构造或度量约束。提交 Wolfram 前必须检查
`scene_code`：若一个三角形有多个顶点出现 `P == {x, y}` 一类坐标等式，必须先删除坐标并改用
一条边的 `Horizontal`/`Rightward` 版面约束。若使用含标量参数的第一参数形式，必须写成
`GeometricScene[{{points...}, {scalars...}}, hypotheses]`。

## 输出

成功时输出：

```text
<name>.resolved.assignment.yaml
build/diagram/diagram_jobs.json
build/diagram/jobs/<job_id>/...
build/diagram/jobs/<job_id>/renderer_result.json
build/diagram/jobs/<job_id>/rendered/<variant>.fragment.tex
```

只有当 `renderer_result.json.status == "ok"`，且由 `renderer_bindings.py`
构建出的 binding `bindable: true`、TikZ fragment 可访问时，才允许 resolver
写入 YAML TikZ 对象。

## References

- `references/solution-reuse-contract.md`: solution/annotated 图如何复用 prompt 构型。
- `references/gate-and-output.md`: gate 后检查、输出文件、resolved YAML TikZ 字段和布局尺寸。
- `references/wolfram-geometricscene-authoring.md`: 出题常见平面几何对象、原生 WL 约束、辅助构造、防退化与错误写法。
- `references/spatial-geometry.md`: 立体几何三维 spec、投影分类、对象角色与质量门禁。
