# LangGraph + Langfuse 工作流框架化评估

## 0. 文档状态

- 状态：架构评审意见（decision input，非 source of truth）
- 日期：2026-08-03
- 评审对象：把 homework/explanation/assignment/diagram/latex 四个 skill 工作流做成 LangGraph 子图，并接入 Langfuse
- 参照实现：`codex/langgraph-question-ingestion-design` 分支的 `scripts/question_transcription/workflow/`

---

## 1. 结论

分三句话：

1. **抽取框架这件事成立，而且已经完成了一半**——但可复用的核心不是 LangGraph，是 `ArtifactRef` / `RunLayout` / `ArtifactStore` / ports+composition / 依赖边界测试这一层，约 950 行，其中 LangGraph 相关只占 `workflow/` 的 20%。
2. **Langfuse 值得马上做，而且不需要 LangGraph**——现有 Langfuse 接入总共约 80 行 OTel bootstrap + adapter 里一个 span，与 LangGraph 无耦合。diagram 侧已经有 `workflow_events.jsonl` 和 `performance_profile.json`，把它们导成 span 是天级工作量，这是"更好调试"这个诉求性价比最高的一步。
3. **四个子图的划分里，有两个不是"迁移"而是"从零写新 Agent"**——Explanation 和 Assignment 目前的 Python 代码量是 **0 行**，工作流全部活在 SKILL.md 的散文规则里，由带完整仓库上下文的交互式 Agent 执行。把它们 LangGraph 化不是重构，是替换执行模型，风险和成本被建议里的排序严重低估了。

一句话版本：**先做 Langfuse 和共享 artifact/failure 契约，LangGraph 只在"控制流确实是瓶颈"的地方上，而目前证据显示控制流不是这四个工作流的主要瓶颈。**

---

## 2. 证据：三类工作流的真实形态并不同构

建议书把四个 skill 当作同一种东西的四个实例。实际测量下来它们分属三种完全不同的形态：

| 维度 | question-ingestion（参照系） | diagram | explanation / assignment | latex |
|---|---|---|---|---|
| Python 实现 | 6,945 行 | 16,840 行 | **0 行**（内容生成） | ~1,460 行 |
| 工作流定义在哪 | 代码（`graph.py` + nodes） | 代码（batch/gate/workflow.py） | **SKILL.md 散文 + 自检清单** | shell + 脚本链 |
| 执行者 | 无人值守子进程 | 无人值守 + Codex 子 Agent | **交互式 Agent（用户在环）** | 确定性脚本 |
| 典型批量 | 8 worker × 数十份卷子 | 一份作业内 N 个 job | **一次一份作业** | 一次 2-3 个文件 |
| 已有 gate 结构化程度 | `PageTextFailure` typed | `DiagramGateCheck{name,status,message,refs}` | 只有 prose 自检清单 | 退出码 + stderr |
| 已有恢复机制 | sqlite checkpoint + 1,170 行恢复脚本 | 内容寻址 cache（cache identity hash） | 无（重跑 Agent） | 无（重跑，本来就幂等） |
| 已有可观测性 | OTel → Langfuse（driver 层） | `workflow_events.jsonl` + StageTimer | 无 | build.log |
| 测试 | 94 | ~150 | 0 | 少量路径测试 |

三个直接后果：

**(a) "把四个 skill 包进四个 graph"在两处不成立。** `grep` 遍历 `scripts/` 和 `.codex/skills/`，没有任何 Python 生成 `dual_explanation` / `route.steps` / `answer_key` 内容；只有 `validate_assignment.py`（校验）、`render_assignment.py`（渲染）、`check_latex.py`（lint）。Explanation 子图描述的 `内容规划 → 生成 YAML → gate → 定向修复`，其中"内容规划"和"生成"目前是 Claude/Codex 读 102 行 SKILL.md + 16 条自检清单现场完成的。

**(b) 甚至没有唯一的规格可以搬。** 同名 skill 在两个 runner 下已经分叉：

```
math-homework-pipeline            .claude 325 行 vs .codex 132 行
math-student-explanation-latex-data  .claude 359 行 vs .codex 102 行
math-structure-analysis           .claude 266 行 vs .codex 204 行
```

