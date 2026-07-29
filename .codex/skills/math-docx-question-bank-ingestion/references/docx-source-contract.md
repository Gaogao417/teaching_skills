# Word 来源提取合同

## 两类产物

DOC/DOCX 来源使用 `scripts/extract_docx_source.py`，只产出两类不可互相替代的
素材：

1. **Word 媒体原图**（`media/*`）：题图、选项图、小问题图、解析图的原始媒体。PDF
   渲染会二次栅格化并丢失透明度，所以独立图必须从 Word 媒体取。
2. **PDF 渲染页**（`pages/*.png`）：所有文字和公式转写的唯一权威来源。DOCX 里的
   公式预览常见为 WMF/EMF，但扩展名不是类别判据；只有绑定 OLE 公式对象的媒体
   才是 `formula`。未绑定 OLE 的 WMF/EMF 是 `diagram`。

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
- `image_attribution`：每张非公式图（排除已绑定 OLE 的媒体）的粗粒度归属判断，每条
  `{media, question_number, bucket, paragraph_index, confidence}`。`bucket` 为
  `prompt`/`solution`/`orphan`；`confidence` 为 `high`/`medium`/`low`。
- `image_attribution_status`：`complete` 或 `failed`。失败表示题号状态机无法给出
  可信的整卷映射，此时 `image_attribution` 必须为空。
- `image_attribution_error`：仅失败时出现，记录错误码和详情。该错误不影响
  `rendered_pages` 作为题干、公式和解析文本转录来源。

图片归属失败是独立失败域：extractor 丢弃全部 partial attribution，但仍保存媒体、
渲染 PDF 和页面。文本观察可以继续；图片 adapter 必须停止，含图题进入
`image_structure: needs_review`。不得把空 attribution 当成“来源没有插图”。

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
| 公式转写 | PDF 渲染页 (`pages/*.png`) | OLE 绑定确定它是公式；文字仍从 PDF 页转写，不从 GDI 记录取 |
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
- **多图选择题**：可靠时建立 A/B/C/D 四个 choice target；无法可靠拆分时保留
  choice panel 并人工确认 mapping。顺序或标签
  无法可靠恢复时标记人工核对。
- **来源证据**：原题来源使用 `question_word_evidence`；官方解答来源使用
  `official_solution.word_evidence`。两者都是**完整连续页数组**，引用整页 PNG
  路径和页码。页码即 `word/pages/NNN.png` 文件名的三位序号（1-based）。
  不得只记录首页、末页或代表页。
- 题目与解析交替排版时，题干页从题号开始覆盖到答案/分析/详解开始页；解答页从
  答案/分析/详解开始覆盖到下一题开始前。最后一题覆盖到文档末页。
- 先整卷题目、后整卷答案时，题干页覆盖到下一题开始前，解答页覆盖到下一题答案
  开始前；最后一题解答覆盖到文档末页。
- 一个边界页同时含题干和解答，或同时含前题结尾和后题开头时，允许被相邻角色或
  相邻题目共同引用。完整性优先于避免整页证据重叠。

## 来源证据示例

```yaml
question_word_evidence:
  - page_image: documents/初三/PAPER/word/pages/002.png
    page_number: 2
  - page_image: documents/初三/PAPER/word/pages/003.png
    page_number: 3
official_solution:
  start_anchor: '13．'
  end_anchor: '14．'
  word_evidence:
    - page_image: documents/初三/PAPER/word/pages/008.png
      page_number: 8
    - page_image: documents/初三/PAPER/word/pages/009.png
      page_number: 9
```

物化时写入 `page_image_sha256`。整页图证据不进入 `content_hash`——源文件是
不可变归档，无需漂移检测；转写内容（`stem_latex`/`solution_steps`）在 hash
中，转写错误仍会触发重审。Review UI 在来源 section 右上角渲染页码胶囊，
点击可打开整页图。

## 公式转写流程

1. 在 `word/pages/*.png` 中定位题干第一页和官方解答第一页（按题号及
   `【答案】`/`【分析】`/`【详解】`视觉锚点）
2. 把两个 seed 页写入 draft 后运行 `scripts/word_evidence_pages.py`，确定性展开
   完整连续页区间
3. 用 `--check` 确认没有缺页后，再从全部相关渲染页读取公式的视觉内容
4. 对于复杂公式，可引用 `media/*` 中的 WMF 原文件作为辅助回查凭证
5. 转写结果写入 `paper.draft.yaml` 的 `block.stem_latex` 或 `block.solution_steps`

## Word 媒体图低分辨率处理

Word 原图低分辨率但内容完整时仍优先保留原图。可生成确定性放大显示副本，但来源
记录必须指向原图；禁止生成式重画。
