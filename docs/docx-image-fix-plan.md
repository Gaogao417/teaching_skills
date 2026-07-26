# ERMO 试卷图片归属修复计划（供多模态模型执行）

> 执行者：多模态模型（负责"看图"判断）
> 数据来源：段落流脚本 + SHA-256 内容比对，已生成结构化待办清单
> 待办清单：`artifacts/题库/2026-07-24-上海初三试卷原题库/staging/_image_audit_todo.json`
> 涉及范围：16 个 ERMO 区，共 **132 题**待人工核对

---

## 背景与分工

这批上海初三二模试卷从 DOCX 入题库时，图片归属靠"看 PDF 渲染页肉眼判断"，导致大量图错配/漏配。本计划用段落流脚本重新计算了每题"应该有哪些 prompt 图"，与 staging 现状做 **SHA-256 内容比对**（不受文件名版本影响），找出 132 处不一致，交给多模态模型做最终的内容确认。

**两层分工（重要）：**
- **段落流已确定**：每张图属于哪道题、是题干(stem)还是解答(solution)——这是 OOXML 结构数据，不需要看图。
- **需要多模态确认**：脚本算出的图，内容上是否真的对应该题题干（例如题干说"圆与角相切"，图里画的应该是几何图而不是统计图）。**只有多模态能做这步。**

---

## 待办清单结构

每条待办（`_image_audit_todo.json`）包含一个不一致题，字段含义：

```jsonc
{
  "2026-XUHUI-ERMO": {           // paper_id
    "source_dir": "documents/初三/2026届-上海市徐汇区-初三二模数学-试卷及解析",
    "paper_dir": "artifacts/题库/.../2026-XUHUI-ERMO",
    "items": [
      {
        "q": 5,                  // 题号
        "stem": "某学校组织了一场体能测试...",  // 题干文字（交叉验证用）
        "script_prompt_files": ["image51.png"],  // 段落流算出该题prompt该有的图
        "staging_prompt_files": ["image13.png"], // staging当前录的图
        "missing_in_staging": ["image51.png"],   // staging漏的（高置信）
        "extra_in_staging": ["image13.png"],     // staging多挂的（可能错配）
        "script_prompt_meta": [{"file":"image51.png","w":...,"h":...}]  // 像素尺寸
      }
    ]
  }
}
```

判断 `missing_in_staging` 和 `extra_in_staging` 是**两类不同的活**：
- **missing（漏图）**：段落流确认题干含图、staging 没录。**多数情况是真漏了，需补。** 多模态只需抽查内容是否对题，对就补。
- **extra（多挂）**：staging 录了图但段落流没算进该题 prompt。**可能是错配（图属于别的题）或被正确归到 solution 区。** 需多模态判断这张图是该删、该留作 prompt、还是该移到 solution。

---

## 工作流程（逐题）

对清单中的每一条，执行 4 步：

### 步骤 1：读取该题上下文

```bash
# 题干文字（已在 JSON 的 stem 字段，可直接读）
# 该题所在 PDF 页（看真实版面）：
#   <source_dir>/word/pages/<page>.png
# 页码在 paper.draft.yaml 的 question_word_evidence.page_number
```

### 步骤 2：看图，判断三类归属

需要看的图（都在 `<source_dir>/word/media/`）：
- `script_prompt_files` 里的每张图（段落流说该是题干图）
- `staging_prompt_files` 里的每张图（staging 当前挂的图）

对每张图，看它的内容，对照题干文字，归入三类之一：

| 图的内容 | 归类 | 动作 |
|---------|------|------|
| 画的就是题干描述的东西（如图形的几何图、"如图"指的对象、统计图等） | **prompt** | 确认/补入 `crops.prompt` |
| 是该题解答过程里的辅助图/分析图 | **solution** | 移入 `crops.solution`（或 `official_solution`） |
| 与该题无关（属于别的题或装饰图） | **不属于** | 从该题删除引用 |

**关键判断标准**：题干里出现"如图""图N""下图""图中"等词，就该有对应数量的 prompt 图；题干没提图，却挂了图，多半是错配或 solution 图误挂。

### 步骤 3：修改 `paper.draft.yaml`

修改文件：`<paper_dir>/paper.draft.yaml`（**只改这个文件**，source.yaml 和 assets/ 由后续脚本自动生成）。

在对应题号的 `items[].prompt` 字段下增删条目。prompt 条目格式：

```yaml
prompt:
  - source: documents/初三/2026届-上海市徐汇区-初三二模数学-试卷及解析/word/media/image51.png
    box_px: [0, 0, 1633, 2740]   # 整图：[0, 0, 图宽, 图高]，像素尺寸见 JSON 的 script_prompt_meta
    width: 120mm                  # 可选，渲染宽度
```

