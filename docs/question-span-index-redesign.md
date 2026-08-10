# 题目观察改造：移除重叠窗口自由发现，改为先索引、后定点转写

## 1. 目标

本次只改题目观察层，消除以下三个串线来源：

1. DOCX 每个观察窗口都注入同一份 OOXML 全文前缀；
2. DOCX/PDF provider 在没有预期题号的情况下自由发现题目；
3. 默认使用 3 页窗口、1 页重叠，导致同一页面和题目被多次解释。

改造后的主链路为：

```text
冻结页图/渲染 PDF
  → 低成本逐页预扫
  → QuestionSpanIndex（题号、角色、页区间、题型提示）
  → 确定性 ObservationBatchPlan
  → 按批定点视觉转写
  → 现有 observation contract
  → 现有 merge / adapt / assemble / audit / review
```

成功标准不是“减少重叠”，而是同时满足：

- 正式视觉转写不再自由决定本批有哪些题；
- 每个正式批次的页面集合确定、默认互不重叠；
- provider 返回题号集合与批计划不一致时隔离异常并定点补读；修复完成前不产生可进入
  merge 的观察文件，但已校验正常的题目可以冻结复用，不整批重跑；
- 下游 `DocxObservationBundle`、`MergedPdfObservation` 和公开
  `QuestionTranscriptionBundle` 的结构不变。

## 2. 已核实的现状

- DOCX 污染源位于
  `scripts/question_transcription/procedural/observe_docx_pages.py::_paragraph_hint()`：
  每个窗口收到同一份最多 12000 字的段落全文。
- DOCX 的 `_prompt()` 和 PDF 的 `SYSTEM_PROMPT` 都让模型自行识别题号、题型及
  题干/解答边界。
- DOCX `build_windows()` 与 PDF `make_windows()` 默认都是 3 页窗口、1 页重叠。
- merge、adapter、assembler 只依赖现有 observation 输出，不要求输入窗口必须重叠。
- DOCX 现有 `DocxWindowObservation` 不含 `needs_review` 或 `build_notes`；
  PDF 的 `notes` 是题级字段。因此索引问题不能塞进现有 observation 顶层而又声称
  contract 完全不变。
- `BailianOcrClient` 当前只有 `complete_json()`；“预扫返回纯文本”不能直接复用
  该入口，必须新增非破坏性的 `complete_text()`，或让预扫返回 JSON 包装。本文选择
  前者。

## 3. 设计边界

### 3.1 本次修改

- 新增独立的预扫索引 contract、构建器、批计划器和 CLI；
- DOCX 删除 OOXML 全文提示，改为按批计划观察；
- PDF 改为按批计划观察，正式转写仍使用 MiMo 以保留 bbox；
- 更新 DOCX/PDF ingestion skill 的固定流程、依赖和失败处理；
- 更新观察层测试和三条端到端 canary。

### 3.2 本次不修改

- `scripts/question_transcription/contracts.py`；
- `docx_observation_contracts.py`、`pdf_observation_contracts.py` 的输出字段；
- merge / adapt / assemble / expand / materialize / audit / review；
- DOCX 图片归属状态机及图片 adapter；
- PDF 正式转写 provider。百炼只用于 PDF 预扫，不新增一个无法提供合规 bbox 的
  PDF 正式转写分支。

## 4. 上游数据模型

新增 `scripts/question_transcription/procedural/question_span_index.py`。模型使用 Pydantic v2
且 `extra="forbid"`。

```python
QuestionRole = Literal["question", "solution"]
QuestionTypeHint = Literal[
    "choice", "fillin", "problem", "short_answer", "unknown"
]
IndexStatus = Literal["ready", "needs_review", "failed"]
IssueSeverity = Literal["warning", "blocking"]


class SourceFingerprint(_Strict):
    source_sha256: str | None
    page_sha256: list[str]
    page_number_offset: int = 0


class SpanIndexIssue(_Strict):
    code: str
    severity: IssueSeverity
    detail: str
    page_number: int | None = None
    question_ref: str | None = None


class IndexedQuestion(_Strict):
    question_ref: str
    question_number: int
    question_pages: list[int]
    solution_pages: list[int]
    question_section_ref: str | None = None
    solution_section_ref: str | None = None
    question_type_hint: QuestionTypeHint = "unknown"
    question_confidence: Literal["high", "medium", "low"] | None = None
    solution_confidence: Literal["high", "medium", "low"] | None = None


class QuestionSpanIndex(_Strict):
    schema: Literal["math_question_span_index/v1"]
    source_kind: Literal["docx", "pdf"]
    page_numbers: list[int]
    fingerprint: SourceFingerprint
    status: IndexStatus
    questions: list[IndexedQuestion]
    issues: list[SpanIndexIssue]
```

