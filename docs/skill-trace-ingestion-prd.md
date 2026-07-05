# PRD: Skill Trace Ingestion & Review MVP

## 1. 背景

`Gaogao417/teaching_skills` 当前已经有一套面向作业/讲义生成的仓库结构：`.codex/skills/`、`.claude/skills/`、`docs/`、`model_rules/`、`scripts/`、`math-assignment-latex/`、`examples/linear-function/` 等目录并存。现有文档中的模型规则工作流强调：`structural analysis -> relation 规范化/入库 -> explanation 与 assignment 并行生成`；`model_rules` 的核心是轻量语义类型、typed ports、single-direction relations 与 constraints，而不是重型数学类型系统。

技能图谱的概念边界以 `docs/skill-graph-conceptual-model.md` 为准：图谱不是知识点标签树，而是学生解题动作网络；本 PRD 只实现其中最小的 reviewed trace 入库闭环。

现在需要补一个更小、更贴近实际使用的 MVP：

> 用户把“题目、解答、自己预期的解题思路”交给 Codex 等 agent，agent 先产出一份可审阅的 `SkillTraceDraft`；每个 trace step 同时带 `cognitive_layer` 和 `reuse_level` 两个坐标。随后调用本地脚本弹出审阅界面，用户修改后提交入库；该任务返回并保存 Codex thread id，后续 explanation / assignment 生成通过同一 thread id 继续上下文。

## 2. 问题定义

当前痛点不是缺一个大型技能图谱系统，而是缺少一个稳定的“人机协同入库闭环”：

1. agent 能分析题目，但每次输出粒度可能不一致。
2. 用户有自己的预期解题思路，需要在入库前审阅和修改。
3. 生成物没有稳定保存到数据库，后续讲解和练习生成难以复用。
4. Codex thread 上下文没有作为一等数据保存，后续调用 explanation / assignment 时容易丢上下文。
5. 现有 `01-structure-analysis.md -> 02-student-explanation -> 03-adaptive-practice` 流水线缺少“已审阅技能 trace”作为更稳定的前置事实源。

## 3. MVP 目标

### 3.1 核心目标

实现一个最小闭环：

```text
用户输入题目 + 解答 + 预期解题思路
  -> Codex 生成 SkillTraceDraft JSON
  -> Codex 调用本地 review 脚本
  -> 浏览器弹出审阅界面
  -> 用户修改并提交
  -> 数据库存储 reviewed trace
  -> 返回 codex_thread_id + problem_case_id + reviewed_trace_id
  -> 后续 explanation / assignment 通过 codex_thread_id 继续生成
```

### 3.2 成功标准

1. 用户能在 5 分钟内把一道题从自然语言输入转成已审阅 skill trace。
2. 每个 trace step 都带有两个坐标：`cognitive_layer` 与 `reuse_level`。
3. 审阅界面允许修改、增删、排序、校验、提交。
4. 数据库持久化：题目、原解答、用户预期思路、draft、reviewed trace、Codex thread id。
5. 后续生成脚本可以通过 `reviewed_trace_id` 和 `codex_thread_id` 继续使用同一任务上下文。
6. 不要求第一版支持学生端、不要求自动判分、不要求完整知识图谱。

## 4. 非目标

MVP 不做以下内容：

1. 不做完整学生练习平台。
2. 不做大规模知识图谱可视化。
3. 不做自动从所有旧题中批量抽取图谱。
4. 不做复杂权限系统。
5. 不做多用户云端部署。
6. 不让 agent 自动把新节点写入 canonical 库，所有提交必须经过审阅界面。
7. 不重写 `math-assignment-latex` 或 diagram workflow，只提供上游 trace artifact。

## 5. 关键概念

### 5.1 Trace Step 的两个坐标

一个 trace step 不是两套图谱，而是同一个学生动作同时带两个属性：

```yaml
cognitive_layer: L3_strategy | L0_structure | L1_encoding | L2_execution
reuse_level: generic_action | domain_action | pattern_step | instance_step
```

#### cognitive_layer

`cognitive_layer` 表示学生动作层级，定义见 `docs/skill-graph-conceptual-model.md`：

- `L3_strategy`：策略控制。先看什么、选哪条路径、是否设元、是否用份数法、是否检查范围。
- `L0_structure`：结构识别。看出目标、对象、对应关系、共高、点在线上、整体-部分。
- `L1_encoding`：条件转化。把结构关系转为比例、方程、参数化表达、面积式。
- `L2_execution`：运算执行。解方程、化简、分份计算、代入、筛选。

#### reuse_level

