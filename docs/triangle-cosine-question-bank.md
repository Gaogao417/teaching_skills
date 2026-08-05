# 四类三角比解三角形题库流水线

## 两套审核界面

这条流水线按数据层分成两套 UI，不把候选题混进素材库页面：

- `http://127.0.0.1:8876/` 是素材库审核 UI，顶部三个页签依次审核“数库 → 三角比库 → 三角形库”。点击卡片切换可用/禁用状态。
- `http://127.0.0.1:8877/` 是现有题库 Review UI。“解三角形生成题候选库”以 500 题的 staging 审核卷出现，逐题只展示题干和答案，可通过或要求修改。

审核状态分别写在：

- 数库：`.codex/skills/math-topic-question-bank/data/training-number-review.yaml`
- 三角比库：`.codex/skills/math-topic-question-bank/data/triangle-trig-ratio-review.yaml`
- 三角形库：`.codex/skills/math-topic-question-bank/data/triangle-cosine-database-review.yaml`
- 候选题：`.codex/skills/math-topic-question-bank/data/triangle-cosine-question-review.yaml`

素材库禁用不直接改写已经物化的下游 YAML；重新运行对应生成脚本时生效。三角比库禁用会在重建三角形库时排除相关三角比，三角形库禁用会在重建候选题时排除相关普通题及整条 SSA 等价类。

## 分层边界

本流水线固定为三个物化数据层：

```text
training-number-database.yaml
  -> triangle-trig-ratio-database.yaml
  -> triangle-cosine-database.yaml
  -> triangle-cosine-question-candidates.yaml
  -> 人工审核
  -> triangle-cosine-question-bank.yaml
  -> sample.assignment.yaml
```

- 三角比库从 review 后仍可用的全部直角三角形 family 提取并去重锐角三角比；不要求
  原记录带 `trig_ratio` 标签。特殊角和一般单根式三角比都可进入。
- 三角形库只读取三角比库，保存三角形及 SSA 一解/二解索引。
- 题库生成器只读取三角形库，不读取数库或三角比库，也不构造新的三角形。
- 抽题只读取人工批准后发布的正式题库，不换数、不改题、不重新求解。

来源追踪逐层进行：

```text
question.source_triangle_ids
  -> triangle.source_trig_ratio_ids
  -> trig_ratio.source_number_entry_ids
```

## 生成和审计

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/generate_triangle_trig_ratio_database.py
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/generate_triangle_cosine_database.py
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/generate_triangle_cosine_questions.py
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/validate_triangle_cosine_pipeline.py
```

题库候选默认每类稳定保留 100 题，并轮转保留求边、求余弦以及 SSA 一解/二解。
使用 `generate_triangle_cosine_questions.py --max-per-type N` 调整每类审核池大小。

## 人工审核

每次审核决定绑定题目 `content_hash`。题目重新生成后，内容哈希不匹配的旧批准不会进入正式题库。

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/review_triangle_cosine_question.py \
  TCQ-XXXXXXXXXXXX --decision approved

./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/review_triangle_cosine_question.py \
  TCQ-XXXXXXXXXXXX --decision rejected --reason "题面数值不够自然"
```

审核文件默认为：

```text
.codex/skills/math-topic-question-bank/data/triangle-cosine-question-review.yaml
```

## 发布与抽题

五类题都至少有一道当前哈希对应的批准题后，才能发布正式题库：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/publish_triangle_cosine_question_bank.py
```

按题型数量抽题；没有难度参数：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/sample_triangle_cosine_question_bank.py \
  .codex/skills/math-topic-question-bank/data/triangle-cosine-question-bank.yaml \
  --sss 2 --sas 2 --ssa 2 --aas 2 --asa 2 \
  --seed 20260805 \
  --output artifacts/余弦解三角形/sample.assignment.yaml
```

输出是单一 assignment，只有题目区和答案区。它不含 `difficulty`、`explanation`、
`solution_steps` 或教师版副本。题库均衡覆盖 `sin`、`cos`、`tan`、`cot`；若实际角为钝角，
assignment 只显示其补角的三角比。

## 契约验证

F# 架构契约位于：

```text
docs/triangle-trig-question-bank-contracts.fsi
```

通过以下命令验证 `.fsi` 与闭环实现一致：

```bash
dotnet build tests/fsharp/TriangleTrigQuestionBank.Contracts.fsproj --no-restore
```