索引逻辑上分成题目区索引和答案区索引，并通过 `question_ref` 汇总到同一个
`IndexedQuestion`。例如：

```yaml
- question_ref: "17"
  question_pages: [4]
  solution_pages: [9]
- question_ref: "18"
  question_pages: [4, 5]
  solution_pages: [9, 10]
- question_ref: "19"
  question_pages: [5]
  solution_pages: [10]
```

不得用一个连续的 `start_page/end_page` 覆盖题干和解析。试卷与答案分文件时，每个
来源各建一个索引，未包含的角色页数组为空；两路 observe 仍按相同
`question_ref` 交给现有 merge 汇合。

`question_type_hint` 只是预扫提示，不是正式转写结果。章节标题无法可靠识别时必须为
`unknown`，不得使用“题号小于 7 就是选择题”等地区卷型假设。

## 5. 索引构建

### 5.1 共享锚定流程

1. 按页保留原始文本，不先拼成全卷字符串。
2. 用 `^\s*(\d{1,3})[．.]` 收集行首题号候选；同时记录章节标题、答案/解析标题和
   `解/证明/答` 等角色信号。
3. 将候选分成题目区和答案区，分别建立索引，再在每一段内寻找最长可信递增序列。
   不能直接复制
   `extract_docx_source.py::attribute_images()` 的全或无状态机，因为该状态机会把
   解答内部的编号步骤和后置答案区的题号重启当作噪声。
4. 同一角色内允许多个题号从同一页开始。每题保存显式页面集合；下一题在同页开始时，
   该页可以同时属于两题。
5. 题目页集合只在题目区内展开，答案页集合只在答案区内展开；一个角色段的末题不得
   吞掉后续另一角色段。
6. 章节标题只生成 `question_type_hint`。无法识别时写 `unknown`。
7. 对缺号、重复候选、乱序、低置信角色、OCR 空页和页数不一致生成结构化 issue。

状态门禁：

- `ready`：题号序列和角色区间可确定；
- `needs_review`：仍能构建候选索引，但存在可能造成漏题或错分角色的 blocking issue；
- `failed`：没有可用题号序列、页数错位或来源指纹不完整。

正式 observe 默认只接受 `ready`。人工核对并修正 index 后再运行；可保留显式
`--allow-index-needs-review` 作为诊断入口，但 ingestion skill 不使用该选项。

### 5.2 DOCX

新增 `scripts/question_transcription/procedural/build_docx_span_index.py`：

```bash
./.venv/bin/python scripts/question_transcription/procedural/build_docx_span_index.py \
  --word-source <source-archive>/word/word-source.yaml \
  --output <build>/word.span-index.yaml
```

实现要求：

- 从 `word-source.yaml.rendered_pdf.path` 相对 manifest 所在目录定位
  `rendered.pdf`，不得假定当前工作目录；
- 执行 `pdftotext -layout <rendered.pdf> -`，按 `\f` 分页；
- 校验文本页数与 `rendered_pages`/`pages/*.png` 页数一致；
- `paragraphs` 只用于章节标题和角色的交叉验证，不能再次注入正式视觉 prompt；
- 支持 `--page-number-offset`，保证答案分文件时索引页码与 `discover_pages()` 一致；
- 指纹至少包含 rendered PDF SHA、每页 PNG SHA 和 offset；
- `pdftotext` 不存在、退出非零或页数不一致时写明错误并退出非零。

### 5.3 PDF

修改 `bailian_ocr_client.py`，新增 `complete_text()`：

- 与 `complete_json()` 使用相同的鉴权、超时和原子磁盘缓存机制；
- 缓存键加入任务名、prompt 版本、page SHA 和模型；
- 缓存分别记录 raw text，不经过 `extract_json()`；
- 不改变现有 `complete_json()` 行为。

新增 `scripts/question_transcription/procedural/prescan_pdf_pages.py`：

