# Solution Reuse Contract

solution 图可以引用 prompt 图并追加辅助对象。workflow 会读取 prompt job 的 `final_renderer_spec.json`，用原图点坐标锁定已有点，再把辅助点和 Wolfram 辅助约束交给 GeometricScene 求解。

推荐契约：

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

- `reuse_geometry_from`: 复用 prompt job 的基础点坐标。
- `add_points`: 新增到 `GeometricScene[{...}]` 点集里的点。
- `hypotheses_wl`: 可直接拼入二阶段 GeometricScene hypotheses 的 Wolfram Language 约束字符串。
- `diagram_spec_delta`: 沿用现有 `diagram_spec` 形状，只决定可见辅助线、角标、等号、文字，不参与几何求解。

不要写需要另造解析器的教学语义 DSL，例如：

```json
{"type": "foot", "point": "H", "from": "A", "to_line": ["B", "D"]}
```