- `box_px` 用完整图范围 `[0, 0, width, height]`（Word 媒体原图直接整张用，不裁切）
- 像素尺寸从 JSON 的 `script_prompt_meta` 取，或用 PIL 读：`from PIL import Image; print(Image.open(path).size)`
- 一题多张 prompt 图就加多条，顺序按题干"如图1/图2/图3"出现顺序
- 移到 solution 的图，加到 `official_solution` 字段（如果存在）或新建 `block.solution_steps` 旁的图引用——**优先按该区现有 staging 的写法保持一致**

### 步骤 4：重跑流水线 + 自检

改完一个区（或一批题）后，在该 paper 目录重跑三个脚本：

```bash
cd /Users/gaochong/develop/teaching_skills

# 1. 展开 draft → source.yaml（重新生成每题 source.yaml）
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py \
  artifacts/题库/2026-07-24-上海初三试卷原题库/staging/<PAPER_ID>/paper.draft.yaml

# 2. 物化（拷图到 assets/，计算 sha256）
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/materialize_staging.py \
  artifacts/题库/2026-07-24-上海初三试卷原题库/staging/<PAPER_ID> --repo-root .

# 3. 审计（检查图是否齐全、有无错配告警）
./.venv/bin/python \
  .codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py \
  artifacts/题库/2026-07-24-上海初三试卷原题库/staging/<PAPER_ID> --repo-root .
```

审计通过（无 error）即该区完成。

---

## 已知风险与处理

### 风险 1：段落流切片偏差（小问级图）
脚本目前按题号切片，不细分小问。Q25 这类多小问题，题干"（1）如图1…（2）如图2…"，第二张图可能在脚本里被判到 solution 区。
**处理**：遇到 `script_prompt_files` 为空但 `staging_prompt_files` 有图的题（清单里标 `extra` 无 `missing`），**优先怀疑脚本误判**，看 PDF 页确认该图是不是该小问的 prompt，不要盲删 staging 的图。

### 风险 2：多选项题（如 Q2 四个图书馆标志）
段落流能识别"该题 prompt 含 N 张图"，但这 N 张是 4 个独立选项还是 1 张合成图，脚本不知道。
**处理**：看图——如果是 4 张独立的选项图，全部挂 prompt（4 条）；如果是 1 张含 4 子图的合成图，挂 1 条。

### 风险 3：题图是照片/情境图（非几何图）
如宝山 Q24 矿车隧道题、统计题的扇形/条形图，这些不是几何图但确实是 prompt。
**处理**：只要题干"如图/下图"指代的就是这张图，就是 prompt，不论图的内容类型。

### 风险 4：文件名版本错位（已用 SHA 消除大部分）
部分区的 `word/media/` 是旧脚本产物，文件名编号可能与 draft 引用的不一致。
**处理**：JSON 里的判断已基于 SHA-256 内容比对，不受文件名影响。但**修改 draft 时引用的文件路径，必须用当前 `word/media/` 里实际存在的文件**——先用 SHA 反查文件名：

```python
import hashlib, json
from pathlib import Path
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""): h.update(c)
    return h.hexdigest()
# 在 word/media/ 里找匹配某个 sha 的文件
```

---

## 完成标准（Definition of Done）

每个区做完后：
1. ✅ 清单中该区的所有条目都已处理（补漏、删错、移 solution）
2. ✅ `paper.draft.yaml` 是唯一改动源
3. ✅ `expand` + `materialize` + `audit` 三脚本全过，audit 无 error
4. ✅ 抽查 3 题：在 review UI 里打开，prompt 图与题干描述内容一致

全部 16 区完成后，可选：跑一次全量 SHA 复检，确认 `missing_in_staging` 归零。

---

## 建议执行顺序

按"漏图多 + 难度低"优先：
1. **青浦**（19 题，漏图最严重，多为纯漏图好判断）
2. **虹口**（12 题）
3. **浦东**（9 题，全是漏图型）
4. **静安**（9 题）
5. **徐汇**（10 题，已知 Q2 四选项图、Q5/Q6 错配，可作为校准样本先做）
6. 其余各区

每个区改完立即跑三脚本自检，**不要攒着一起改**——单区出错容易定位。

---

## 附：字段速查

**draft 里一题的完整结构（改 prompt 只动这里）：**
```yaml
- item_id: Q005
  question_number: 5
  question_type: choice
  question_word_evidence:
    - page_image: documents/初三/.../word/pages/004.png
      page_number: 4
  prompt:                          # ← 改这个
    - source: documents/初三/.../word/media/image51.png
      box_px: [0, 0, 1633, 2740]
  official_solution:
    word_evidence:
      - page_image: documents/初三/.../word/pages/005.png
        page_number: 5
  block:
    stem_latex: ...
    answer: ...
    solution_steps: [...]
```

**媒体原图路径模板：**
`<source_dir>/word/media/imageN.png`（N 见 JSON 的 `script_prompt_files`）

**PDF 渲染页路径模板：**
`<source_dir>/word/pages/NNN.png`（页码见 draft 的 `question_word_evidence[].page_number`）
