# Implementation Plan: Skill Trace Ingestion & Review MVP

## 1. 实施原则

1. 先做最小闭环，不做完整平台。
2. SQLite first，后续再迁移 PostgreSQL。
3. Codex/agent 只生成 draft，不直接写正式库。
4. 用户审阅后才入库。
5. 不改动现有 `math-assignment-latex` 主流程，只新增上游 adapter。
6. 每个 trace step 同时带两个字段：`cognitive_layer` 与 `reuse_level`。
7. `codex_thread_id` 是一等字段，必须贯穿 draft、review、handoff。
8. 技能图谱语义以 `docs/skill-graph-conceptual-model.md` 为准；本 MVP 只保存 reviewed trace，不自动合并 canonical 图谱节点。

## 2. 目标目录结构

新增或修改：

```text
.codex/skills/math-skill-trace-ingestion/SKILL.md

docs/skill-trace-ingestion-prd.md
docs/skill-trace-implementation-plan.md
docs/skill-graph-conceptual-model.md

scripts/skill_trace/
  __init__.py
  contracts.py
  db.py
  validate_trace.py
  open_review.py
  review_server.py
  export_for_pipeline.py
  codex_continue_thread.mjs
  seed_demo.py

scripts/skill_trace/static/
  review.css
  review.js

scripts/skill_trace/templates/
  review.html

prompts/
  skill_trace_draft_prompt.md
  generate_explanation_from_reviewed_trace.md
  generate_assignment_from_reviewed_trace.md

tests/skill_trace/
  test_contracts.py
  test_validate_trace.py
  test_db_roundtrip.py
  test_export_for_pipeline.py
```

## 3. Milestone 0：文档与约定落地

### 3.1 添加文档

将技能图谱说明、PRD 和实施计划放入：

```text
docs/skill-graph-conceptual-model.md
docs/skill-trace-ingestion-prd.md
docs/skill-trace-implementation-plan.md
```

三份文档分工：

- `skill-graph-conceptual-model.md`：固定 L0/L1/L2/L3、复用层级和 Skill Trace / Skill Graph 边界。
- `skill-trace-ingestion-prd.md`：定义产品闭环、用户流程、功能需求和验收标准。
- `skill-trace-implementation-plan.md`：定义实施目录、milestone、脚本、测试和任务拆分。

### 3.2 更新 AGENTS 约定

补充 commit 分类：

```text
[workflow] skill trace schema, review UI, scripts, DB migrations, Codex skill
[artifacts] generated reviewed traces and demo outputs
```

保留现有原则：workflow 改动和 generated artifact 不混在一个 commit。

## 4. Milestone 1：数据合同与校验器

### 4.1 `contracts.py`

使用 Pydantic 实现合同。Milestone 1 不支持 dataclass 手写校验替代方案；如果依赖缺失，先在 `./.venv` 中安装 Pydantic。

```python
# scripts/skill_trace/contracts.py
from typing import Literal, List, Optional
from pydantic import BaseModel, Field

CognitiveLayer = Literal[
    "L3_strategy",
    "L0_structure",
    "L1_encoding",
    "L2_execution",
]

ReuseLevel = Literal[
    "generic_action",
    "domain_action",
    "pattern_step",
    "instance_step",
]

class ProblemCase(BaseModel):
    title: str
    raw_problem: str
    provided_solution: str = ""
    expected_thinking: str = ""
    topic_tags: List[str] = []
    target_student_level: str = ""

class SkillTraceStep(BaseModel):
    step_id: str
    order: int
    name: str
    cognitive_layer: CognitiveLayer
    reuse_level: ReuseLevel
    domain: str = "general"
    student_action_norm: str
    common_errors: List[str] = []
    is_core_step: bool = True

class SkillTraceDraft(BaseModel):
    draft_id: str
    schema_version: str = "skill_trace_draft.v0"
    codex_thread_id: str
    problem_case: ProblemCase
    trace_summary: dict
    steps: List[SkillTraceStep]
    validation: dict = Field(default_factory=lambda: {"warnings": [], "unresolved_questions": []})
```

