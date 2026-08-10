# D 类: 页图路径 / 命名问题

## D-1: 2026-BAOSHAN-ERMO（进 staging，受影响）

### 根因
`_last_page_from_evidence` 报 "no rendered pages found in
.../2026届-上海市宝山区.../word"。parent 路径**正确**
（`documents/初三/2026届-.../word/pages`），目录里有 **36 个 png**，
但文件名是 `page-01.png`、`page-02.png` …（PDF 提取命名，带 `page-` 前缀）。

`_last_page_from_evidence` 用 `path.stem.isdigit()` 过滤页文件：
`"page-01".isdigit()` 为 False → 全部被跳过 → 扫到 0 个页 → 报错。

### 这卷的 word-source.yaml 是非标准产物
```
顶层 keys: ['source_file', 'total_paragraphs', 'total_images', 'images', 'paragraphs']
schema 字段: None  （不是 math_word_source_extract/v1）
rendered_pages: 不存在
```
这是旧版/手动 PDF 提取的产物（用 `images` 字段而非 `media`，无 `rendered_pages`），
命名规则 `page-NN.png`。而 DOCX 路径的 `extract_docx_source.py` 产出 `NNN.png`
（纯数字），与 `isdigit()` 兼容。

### 影响范围
**只有 2 个 page-N 卷真正进了 staging 题库**（其余 15 个"精品解析"卷只是
documents 源数据，未进 staging，不影响 ingestion）：

| 卷 | page_image 样例 | word-source schema | 进 staging |
|----|----------------|-------------------|-----------|
| 2026-BAOSHAN-ERMO | `.../word/pages/page-01.png` | 无 schema（旧 PDF 提取） | 是（报错） |
| 2024-QINGPU-ERMO | `.../word/pages/page-1.png` | math_word_source_extract/v1 | 是（报 cannot infer layout，见 B 类） |

> 2024-QINGPU-ERMO 同时命中 B 类（layout）和 D 类（page-N 命名）。
> 它的 word-source.yaml 是标准 schema，但页图用了 PDF 命名。

## D-2: documents 下 17 个 page-N 卷（未进 staging，仅源数据）

```
2024届-青浦区二模                6 个 page-N (标准 schema)
2026届-宝山区二模               35 个 page-N (无 schema)
精品解析：2026 各区二模 ×15     34-41 个 page-N (无 schema)
```
这些卷的 word-source.yaml 多为非标准/手动提取（无 schema 字段），
页图用 `page-N.png` 命名。**它们目前都没进 staging 题库**，所以不影响
当前 ingestion。但如果将来用它们建 staging，会触发和 2026-BAOSHAN 一样的
`isdigit()` 问题。

## 修复方案（三选一，按侵入性排序）

### 方案 1（推荐，改脚本）：`_last_page_from_evidence` 兼容 page-N 命名
在 `word_evidence_pages.py` 的 `_last_page_from_evidence` 里，把页号提取
从 `int(path.stem)` 改成兼容两种命名：
```python
def _page_index_from_name(stem: str) -> int | None:
    if stem.isdigit():           # 001 / 42
        return int(stem)
    if stem.startswith("page-"): # page-01 / page-1
        tail = stem.removeprefix("page-").lstrip("0") or "0"
        return int(tail) if tail.isdigit() else None
    return None
```
同步改 `discover_pages`（observe_docx_pages.py:590 的 `int(path.stem)`）和
`build_docx_span_index.py:340`。**一处定义、多处复用**。

优点：根治；page-N 卷和纯数字卷统一处理。缺点：需确认所有调用点。

### 方案 2（改数据）：把 page-N.png 重命名为纯数字
对 2026-BAOSHAN 和 2024-QINGPU 的 pages 目录，`page-01.png` → `001.png`。
同时改 draft 里所有 page_image 路径。

优点：不动脚本。缺点：每卷手动改；治标。

### 方案 3（最小，仅修 2 个进 staging 的卷）
只对 2026-BAOSHAN-ERMO 和 2024-QINGPU-ERMO 执行方案 2 的重命名，
其余 15 个未进 staging 的卷暂不动。

## 建议
- **短期**：方案 3（先让 2 个 staging 卷能跑通）。
- **长期**：方案 1（脚本兼容 page-N，避免将来 15 个精品解析卷入库时再踩）。
- 这两卷的 layout 另见 B 类报告（2026-BAOSHAN 未在 B 类是因为它先卡在
  D 类的 last_page，没走到 layout 推断；2024-QINGPU 已在 B 类确诊 interleaved）。
