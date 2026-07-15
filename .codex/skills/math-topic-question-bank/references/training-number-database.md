# Training Number Database

题库数值素材位于 `data/training-number-database.yaml`，schema 为
`math_training_number_database/v1`。它由 Wolfram 脚本生成，不手工维护条目。

生成链路：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/generate_training_number_database.py
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/validate_training_number_database.py \
  .codex/skills/math-topic-question-bank/data/training-number-database.yaml \
  --review .codex/skills/math-topic-question-bank/data/training-number-review.yaml
```

Wolfram 使用 `Solve[..., Integers]` 生成有界完整解集，使用
`FullSimplify`、`FactorInteger`、`SquareFreeQ` 和 `RootReduce` 处理精确根式。
Python/Pydantic 复核倍数、勾股、缩放引用和根式规范形式。

缩放三角形固定分成两族：

- `integer_right_triangles_fraction_scaled`：整数勾股数组只能乘最简分数；分子不超过 7，分母在 2..7，比例在 1/2..2，不能乘根式。
- `radical_right_triangles_simple_scaled`：30/45 度根式三角形可以乘同一组简单分数；根式缩放只允许原三角形已有的被开方数，以及对应倒数根式形式（如 `sqrt(3)`、`sqrt(3)/3`）。

任何缩放系数的最大素因数不得超过 7。像 `(3sqrt(3),4sqrt(3),5sqrt(3))` 这种整数勾股数组整体乘根式的组合不生成。

`rational_multiple_pairs` 只使用 `2,3,4,5,6` 五种整数倍数；两条分数边长的最终商必须是大于 1 的整数。
两条边也遵守相同的素因数上限：最简分数的分子、分母最大素因数均不得超过 7，因此不会生成带公因数 11 或分母 11 的组合。

该 family 不重新生成三套数据，而是在 review/selection 层按现有最简分数派生三个子分类：

- `numerator_multiple_only`：分母相同，两个分子成整数倍关系；
- `denominator_multiple_only`：分子相同，两个分母成整数倍关系；
- `numerator_and_denominator_multiple`：分子、分母都不同，且两组分别成整数倍关系；
- `not_integer_multiple`：仅作为防御性分类保留；当前 Wolfram 生成库不应产生此类条目。

可用 `select_training_numbers.py --subcategory <id>` 限定其中一类。分类不改变原 entry id，也不影响已有禁用状态。

## Review 状态

`data/training-number-review.yaml` 只保存禁用 id。重新生成数据库不得覆盖该文件。
若规则调整导致旧条目消失，旧禁用 id 会移动到 `retired_entry_ids`，保留审核历史但不参与当前筛选。
打开审核界面：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/open_training_number_review.py
```

按钮凸起表示可用；按钮凹下且 `aria-pressed=true` 表示禁用。点击后立即原子写入 review YAML。

审核服务同时提供 `/game` 的“倍数快找”训练：每题从 review 后仍可用的
`rational_multiple_pairs` 中取一组正确答案，四个按钮各显示一整对分数，三个干扰按钮也直接取自
review 后可用且最终商为整数的分数对。后端用精确分数保证只有一个按钮中的一对数相除能得到目标整数倍数。
难度对应每题 20 秒、12 秒、7 秒；练习内容可组合选择
分子倍数、分母倍数、分子分母同时倍数三类。

每轮结束会写入同目录的 `training-number-game-history.sqlite3`。该运行时数据库不进入版本控制；
`/api/game/history` 返回最近训练及汇总，记录正确率、得分和平均答题用时；超时题按该档完整时限
计入平均值。每道答错或超时题同时冻结目标倍数、四个分数对、正确选项、学生选择、题型和用时；
结果页和历史记录均可回看。功能启用前的旧轮次明确标记为“未记录”，不尝试还原。
游戏内“训练记录”页面可切换三项折线图展示变化。

单题得分为：答对基础分 100，加 `round(剩余时间 / 本题时限 * 50)` 的速度分，再加连续答对奖励；
连对从第 2 题起每题增加 10 分，最高增加 50 分。答错或超时不加分。

## Writer 使用约束

Writer 不直接从数据库全文凭印象选数。必须调用选择脚本；该脚本会排除 review 中禁用的 id：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/select_training_numbers.py \
  --family radical_multiple_pairs \
  --tag k_equals_a \
  --count 3 \
  --seed 7
```

选定后在 coverage plan 和单题教师 assignment 的 `teaching` 中冻结：

```yaml
number_selection:
  database_id: question-bank-training-numbers
  family_id: radical_multiple_pairs
  entry_id: sqrt-ka-a3-k3
```

抽题阶段不得更换 `entry_id` 或重新生成数字。