### 4.2 `validate_trace.py`

实现校验：

```bash
python3 scripts/skill_trace/validate_trace.py artifacts/skill-trace-drafts/demo.json
```

校验规则：

- JSON 可解析。
- `codex_thread_id` 非空。
- `raw_problem` 非空。
- `steps` 非空。
- `order` 唯一。
- 每个 step 有合法 `cognitive_layer` 和 `reuse_level`。
- 至少一个 `L3_strategy`。
- 至少一个 `L0_structure` 或 `L1_encoding`。
- 每个 step 有 `student_action_norm`。
- 每个 step 只表达一个学生动作；疑似“找关系并计算”这类复合动作时给出 warning。

输出：

```json
{
  "ok": true,
  "errors": [],
  "warnings": []
}
```

### 4.3 测试

```bash
pytest tests/skill_trace/test_contracts.py tests/skill_trace/test_validate_trace.py
```

## 5. Milestone 2：SQLite 数据库

### 5.1 `db.py`

实现：

- 初始化数据库。
- 插入 draft（仅用于手动调试或 reviewed trace 提交兜底）。
- 插入 reviewed trace。
- 查询 reviewed trace。
- 查询 thread handoff。

默认数据库：

```text
artifacts/skill_trace.db
```

环境变量覆盖：

```bash
export SKILL_TRACE_DB=.local/skill_trace.db
```

### 5.2 SQLite schema

```sql
CREATE TABLE IF NOT EXISTS codex_threads (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL DEFAULT 'codex',
  created_at TEXT NOT NULL,
  last_used_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS problem_cases (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  raw_problem TEXT NOT NULL,
  provided_solution TEXT NOT NULL DEFAULT '',
  expected_thinking TEXT NOT NULL DEFAULT '',
  topic_tags_json TEXT NOT NULL DEFAULT '[]',
  target_student_level TEXT NOT NULL DEFAULT '',
  codex_thread_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_trace_drafts (
  id TEXT PRIMARY KEY,
  problem_case_id TEXT NOT NULL,
  codex_thread_id TEXT NOT NULL,
  draft_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_trace_reviews (
  id TEXT PRIMARY KEY,
  draft_id TEXT NOT NULL,
  problem_case_id TEXT NOT NULL,
  codex_thread_id TEXT NOT NULL,
  reviewed_json TEXT NOT NULL,
  reviewer_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_trace_steps (
  id TEXT PRIMARY KEY,
  reviewed_trace_id TEXT NOT NULL,
  step_order INTEGER NOT NULL,
  name TEXT NOT NULL,
  cognitive_layer TEXT NOT NULL,
  reuse_level TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT 'general',
  student_action_norm TEXT NOT NULL,
  common_errors_json TEXT NOT NULL DEFAULT '[]',
  is_core_step INTEGER NOT NULL DEFAULT 1
);
```

表语义：

- `skill_trace_drafts.draft_json` 保存 agent 生成的原始 draft。打开 review 页时不提前写入；用户点击“全部提交入库”时，如果 DB 中还没有 draft，再把原始 draft 写入该表。
- `skill_trace_reviews.reviewed_json` 保存用户在页面中编辑后提交的 reviewed trace。
- `skill_trace_steps` 保存 reviewed trace 中每个 step 的结构化展开。
- 自动生成的 `reviewed_trace_id` 使用 `trace_` + 完整 `uuid4().hex`，并在生成时查重，避免自动提交覆盖已有 review。

### 5.3 CLI

```bash
python3 scripts/skill_trace/db.py init
python3 scripts/skill_trace/db.py insert-draft --draft artifacts/skill-trace-drafts/demo.json
python3 scripts/skill_trace/db.py get-review --reviewed-trace-id trace_xxx
```

### 5.4 测试

```bash
pytest tests/skill_trace/test_db_roundtrip.py
```

## 6. Milestone 3：审阅服务与 UI

### 6.1 `review_server.py`

使用 FastAPI + uvicorn 实现本地审阅服务。Milestone 3 不支持标准库或 Flask 替代方案；如果依赖缺失，先安装 `scripts/skill_trace/requirements.txt`。

