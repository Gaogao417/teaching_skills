# Word 来源提取合同

## 两类产物

DOC/DOCX 来源使用 `scripts/extract_docx_source.py`，只产出两类不可互相替代的
素材：

1. **Word 媒体原图**（`media/*`）：题图、解析图的原始分辨率/透明度位图。PDF
   渲染会二次栅格化并丢失透明度，所以独立图必须从 Word 媒体取。
2. **PDF 渲染页**（`pages/*.png`）：所有文字和公式转写的唯一权威来源。DOCX 里的
   公式是 WMF/EMF 矢量对象，无法直接读取；soffice 转 PDF 后烘焙成位图才能转写。

Word 解包通道导出段落流（`paragraphs`）并据此自动计算图片归属
（`image_attribution`）。题干文字、公式、题号定位以 PDF 渲染页为准；图片归属以
段落流为准——OOXML 结构里每张图绑定其所在段落，按题号切片 + `【分析】`/`【详解】`
锚点确定性判定 prompt/solution 桶，不再靠肉眼在 PDF 页上认图。

## 输出目录

```text
<source-archive>/word/
├── source.doc|source.docx          # 原始文件副本
├── normalized.docx                  # OOXML 规范化版本
├── word-source.yaml                 # 段落流 + 图片归属 + 媒体清单 + PDF 页记录
├── media/                           # Word 原始嵌入媒体
│   ├── image1.png                   #   题图（几何图、统计图、照片等）
│   ├── image2.wmf                   #   公式对象（MathType OLE → 矢量图）
│   └── ...
├── ooxml/
│   ├── document.xml                 # 溯源归档（不再解析段落）
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
- `paragraphs`：段落流，每条 `{index, text, images, previous_text, next_text}`，
  按 OOXML 文档流顺序；空段落已剔除。这是图片归属的结构化数据源。
- `image_attribution`：每张非公式图（排除 wmf/emf）的归属判断，每条
  `{media, question_number, bucket, paragraph_index, confidence}`。`bucket` 为
  `prompt`/`solution`/`orphan`；`confidence` 为 `high`/`medium`/`low`。

## 图片归属的职责

`media/image1.png` 只按 Word 内部嵌入顺序编号，不带题号语义。图片归属**以段落流的
`image_attribution` 为准**，不按文件名编号猜测，也不靠肉眼在 PDF 渲染页认图：

- **prompt 桶**：图所在段落落在某题题号区间内、且在 `【分析】`/`【详解】` 之前。
- **solution 桶**：图落在题号区间内、但出现在 `【分析】`/`【详解】` 之后。
- **orphan**：图不在任何题号区间内（章节插图/装饰图），标 `low` 置信度，需人工核对。

### 置信度含义

| confidence | 含义 | agent 处理 |
|-----------|------|-----------|
| `high` | 图数与题干"如图N"声明一致、单一桶、无重复出现 | 直接写入 `prompt`/`solution`，无需看 PDF |
| `medium` | 图数与题干声明不符（合成图/多小问图）、或多选项题 | 写入后看 PDF 页或图本身确认 |
| `low` | 图跨多段重复、题号切片存疑、orphan | 必须人工核对后再写 |

agent 录入时优先消费 `high`，`medium`/`low` 在 review 阶段对照 PDF 渲染页确认。

## 图片归属

`media/image1.png` 只按 Word 内部嵌入顺序编号，不带题号语义。图片归属（哪张图
属于哪道题、是题图还是解析图）由 `extract_docx_source.py` 的段落状态机自动判定，
写入 `word-source.yaml` 的 `image_attribution`。agent 录入时直接读取归属结果，
不按文件名编号猜测，也不在 PDF 渲染页上肉眼认图。归属置信度为 `medium`/`low`
的项，在 review 阶段对照 PDF 渲染页确认。一个媒体文件在题干与解析中重复出现时，
段落流会分别记录其在 prompt/solution 段落的出现，不因像素相同而省略来源关系。

## 两类产物的职责

| 内容类型 | 来源 | 说明 |
|----------|----------|------|
| 公式转写 | PDF 渲染页 (`pages/*.png`) | WMF/EMF 是二进制矢量，无法直接读取；PDF 里公式是渲染好的位图，可准确转为 LaTeX |
| 题干文字 | PDF 渲染页 (`pages/*.png`) | 与公式一起从渲染页转写，保证题号、上下文、版面一致 |
| 题图 prompt | Word 媒体原图 (`media/*`) | 几何图、函数图、统计图、表格、照片等独立图片，保留原始分辨率和透明度 |
| solution 图 | Word 媒体原图 (`media/*`) | 官方解答中的独立图片 |
| 来源证据 | 整页 PNG + 页码 | `question_word_evidence` 和 `official_solution.word_evidence` 引用 `word/pages/NNN.png` 和页码 |
| 审计凭证 | PDF 渲染页 | 结构审计和人工审核时对照渲染页验证转写正确性 |

## 题图和公式处理规则

- **独立几何图、函数图、统计图、表格或照片**：优先直接作为 `prompt` / `solution`
  来源，使用 Word 媒体原图，`box_px` 使用完整像素范围。
- **公式对象（WMF/EMF）**：不在 draft 中声明为 `prompt`。转写时对照 PDF 渲染页
  读取公式内容，写入 `stem_latex` 或 `solution_steps`。转写后仍保留 WMF 原媒体和
  哈希，供疑难公式回查。
- **多图选择题**：按 PDF 渲染页版面顺序和 A/B/C/D 标签确定性组合；顺序或标签
  无法可靠恢复时标记人工核对。
- **来源证据**：原题来源使用 `question_word_evidence`；官方解答来源使用
  `official_solution.word_evidence`。两者都引用整页 PNG 路径和页码。页码即
  `word/pages/NNN.png` 文件名的三位序号（1-based）——agent 在转写时本就在看
  渲染页，顺手填页码。

## 来源证据示例

```yaml
question_word_evidence:
  - page_image: documents/初三/PAPER/word/pages/002.png
    page_number: 2
official_solution:
  start_anchor: '13．'
  end_anchor: '14．'
  word_evidence:
    - page_image: documents/初三/PAPER/word/pages/008.png
      page_number: 8
```

物化时写入 `page_image_sha256`。整页图证据不进入 `content_hash`——源文件是
不可变归档，无需漂移检测；转写内容（`stem_latex`/`solution_steps`）在 hash
中，转写错误仍会触发重审。Review UI 在来源 section 右上角渲染页码胶囊，
点击可打开整页图。

## 公式转写流程

1. 在 `word/pages/*.png` 中定位题目所在页（按题号视觉锚点）
2. 把该页路径和页码填入 `question_word_evidence`（或 `official_solution.word_evidence`）
3. 从该渲染页读取公式的视觉内容，转为可检索 LaTeX
4. 对于复杂公式，可引用 `media/*` 中的 WMF 原文件作为辅助回查凭证
5. 转写结果写入 `paper.draft.yaml` 的 `block.stem_latex` 或 `block.solution_steps`

## Word 媒体图低分辨率处理

Word 原图低分辨率但内容完整时仍优先保留原图。可生成确定性放大显示副本，但来源
记录必须指向原图；禁止生成式重画。
