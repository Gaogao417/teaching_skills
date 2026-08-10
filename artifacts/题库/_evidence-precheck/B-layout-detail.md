# B 类: 布局无法自动推断（3 卷）

`infer_layout` 在种子页既不满足 interleaved 也不满足 separated 时抛
"cannot infer Word source layout"。这三卷经诊断**全部是 interleaved**
（题解同页/相邻页交错，solution 从 page 1 起），不是 separated。

## 诊断结论

| 卷 | 题数 | 真实 layout | 无法推断原因 | coerce interleaved | 建议 |
|----|------|------------|------------|-------------------|------|
| 2024-QINGPU-ERMO | 25 | interleaved | question 种子整体偏大（多题 q>s），coerce 钳回 | 16 处钳位，结果合理 | `--layout interleaved --layout-override-seeds` |
| 2026-CHONGMING-ERMO | 25 | interleaved | 仅 Q021 的 s=25 > q_next=21 一处违反 | corrections=[] 直接通过 | `--layout interleaved`（无需 override） |
| 2026-JIADING-ERMO | 25 | interleaved | 仅 Q022 的 s=25 > q_next=24 一处违反 | corrections=[] 直接通过 | `--layout interleaved`（无需 override） |

### 关键判断依据

三卷的 `min(solution_starts)` 都是 1（答案从第 1 页就有），所以
`coerce separated` 必然抛 "separated layout impossible: solution evidence
starts at page 1" —— 这是 interleaved 的铁证（separated 卷的答案不可能在第 1 页）。

2026-CHONGMING 和 2026-JIADING 的种子页本就合法（coerce corrections 为空），
只是 `infer_layout` 的自动判定对个别 `s[i] > q[i+1]`（相邻题跨页解答）过于
严格而拒绝。手动指定 `--layout interleaved` 即可正常展开，**不需要 override**。

2024-QINGPU 的 question 种子整体偏大（转录把多题 question 标到后面页），
需要 `--layout-override-seeds` 钳位。

## 处理命令

```bash
# 2026-CHONGMING-ERMO / 2026-JIADING-ERMO（种子合法，仅需指定 layout）
./.venv/bin/python .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py \
  artifacts/题库/2026-07-24-上海初三试卷原题库/staging/<PAPER>/paper.draft.yaml \
  --layout interleaved --check   # 先 --check 看 changes，确认后再去掉 --check

# 2024-QINGPU-ERMO（需 coerce 种子）
./.venv/bin/python .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py \
  artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-QINGPU-ERMO/paper.draft.yaml \
  --layout interleaved --layout-override-seeds --check
```

## 种子页序列（诊断依据）

### 2024-QINGPU-ERMO
- q: [1,1,1,1, **2,2,2,2,2,2,2,2,2**, 3,3,3,3,3,3,3, 4,4,4,4, 5]
- s: [1,1,1,1,1,1,1,1,1,1,1,1,1, 2,2,2,2,2, 3,3,3, 4, 5,6,7]
- 问题：Q005-Q013 的 q=2 > s=1，Q014-Q018 的 q=3 > s=2 等（question 标到后面页）

### 2026-CHONGMING-ERMO
- q: [1,2,2,3,4,5,7,7,8,9,10,10,11,12,13,14,14,15,20,21,21,21,26,28,35]
- s: [1,2,3,4,5,6,7,8,8,9,10,11,12,12,14,14,15,20,21,21,25,26,28,34,40]
- 问题：仅 Q021 s=25 > q_next=21（跨页解答，正常现象，自动推断过严）

### 2026-JIADING-ERMO
- q: [1,1,2,3,4,5,7,8,8,9,10,10,11,12,13,14,15,16,18,19,20,21,24,27,31]
- s: [1,2,3,3,4,7,8,8,9,9,10,11,12,12,13,14,16,18,19,19,20,25,27,31,35]
- 问题：仅 Q022 s=25 > q_next=24（同上）