接口：

```text
GET  /review/{draft_id}
GET  /api/drafts/{draft_id}
POST /api/reviews
GET  /api/reviews/{reviewed_trace_id}
GET  /healthz
```

### 6.2 `open_review.py`

职责：

1. 校验 draft。
2. 将 draft 暂存在本次 review server 进程内存中，不提前写数据库。
3. 启动 review server。
4. 自动打开浏览器。
5. 在终端打印 handoff 信息。

命令：

```bash
./.venv/bin/python scripts/skill_trace/open_review.py \
  --draft artifacts/skill-trace-drafts/demo.json \
  --codex-thread-id thr_demo \
  --port 8765
```

输出：

```json
{
  "status": "review_ui_ready",
  "review_url": "http://127.0.0.1:8765/review/draft_demo",
  "codex_thread_id": "thr_demo",
  "draft_id": "draft_demo"
}
```

### 6.3 `review.html`

MVP 用原生 HTML + JS，不引入 React。

页面包含：

- source panel：题目、解答、预期思路。
- steps table：step list。
- editor panel：当前 step 编辑。
- validation panel。
- submit button。

### 6.4 `review.js`

功能：

- 获取 draft。
- 渲染 steps。
- 编辑当前 step。
- 新增/删除 step。
- 上移/下移 step。
- 本地校验。
- POST review。

提交 payload：

```json
{
  "draft_id": "draft_xxx",
  "codex_thread_id": "thr_xxx",
  "reviewed_json": { "...": "..." },
  "reviewer_note": ""
}
```

提交成功展示：

```json
{
  "status": "reviewed",
  "problem_case_id": "case_xxx",
  "reviewed_trace_id": "trace_xxx",
  "codex_thread_id": "thr_xxx"
}
```

## 7. Milestone 4：Codex skill 集成

### 7.1 新增 `.codex/skills/math-skill-trace-ingestion/SKILL.md`

内容要固定：

- Use when：用户提供题目/解答/预期思路，要求技能节点、技能图谱、trace 入库、审阅。
- Skip when：用户只要求渲染 PDF、只要求普通解题、只要求出题。
- Workflow：
  1. 读取用户输入。
  2. 按 `docs/skill-graph-conceptual-model.md` 拆分 L3/L0/L1/L2 动作链。
  3. 生成 `SkillTraceDraft` JSON。
  4. 保存到 `artifacts/skill-trace-drafts/<draft_id>.json`。
  5. 调用 `./.venv/bin/python scripts/skill_trace/open_review.py --draft ... --codex-thread-id <thread_id>`。
  6. 返回 `codex_thread_id` 和 review URL。

### 7.2 Draft prompt

新增：

```text
prompts/skill_trace_draft_prompt.md
```

核心约束：

```text
不要直接写讲解。
不要直接出练习题。
不要创造复杂大图谱。
只输出 SkillTraceDraft JSON。
每个 step 只能表达一个动作。
每个 step 必须有 cognitive_layer 和 reuse_level。
`cognitive_layer` 和 `reuse_level` 的含义必须对齐 docs/skill-graph-conceptual-model.md。
必须体现用户预期解题思路。
必须标出学生原解法的问题点。
```

### 7.3 Codex thread id 获取

支持三种方式：

1. Codex SDK 调用时由 SDK 返回并注入 prompt/template。
2. Codex CLI 场景由用户或 wrapper 传入 `--codex-thread-id`。
3. 如果取不到，生成 `manual_<uuid>`，但 UI 警告“非真实 Codex thread id”。

## 8. Milestone 5：导出到现有 pipeline

### 8.1 `export_for_pipeline.py`

命令：

```bash
./.venv/bin/python scripts/skill_trace/export_for_pipeline.py \
  --reviewed-trace-id trace_xxx \
  --out-dir artifacts/<学生名>/YYYY-MM-DD-<内容>
```

输出：

```text
01-skill-trace.reviewed.json
01-structure-analysis.md
thread_handoff.json
```

### 8.2 `01-skill-trace.reviewed.json`

