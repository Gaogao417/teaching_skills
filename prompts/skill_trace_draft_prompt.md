# Skill Trace Draft Prompt

你要把用户提供的数学题、解答、预期思路和学生可见问题，整理成一个 `SkillTraceDraft` JSON。

只输出 JSON，不要输出讲解正文、练习题、Markdown 说明或额外注释。

## 必须遵守

- 不要直接写讲解。
- 不要直接出练习题。
- 不要创造复杂大图谱。
- 只输出 `SkillTraceDraft` JSON。
- 每个 step 只能表达一个学生动作。
- 每个 step 必须有 `cognitive_layer` 和 `reuse_level`。
- `cognitive_layer` 和 `reuse_level` 的含义必须对齐 `docs/skill-graph-conceptual-model.md`。
- 必须体现用户预期解题思路。
- 必须标出学生原解法的问题点；没有学生作答时，在 `validation.unresolved_questions` 中说明缺少学生证据。

## 字段约定

- `schema_version` 使用 `skill_trace_draft.v0`。
- `draft_id` 使用可读短 id，例如 `draft_ratio_ed_001`。
- `codex_thread_id` 优先使用外部传入的真实 thread id；没有时留给 `open_review.py` 生成 `manual_<uuid>`。
- `problem_case.raw_problem` 必须保留原题。
- `problem_case.provided_solution` 放用户提供的解答或参考解法。
- `problem_case.expected_thinking` 放用户强调的预期思路。
- `trace_summary` 只放本题目标、核心策略、学生卡点摘要等轻量信息。
- `steps` 至少包含一个 `L3_strategy`，并至少包含一个 `L0_structure` 或 `L1_encoding`。

## Step 写法

- `student_action_norm` 写学生应该做的一个动作，不写教师评价。
- `common_errors` 写学生容易错在哪里，尤其要覆盖用户提供的原解法问题点。
- `is_core_step` 对主路径步骤设为 `true`，旁支检查或非关键提醒可设为 `false`。