LangGraph 化之前必须先合并这两套规格，这本身是一个独立的、不小的任务。

**(c) 交互性是当前的质量机制，不是缺陷。** SKILL.md 明确写着 `流程不中断、不设置人工确认点`，以及 `若用户直接修改了渲染后的 .tex，先用 Git diff 提取其结构性反馈`。这个"用户改 .tex → 反馈回流到 skill 规则"的循环，是无头 graph run 会丢掉的东西。question-ingestion 能从 graph 化受益，很大程度是因为它是 **批处理**（`batch_transcribe_papers.py --workers 8`）；讲义生产是 **单件交互**。

---

## 3. 建议中站得住的部分

这些我完全同意，而且现有代码已经验证过：

- **只传 artifact 引用不传内容**。`WorkflowState` 已经严格做到，checkpoint 里没有页图/PDF/模型响应。这条是整个设计里最有价值的不变量，应该原样进共享框架。
- **provider 选择只在 composition root**。`bootstrap/composition.py` 是唯一 import `config` 的模块，并且有 `test_dependency_boundaries.py` 用 importlib 真实 import 图守着，不是 grep。这个测试模式应该复制到任何新框架里。
- **人工审核是显式 interrupt 而非异常分支**。已实现，且踩过的坑值得写进框架：`Command(resume=None)` 在 langgraph 0.2.76 会抛 `EmptyInputError`，所以需要一个非 falsy 的 `_RESUME_WAKE_ACK`；并且**每个 gate 在 resume 时重读磁盘 artifact**，wake 信号本身不携带审批决定。这条设计（wake ≠ approve）是对的，应该是框架级约束。
- **gate 输出结构化 failure**。diagram 侧的 `DiagramGateCheck{name, status: pass|warn|block, message, refs}` 已经是这个形状，只差 `severity` / `repair_owner` / `retryable`。
- **主图只看少量状态枚举**。方向对，但枚举本身要调整（见 §4.3）。

---

## 4. 需要修正的五点

### 4.1 "Diagram 最适合第一个 LangGraph 化" —— 我认为恰好相反

理由是：diagram 已经自己长出了 LangGraph 会提供的大部分东西，所以**边际收益最低、迁移成本最高**。

已有：DAG（`depends_on` 来自 `reuse_geometry_from`）、topological batch、内容寻址 cache（`cache_identity` 含 model_config + skill bundle version + workflow code version）、`JobPackageGate` / `ResolvedAssignmentGate`、`workflow_events.jsonl` 事件流、`performance_profile.json` 分阶段计时、`human_reviews/` + monitor server、按 job 的 subprocess 隔离。

成本：16,840 行、~150 个测试、独立的 `.venv-diagram` 解释器、Wolfram 子进程、每 job 一个 Codex thread。LangGraph 在这里主要能替换掉 `ThreadPoolExecutor` 和一段手写调度——而调度不是这部分出问题的地方。

**更重要的是：内容寻址 cache 已经是比 checkpoint 更好的恢复机制。** cache key 包含代码版本和模型配置，命中即跳过；checkpoint 只知道"这个 node 跑过了"。两者并存会制造歧义（见 4.2）。

### 4.2 幂等 + hash 跳过 会让 LangGraph checkpoint 部分冗余，必须只保留一个恢复权威

建议第 3 条说"checkpoint 恢复时先根据 artifact hash 判断是否需要重跑"。如果每个节点都幂等且 hash 寻址，那么 **artifact 树本身就是 checkpoint**，sqlite checkpoint 就退化成一个可能与磁盘不一致的第二真源。

这不是理论担忧，仓库里有代价明确的证据：

```
scripts/question_transcription/recover_failed_runs.py    562 行
scripts/question_transcription/resume_from_barrier.py    318 行
scripts/question_transcription/retry_page_text.py        290 行
                                                       ------
                                                       1,170 行
```

`recover_failed_runs.py` 的 docstring 直接说明了原因：**"Terminal LangGraph checkpoints cannot be resumed because they have no pending task. This command therefore replays only the deterministic downstream node sequence on the existing run artifacts."**