```bash
./.venv/bin/python scripts/question_transcription/procedural/prescan_pdf_pages.py \
  --manifest <build>/pdf-source.yaml \
  --output-dir <build>/prescan \
  --cache-dir <build>/cache/prescan
```

每页单独调用百炼，只做文字、公式和题号锚的忠实 OCR，不要求 bbox。产物为：

```text
prescan/
  prescan-manifest.yaml   # prompt/model/page SHA/页码/文本文件映射
  page-001.txt
  page-002.txt
```

写文件采用临时文件后原子替换。已存在的 page text 只有在 page SHA、模型和 prompt
版本都匹配时才复用。

新增 `scripts/question_transcription/procedural/build_pdf_span_index.py`：

```bash
./.venv/bin/python scripts/question_transcription/procedural/build_pdf_span_index.py \
  --prescan <build>/prescan/prescan-manifest.yaml \
  --output <build>/pdf.span-index.yaml
```

构建器必须从 prescan manifest 读取显式页码，不能依赖文件名字符串排序。

## 6. 确定性批计划

在 `question_span_index.py` 中新增：

```python
class ObservationBatch(_Strict):
    batch_id: str
    role: QuestionRole
    page_numbers: list[int]
    expected_question_refs: list[str]
    section_refs: list[str]
    oversized: bool = False


def build_observation_batches(
    index: QuestionSpanIndex,
    *,
    target_page_count: int = 6,
    hard_page_limit: int = 8,
    target_question_count: int = 12,
) -> list[ObservationBatch]: ...
```

规则：

1. 题目区和答案区分别计算、分别装批，绝不放入同一正式批次。
2. 对每个角色的题目页集合建立连通关系：一道题跨越的页面不可拆；题目共享页面时，
   它们及相关页面归入同一个连续连通分量。该分量就是“不可拆页面块”。
3. 例如 Q17 只在第 4 页、Q18 在第 4–5 页、Q19 只在第 5 页，则三题形成同一个
   `pages=[4,5]`、`expected=[17,18,19]` 的不可拆块。
4. 按页码顺序将相邻不可拆块贪心装批。加入一个完整块后，达到 6 页或约 12 题时
   优先封批；章节切换处优先在加入新章节块之前封批。
5. 加入下一个块会超过 8 页时，先封当前批。单个不可拆块自身超过 8 页时允许单独
   生成 `oversized=true` 特殊批次并记录 warning；不得为满足限制拆开跨页题。
6. 12 题是输出长度控制目标而不是硬门槛。一个不可拆块或最后加入的完整块可以使批次
   略超 12 题，例如 4 页 14 道选择题；加入后立即封批。
7. 前言、封面等不属于任何题目的页不进入正式题目观察；它们仍保留在 source
   manifest 中供审计。

首轮正式批次之间页面交集必须为空，因此每页首轮只读一次。不再需要“发现跨页后自动
补读下一页”；只有集合校验失败时，才允许对缺失/重复题涉及的页面做定点补读。

## 7. 正式观察改造

### 7.1 共同约束

DOCX/PDF observe 都新增必需参数 `--span-index`，启动时先验证：

- index schema 与 source kind；
- index 状态为 `ready`；
- page numbers、page SHA、source SHA 和 offset 与当前输入一致；
- 批次页面存在且无重复；
- 每个角色的每道题都被且只被一个首轮批次覆盖；
- question batch 不包含 solution-only 页面，solution batch 不包含 question-only
  页面。

每批 prompt 必须包含：

- 本批图片与真实 `page_number` 映射；
- 精确的预期题号集合；
- 本批统一角色以及每个题号的角色内页面集合；
- “只返回预期题号；不得创建、合并、借用其他题号”的明确约束。

provider 返回后、Pydantic observation 校验前，计算：

```python
missing = expected_refs - returned_refs
unexpected = returned_refs - expected_refs
duplicate = {ref for ref, count in counts.items() if count > 1}
```

处理规则：

1. 三个集合都为空时，生成正常 observation。
2. `expected` 中恰好返回一次、题号一致且通过 contract 校验的正常题，冻结到该批的
   repair workspace，后续补读不得覆盖它。
3. `missing`：仅用索引中该题的角色内页面集合发起定点补读；prompt 的 expected
   只包含缺失题。
4. `unexpected`：隔离原始 payload，不进入候选池，不自动改写成某个 expected 题号。
5. `duplicate`：隔离该题的多个 payload，定点重读该题；达到重试上限后转 blocking
   人工审核，不能由代码随意选一个。
