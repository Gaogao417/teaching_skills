# Homework Review：双勾股 workflow 真跑

审核印象：基本可用但需继续增强 workflow 语义复核。

1. 完整性：结构分析、讲解 YAML/TEX/PDF、学生版练习 YAML/TEX/PDF、教师版练习 YAML/TEX/PDF、diagram job 日志和 PDF 预览均已生成。所有正式引用的图片都来自 `diagram/jobs/<job-id>/rendered/prompt.png`。

2. 数学正确性：原题讲解保留了 $AD=AB$、作高得中点、共高双勾股相减的核心链条，答案 $BC=4$ 自洽。练习题答案与题干基本匹配；大题为稳定画图改成了显式给 $BH=9,CH=5$ 的共高读图版，仍训练同一动作但迁移强度比原计划略低。

3. 结构分析：结构分析能抓住“等腰底边高 + 共高消元”主结构，并给出可执行的标准解。后续 workflow 暴露出结构分析里的 `BH=HD`、中点等推理信息容易泄露到 prompt 图，已通过 clean prompt gate 清理。

4. 讲解质量：讲解按“作高、得中点、表示底边、双勾股相减”展开，学生能跟住主线。讲义原题图在右侧图栏，顶点标签清楚，未把 workflow 调试信息暴露给学生。

5. 练习设计：选择题、填空题、解答题都围绕同一结构；学生版隐藏答案，教师版给答案和解析。填空题图行后置，避免图先于题干出现。

6. 几何插图与版式：选择题使用右侧 `diagram_col` 且选项竖排；填空题先出题干，后置 `diagram_row`；解答题每问答题区右侧有图栏，复用同一大题图时显式写了 `reuse_from`。各题图片路径不再静默共用 artifact 级图；prompt 图经过 clean gate 清掉了多边形和推理提示，顶点标签在预览中可读。

最需要关注：当前 workflow 已能做到题目级 job 和版式契约，但 GSB 返回 `usable=true` 时仍可能出现点序语义不合题意，需要把“点序/共线比例/题干条件是否被图满足”的语义复核固定进 renderer 或 reviewer。

建议下一步：把本轮发现的语义复核规则加入 `math-geometry-diagram-renderer` 的 workflow gate：不仅检查图片存在和 label 清楚，还要检查题干中的点序、显式长度/比例、禁止泄露项是否在 `final_renderer_spec.json` 和 solver 参数中一致。
