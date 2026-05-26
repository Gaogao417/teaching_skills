---
name: math-geometry-diagram-renderer
description: "为 LaTeX/YAML writer 生成几何题配套图片。仅在 math-student-explanation-latex-data 或 math-adaptive-practice-latex-data 准备插入 diagram_col、diagram_row、answer_space.diagram_col 或讲义 diagram block、且结构分析/题目判定需要插图时使用。不要在 math-assignment-latex 渲染阶段直接触发。"
---

# math-geometry-diagram-renderer

## 职责

这是 LaTeX/YAML writer 的局部辅助 skill：把结构分析里的几何画图需求变成可打印 PNG，并返回可插入 assignment.yaml 的图片对象。

不要把 GSB、renderer、重试细节暴露到学生页、HTML skill、pipeline skill 或 LaTeX 渲染 skill。

本 skill 必须区分两种图：

- `prompt` / `clean`：原题图，只画题干已知对象和必要顶点标签；不画辅助线、不写推理标注、不泄露答案。
- `solution` / `annotated`：讲解图或教师版答案图，可画辅助线、垂足、角标、相等标记和关键推理标注。

solution 图不得让 Python 自己成为第二套几何求解器，也不得手写脚本改 PNG。正确分工是：

- Wolfram/GeometricScene 是几何真相源：原题点、辅助点、交点、垂足、中点等坐标都由 GeometricScene 求解。
- agent 负责根据题干和 skill 写 Wolfram `GeometricScene` 或辅助约束；workflow 负责注入 skill、校验、执行、重试和日志。
- Python adapter 只消费结构化字段、锁定原图坐标、拼接/校验 GeometricScene 约束、检查输出和渲染，不负责几何计算。
- visual/renderer 阶段只决定可见对象和标注，不改变几何点位。

## 输入

- 当前 artifact 目录，例如 `artifacts/<slug>/`
- `01-structure-analysis.md`
- 结构分析中的 `diagram_request_packet`
- 当前 YAML writer 要插图的位置、题型、caption 意图
- `diagram_job_id`: 题目级 job id，例如 `c1-prompt`、`f2-prompt`、`p1-part1-prompt`
- `diagram_variant`: `prompt` 或 `solution`；未指定时默认 `prompt`
- `disclosure_policy`: `clean` 或 `annotated`；未指定时 `prompt → clean`，`solution → annotated`

只支持合成几何图的默认路径。坐标几何/函数图如果没有确定性 renderer 支持，直接 fallback，不强行走 GeometricScene。

solution 图可以引用 prompt 图并追加辅助对象。workflow 会读取 prompt job 的 `final_renderer_spec.json`，用原图点坐标锁定已有点，再把辅助点和 Wolfram 辅助约束交给 GeometricScene 求解。若 YAML 已经给出 `add_auxiliary`，它必须写成本地 workflow 容易消费的形式，不能写成需要另造解析器的教学语义 DSL。推荐契约：

```json
{
  "diagram_job_id": "p1-part1-solution",
  "diagram_variant": "solution",
  "disclosure_policy": "annotated",
  "reuse_geometry_from": "p1-prompt",
  "add_auxiliary": {
    "add_points": ["H"],
    "hypotheses_wl": [
      "H == TriangleCenter[{A, B, D}, {\"Foot\", A}]",
      "GeometricAssertion[{Line[{A, H}], Line[{B, D}]}, \"Perpendicular\"]"
    ],
    "diagram_spec_delta": {
      "segments": [["A", "H"]],
      "markers": [
        {"type": "right_angle", "vertex": "H", "arms": ["A", "B"]}
      ],
      "labels": {
        "H": {"text": "H"}
      },
      "annotations": [
        {"target": ["B", "H"], "text": "BH"}
      ]
    }
  }
}
```

字段含义：

- `reuse_geometry_from`：复用 prompt job 的基础点坐标，避免 solution 图重造构型。
- `add_points`：新增到 `GeometricScene[{...}]` 点集里的点。
- `hypotheses_wl`：可直接拼入二阶段 GeometricScene hypotheses 的 Wolfram Language 约束字符串；只允许 GeometricScene 支持的安全表达式。
- `diagram_spec_delta`：沿用现有 `diagram_spec` 形状，告诉最终 renderer 哪些辅助线、角标、等号、文字可见；它不参与几何求解。

不要写：

```json
{"type": "foot", "point": "H", "from": "A", "to_line": ["B", "D"]}
```

这种字段还要再翻译成 Wolfram，GSB 已有解析器也不能直接消费，后续会变成隐式 DSL。

## 工作流

在 artifact 目录下执行单个 job：

```bash
python3 -m venv .venv-diagram
.venv-diagram/bin/python -m pip install -r scripts/geometry_diagram_workflow/requirements.txt
.venv-diagram/bin/python scripts/geometry_diagram_workflow/examples/verify_setup.py

python3 scripts/build_diagram_request.py artifacts/<slug>/01-structure-analysis.md \
  --job-id c1-prompt \
  --problem-text "当前题目的完整题干和已知条件" \
  --variant prompt \
  --disclosure-policy clean \
  --out artifacts/<slug>/diagram/jobs/c1-prompt/diagram-request.json

python3 scripts/run_diagram_workflow.py artifacts/<slug>/diagram/jobs/c1-prompt/diagram-request.json \
  --job-id c1-prompt \
  --python .venv-diagram/bin/python \
  --out artifacts/<slug>/diagram

python3 scripts/render_geometry_spec.py artifacts/<slug>/diagram/jobs/c1-prompt/final_renderer_spec.json \
  --variant prompt \
  --out-dir artifacts/<slug>/diagram/jobs/c1-prompt
```