保持 reviewed JSON 原貌，加上 DB id：

```json
{
  "reviewed_trace_id": "trace_xxx",
  "codex_thread_id": "thr_xxx",
  "problem_case_id": "case_xxx",
  "problem_case": { "...": "..." },
  "trace_summary": { "...": "..." },
  "steps": ["..."]
}
```

### 8.3 `01-structure-analysis.md`

兼容现有 skill 的 Markdown 适配层：

```markdown
# 结构分析

## 题目
...

## 用户预期解题思路
...

## 已审阅技能 Trace 摘要

### 核心路径
1. L3: 先看要求 ED
2. L0: 定位 ED 所在对应线段
3. L1: 将 AE:ED 转为 2:3
4. L1: 将 AD 转为 5 份
5. L2: 计算 ED

## 学生主要卡点
...

## 讲解生成约束
- 必须先引导“要求什么”。
- 不要一开始提示设 x。
- 先给动作规范，再给算式。

## 练习生成约束
- 练习应围绕 reviewed trace 的 core steps。
- 每道题至少绑定一个 target step。
- 变式不要只换数，要改变一个主维度。
```

### 8.4 `thread_handoff.json`

```json
{
  "codex_thread_id": "thr_xxx",
  "problem_case_id": "case_xxx",
  "reviewed_trace_id": "trace_xxx",
  "artifact_dir": "artifacts/<...>",
  "next": {
    "explanation": "generate 02-student-explanation.assignment.yaml from reviewed trace",
    "assignment": "generate 03-adaptive-practice.*.assignment.yaml from reviewed trace"
  }
}
```

## 9. Milestone 6：Codex SDK 继续 thread

### 9.1 `codex_continue_thread.mjs`

薄封装，用于后续继续同一个 thread：

```javascript
// scripts/skill_trace/codex_continue_thread.mjs
import fs from "node:fs";
import { Codex } from "@openai/codex-sdk";

const args = parseArgs(process.argv.slice(2));
const prompt = fs.readFileSync(args["prompt-file"], "utf8");
const codex = new Codex();
const thread = codex.resumeThread(args["thread-id"]);
const result = await thread.run(prompt);
console.log(JSON.stringify({ thread_id: args["thread-id"], result }, null, 2));
```

实际 API 名称以当前 Codex SDK 为准；实现时要对照官方 SDK 文档调整。关键产品要求不是具体函数名，而是：

```text
保存 thread id -> 后续用 thread id resume/continue -> 在同一上下文生成 explanation/assignment
```

### 9.2 prompt 文件

`prompts/generate_explanation_from_reviewed_trace.md`：

```markdown
请读取当前仓库中的 reviewed trace artifact，并生成学生版讲解 YAML。

输入：
- 01-skill-trace.reviewed.json
- 01-structure-analysis.md

约束：
- 不重新自由分析题目。
- 必须沿用 reviewed trace 的 core steps。
- 每个提示先给动作规范，再给接近答案的提示。
- 输出 02-student-explanation.assignment.yaml。
```

`prompts/generate_assignment_from_reviewed_trace.md`：

```markdown
请基于 reviewed trace 和 02-student-explanation 生成自适应练习。

约束：
- 每道题标注 target trace step。
- 练习要覆盖 L3/L0/L1/L2 中最可能卡住的动作。
- 不要只换数。
- 学生版不含答案，教师版含 answer_key。
```

## 10. Milestone 7：测试与 demo

### 10.1 Demo 数据

新增：

```bash
python3 scripts/skill_trace/seed_demo.py
```

生成一个比例题 demo draft：

```text
AB=2, BC=3, AD=7, BE∥CD，求 ED。
```

预期 trace：

```text
L3: 先看要求 ED
L0: ED 在右侧分段中
L0: ED 对应 BC
L1: AE:ED = AB:BC = 2:3
L3: 选择份数法，不先设 x
L1: AD = 5 份，ED = 3 份
L2: ED = 7 × 3/5
```

### 10.2 E2E 流程