`reuse_level` 表示动作的复用范围：

- `generic_action`：抽象策略层。跨专题复用动作，例如“目标驱动选关系”“用结构减少未知量”。
- `domain_action`：领域关系层。领域内复用动作，例如“点在线上参数化”“等高面积比转底边比”。
- `pattern_step`：题型路径层。题型中的稳定步骤，例如“直线上动点 + 面积条件求点坐标”的某一步。
- `instance_step`：题目实例层。只服务当前题目的具体证据，例如“本题 ED 对应 BC”。

### 5.2 目标驱动选关系

比例题里的“要求什么？它和什么已知量作比？”要泛化为：

```text
要求什么对象？
它由哪些已知关系约束？
这些关系能转化成什么表达式或方程？
```

因此 Skill Trace 应尽量呈现这条动作链：

```text
目标量定位
-> 找到目标量所在的关系
-> 选择最有用的关系
-> 把关系转化成数学表达
-> 计算并按题目范围筛选
```

### 5.3 Skill Trace

一份 `SkillTrace` 是一道题的标准动作链。它不等于完整讲解，也不等于最终作业 YAML。它是后续讲解、提示、变式题的上游事实源。

MVP 保存的是 problem-level reviewed trace，不自动把新节点合并进 canonical 技能图谱。后续可以在 reviewed trace 稳定后，再做 canonical node 候选合并。

### 5.4 Codex Thread

每次 agent 处理一道题时，应保存 `codex_thread_id`。后续 explanation / assignment 生成通过同一 thread 继续，避免重复输入上下文。

## 6. 用户流程

### 6.1 输入阶段

用户给 Codex 或其他 agent 输入：

```yaml
problem_input:
  title: 比例结构：平行线分段求 ED
  raw_problem: |
    AB = 2, BC = 3, AD = 7, BE ∥ CD，求 ED。
  provided_solution: |
    设 ED = x，则 AE = 7-x，列 (7-x)/x = 2/3。
  expected_thinking: |
    不希望学生一上来设 x。应先看要求 ED，找 ED 对应 BC，推出 AE:ED=2:3，AD 是 5 份，ED 是 3 份。
  topic_tags: ["比例", "平行线分线段", "份数法"]
  target_student_level: 初二
```

### 6.2 Agent 输出阶段

Codex 产出 `SkillTraceDraft` JSON，并调用：

```bash
./.venv/bin/python scripts/skill_trace/open_review.py \
  --draft artifacts/skill-trace-drafts/<draft_id>.json \
  --codex-thread-id <thread_id>
```

脚本启动本地审阅服务并打开浏览器：

```text
http://127.0.0.1:8765/review/<draft_id>
```

打开审阅页前只校验 draft，并把 draft 暂存在本次 review server 进程内存中；不要提前写入 SQLite/PostgreSQL。

### 6.3 审阅阶段

审阅界面展示：

左侧：题目、原解答、用户预期思路。  
中间：trace step 列表。  
右侧：当前 step 详情、校验结果、提交按钮。

用户可以：

- 修改 step 的 `name`、`cognitive_layer`、`reuse_level`、`student_action_norm`。
- 增加或删除 step。
- 调整 step 顺序。
- 标记 core step / support step。
- 添加 common error。
- 点击“全部提交入库”，一次性提交页面中的全部 steps。

### 6.4 入库阶段

点击“全部提交入库”后写入 SQLite/PostgreSQL：

- `problem_cases`
- `codex_threads`
- `skill_trace_drafts`：保存 agent 生成的原始 draft。
- `skill_trace_reviews`：保存用户在页面提交后的 reviewed trace。
- `skill_trace_steps`：保存 reviewed trace 中每个 step 的结构化展开。

自动生成的 `reviewed_trace_id` 使用 `trace_` + 完整 `uuid4().hex`；自动生成时必须先查重，不能因为 id 冲突覆盖已有 review。

提交成功后 UI 和 CLI 返回：

```json
{
  "status": "reviewed",
  "codex_thread_id": "thr_xxx",
  "problem_case_id": "case_xxx",
  "draft_id": "draft_xxx",
  "reviewed_trace_id": "trace_xxx"
}
```

### 6.5 后续生成阶段

后续 explanation / assignment 生成不重新分析题目，而是读取 reviewed trace：

```bash
python3 scripts/skill_trace/export_for_pipeline.py \
  --reviewed-trace-id trace_xxx \
  --out artifacts/<student>/<date-topic>/01-skill-trace.reviewed.json
```

然后通过 Codex SDK 或 CLI resume 同一个 thread，继续发 prompt：

