# 任务：修复 needs_review 配图被丢弃、review UI 无法确认的问题

## 工作位置

worktree：`/Users/gaochong/develop/teaching_skills/.codex/worktrees/langgraph-question-ingestion/teaching_skills`
branch：`codex/langgraph-question-ingestion-design`
运行环境：`./.venv/bin/python`（通用工具）；加载 API 密钥用 `source ~/.zshrc 2>/dev/null`。

## 问题本质

`needs_review` 是一个**空头支票状态**：image attribution 标了它，但没有任何下游真正消费它——projector 直接丢弃，review UI 根本不显示。结果：docx 源几何题的配图（OOXML 段落结构确定性绑定的，只是题干没写"如图"）大批丢失，audit 报"如图但无 prompt crop"。

**正确的设计意图**（用户明确）：`needs_review` 的图应该**进 staging（带提示标记），在 review UI 里显示出来让人确认**，而不是被静默丢弃。

## 根因链条（已验证，文件:行号）

### 1. extract_docx_source 给 prompt 图定 medium confidence
`.codex/skills/math-docx-question-bank-ingestion/scripts/extract_docx_source.py`，`_classify_images`（~line 167）：
- `high`：图在题目区域内 + 题干有配图声明（"如图""见图"）。
- `medium`：图在题目区域内（OOXML 段落绑定），但题干没配图声明词。**归因本身是确定性的（图嵌在哪个段落→段落属于哪道题），不是模型推测。**
- `low`：跨多段/题号不清。

### 2. adapt_docx_images 把 medium 映射成 needs_review
`scripts/question_transcription/adapt_docx_images.py:52-54`：
```python
CONFIDENCE_TO_STATE = {
    "high": "accepted",
    "medium": "needs_review",
    "low": "needs_review",
}
```

### 3. projector 只取 accepted，needs_review 全丢  ← 核心 bug
`scripts/question_transcription/project_source_paper.py:186`，`project_image_bundle`：
```python
accepted = [attr for attr in source.attributions if attr.state == "accepted"]
```
needs_review 的 attribution 被直接过滤，不进 staging draft，不进 review UI。

### 4. review server 只读 final staging 的 crops.prompt，无 needs_review/confidence 概念
`.codex/skills/math-topic-question-bank/scripts/question_bank_review_server.py`，`_crop_previews`（~line 993）：读 `crops.prompt[].output`（裁切图路径）显示预览。如果 crops.prompt 为空，图完全不可见。server 全文无 `confidence`/`needs_review`/`review_flag`/`warning` 字段。

### 结果
needs_review 的图：projector 丢 → staging 无 prompt crop → review UI 不显示 → 人工无从确认 → audit 拦"如图无图"。整个 needs_review 机制形同虚设。

## 验证数据（worktree build 语料可查）

- `build/question-ingestion/2012-PUTUO-ERMO/run-1b2e1215151d/structured/image-attribution.yaml`：174 attribution，prompt role 的 28 个全是 `confidence=medium, state=needs_review, provider.kind=docx_structure`，paragraph_index 明确。
- 同卷 staging `items/Q*/source.yaml` 的 `crops.prompt` 全为空。
- 成功卷也大量 medium（某 B 类卷 prompt attrs=26, needs_review=23, accepted=3，只有 3 个 item 有 prompt crop）。
- 全仓库 docx 源卷都受系统性影响。

## 需要做的（agent 验证 + 实现 + 回归）

### 设计决策（agent 验证后定，但范围有限）

`needs_review` 的图必须能进 review UI 让人确认。具体怎么进有两种路线：

- **路线 A**：projector 不再过滤 needs_review，把它们也 project 进 draft（带标记），让图进 staging → review server 读到 crops.prompt 自然显示。需要某种方式把"这张图待确认"的提示带到 review UI（比如 staging item 上加 `review_flags` / `pending_attribution` 字段，review server 展示）。
- **路线 B**：在 projector 里把 docx_structure 的 medium 提升为 accepted（因为 OOXML 段落绑定是确定性的，配图声明词缺失不等于归因不可靠），low 仍丢。更简单，但不解决 needs_review 机制本身的设计缺陷（low 的图、未来其他 provider 的 needs_review 图还是没出路）。

**优先验证路线 A**（修复设计缺陷），如果工程量过大再退回路线 B。但必须：
- low confidence 归因的处理要明确（要么也能进 review UI 标注，要么明确文档说明为何丢弃）。
- 不破坏已 accepted 的归因路径。

### 验证步骤

1. 确认 review server 的 item record 结构（`build/.../structured/items/Q*/` 下哪些文件），找到 crops.prompt 之外能携带"待确认图"提示的字段位置。
2. 抽样 medium 的 docx_structure prompt 归因，确认 OOXML 段落绑定的可靠性（paragraph_index 与题目边界对齐）。
3. 确认 review server 前端怎么渲染 item（是否有展示 warning/flag 的现有机制，或需新增）。

### 实现

根据验证结果，改 projector（让 needs_review 图进 staging）+ review server（显示待确认提示）。核心改动大概率在：
- `scripts/question_transcription/project_source_paper.py` 的 `project_image_bundle`
- `scripts/question_transcription/assemble_paper_draft.py`（prompt crops 怎么写进 draft item）
- `.codex/skills/math-topic-question-bank/scripts/question_bank_review_server.py`（读 + 展示待确认图）
- 可能涉及 `scripts/question_transcription/source_contracts.py`（如果要在 staging item 上加 review_flag 字段）

### 回归要求

1. **新增测试**：
   - medium 的 docx_structure prompt 归因经过 project 后**出现在 staging 的 prompt crops 里**（带待确认标记）。
   - review server 能读到并展示这张待确认图（如有 server 级测试）。
   - low 归因行为明确（按验证结论）。
   - 已 accepted 归因不受影响。

2. **现有测试全绿**：
   ```
   ./.venv/bin/python -m pytest tests/question_transcription/workflow/ -q
   ./.venv/bin/python -m pytest tests/test_question_bank_review*.py -q 2>/dev/null
   ```

3. **真实语料回归**（build 是 gitignored，只看行为）：
   - 选 2-3 卷之前因"如图无图"blocked 的 E 类卷，重跑下游确认 prompt crop 出现 + audit 通过：
     ```
     source ~/.zshrc 2>/dev/null
     PYTHONPATH=. ./.venv/bin/python scripts/question_transcription/workflow/cli/resume_from_barrier.py --apply --paper-id <PAPER> --page-provider mimo
     ```
   - 选 2-3 卷之前成功的卷，`--verify` 仍 VERIFIED：
     ```
     PYTHONPATH=. ./.venv/bin/python scripts/question_transcription/workflow/cli/recover_failed_runs.py --classes A,B,C --verify --paper-id <PAPER>
     ```

## 约束

- review server 在 `.codex/skills/math-topic-question-bank/scripts/`（skill 脚本），改完确认 workflow adapter import 不受影响。
- `extract_docx_source.py` 在 `.codex/skills/math-docx-question-bank-ingestion/scripts/`。
- 提交用 `[workflow]` 类别（AGENTS.md），commit message 说明改了什么 + 为什么。
- build 产物 gitignored，不提交。
- **不要碰**那条未提交的 `audit_staging.py` "如图"规则改动（`.codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py` 的 working-tree 修改）——那是独立工作。
- `test_pdf_question_bank_ingestion.py` 和 `AGENTS.md` 的未提交改动也不是本任务范围。
