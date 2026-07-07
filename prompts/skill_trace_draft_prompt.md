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

- 生成前先识别学生完成本题所需的可训练 skill 节点，再给每个 skill 判定 `cognitive_layer`，最后写 `name`。
- 不要把标准解答逐句拆成 step trace。普通读数、代入和小算术如果不能支撑针对性练习，默认不是 core skill。
- `name` 写可复用技能节点名，不写本题具体对象、数值或完整学生动作。
  - 好例子：`比例结构识别`、`目标参照量建模`、`整体部分结构识别`、`比例对象校准`、`目标参照比例表达`。
  - 坏例子：`定位要求量BC`、`填入BC和AC份数`、`计算40×5/8`。
- `student_action_norm` 写这个 skill 在本题中的具体表现，不写教师评价。
- `common_errors` 写学生容易错在哪里，尤其要覆盖用户提供的原解法问题点。
- `is_core_step` 表示是否是当前题型值得诊断和训练的核心 skill，不表示是否出现在标准解答主路径上。
  - 缺失后会导致此类题不会做、做繁或迁移失败，设为 `true`。
  - 只是辅助读数、普通代入、小算术或格式收尾，设为 `false`。

## Layer Audit

- 如果一个动作同时像策略和转化，拆成两步：L3 写“选择哪条关系/参照量”，L1 写“把关系表达成比例、方程或份数关系”。
- 看到“这是什么结构模型、目标量与已知量处在什么关系、谁是整体/部分”等结构识别，优先判断为 L0。
- 不要把“读出题目要求 BC”“读出 AC=40”单独当作核心 skill；它们只有合并进目标-已知关系识别时才有训练价值。
- 看到“决定先用哪个已知量、是否用份数法、是否避免设元”等路径选择，判断为 L3。
- 看到“写成比例式/方程/参数式/份数关系”，判断为 L1。
- 看到“代入、化简、计算、解方程、求得数值”，判断为 L2。
- 看到“BC 是 5 份”这类结果句，先判断它训练的是“目标份数表达”还是普通计算；核心通常是 L1 表达，L2 小算术多为 support。
- `reuse_level` 不能用来弥补 `cognitive_layer` 模糊；先判定动作类型，再判定复用范围。

## 比例题拆层正反例

错误：

```json
{"name": "定位要求量BC", "cognitive_layer": "L3_strategy", "student_action_norm": "先确定题目要求的是 BC。"}
```

正确：

```json
{"name": "比例结构识别", "cognitive_layer": "L0_structure", "student_action_norm": "识别本题要用目标量 BC 与已知量 AC 的份数比求线段。"}
```

错误：

```json
{"name": "求出BC份数", "cognitive_layer": "L1_encoding", "student_action_norm": "用 AC 的 8 份减去 AB 的 3 份，得到 BC 的 5 份。"}
```

正确拆法：

```json
{"name": "目标份数表达", "cognitive_layer": "L1_encoding", "student_action_norm": "用整体 AC 的份数减去已知部分 AB 的份数来表达 BC 的份数。", "is_core_step": true}
{"name": "份数差计算", "cognitive_layer": "L2_execution", "student_action_norm": "计算 8 - 3 = 5，得到 BC 是 5 份。", "is_core_step": false}
```