6. `question_number` 与 `question_ref` 不一致按 duplicate/invalid candidate 处理。
7. 默认每题最多一次自动定点补读；可通过显式 CLI 调整，但必须设置有限上限，禁止
   无限重试。
8. 只有所有 expected 题都恰好得到一个有效冻结结果后，才把冻结结果组装为最终批次
   observation。修复前不得生成可被 merge glob 匹配的正常文件。

repair workspace 至少保存首轮 raw response、集合差异、已冻结题号、补读历史和最终
状态，且不得写 API key。这样既保证“先索引”是强边界，也不因一个漏题而重跑整批。

### 7.2 DOCX

修改 `observe_docx_pages.py`：

- 删除 `_paragraph_hint()` 及 prompt 中的 OOXML 全文；
- 用 `build_observation_batches()` 替换 `build_windows()`；
- prompt 按批次角色允许局部内容：
  - `question` 批只要求可见题干；
  - `solution` 批只要求可见官方解答；
- 保留 `PartialQuestionContent` / `PartialQuestionEvidence`，因为试卷与答案分文件的
  合法流程仍需要 merge 拼接，不能笼统要求每批都含完整题干和完整解答；
- 缓存键加入 span-index 指纹、batch plan、expected refs 和新 prompt version；
- 百炼 DOCX 正式降级路径目前只支持单页 native JSON。若批次多页，必须明确报
  unsupported，或先实现多题多页标准 JSON；不能沿用现有 normalize 后假装支持。

CLI 迁移：

- 新增 `--target-batch-pages`（默认 6）、`--max-batch-pages`（默认 8）和
  `--target-batch-questions`（默认 12）；
- `--window-size`、`--overlap` 保留一个迁移周期并打印 deprecation；
- 旧参数不参与窗口构造。为避免误以为重叠仍有效，显式传
  `--overlap` 非 0 时直接报错。

### 7.3 PDF

修改 `observe_pdf_pages.py`：

- `make_windows()` 改为从 span index 生成批次；
- 将 `SYSTEM_PROMPT` 拆为稳定的系统约束和每批动态 user prompt；
- cache material 加入 index/batch/expected refs；
- 继续使用 MiMo 做正式联合转写和 bbox；
- 不移植 DOCX 的百炼正式 provider 分支，因为当前百炼响应不能满足
  `RegionEvidence`/figure bbox contract。

PDF 的 `content=null` 容忍仍保留给只出现题干或只出现解答的页段；是否满足公开
`QuestionContent` 由现有 merge/adapter gate 处理。

## 8. 文件改动矩阵

### 新增

- `scripts/question_transcription/procedural/question_span_index.py`
- `scripts/question_transcription/procedural/build_docx_span_index.py`
- `scripts/question_transcription/procedural/prescan_pdf_pages.py`
- `scripts/question_transcription/procedural/build_pdf_span_index.py`
- `tests/question_transcription/test_question_span_index.py`
- `tests/question_transcription/test_pdf_prescan.py`

### 修改

- `scripts/question_transcription/bailian_ocr_client.py`
- `scripts/question_transcription/procedural/observe_docx_pages.py`
- `scripts/question_transcription/procedural/observe_pdf_pages.py`
- `tests/question_transcription/test_docx_observation.py`
- `tests/question_transcription/test_pdf_observation.py`
- `.codex/skills/math-docx-question-bank-ingestion/SKILL.md`
- `.codex/skills/math-pdf-question-bank-ingestion/SKILL.md`

不预先写“5 个新文件 + 2 个改写”这类易失计数；以本矩阵和最终 diff 为准。

## 9. Skill 流程更新

### 9.1 DOCX

在 extract 后新增索引步骤。试卷与答案分文件时分别建索引，并使用相同 offset 规则：

```bash
./.venv/bin/python scripts/question_transcription/procedural/build_docx_span_index.py \
  --word-source <source-archive>/word/word-source.yaml \
  --output <build>/word.span-index.yaml

./.venv/bin/python scripts/question_transcription/procedural/observe_docx_pages.py \
  --word-source <source-archive>/word/word-source.yaml \
  --span-index <build>/word.span-index.yaml \
  --source-archive <source-archive> \
  --mimo --cache-dir <build>/cache --output-dir <build>/windows
```

答案文件的 build/observe 都传同一个 `--page-number-offset <exam-page-count>`。