也就是说：上了 LangGraph 之后，失败恢复不但没有变成"免费"，反而额外写了 1,170 行绕过 checkpoint、直接在 artifact 上重放的代码。这个数字应该直接推翻"LaTeX 子图即使不用 Agent 也值得做成子图，以获得统一 checkpoint 和失败恢复"这条论证。

**框架层面的决定应该是：artifact 树是唯一恢复权威，checkpoint 只用于 interrupt/resume 的暂停点，不用于"跑到哪了"。**

### 4.3 四状态枚举丢信息

`completed / needs_review / failed_retryable / failed_terminal` 会把 ingestion 现有的 `waiting_for_source_review` 和 `waiting_for_final_review` 压成同一个 `needs_review`，而这两者的恢复动作完全不同（一个写 `review-resolutions.yaml`，一个写 `items/*/review.yaml`）。

建议改成正交两维：

```
status:        running | completed | needs_review | failed_retryable | failed_terminal
interrupt_kind: <子图自己定义的枚举>   # 仅当 status == needs_review
resume_contract: <需要人写哪个 artifact 才能继续>
```

主图仍然只 switch `status`，但恢复工具和 UI 有足够信息，不必反向猜。

### 4.4 LaTeX 不该做成子图，做成一个函数就够了

组成：`render_assignment.py` (442) + `validate_assignment.py` (509) + `check_latex.py` (157) + `sanitize_latex.py` (71) + `compile_latex.sh` (282)。全确定性、无状态、单机秒级、天然幂等（重跑覆盖同名 .tex/.pdf）。

给它套 StateGraph 得到的是：一份 state schema、一组 reducer、一个 checkpointer 生命周期、一层 dict↔Pydantic 序列化开销——换来的"事件和失败恢复"用一个带 `try/except` 和日志分类器的 60 行函数就能拿到，而且能被 Langfuse span 完整覆盖。

**它应该是共享框架的一个 `Stage`，被任何编排层直接调用，而不是一个 graph。**

### 4.5 迁移顺序建议倒过来

建议的顺序是"先定契约 → diagram 单 job → diagram batch → explanation/assignment → latex"，即从最重、最成熟的部分开始。但第 1 步"定义共享 `ArtifactRef/StageResult/Failure/Evidence`"在只有一个真实消费者时，必然定成 question-ingestion 的形状；等 diagram 接进来才发现要改，那时已经有代码依赖它了。

契约应该在**第二个消费者出现的同时**定型，而不是之前。

---

## 5. 关于 Langfuse：先清理，再推广

现状是两套并行的 tracing，其中一套是死代码：

**活的那套**（`run_live_paper.py:66-144`）：手写 OTel `TracerProvider` → OTLP HTTP → `{langfuse_host}/api/public/otel/v1/traces`，Basic Auth + `x-langfuse-ingestion-version: 4`；`_NodeSpan` 包住每个 graph node 的 stream chunk；`adapters/page_text/qwen.py` 里一个 `llm.qwen_ocr` span 记录 redacted prompt / completion / cache_hit；顺带用 `OTEL_EXPORTER_OTLP_*` 环境变量把 claude-agent-sdk 的自带 trace 汇到同一个 endpoint。这套是好的，设计上"OTEL 没配就自动 no-op"也对。

**死的那套**（`workflow/tracing.py`，132 行）：`TraceSink` / `NullTraceSink` / `_LangSmithTraceSink` / `default_sink()`。实测：

- `default_sink()` 全仓库无调用方；
- `flush()` 从未被调用；
- `RunLayout.trace_summary_path` 定义了但没人写；
- `deps.trace_sink` 在 composition 和 fakes 里都被传 `None`；
- 节点里 18 处 `with trace_event(...)` 全部写进一个进程内 list，然后被丢弃。

**行动项：** 删掉 `tracing.py` 和 18 处 `trace_event` 调用点，或者把它改造成 OTel span 的薄包装。**绝对不要把这个模式复制到另外四个子图里**——那会变成 5 份各自失效的 trace 抽象。

