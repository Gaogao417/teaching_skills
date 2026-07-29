# SourceQuestion v2 DOCX 金丝雀结果

日期：2026-07-29

金丝雀定义：
`tests/question_transcription/fixtures/docx-v2-canary-set.yaml`

## 覆盖范围

| 样本 | 主要覆盖 | 真实提取结果 |
|---|---|---|
| 2022 长宁 exam | 四个函数图选项、页 crop fallback、旧题号状态机 | 图片归属失败：期望 Q5 时误读到 36；文本/页面提取继续 |
| 2022 徐汇 exam | 未绑定 EMF、小问题干图、旧题号状态机 | 图片归属失败：期望 Q5 时读到 Q6；文本/页面提取继续 |
| 2026 长宁 teacher | OLE 密集、小问题干图、解答图 | 成功：526 media，509 OLE formula，17 attribution，36 页 |
| 2025 杨浦 teacher | 纯栅格媒体、多小问/多解答步骤图 | 成功：24 media，24 attribution，32 页 |
| 2024 虹口 teacher | OLE 与未绑定 WMF 并存、重复媒体、mixed-content 嫌疑 | 成功：466 media，440 OLE formula，2 unbound WMF，30 attribution，36 页 |

## 已确认结论

1. OLE 判据在真实 Office 文件上可工作：OLE 密集的 2026 长宁将 509 个矢量预览
   稳定标为 `formula`；2024 虹口的两个未绑定 WMF 稳定标为 `diagram`。
2. 扩展名不能代替 OLE 判据：虹口的 `image257.wmf`、`image6.wmf` 未绑定 OLE，
   不会再被 extractor 直接过滤。
3. `diagram` 分类不等于“归属已确认”：`image6.wmf` 横跨 Q2、Q4、Q21 多次出现，
   其中至少一条 attribution 为 low，必须进入 attribution review。
4. 2022 长宁 Q5 的四个函数图在渲染页
   `documents/初三/2022届-上海市长宁区-初三二模数学-试卷及参考答案/word/pages/002.png`
   中完整可见，而现有 staging 的 `prompt` 为空。该题是 choice panel/page fallback
   的强制回归样本。
5. 两个状态机失败样本会清空全部 partial attribution，但仍产出完整
   `word-source.yaml`、媒体、PDF 和页面，供文本转录继续使用。

## 暴露的下一层缺口

- 旧题号状态机把正文中的 `36` 或连续题号 Q6 误当成结构跳号，导致 2022 长宁、
  徐汇的 OOXML 图片归属不可用。文本仍可进入 assembler；修复前不得恢复到按媒体
  编号猜归属。
- 当前粗粒度 extractor 只能给出 prompt/solution bucket；还需要 SourceQuestion
  assembler 把金丝雀中的图片进一步绑定到 choice、part_stem 和具体 solution_step。
- `mixed_content` 仍必须由人工根据渲染页确认；本轮只识别 review candidate，没有
  自动定类。

## 验证

- 3 份成功样本完成了真实 LibreOffice PDF 渲染与 `pdftoppm` 页面生成。
- 真实 manifest 中所有 WMF/EMF 均带 `ole_binding` 和 `emf_class`。
- 2 份失败样本验证了 attribution 清空、错误持久化与文本输入保留。
- `tests/question_transcription` 全套测试通过。
