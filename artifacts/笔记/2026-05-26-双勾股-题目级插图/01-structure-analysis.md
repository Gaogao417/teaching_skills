# 结构分析：双勾股求边长

## 原题
如图，在三角形 $ABC$ 中，点 $D$ 在射线 $BC$ 上，且 $C$ 在 $B,D$ 之间，$AD=AB$。已知 $AB=15$，$AC=13$，且 $2BD=9BC$，求 $BC$ 的长。

## 核心结构
本题是“等腰三角形底边高 + 共高双勾股”。过 $A$ 作 $AH\perp BD$，由 $AD=AB$ 得 $H$ 为 $BD$ 中点，于是 $BH$ 与 $CH$ 都能用 $BC$ 表示。再在 $\triangle ABH$ 与 $\triangle ACH$ 中两次勾股，相减消去 $AH^2$。

## 标准解
设 $BC=x$。由 $2BD=9BC$ 得 $BD=\dfrac92x$。因为 $AD=AB$，且 $AH\perp BD$，所以 $H$ 是 $BD$ 的中点，
$$BH=HD=\frac12BD=\frac94x.$$
点序为 $B-C-H-D$，所以
$$CH=BH-BC=\frac94x-x=\frac54x.$$
在 $\triangle ABH$ 与 $\triangle ACH$ 中：
$$15^2=AH^2+\left(\frac94x\right)^2,\qquad 13^2=AH^2+\left(\frac54x\right)^2.$$
两式相减：
$$56=\frac{81-25}{16}x^2=\frac72x^2,$$
所以 $x^2=16$，$x=4$。故 $BC=4$。

## 变式原则
保留：$AD=AB$、点 $D$ 在 $BC$ 射线上、两个共高直角三角形、两条斜边长度、一个能把 $BD$ 与 $BC$ 联系起来的条件。可变：边长数字、比例、求 $BC$ 或反向求某条斜边。

```json
{
  "problem_pattern": "等腰三角形底边高 + 共高双勾股求线段",
  "core_transformation": "由 AD=AB 和 AH 垂直 BD 得 H 为 BD 中点，再把 BH、CH 都表示成 BC 的倍数",
  "diagram_request_packet": {
    "needs_diagram": true,
    "diagram_type": "synthetic_geometry",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": ["A", "B", "C", "H", "D"],
      "segments": ["AB", "AC", "AD", "AH", "BD"],
      "constraints": ["B,C,H,D collinear", "AH perpendicular BD", "BH=HD", "C between B and H"]
    },
    "teaching_focus": ["先作高", "再看中点", "最后看两个直角三角形"],
    "must_not_imply": ["不要暗示 C=H", "不要暗示 AC=AD"],
    "fallback": "textual_diagram_description"
  }
}
```