推广路径（不依赖 LangGraph）：

1. 把 `setup_otel()` + `_NodeSpan` 从 `run_live_paper.py` 提到 `scripts/infrastructure/observability/otel.py`（与 `scripts/infrastructure/ai/` 同层，已经是共享层了）。
2. diagram 的 `_emit_event(out_dir, event, **fields)` 已经是统一事件入口，且已有 `redact_secrets`。在它内部**同时**发一个 OTel span，一处改动即可让整个 diagram workflow 在 Langfuse 里可见，包括每个 Codex scene-writer 调用。
3. `StageTimer.measure(name)` 已经是 context manager，直接改成同时开 span，`performance_profile.json` 的分阶段耗时立刻变成火焰图。
4. explanation/assignment 因为跑在交互式 Agent 里，天然不产生 trace——这恰好是它们**先不该 graph 化**的另一个佐证：没有 trace 可看，Langfuse 也帮不上忙。

---

## 6. 建议的替代顺序

按"每单位工作量换到的调试能力"排序：

| # | 动作 | 规模 | 换到什么 |
|---|---|---|---|
| 1 | 提取 `infrastructure/observability/otel.py`，删除死的 `tracing.py` | ~150 行净减少 | 单一 trace 入口 |
| 2 | 在 `_emit_event` 和 `StageTimer` 内部发 span | ~40 行 | **整个 diagram workflow 在 Langfuse 可见**，含每个 Codex 调用 |
| 3 | 把 `DiagramGateCheck` 补齐为共享 `Failure{stage,code,severity,artifact,evidence,repair_owner,retryable}`，两侧 gate 都产出它 | ~200 行 | 结构化失败，可聚合、可路由 |
| 4 | 提取 `ArtifactRef` + `RunLayout` + `ArtifactStore` 到 `scripts/infrastructure/artifacts/`，让 diagram 也用 | ~300 行搬迁 | 统一 artifact 语义；**这时契约才有 2 个真实消费者** |
| 5 | 把 latex 链做成一个共享 `Stage` 函数（非 graph），带 span 和结构化 failure | ~150 行 | 可被任何编排层调用 |
| 6 | 只有到这里，才评估 diagram batch 是否值得换成 LangGraph | — | 届时已有数据说明调度是不是瓶颈 |
| 7 | explanation/assignment：**单独立项**，按"新建 Agent"而非"迁移"来估算 | 大 | — |

第 1-5 步全部不引入 LangGraph 依赖，全部可独立回滚，且每一步结束时仓库都是绿的。

---

## 7. 明确不建议的事

- **不要为了统一而把 latex 包成 graph。** 见 4.4。
- **不要在只有一个消费者时冻结共享契约。** 见 4.5。
- **不要同时保留 checkpoint 和 artifact-hash 两个恢复权威。** 见 4.2，代价已经量化为 1,170 行。
- **不要把 explanation/assignment 的 LangGraph 化和其余四步捆绑发布。** 它的失败模式（生成质量下降）不可通过回滚代码恢复，因为质量标准活在 prose 里。
- **不要在合并 `.claude` / `.codex` 双份 SKILL.md 之前动内容生成层。** 见 2(b)。

---

## 8. 一个便宜的证伪实验

在投入之前，用一天验证核心假设"LangGraph 能提升讲义工作流的可调试性"：

1. 选一份已完成的 artifact（如 `artifacts/刘濯嘉/2026-06-15-平行四边形矩形菱形存在性/`）。
2. 只做第 1-2 步（OTel 提取 + diagram 发 span），重跑它的 diagram 阶段。
3. 在 Langfuse 里回答这三个问题：哪个 job 最慢？哪次 scene-writer 输出被 audit 拒了、原因是什么？cache 命中率多少？

如果这三个问题在只加了 trace、没有任何 graph 改动的情况下就能答出来——那么 LangGraph 对于"调试"这个具体诉求就不是必需品，它的价值应该单独按"可恢复的长时批处理"来论证。而按 §2 的表格，真正符合这个描述的工作流，仓库里目前只有 question-ingestion 一个。
