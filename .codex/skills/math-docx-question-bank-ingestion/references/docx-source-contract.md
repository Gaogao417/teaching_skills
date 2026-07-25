# Word 来源提取合同

## 双通道提取

DOC/DOCX 来源使用 `scripts/extract_word_source.py`，同时产出两个通道：

1. **Word 解包通道**：提取段落结构、原始嵌入媒体（题图 + 公式对象）
2. **PDF 渲染通道**：soffice 转 PDF 后逐页渲染为 PNG（公式已变为可读位图）

## 输出目录

```text
<source-archive>/word/
├── source.doc|source.docx          # 原始文件副本
├── normalized.docx                  # OOXML 规范化版本
├── word-source.yaml                 # 段落结构 + 媒体清单 + PDF 页记录
├── media/                           # Word 原始嵌入媒体
│   ├── image1.png                   #   题图（几何图、统计图、照片等）
│   ├── image2.wmf                   #   公式对象（MathType OLE → 矢量图）
│   └── ...
├── ooxml/
│   ├── document.xml
│   └── document.xml.rels
├── rendered.pdf                     # soffice 渲染的 PDF
└── pages/                           # PDF 逐页渲染的 PNG
    ├── 001.png
    ├── 002.png
    └── ...
```

`.doc` 先由 soffice 规范化为 `.docx`，再走相同流程。所有产出文件一旦被 draft 引用即不可变。

## word-source.yaml 结构

使用 `math_word_source_extract/v1`，包含：

- `source`：原文件路径和 SHA-256
- `normalized_docx`：规范化 DOCX 路径和 SHA-256
- `rendered_pdf`：PDF 路径、SHA-256 和 DPI
- `media`：每个媒体文件的路径、SHA-256 和像素尺寸
- `rendered_pages`：每个 PDF 页面的路径、SHA-256 和像素尺寸
- `paragraphs`：有文字或图片的段落顺序、文本、图片归属、前后文

## 段落与图片归属

按段落顺序和邻近题号判断图片归属，不按 `image1.png` 的编号猜测。空段落中的图片
必须结合前后文本确认；归属仍不明确时标记人工核对。一个媒体文件在题干与解析中重复出现时，分别按实际
段落归属处理，不因像素相同而省略来源关系。

## 双通道各自职责

| 内容类型 | 来源通道 | 说明 |
|----------|----------|------|
| 公式转写 | PDF 渲染页 (`pages/*.png`) | WMF/EMF 是二进制矢量，无法直接读取；PDF 里公式是渲染好的位图，可准确转为 LaTeX |
| 题图 prompt | Word 媒体原图 (`media/*`) | 几何图、函数图、统计图、表格、照片等独立图片，保留原始分辨率和透明度 |
| solution 图 | Word 媒体原图 (`media/*`) | 官方解答中的独立图片 |
| 段落证据 | `word-source.yaml` 段落范围 | `question_word_evidence` 和 `official_solution.word_evidence` 引用段落编号 |
| 审计凭证 | PDF 渲染页 | 结构审计和人工审核时对照渲染页验证转写正确性 |

## 题图和公式处理规则

- **独立几何图、函数图、统计图、表格或照片**：优先直接作为 `prompt` / `solution`
  来源，使用 Word 媒体原图，`box_px` 使用完整像素范围。
- **公式对象（WMF/EMF）**：不在 draft 中声明为 `prompt`。转写时对照 PDF 渲染页
  读取公式内容，写入 `stem_latex` 或 `solution_steps`。转写后仍保留 WMF 原媒体和
  哈希，供疑难公式回查。
- **多图选择题**：按段落内媒体顺序和 A/B/C/D 文本确定性组合；顺序或标签无法可靠恢复
  时标记人工核对。
- **段落证据**：原题来源使用 `question_word_evidence`；官方解答来源使用
  `official_solution.word_evidence`。两者都引用 manifest 和闭区间段落编号。

## 来源证据示例

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

## 公式转写流程

1. 在 `word-source.yaml` 中定位题目段落范围
2. 读取对应 PDF 渲染页（根据段落范围估算页码）
3. 从渲染页读取公式的视觉内容，转为可检索 LaTeX
4. 对于复杂公式，可引用 `media/*` 中的 WMF 原文件作为辅助回查凭证
5. 转写结果写入 `paper.draft.yaml` 的 `block.stem_latex` 或 `block.solution_steps`

## Word 媒体图低分辨率处理

Word 原图低分辨率但内容完整时仍优先保留原图。可生成确定性放大显示副本，但来源
记录必须指向原图；禁止生成式重画。
