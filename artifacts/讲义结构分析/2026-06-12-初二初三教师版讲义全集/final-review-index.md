# 初二初三讲义逐题 Structural Analysis 总验收

- 输出根目录：`/Users/gaochong/develop/teaching_skills/artifacts/讲义结构分析/2026-06-12-初二初三教师版讲义全集`
- 讲义来源 manifest：`manifest.json`（205 份教师版讲义）
- 候选题 manifest：`problem-analysis-manifest.json`
- 逐题输出目录：`problems/`

## 完成度

- 候选题总数：967
- 已生成逐题 `01-structure-analysis.md`：967
- 缺失：0
- 结构摘要 JSON 可解析：967
- 结构摘要 JSON 解析失败：0
- 候选中需要图形/原图复核的题：721
- 文本内标记需人工复核/无法锁定/OCR复核：851

## 来源分布

- xindongfang-初二: 152
- xindongfang-初三: 105
- xueersi-初二: 560
- xueersi-初三: 150

## 批次产物

- `candidate-problems-xindongfang.json`
- `candidate-problems-xueersi-初二.json`
- `candidate-problems-xueersi-初三.json`
- `analysis-batch-xindongfang.json`
- `analysis-batch-xueersi-初三.json`
- `analysis-batch-xueersi-初二-1.json`
- `analysis-batch-xueersi-初二-2.json`
- `analysis-batch-xueersi-初二-3.json`
- `analysis-batch-xueersi-初二-4.json`

## 进度/复核记录

- `progress-analysis-xindongfang.md`
- `progress-analysis-xueersi-初三.md`
- `progress-analysis-xueersi-初二-1.md`
- `progress-analysis-xueersi-初二-2.md`
- `progress-analysis-xueersi-初二-3.md`
- `progress-analysis-xueersi-初二-4.md`
- `final-quality-summary.json`

## 质量说明

- 本轮按“两段式”完成：先逐讲义筛选值得分析的题，再逐题生成 structural analysis。
- 没有生成 assignment YAML、TEX、PDF 或真实图片。
- 图形题只在结构分析里写 `diagram_request_packet`；真实插图应留到后续作业/讲解阶段。
- OCR 里大量题只有截图占位或解析粘连；相关题已标记“需人工复核/无法锁定”，避免后续误把缺图条件编造成题设。
- 部分文件标题使用“交付给下一阶段的结构摘要”而非完整“结构摘要 JSON”字样，但末尾 JSON 块均可解析。