依赖表新增：

| 工具 | 用途 | 必需 |
|---|---|---|
| `pdftotext`（Poppler） | DOCX rendered PDF 的逐页题号预扫 | 是 |

### 9.2 PDF

在 manifest 后、正式 observe 前插入：

```bash
./.venv/bin/python scripts/question_transcription/procedural/prescan_pdf_pages.py \
  --manifest <build>/pdf-source.yaml \
  --output-dir <build>/prescan \
  --cache-dir <build>/cache/prescan

./.venv/bin/python scripts/question_transcription/procedural/build_pdf_span_index.py \
  --prescan <build>/prescan/prescan-manifest.yaml \
  --output <build>/pdf.span-index.yaml

./.venv/bin/python scripts/question_transcription/procedural/observe_pdf_pages.py \
  --manifest <build>/pdf-source.yaml \
  --span-index <build>/pdf.span-index.yaml \
  --paper-meta <build>/paper-meta.yaml \
  --cache-dir <build>/cache --output-dir <build>/windows
```

Skill 必须写明：百炼用于逐页索引预扫；MiMo 用于正式文字+bbox 联合观察。

## 10. 测试与验收

### 10.1 单元测试

`test_question_span_index.py`：

- 正常递增题号；
- 行首空白和全角/半角点；
- 考生须知编号不被识别为正式题目；
- 选择/填空/解答章节识别；
- 未知题型保持 `unknown`，不套题号阈值；
- 同页开始两题时页面集合合法；
- 跨页题；
- 后置答案区题号从 1 重启并写入独立 `solution_pages`；
- 解答内部 `1．/2．` 步骤不被识别为新题；
- 缺号、乱序、重复候选产生 issue 和正确 status；
- OCR 空页、页数不一致和 source 指纹错误；
- `page_number_offset`；
- Q17@P4、Q18@P4–5、Q19@P5 合成同一个不可拆页面块；
- 6 页/12 题目标触发封批，章节切换优先封批；
- 加入下一块超过 8 页时先封批；
- 首轮批次默认无重复页、不拆题目页面集合；
- 超过 8 页生成 oversized batch；
- 每个角色的每道题恰好被一个首轮批次覆盖；
- question/solution 页面块从不进入同一批。

`test_pdf_prescan.py`：

- `complete_text()` 不走 JSON 提取；
- cache hit 不重复调用 provider；
- cache key 随 page SHA/prompt/model 改变；
- prescan manifest 与 page text 原子落盘；
- 非连续或错位页码被拒绝。

观察测试：

- prompt 不再包含 OOXML 全文；
- prompt 含预期题号、角色、页码映射；
- 返回集合精确匹配时通过；
- 漏报只定点补读缺失题页面，已通过题保持冻结且不被再次调用；
- 多报题被隔离，不进入最终 observation；
- 重复题只定点补读该题，超过重试上限产生 blocking 状态；
- 修复完成前不生成正常 observation，完成后组装结果可被现有 merge 消费；
- span index 指纹过期时在 provider 调用前失败；
- DOCX question-only/solution-only 分批仍能由现有 merge 拼成完整题；
- PDF bbox 转换、figure gate 和 adapter 回归保持不变；
- 旧 `--overlap 1` 明确报错，不能静默恢复重叠。

### 10.2 测试命令

```bash
./.venv/bin/python -m pytest \
  tests/question_transcription/test_question_span_index.py \
  tests/question_transcription/test_pdf_prescan.py \
  tests/question_transcription/test_docx_observation.py \
  tests/question_transcription/test_pdf_observation.py -q

./.venv/bin/python -m pytest tests/question_transcription/ -q
```

### 10.3 端到端 canary

至少覆盖三种来源形态：

1. 已知发生 DOCX 串线的 interleaved 卷；
2. 试卷与答案分文件，或题目后置整卷答案的 separated 卷。

PDF 再选一卷含跨页题和独立题图的 canary，验证 bbox/裁图链路未退化。

每卷记录：

- index status、题号列表、question/solution 页面集合、issue 数；
- 不可拆页面块数、batch 数、每批角色/页码/题数、是否有首轮重复页、oversized 数；
- provider 首轮及定点补读的返回题号集合；
- missing/unexpected/duplicate、冻结复用数和定点补读次数；
- merge issue/conflict 数；
- adapter 是否无需修改即可消费；
- structural audit 结果；
- 与旧流程比较的 API 调用次数和总输入页数。