```text
基于 reviewed_trace_id=trace_xxx 和 artifacts/.../01-skill-trace.reviewed.json，生成 02-student-explanation.assignment.yaml。
```

## 7. 功能需求

### FR1. Agent 输入合同

系统必须提供固定输入模板，要求用户提供：

- 题目原文。
- 参考解答或学生解答。
- 用户预期解题思路。
- 可选：学生水平、主题标签、图像路径、已有 artifacts 路径。

### FR2. Draft 输出合同

Codex 必须输出 `SkillTraceDraft` JSON，字段如下：

```yaml
draft_id: string
schema_version: "skill_trace_draft.v0"
codex_thread_id: string
problem_case:
  title: string
  raw_problem: string
  provided_solution: string
  expected_thinking: string
  topic_tags: string[]
trace_summary:
  target: string
  core_strategy: string
  target_relation_chain: string
  main_student_blocker: string
  preferred_path: string
steps:
  - step_id: string
    order: number
    name: string
    cognitive_layer: L3_strategy | L0_structure | L1_encoding | L2_execution
    reuse_level: generic_action | domain_action | pattern_step | instance_step
    domain: string
    student_action_norm: string
    common_errors: string[]
    is_core_step: boolean
validation:
  warnings: string[]
  unresolved_questions: string[]
```

### FR3. Review UI

审阅界面必须支持：

- 读取 draft JSON。
- 展示原题、解答、预期思路。
- 展示 step 表格。
- 对每个 step 进行编辑。
- 增删 step。
- 拖拽或按钮排序。
- 实时校验。
- 提交入库。
- 提交后显示 `reviewed_trace_id` 和 `codex_thread_id`。

### FR4. 校验规则

提交前至少检查：

1. 每个 step 必须有 `cognitive_layer`。
2. 每个 step 必须有 `reuse_level`。
3. 每个 step 必须有 `student_action_norm`。
4. trace 至少包含一个 L3 策略步骤。
5. trace 至少包含一个 L0 或 L1 步骤。
6. `order` 不重复。
7. `codex_thread_id` 非空。
8. `problem_case.raw_problem` 非空。
9. 不允许一个 step 同时包含多个动作，例如“找对应并计算结果”。这种必须拆成两个 step。

### FR5. 数据库存储

MVP 默认使用 SQLite，后续可迁移 PostgreSQL。

最低表结构：

```sql
codex_threads(
  id TEXT PRIMARY KEY,
  provider TEXT,
  created_at TEXT,
  last_used_at TEXT,
  metadata_json TEXT
);

problem_cases(
  id TEXT PRIMARY KEY,
  title TEXT,
  raw_problem TEXT NOT NULL,
  provided_solution TEXT,
  expected_thinking TEXT,
  topic_tags_json TEXT,
  target_student_level TEXT,
  codex_thread_id TEXT,
  created_at TEXT
);

skill_trace_drafts(
  id TEXT PRIMARY KEY,
  problem_case_id TEXT,
  codex_thread_id TEXT,
  draft_json TEXT NOT NULL,
  created_at TEXT
);

skill_trace_reviews(
  id TEXT PRIMARY KEY,
  draft_id TEXT,
  problem_case_id TEXT,
  codex_thread_id TEXT,
  reviewed_json TEXT NOT NULL,
  created_at TEXT,
  reviewer_note TEXT
);

skill_trace_steps(
  id TEXT PRIMARY KEY,
  reviewed_trace_id TEXT,
  step_order INTEGER,
  name TEXT,
  cognitive_layer TEXT,
  reuse_level TEXT,
  domain TEXT,
  student_action_norm TEXT,
  common_errors_json TEXT,
  is_core_step INTEGER
);
```

### FR6. Handoff

每次入库后必须能导出：

```text
01-skill-trace.reviewed.json
01-structure-analysis.md
thread_handoff.json
```

其中 `thread_handoff.json`：

```json
{
  "codex_thread_id": "thr_xxx",
  "problem_case_id": "case_xxx",
  "reviewed_trace_id": "trace_xxx",
  "next_suggested_actions": [
    "generate_student_explanation",
    "generate_adaptive_assignment"
  ]
}
```

`01-structure-analysis.md` 是兼容现有 pipeline 的适配文件，内容来自 reviewed trace，不重新自由分析。

## 8. 与现有仓库的集成点

### 8.1 新增 Codex skill

新增：

```text
.codex/skills/math-skill-trace-ingestion/SKILL.md
```

职责：

- 读取题目、解答、用户预期思路。
- 生成 `SkillTraceDraft`。
- 调用 review 脚本。
- 返回 `codex_thread_id`、`draft_id`。