```bash
python3 scripts/skill_trace/seed_demo.py
./.venv/bin/python scripts/skill_trace/open_review.py --draft artifacts/skill-trace-drafts/demo_ratio.json --codex-thread-id thr_demo
# 浏览器审阅并提交
python3 scripts/skill_trace/export_for_pipeline.py --reviewed-trace-id trace_demo --out-dir artifacts/demo/2026-07-04-ratio-trace
```

检查输出：

```text
artifacts/demo/2026-07-04-ratio-trace/01-skill-trace.reviewed.json
artifacts/demo/2026-07-04-ratio-trace/01-structure-analysis.md
artifacts/demo/2026-07-04-ratio-trace/thread_handoff.json
```

### 10.3 自动测试

```bash
pytest tests/skill_trace
```

测试范围：

- contracts parse valid draft。
- validate rejects missing thread id。
- validate rejects duplicated order。
- db roundtrip preserves steps。
- export produces three files。

## 11. Codex 执行任务拆分

可以直接给 Codex 按下面顺序执行。

### Task 1：实现 contracts 和 validator

```text
实现 scripts/skill_trace/contracts.py 和 validate_trace.py。
加入 tests/skill_trace/test_contracts.py 和 test_validate_trace.py。
不要实现 UI。
```

### Task 2：实现 SQLite DB

```text
实现 scripts/skill_trace/db.py。
支持 init、insert draft、insert review、get review。
加入 test_db_roundtrip.py。
```

### Task 3：实现 open_review 和 review_server

```text
实现本地审阅 UI。
使用 FastAPI + 原生 JS。
open_review.py 启动服务并打开浏览器。
POST /api/reviews 后写 DB。
```

### Task 4：实现 export_for_pipeline

```text
从 reviewed_trace_id 导出：
01-skill-trace.reviewed.json
01-structure-analysis.md
thread_handoff.json
加入测试。
```

### Task 5：新增 Codex skill

```text
新增 .codex/skills/math-skill-trace-ingestion/SKILL.md。
固定输入、输出、脚本调用、验收。
```

### Task 6：Codex SDK handoff

```text
新增 scripts/skill_trace/codex_continue_thread.mjs 和 prompts。
实现 thread id 继续调用的薄封装。
实际 SDK 方法名以官方文档为准。
```

## 12. 预期最终使用方式

### 12.1 用户给 Codex 的自然语言

```text
请使用 math-skill-trace-ingestion：
题目：AB=2, BC=3, AD=7, BE∥CD，求 ED。
学生解法：设 ED=x，列 (7-x)/x=2/3。
我的预期：不要直接设 x。先看要求 ED，找 ED 对应 BC，推出 AE:ED=2:3，AD 是 5 份，ED 是 3 份。
请生成 SkillTraceDraft，并打开审阅界面。
```

### 12.2 Codex 应返回

```json
{
  "status": "review_ui_ready",
  "codex_thread_id": "thr_xxx",
  "draft_id": "draft_xxx",
  "review_url": "http://127.0.0.1:8765/review/draft_xxx",
  "draft_path": "artifacts/skill-trace-drafts/draft_xxx.json"
}
```

### 12.3 用户审阅提交后

UI 返回：

```json
{
  "status": "reviewed",
  "codex_thread_id": "thr_xxx",
  "problem_case_id": "case_xxx",
  "reviewed_trace_id": "trace_xxx"
}
```

### 12.4 后续生成

```text
继续 thread thr_xxx：
请读取 reviewed_trace_id=trace_xxx 对应的 01-skill-trace.reviewed.json，生成 02-student-explanation.assignment.yaml。
```

## 13. 完成定义

MVP 完成时，应满足：

1. 仓库中存在 `math-skill-trace-ingestion` skill。
2. 仓库中存在 `docs/skill-graph-conceptual-model.md`，并且 PRD、prompt、skill 解释两个坐标时引用同一套语义。
3. 能通过脚本打开审阅 UI。
4. 能编辑并提交 reviewed trace。
5. SQLite 中有持久记录。
6. 能导出 pipeline artifact。
7. 能返回并保存 Codex thread id。
8. 有一份比例题 demo 能跑通。