验收门槛：

- 新流程没有题号串线；
- 修复后的每个批次都满足 `actual_refs == expected_refs`；
- 同一角色的首轮正式批次间页面交集为空；
- 题目区和答案区没有混批；
- 集合异常只触发定点补读，正常题没有随整批重跑；
- 索引题数与最终 transcription 题数一致；
- 两种 separated 布局的题干/解答均未丢失；
- PDF bbox 和图片 adapter 回归通过；
- 全套 `tests/question_transcription/` 通过。

## 11. 实施顺序

1. 先实现 index contract、锚定算法、status/issue 和批计划器及单测；
2. 为百炼客户端增加 `complete_text()`，实现 PDF prescan 和缓存测试；
3. 实现 DOCX/PDF 两个 index CLI，完成指纹与页数校验；
4. 改 DOCX observe：删除全文 hint、接入批计划、实现冻结与定点补读；
5. 改 PDF observe：接入批计划、动态预期题号、实现冻结与定点补读并保持 MiMo+bbox；
6. 跑观察层测试，再跑完整 `tests/question_transcription/`；
7. 更新两个 SKILL.md；
8. 跑 DOCX interleaved、DOCX separated、PDF 三条 canary；
9. 将 canary 结果补入 PR/提交说明后再移除旧窗口帮助文案。

## 12. 回滚与提交

- 代码回滚单位是 observation/index 改造提交；索引和 prescan 都是 build 产物，不写入
  staging 或正式题库。
- 回滚不需要迁移下游 YAML，因为 observation 和公开 bundle contract 未改变。
- 所有代码、测试、skill 和本文档使用 `[workflow]` 提交。
- 若 canary 需要生成 `artifacts/` 结果，另用 `[artifacts]` 提交，不与 workflow
  改动混合。

## 13. 完成状态与验证记录（2026-07-29）

`question-span-index-redesign` 已完成。DOCX/PDF 正式观察 CLI 现在强制要求
`--span-index`；旧滑窗函数仅作为库内兼容面保留，命令行不能再绕过 index。非零
`--overlap` 明确失败。首轮批次按角色和不可拆页面块规划，返回集合异常时冻结正确题，
repair 只发送未解决题的索引页。

实现期间同时修复了 MiMo v2.5 + PydanticAI 结构化调用的媒体适配问题：旧 adapter 把
OpenAI 风格 message dict 直接传给 `Agent.run()`，PydanticAI 没有把其中的图片解释为
多模态输入；现在统一使用 `BinaryContent`，并由 `ToolOutput` + Pydantic contract
验证最终结果。安全合成图 A/B 验证中，旧路径返回图片缺失，新路径正确读取验证码
`7319`。这说明此前观察到的主要问题是 adapter 丢图，而不是 MiMo tool calling 本身
无法处理图片。

验证结果：

- 指定观察/索引测试：99 项通过；
- 完整 `tests/question_transcription/`：246 项通过；
- DOCX interleaved 实卷离线 index canary：`ready`，25 题，0 issue，6 个 question
  batch，无 oversized；
- DOCX separated 实卷重新提取后：试卷 index `ready`，25 题，2 个 warning，2 个
  question batch；答案 index `ready`，25 题，0 issue，2 个 solution batch；
- 旧 separated 页面目录存在 rendered PDF 8 页但 PNG 17 页的陈旧状态，现会在
  provider 调用前被页数/指纹门禁拒绝；
- DOCX 安全合成 live canary：2 个批次、2/2 题准确返回（选择题答案 B、填空题答案
  7），证明 PydanticAI + MiMo 多模态结构化路径端到端可用；
- PDF 安全合成 live canary：1 道题跨 2 页，文字、两页 evidence 与独立矩形题图均
  返回；图框换算为像素坐标 `[252, 280, 1148, 720]`，0 repair；
- PDF canary 还发现并修复 MiMo 将无 whiteout 表示为扁平 `[0,0,0,0]`、空章节字段
  及单字符串 notes 的非语义 shape drift；真正缺题、重复题、越界 bbox 和陈旧指纹
  仍保持 blocking。

为避免把真实试卷内容发送到外部 provider，实卷 canary 只验证本地 index/batch 计划；
live provider 验证使用无真实数据的合成页面。所有正式内容契约、merge 和 adapter
回归均由完整测试集覆盖。
