# 转写可疑项审核契约

本契约定义转写流程中的两个 paper 级 sidecar：`review-issues.yaml` 记录所有需要人工
裁决的可疑字段及其全部候选；`review-resolutions.yaml` 记录每条 issue 的裁决决定。它们
是 DOCX/PDF 两条 ingestion 线共享的「隔离审核 staging」数据来源。契约实现位于
`scripts/question_transcription/review_issue_contracts.py`，schema 版本分别为
`math_transcription_review_issues/v1` 与 `math_transcription_review_resolutions/v1`。

`review-issues.yaml` 与 `review-resolutions.yaml` 放在隔离审核 staging 的根目录。无冲突
的试卷不写 sidecar；没有 sidecar 的历史 staging 按现有流程处理，保持兼容。

## 目录

- [review-issues.yaml 示例](#review-issuesyaml-示例)
- [review-resolutions.yaml 示例](#review-resolutionsyaml-示例)
- [严重度与规范 code](#严重度与规范-code)
- [数学敏感差异标记](#数学敏感差异标记)
- [候选集合哈希与失效](#候选集合哈希与失效)

## review-issues.yaml 示例

```yaml
schema: math_transcription_review_issues/v1
paper_id: 2024-BAOSHAN-ERMO
generated_at: 2026-07-28T12:00:00
issues:
  - issue_id: Q015-answer-sign
    question_ref: "15"
    question_number: 15
    code: answer_conflict
    severity: blocking
    field_path: answer
    math_token: sign
    origin: merge
    candidates:
      - window_id: docx-window-03
        raw_value: "$3$"
        normalized_value: "3"
        confidence: high
        evidence:
          - kind: page
            source: documents/初三/PAPER-2026/word/pages/004.png
            page_number: 4
      - window_id: docx-window-04
        raw_value: "$-3$"
        normalized_value: "-3"
        confidence: medium
        selected: true
        evidence:
          - kind: page
            source: documents/初三/PAPER-2026/word/pages/005.png
            page_number: 5
    candidates_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
    detail: 正负号冲突：两个重叠窗口分别读到 $3$ 与 $-3$，暂选低置信度窗口的 $-3$ 待人工确认。
  - issue_id: Q018-stem-baseline
    question_ref: "18"
    question_number: 18
    item_id: Q018
    code: existing_staging_stem_mismatch
    severity: blocking
    field_path: stem_latex
    origin: baseline_compare
    baseline_paper_id: 2024-BAOSHAN-ERMO-PREV
    baseline_value: 如图，在$\triangle ABC$中……
    candidates:
      - window_id: pdf-region-12
        raw_value: 如图，在$\triangle AB C$中……
        normalized_value: 如图，在$\triangle ABC$中……
        confidence: high
        selected: true
        evidence:
          - kind: region
            source: documents/初三/PAPER-2026/005.png
            page_number: 5
            box_px: [80, 210, 1010, 860]
      - window_id: baseline:2024-BAOSHAN-ERMO-PREV
        raw_value: 如图，在$\triangle ABC$中……
        normalized_value: 如图，在$\triangle ABC$中……
        confidence: medium
        evidence:
          - kind: page
            source: documents/初三/PAPER-OLD/word/pages/005.png
            page_number: 5
    candidates_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
    detail: 与既有 staging 题干指纹不一致，请人工确认是否盲跑错配。
```

规则：

- `issues` 每条对应一个可疑字段；`issue_id` 在 paper 内唯一。
- `question_ref` 是与转写管线共用的稳定 join key（源本地十进制题号字符串）；
  `item_id` 仅在物化进 staging 时盖印为 `Q0xx`，可缺省。
- 每条 `candidates` 至少 2 个；baseline 比较也必须把旧基线作为
  `window_id: baseline:<paper-id>` 的候选写入，少于 2 个不构成冲突。
- 每个候选必须带至少一条 `evidence`，`kind` 为 `page`（整页）或 `region`（带 `box_px`）。
- 每条 issue 恰有一个 `selected: true` 的候选作为暂选；零个或多个都被拒绝。
- 同一 issue 内候选的 `window_id` 必须唯一（重复候选拒绝）。
- `candidates_hash` 必须等于 `compute_candidates_hash(candidates)`（见下节）。
- `origin: baseline_compare` 时 `baseline_paper_id` 必填；`baseline_value` 仅供比较，
  Review UI 必须标注「不代表正确」。

## review-resolutions.yaml 示例

```yaml
schema: math_transcription_review_resolutions/v1
paper_id: 2024-BAOSHAN-ERMO
resolutions:
  - issue_id: Q015-answer-sign
    decision: accept_candidate
    accepted_window_id: docx-window-04
    resolved_candidates_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
    reviewer: question-bank-review-ui
    resolved_at: 2026-07-28T12:05:00
    note: 核对原卷第 5 页，答案为 $-3$，采用 docx-window-04。
  - issue_id: Q018-stem-baseline
    decision: manual
    manual_value: 如图，在$\triangle ABC$中……
    resolved_candidates_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
    reviewer: gaochong
    resolved_at: 2026-07-28T12:10:00
```

规则：

- 每条 resolution 对应一个 `issue_id`；`issue_id` 唯一。
- `decision`：
  - `accept_candidate`：必须填 `accepted_window_id`，且该 id 必须存在于对应 issue 的候选中。
  - `manual`：必须填 `manual_value`。
  - `accept_baseline`：直接采用旧基线值（仍需后续逐题最终审核确认）。
- `resolved_candidates_hash` 必须等于裁决时对应 issue 的 `candidates_hash`。候选或来源
  变化后哈希不一致，旧 resolution 自动失效（staleness）。
- 候选、来源、图片或文字变化后，旧 `review.yaml`（逐题最终批准）也随之失效。

## 严重度与规范 code

`code` 为开放字符串，可演进；下表的规范 code 被软校验——命中者 `severity` 必须匹配。

| code | severity | 含义 |
|---|---|---|
| `stem_conflict` | blocking | 题干冲突 |
| `choice_conflict` | blocking | 选项冲突 |
| `answer_conflict` | blocking | 答案冲突 |
| `formula_conflict` | blocking | 公式冲突 |
| `solution_conclusion_conflict` | blocking | 解析结论冲突 |
| `question_ref_mismatch` | blocking | 题号归属冲突 |
| `existing_staging_stem_mismatch` | blocking | 与既有 staging 题干指纹不一致（盲跑错配） |
| `image_crop_needs_confirmation` | warning | 图片裁框需确认 |
| `evidence_span_needs_confirmation` | warning | 证据范围需确认 |
| `auto_resolved_format_diff` | info | 已自动消除的格式差异 |

未列入此表的 `code` 可使用任意 `severity`，保持前向兼容。`blocking` 未全部解决前，
单题通过、全卷通过、audit 与 promote 均被拒绝；`warning` 允许查看但晋升前必须显式确认。

## 数学敏感差异标记

数学敏感差异必须单独标记 `math_token`，Review UI 据此高亮：

| math_token | 含义 |
|---|---|
| `sign` | 正负号 |
| `exponent` | 指数 |
| `radicand` | 根号范围 |
| `fraction` | 分子分母 |
| `inequality` | 不等号 |
| `numeric_value` | 数值 |
| `choice_letter` | 选项字母 |

## 候选集合哈希与失效

`compute_candidates_hash(candidates)` 计算候选集合指纹，用于判定 resolution 是否过期：

- 候选先按 `window_id` 升序排序，排序不影响结果。
- 纳入指纹的字段：`window_id`、`raw_value`、`normalized_value`、`confidence`，
  以及每条 evidence 的 `source` 路径、`page_number` 与（region 的）`box_px`。
- **刻意排除** `source_sha256` / `output_sha256`：它们是 `materialize_staging.py` 的产物
  盖印，纳入会使每次重物化误失效 resolution。evidence 模型本身也不携带这些字段。

`validate_resolutions_against_issues(issues, resolutions)` 返回错误列表（空为全通过）：

- resolution 指向不存在的 `issue_id` → `unknown issue: <id>`。
- `resolved_candidates_hash` 与当前 `candidates_hash` 不一致 → `stale: <id>`。
- `accept_candidate` 的 `accepted_window_id` 不在候选中 → `dangling window: <id>`。

任何 resolution 失效后，Review UI 必须重新裁决该 issue，且对应的逐题最终批准
（`review.yaml`）也视为过期。
