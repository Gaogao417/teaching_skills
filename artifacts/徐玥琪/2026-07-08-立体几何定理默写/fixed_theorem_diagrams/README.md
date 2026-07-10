# 立体几何定理默写固定图说明

这个目录存放“定理默写”专用固定图。以后生成本专题 assignment 时，优先直接引用这里的 TikZ fragment，不再为这些定理声明 `diagram_slot`。

固定图不是手写 TikZ。单一事实源是 `specs.yaml`：

```text
定理条件 -> 三维坐标 -> tikz-3dplot TikZ
```

`render_fixed_diagrams.py` 会先在三维坐标层校验平行、垂直、共面、交线和从属关系，再生成基于 `tikz-3dplot` 的 `tikz/*.fragment.tex` 与 `catalog.yaml`。

## 使用原则

1. 一条定理对应一张固定图。
2. 左侧竖式条件组是标准；右侧图只画条件组里的对象。
3. 图上只标点、线、面、交线、垂足、角或距离这些必要对象。
4. 不画正方体、棱锥等真实题目载体；定理默写图统一用“关系示意图”。
5. 不出现构造点、平面边角字母、辅助端点、调试标签。
6. 两个平面相交时，必须在 `conditions` 中声明 `plane_intersection_line`；renderer 会由两个平面方程求出交线，并裁剪成两个平面四边形的公共可见段，最后高亮绘制。
7. 图形统一使用低干扰灰阶：实线表示定理原对象，虚线表示辅助线、投影线、高度线或背景边，较粗实线表示交线。
8. 不用多种鲜艳颜色承担数学关系，避免图形本身抢走学生对条件组的注意力。
9. 新增定理时，先补 `specs.yaml`，运行生成脚本，再出 assignment。

## YAML 引用格式

```yaml
diagram_col:
  kind: tikz
  tikz_path: fixed_theorem_diagrams/tikz/b03-line-plane-parallel-judge.fragment.tex
  width: 55mm
  variant: prompt
  disclosure_policy: clean
  caption: ""
```

`tikz_path` 必须相对最终 `.tex` 所在目录可访问。当前目录下的 assignment 编译工作目录就是本 artifact 目录，所以可直接使用上面的相对路径。

## 生成规则

- 本目录已有固定图的定理，不再走 `diagram_slot` / diagram workflow。
- `diagram_slot` 只用于本目录尚未入库的新几何构型；一旦确认可复用，应沉淀为 `specs.yaml` 条目并生成固定 TikZ fragment。
- 不直接手改 `tikz/*.fragment.tex`；如需改图，修改 `specs.yaml` 里的条件对象或三维坐标，然后运行：

  ```bash
  ./.venv/bin/python artifacts/徐玥琪/2026-07-08-立体几何定理默写/fixed_theorem_diagrams/render_fixed_diagrams.py
  ```

- 题目左侧条件组的对象集合，应与 `catalog.yaml` 中 `diagram_labels` 基本一致。
- 若挖空在右侧结论，图仍只展示定理对象关系，不额外写答案文字。
- `tikz-3dplot` 只负责三维坐标到页面的投影；相交平面的交线由本目录 renderer 根据 `plane_intersection_line` 求解，可读性由半透明平面样式和交线高亮规则保证。
- 每张图的视角应让核心线线夹角尽量打开，避免辅助线、交线和原线在投影后重叠。