### 8.2 新增脚本目录

新增：

```text
scripts/skill_trace/
  contracts.py
  db.py
  validate_trace.py
  open_review.py
  review_server.py
  export_for_pipeline.py
  seed_demo.py
```

### 8.3 新增 artifact 目录约定

```text
artifacts/skill-trace-drafts/<draft_id>.json
artifacts/skill-trace-reviewed/<reviewed_trace_id>.json
artifacts/<学生名>/YYYY-MM-DD-<内容>/01-skill-trace.reviewed.json
artifacts/<学生名>/YYYY-MM-DD-<内容>/01-structure-analysis.md
```

### 8.4 兼容现有 skill

`math-adaptive-practice-latex-data` 当前以 `01-structure-analysis.md` 和 `02-student-explanation` 为输入。MVP 不要求立即改掉这个约定，而是通过 `export_for_pipeline.py` 生成兼容版 `01-structure-analysis.md`。后续再让 explanation/practice skill 原生读取 `01-skill-trace.reviewed.json`。

## 9. 审阅 UI 信息架构

### 9.1 页面布局

```text
+------------------------------------------------------------+
| Header: draft_id | thread_id | Save Draft | Submit Review  |
+----------------------+----------------------+--------------+
| Source               | Trace Steps          | Step Editor  |
| - raw_problem         | 1. L3 target_first   | fields       |
| - solution            | 2. L0 locate ED      | validation   |
| - expected_thinking   | 3. L0 ED <-> BC      | notes        |
|                      | ...                  |              |
+----------------------+----------------------+--------------+
| Validation messages                                         |
+------------------------------------------------------------+
```

### 9.2 Step 表格字段

- order
- name
- cognitive_layer
- reuse_level
- domain
- student_action_norm
- is_core_step
- warning badge

### 9.3 Step editor 字段

- name
- cognitive_layer
- reuse_level
- domain
- student_action_norm
- common_errors
- is_core_step

## 10. 后续 explanation / assignment 生成接口

MVP 提供两个命令：

```bash
python3 scripts/skill_trace/export_for_pipeline.py --reviewed-trace-id trace_xxx --out-dir artifacts/<...>
```

```bash
node scripts/skill_trace/codex_continue_thread.mjs \
  --thread-id thr_xxx \
  --prompt-file prompts/generate_explanation_from_reviewed_trace.md
```

其中第二个脚本只作为薄封装，真正生成仍由 Codex thread 承接。

## 11. 验收标准

### AC1. Draft 生成

给定一份题目、解答、预期思路，agent 能生成合法 `SkillTraceDraft` JSON。

### AC2. UI 弹出

agent 调用脚本后，浏览器打开审阅地址。

### AC3. 用户修改

用户能修改 step，新增 step，删除 step，调整顺序。

### AC4. 校验

缺少 layer、reuse_level、thread_id 时不能提交。

### AC5. 入库

提交后 SQLite 中能查到 problem case、draft、review、steps。

### AC6. Handoff

提交后返回：

```text
codex_thread_id
problem_case_id
reviewed_trace_id
```

并能导出 `01-skill-trace.reviewed.json`。

### AC7. Pipeline 兼容

能从 reviewed trace 生成兼容版 `01-structure-analysis.md`，供现有 explanation / assignment 流程继续使用。

## 12. 风险与约束

### 风险 1：节点过细或过粗

缓解：UI 中强制每个 step 只表达一个动作；同时支持 `is_core_step`，让用户区分核心路径和支撑细节。

### 风险 2：agent 自由发明节点名

缓解：MVP 暂不做 canonical node 自动入库。reviewed trace 先作为 problem-level trace 保存；后续再做 canonical skill node 合并。

### 风险 3：Codex thread id 获取方式不稳定

缓解：支持两种来源：

1. Codex SDK 调用返回的 thread id。
2. 用户或 CLI 显式传入 `--codex-thread-id`。

### 风险 4：和现有 pipeline 断裂

缓解：第一版只新增上游 adapter，生成兼容 `01-structure-analysis.md`，不重写下游 skills。

## 13. 版本规划

### v0.1

- JSON schema
- SQLite DB
- 本地审阅 UI
- 手动/脚本提交
- 导出 reviewed trace

### v0.2

- Codex skill 集成
- Codex SDK 继续 thread
- explanation handoff

### v0.3

- canonical skill node 候选合并
- pattern path 检索
- 和 `model_rules` relation 入库产生弱关联

### v0.4

- 学生练习端读取 trace step，生成即时提示和动作规范
