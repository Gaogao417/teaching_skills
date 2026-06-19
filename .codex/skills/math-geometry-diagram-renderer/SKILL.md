---
name: math-geometry-diagram-renderer
description: "为 LaTeX/YAML writer 生成几何题配套 TikZ 图。仅在 math-student-explanation-latex-data 或 math-adaptive-practice-latex-data 已声明 diagram_slot、且结构分析/题目判定需要插图时使用；本 skill 负责真实 collect/batch/gate/resolve 链路。不要在 math-assignment-latex 渲染阶段直接触发。"
---

# math-geometry-diagram-renderer

## 职责

读取 plan YAML 中的 `diagram_slot`，运行真实 collect/batch/gate/resolve 链路，生成可渲染的 `*.resolved.assignment.yaml`。本 skill 不判断题目是否需要图，不修改 LaTeX 模板，不编译最终作业 PDF。

latex-data skill 只负责声明图位和教学语义；本 skill 负责确认 TikZ fragment 真实存在、gate 通过、resolved YAML 可绑定。PDF/PNG/SVG 只作为调试预览。

## 输入

- 当前 artifact 目录或一个 `*.plan.assignment.yaml`
- `01-structure-analysis.md` 中的 `diagram_request_packet`
- plan YAML 中的 `diagram_slot`

支持合成几何、坐标几何和函数图的确定性 TikZ compiler。workflow 仍负责几何事实和函数采样，TikZ backend 只负责编译绘图。

## 图形类型

- `prompt` / `clean`: 原题图，只画题干已知对象和必要顶点标签；不画辅助线、不写推理标注、不泄露答案。
- `solution` / `annotated`: 讲解图或教师版答案图，可画辅助线、垂足、角标、相等标记和关键推理标注。

solution 图必须复用 prompt 图构型，不让 Python 成为第二套几何求解器。需要写辅助约束时读取 `references/solution-reuse-contract.md`。

## 工作流

优先使用一键脚本：

```bash
python3 scripts/diagram_workflow/run_assignment_diagrams.py \
  artifacts/<学生名>/YYYY-MM-DD-<内容>/<name>.plan.assignment.yaml
```

常用选项：

```bash
python3 scripts/diagram_workflow/run_assignment_diagrams.py <plan.yaml> --out <resolved.yaml> --max-workers 4
python3 scripts/diagram_workflow/run_assignment_diagrams.py <plan.yaml> --dry-run
```

脚本内部顺序为：

```text
collect_diagram_jobs.py
run_diagram_batch.py
check_diagram_gate.py
resolve_assignment_diagrams.py
```

不要跳过 gate，除非正在调试脚本本身。

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