若要生成讲解/教师版辅助线图，把上面两个命令的 `prompt/clean` 改成 `solution/annotated`，并在 request/YAML 中显式写 `reuse_geometry_from`，输出/引用 `diagram/jobs/<job_id>/rendered/solution.png`。

然后检查：

```text
artifacts/<slug>/diagram/jobs/<job_id>/workflow_events.jsonl
artifacts/<slug>/diagram/jobs/<job_id>/rounds/round_*/scene_payload.json
artifacts/<slug>/diagram/jobs/<job_id>/rounds/round_*/render_result.json
artifacts/<slug>/diagram/jobs/<job_id>/rounds/round_*/vision_result.json
artifacts/<slug>/diagram/jobs/<job_id>/renderer_result.json
artifacts/<slug>/diagram/jobs/<job_id>/rendered/prompt.png
artifacts/<slug>/diagram/jobs/<job_id>/rendered/solution.png  # 仅在需要 annotated 解答图时存在
```

语义复核不能只看 `usable=true`。每个 prompt job 还必须核对：

- 题干若写了点序（如 `B,C,H,D`、`C 在 B,H 之间`），solver 参数和预览图中的共线点顺序必须一致。
- 题干显式给出的长度、比例、相等、垂直、平行、共线等条件，必须能在 `scene_code` 或 `final_renderer_spec.json` 中找到对应表达；若缺失，回退重跑。
- prompt 图不得包含推理得到但题干未给出的结论标注，例如 `BH=HD`、中点提示、相等刻痕、解题文字。
- 若图形虽然可渲染但点序、比例或题干对象明显不符，不得写入 YAML；应保留失败日志并重新生成该 job。

不要在缺依赖时报 fallback。先安装 `scripts/geometry_diagram_workflow/requirements.txt` 并运行 `scripts/geometry_diagram_workflow/examples/verify_setup.py`；只有依赖和 Wolfram 验证仍失败，或 renderer 明确不支持当前图形类型时，才 fallback。

只有当 `renderer_result.json.status == "ok"` 且对应的 `diagram/jobs/<job_id>/rendered/<variant>.png` 存在时，才插入 YAML 图片对象。练习题不要默认引用 artifact 级 `diagram/rendered/prompt.png`。

## YAML 输出

成功时，LaTeX/YAML writer 插入图片对象，并且必须显式设置 `width`，不要依赖模板默认值：

```yaml
diagram_col:
  image_path: "diagram/jobs/c1-prompt/rendered/prompt.png"
  diagram_job_id: "c1-prompt"
  width: "0.30\\linewidth"
  caption: "观察点 D 在 BC 上的位置。"
  variant: "prompt"
  disclosure_policy: "clean"
```

插图位置和尺寸规则：

- 讲义原题展示用 clean prompt 图；讲解步骤如需辅助线，另生成 annotated solution 图。
- 选择题用 `diagram_col`，宽度优先 `0.28\\linewidth` 到 `0.32\\linewidth`。
- 填空题先排题干，再在题后用 `diagram_row.items[]`，单图宽度优先 `0.20\\linewidth` 到 `0.25\\linewidth`。
- 解答题用 `answer_space.diagram_col` 或 `answer_space.parts[].diagram_col`，宽度优先 `0.30\\linewidth` 到 `0.34\\linewidth`。
- 试卷中不要再用独立 `type: diagram` block 承载原题图；它容易挤占纵向空间。
- 插图后必须重新渲染 PDF，并用 `pdftoppm` 或等价工具预览首页，确认图的尺寸和位置合适。
- `caption` 写学生要观察的动作，不写“模型生成”“第几轮成功”等调试信息。
- 顶点/关键点标签必须清晰可读；在 PDF 缩小后的预览里仍要能看见 $A,B,C,D$ 等点名，不能只画点不标点。

试卷解答题推荐写法：

```yaml
answer_space:
  type: "steps"
  height: "62mm"
  parts:
    - label: "(1)"
      height: "28mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part1-prompt/rendered/prompt.png"
        diagram_job_id: "p1-part1-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
    - label: "(2)"
      height: "34mm"
      diagram_col:
        image_path: "diagram/jobs/p1-part2-prompt/rendered/prompt.png"
        diagram_job_id: "p1-part2-prompt"
        width: "0.32\\linewidth"
        caption: "原题图"
        variant: "prompt"
        disclosure_policy: "clean"
```

失败、跳过或图片缺失时，不插入破图字段；改插入一个简短 `hint` 或 `reading_tip`，例如：

```yaml
type: "hint"
id: "fig-main-fallback"
content: "本题建议先手动画出题干中的三角形和辅助线，再观察底边与高的对应关系。"
level: 1
```

## 边界

- 本 skill 可以调用 `scripts/build_diagram_request.py`、`scripts/run_diagram_workflow.py`、`scripts/render_geometry_spec.py`。
- 本 skill 不修改 LaTeX 模板，不编译 PDF。
- 本 skill 不要求 Wolfram 输出 PNG；正式图片来自 teaching renderer。
- 本 skill 不把 `workflow_result`、`final_renderer_spec`、`renderer_result` 写进学生可见内容。
