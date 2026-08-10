# B 类: 布局无法推断

| paper | 题数 | 根因 | draft 路径(代表) | 种子页序列(question→solution) |
|-------|------|------|------------------|------------------------------|
| 2024-QINGPU-ERMO | 25 | cannot infer Word source layout from page seeds; pass --layout interle | `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-QINGPU-ERMO/paper.draft.yaml` | q=[1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2]..<br>s=[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1].. |
| 2026-FENGXIAN-ERMO | 24 | cannot infer Word source layout from page seeds; pass --layout interle | `.codex/worktrees/langgraph-question-ingestion/teaching_skills/build/question-ingestion/2026-FENGXIAN-ERMO/run-4292dc9f7bc4/structured/paper.draft.yaml` | q=[1, 2, 2, 3, 4, 5, 6, 7, 7, 7, 8, 8]..<br>s=[1, 2, 3, 4, 5, 6, 7, 7, 7, 8, 8, 9].. |
| 2026-JIADING-ERMO | 25 | cannot infer Word source layout from page seeds; pass --layout interle | `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-JIADING-ERMO/paper.draft.yaml` | q=[1, 1, 2, 3, 4, 5, 7, 8, 8, 9, 10, 10]..<br>s=[1, 2, 3, 3, 4, 7, 8, 8, 9, 9, 10, 11].. |

> 同一卷可能在 build/staging/recovery 多处有副本,上表只列代表路径;完整副本见各卷 all_paths。