# Word 来源提取合同

## 输出目录

对 DOC/DOCX 运行 `scripts/extract_word_source.py`，输出必须是新目录：

```text
<source-archive>/word/
├── source.doc|source.docx
├── normalized.docx
├── word-source.yaml
├── media/
└── ooxml/
    ├── document.xml
    └── document.xml.rels
```

`.doc` 先规范化为 DOCX；这是结构转换，不是页面渲染。`source.*`、
`normalized.docx`、`media/*` 和 `word-source.yaml` 一旦被 draft 引用即不可变。

## 段落与图片归属

`word-source.yaml` 使用 `math_word_source_extract/v1`，记录：

- 原文件与规范化 DOCX 的 SHA-256；
- 每个媒体文件的 SHA-256 和像素尺寸；
- 有正文或图片的段落顺序；
- 段落文字、图片路径及前后最近的非空文本。

按段落顺序和邻近题号判断图片归属，不按 `image1.png` 的编号猜测。空段落中的图片
必须结合前后文本确认；归属仍不明确时标记人工核对。一个媒体文件在题干与解析中重复出现时，分别按实际
段落归属处理，不因像素相同而省略来源关系。

## 题图、公式和段落证据

- 独立几何图、函数图、统计图、表格或照片：优先直接作为 `prompt` / `solution`
  来源，`box_px` 使用完整像素范围。
- 公式对象：用于补全可检索 LaTeX；默认不进入题面图片。转写后仍保留原媒体和哈希，
  供疑难公式回查。
- 多图选择题：按段落内媒体顺序和 A/B/C/D 文本确定性组合；顺序或标签无法可靠恢复
  时标记人工核对，不把四图误当成四个无标签 prompt。
- 原题来源使用 `question_word_evidence`；官方解答来源使用
  `official_solution.word_evidence`。两者都引用 manifest 和闭区间段落编号。

Word 原图低分辨率但内容完整时仍优先保留原图。可生成确定性放大显示副本，但来源
记录必须指向原图；禁止生成式重画。

示例：

```yaml
question_word_evidence:
  - manifest: documents/初三/PAPER/word/word-source.yaml
    paragraph_start: 27
    paragraph_end: 28
official_solution:
  start_anchor: '13．'
  end_anchor: '14．'
  word_evidence:
    - manifest: documents/初三/PAPER/word/word-source.yaml
      paragraph_start: 210
      paragraph_end: 222
```

物化时写入 manifest SHA-256；审计必须确认段落范围至少包含一条记录。正文、图片或
范围变化都会刷新 `content_hash` 并使旧人工审核失效。

## 可选页面复核

机器录入默认不导出 PDF、不渲染页图。只有用户明确要求检查原版分页、浮动对象、页眉
页脚或强排版整体时，才在 structural gate 之后用 Word/Pages 做页面复核。可选复核产物
不得替代 `word-source.yaml`，也不得计入 DOC 首次机器录入耗时。
