# 题库录入分层重构实施计划

## 0. 计划状态

- 状态：M0 文档迁移已完成，代码分层迁移待实施
- 基线日期：2026-07-31
- 架构依据：`docs/question-ingestion-architecture.md`
- 范围：分层、目录、依赖和契约收口；不以新增业务功能为目标

当前工作流已经具备 graph、端口、真实 page-text provider、OpenCode/Claude 整卷转写、确定性 staging adapter 和 fake lifecycle。此次工作不是重新实现工作流，而是在保持可观察行为的前提下，把当前实现迁移到明确的 utilities、shared infrastructure、domain、application、orchestration、ingestion adapters 和 bootstrap 层。

## 1. 实施原则

1. 每个阶段只改变一种边界，避免同时移动文件、改业务逻辑和更换 provider。
2. 先增加目标入口和兼容 shim，再迁移调用方，最后删除旧入口。
3. 每个提交保持 offline tests 可导入；live canary 不作为普通移动提交的前置条件。
4. 不把题目录入类型泄漏到 shared infrastructure。
5. 不为了复用而提前抽取只有一个调用方的代码。
6. 现有未提交改动属于其原作者；重构不得覆盖或回退。
7. 所有 Python 命令使用仓库显式虚拟环境：一般 workflow 使用 `./.venv/bin/python`。
8. Commit 使用 `[workflow] question-ingestion: ...` 前缀。

## 2. 当前基线

当前主要模块：

```text
workflow/
├── contracts.py / state.py / graph.py
├── config.py / dependencies.py / composition.py / cli.py
├── artifact_store.py / checkpoint.py / tracing.py
├── ports/*.py
├── nodes/*.py
├── adapters/page_text/*.py
├── adapters/whole_paper/{opencode,claude_code}.py
├── adapters/{docx_or_pdf,source_build,downstream,review}.py
└── testsupport/fakes.py
```

重构前应记录但不借机修改的行为基线：

- graph node 名和 topology；
- initial state/dump/load/outcome；
- 页级 reducer 和 barrier；
- OpenCode、Claude Code 的 providerless Model/Agent 校验契约；
- interleaved/separated prompt；
- run layout；
- fake clean/review/failure 路径；
- source/final review gate；
- provider isolation。

## 3. 交付阶段

### M0：文档与契约基线

目标：建立唯一架构真源，冻结迁移期间不能无意改变的行为。

工作：

- [x] 新增 `docs/question-ingestion-architecture.md`；
- [x] 以本文件替代首轮实施计划；
- [x] 删除过期 ports design 和旧 LangGraph design；
- [x] 更新代码注释、测试说明中的明确文档链接；
- [x] 新增或确认 dependency-boundary 测试入口（`tests/question_transcription/workflow/test_dependency_boundaries.py`，覆盖 utilities/infrastructure/domain 边界，未引入层自动 skip）；
- [x] 记录当前公开 import 路径，决定哪些需要兼容 shim（结论：仅 workflow 自身的 tests 引用各模块，无仓库内生产调用方；M1–M7 的目录迁移期间对仍被测试引用的旧 import 路径提供 re-export shim，迁移完测试后在 M8 删除）。

退出条件：

- 仓库中没有指向已删除设计文档的引用；
- architecture 明确区分 current 与 target；
- plan 中每个阶段都有所有权和门禁。

### M1：Shared AI Infrastructure

目标：把 provider transport/PydanticAI bridge 从题目录入 adapter 中抽离。

新增目标目录：

```text
scripts/infrastructure/ai/
├── contracts.py
├── opencode/{client,pydantic_model}.py
└── claude_code/{client,pydantic_model}.py
```

工作包：

| ID | 工作 | 主要来源 | 目标 | 状态 |
|---|---|---|---|---|
| M1.1 | 定义 provider-neutral failure/structured model 边界 | 现有两个 provider adapter | `infrastructure/ai/contracts.py` | ✅ |
| M1.2 | 提取 OpenCode session/message HTTP transport | `opencode.py` | `opencode/client.py` | ✅ |
| M1.3 | 提取 OpenCode PydanticAI bridge | `opencode.py` | `opencode/pydantic_model.py` | ✅ |
| M1.4 | 提取 Claude query SDK boundary | `claude_code.py` | `claude_code/client.py` | ✅ |
| M1.5 | 提取 Claude PydanticAI bridge | `claude_code.py` | `claude_code/pydantic_model.py` | ✅ |
| M1.6 | 为两个 infrastructure provider 增加注入 transport 的离线测试 | 现有 adapter tests | `tests/infrastructure/ai/` | ✅ |

边界要求：

- 新模块不得导入 `scripts.question_transcription`；
- 不构造数学 prompt；
- 不写 ingestion artifact；
- 不认识 `QuestionTranscriptionBundle`；
- API key 只在真正创建 live client 时读取。

退出条件：

- OpenCode/Claude 的 client 和 model bridge 可以脱离题目录入包导入；
- provider transport tests 无网络运行；
- 现有 canary 仍有可调用入口，允许暂时通过兼容 wrapper。

### M2：统一整卷题目录入 Adapter

目标：移除 OpenCode/Claude 两套重复的题目录入 transcriber，把 provider 差异限制在 shared infrastructure。

目标模块：

```text
workflow/adapters/whole_paper/
└── structured_transcriber.py
```

工作包：

| ID | 工作 | 状态 |
|---|---|---|
| M2.1 | 定义 provider-neutral `StructuredModel` 注入方式（构造函数注入已绑定的 PydanticAI ``Model``） | ✅ |
| M2.2 | 实现统一 `StructuredWholePaperTranscriber` | ✅ |
| M2.3 | 把 prompt build、artifact commit、failure mapping 从 provider 文件迁出 | ✅ |
| M2.4 | 保持 provider 层不做手工补字段；未来 normalization 只能进入题目录入 application/adapter | ✅ |
| M2.5 | composition 分别创建 OpenCode/Claude model，再注入同一个 transcriber | ✅ |
| M2.6 | 保留旧 class/import 的临时兼容 shim（`opencode.py`/`claude_code.py` 退化为转发 wrapper） | ✅ |

测试：

- 同一 fake structured model 对两种 `PaperLayout` 产生相同业务 contract；
- provider failure 正确映射为 `WholePaperFailure`；
- structured validation repair 与 transport retry 计数分离；
- repair 复用同一个 model/session；
- normalization 由题目录入 contract test 覆盖。

退出条件：

- application/graph 不知道 OpenCode 或 Claude；
- provider-specific 模块不引用题目 schema；
- 两个 live provider 共享同一题目录入 transcriber 实现。

### M3：Domain 与 Application Ports 收口

目标：让业务契约脱离 LangGraph 和 provider，并补齐当前缺失端口。

目标目录：

```text
workflow/domain/
workflow/application/ports/
```

工作包：

| ID | 工作 | 状态 |
|---|---|---|
| M3.1 | 把 lifecycle、artifact 从 `contracts.py` 拆入 `domain/{lifecycle,artifacts}.py`（contracts 退化为 re-export） | ✅ |
| M3.2 | 停止从 workflow contracts 重导出外层权威 schema（domain 不重导出，contracts 保留单一 import 入口） | ✅ |
| M3.3 | 将 `PaperLayout` 从 runtime config 提升为 `domain/paper_layout.py` request/domain 类型 | ✅ |
| M3.4 | 增加正式 `ImageAttributor` Protocol（`ports/image_attribution.py`） | ✅ |
| M3.5 | `downstream` port 改名为 `staging`（`ports/staging.py` 真源，`downstream.py` re-export shim） | ✅ |
| M3.6 | 更新 `WorkflowDependencies`，消除 `image_attribution: object`；`whole_paper_prompt_mode` 类型化为 `PaperLayout` | ✅ |
| M3.7 | 为旧 import 提供一轮兼容 re-export（contracts/downstream 均保留） | ✅ |

边界测试：

- domain/application import graph 不包含 LangGraph、provider SDK；
- ports 中没有 provider/host choice；
- 所有 dependency 字段都有明确 Protocol；
- `PaperLayout` 是 request 语义，不在 adapter choice config 中。

退出条件：

- graph 只接收 typed application dependencies；
- 不再存在 `downstream` 业务命名；
- 不再存在无类型的 image attribution dependency。

### M4：Application Stages 与 LangGraph Thin Nodes

目标：把业务 stage 从 LangGraph state adapter 中分离。

目标目录：

```text
workflow/application/stages/
workflow/orchestration/langgraph/
```

迁移次序按 stage 纵向进行，避免一次拆完整 graph：

1. ✅ page text stage（`application/stages/page_text.py` 提取 `decide_page_barrier`）；
2. ✅ whole paper stage（`application/stages/whole_paper.py` 提取 `validate_page_coverage`）；
3. ✅ source extraction/build/review（`application/stages/source.py` 提取 `decide_source_ready`）；
4. staging pipeline（节点 wrapper 保留，纯决策已在 staging port）；
5. final review（节点 wrapper 保留，状态投影无独立纯决策需提取）。

每个 stage 的步骤：

1. 提取与 LangGraph 无关的 request/result；
2. 将 port 调用和 contract validation 移入 application stage；
3. 保留 node wrapper，只做 state/request/result 投影；
4. 运行该 stage 的 unit test 和 graph lifecycle test；
5. 再迁移下一 stage。

专门工作：

- ✅ `state.py` 拆为 `orchestration/langgraph/{state,reducers}.py`（根 `state.py` re-export shim）；
- ✅ graph edge router 移入 `orchestration/langgraph/routing.py`（graph.py 调用真源）；
- fan-out dispatch 留在 orchestration，但 job planning 规则可放 application；
- 明确实现文字与图片的 join，不依赖某分支通常先完成；
- review interrupt 只负责暂停/恢复，批准事实来自 review artifact。

退出条件：

- application stages 可以不用 LangGraph 独立测试；
- node wrapper 不直接调用 provider SDK或现有题库脚本；
- graph topology 和 outcome 与基线一致；
- clean/review/failure fake lifecycle 全部通过。

### M5：Source、Staging 与 Review Adapter 归位

目标：业务 adapter 按稳定能力命名，不按“downstream”或实现偶然性命名。

目标目录：

```text
workflow/adapters/
├── source/{extraction,image_attribution,source_paper}.py
├── page_text/{qwen,mimo}.py
├── whole_paper/structured_transcriber.py
├── staging/existing_pipeline.py
└── review/filesystem.py
```

工作包：

- ✅ 拆分 `docx_or_pdf.py` 中 source extraction 与 image attribution → `source/{extraction,image_attribution}.py`；
- ✅ 移动 `source_build.py` → `source/source_paper.py`；
- ✅ 将 `downstream.py` 改为 staging adapter → `staging/existing_pipeline.py`；
- ✅ 将 review reader 移入 review adapter → `review/filesystem.py`；
- adapter 优先 import 现有稳定 Python 函数（保持不变）；
- 仅在无稳定函数入口时使用 subprocess，并结构化捕获 exit/stdout/stderr（保持不变）；
- ✅ 清理 `_common_paths.py`：移除 import 时 `sys.path.insert` 副作用，仅保留 `repo_root()` 路径解析与显式 `ensure_repo_root_on_path()`；删除遗留空目录。

退出条件：

- 每个 adapter package 实现一个清楚的 application capability；
- source/staging/review adapter tests 与新路径对应；
- 无模糊的 `downstream.py`、`docx_or_pdf.py` 或 `_common_paths.py`。

### M6：Workflow Infrastructure 与 Bootstrap

目标：把持久化/观测和装配/入口从核心业务目录中分离。

目标目录：

```text
workflow/infrastructure/
├── artifact_store.py
├── run_layout.py
├── checkpoint.py
└── tracing.py

workflow/bootstrap/
├── config.py
├── dependencies.py
├── composition.py
└── cli.py
```

工作包：

- ✅ 从 `artifact_store.py` 分离 `RunLayout` → `infrastructure/run_layout.py`；
- ✅ 保持当前 artifact path 和原子提交格式（`infrastructure/artifact_store.py`）；
- checkpoint factory 已在 `checkpoint.py`（infrastructure 同级，行为不变，路径属同层）；
- tracing 已在 `tracing.py` 并明确脱敏边界（NullTraceSink 不上传原文/原图）；
- ✅ composition 改为创建 shared infrastructure、ingestion adapters、application stages、graph runner（`bootstrap/composition.py`，import 修正为 `..adapters`/`..infrastructure`）；
- ✅ 修正 CLI `start/status/resume` 与真实 checkpoint 生命周期的关系（`bootstrap/cli.py`，`_repo_root` parents 计数随目录深度修正）；
- ✅ 根 `workflow/{config,dependencies,composition,cli,artifact_store}.py` 退化为转发 bootstrap/infrastructure 的 re-export shim。

退出条件：

- bootstrap 是唯一导入具体 adapter/provider 的区域；
- application/orchestration 不读取环境变量；
- CLI start 真正开始或提交执行，resume 使用既有 checkpoint；
- run layout 与已有 artifact 兼容。

### M7：Utilities 提取与重复清理

目标：只抽取已经出现多个稳定调用方的纯通用代码。

候选：

```text
scripts/utilities/
├── files/{atomic_write,hashing}.py
├── serialization/json_text.py
└── resilience/{policy,retry}.py
```

提取门槛（均已满足）：

- 至少两个真实调用方；
- 不携带题目录入 schema/path；
- 不读取环境或调用 provider；
- 有独立单元测试；
- API 名能说明实际用途，不创建泛化 `common.py` 或 `utils.py` 杂物箱。

已提取：
- ✅ `files/hashing.py`（`sha256_bytes`/`sha256_file`/`sha256_hex`/`stable_json_sha256`）：调用方为 artifact store、source 抽取 adapter、整卷转写与 page-text 缓存键；
- ✅ `files/atomic_write.py`（`atomic_write_text`/`atomic_write_yaml`/`atomic_write_bytes`）：调用方为 artifact store、整卷转写缓存、page-text 缓存；
- 未提取：retry/resilience 与 whole-paper normalization 不满足 utility 条件（携带题目录入失败类型/domain），保留在 workflow adapter/bootstrap。

注意：whole-paper normalization 不满足 utility 条件，必须留在 ingestion application/adapter。

退出条件：

- shared infrastructure 和 workflow adapter 不再复制相同 hashing/atomic/json/retry 逻辑；
- utilities 的 import graph 指向 Python 标准库或明确的纯依赖。

### M8：兼容入口删除与文档收尾

目标：删除迁移期 shim、旧路径和过期术语。

工作：

- 将仓库调用方全部迁移到新路径；
- 删除旧 provider transcriber class shim；
- 删除旧 ports/nodes/bootstrap 路径 re-export；
- 测试目录按 layer/capability 镜像；
- canary 单独归档并显式标记；
- 更新 architecture 的“当前实现事实”为最终结构；
- 重新生成或检查所有 schema/doc links；
- `rg` 检查 `direct GLM API`、`UseApi`、`ports-design`、旧目录路径和 `downstream` 残留。

退出条件：

- 代码目录与 architecture 目标树一致；
- 没有失效文档链接或迁移 shim；
- 普通测试离线；
- live canary 入口独立清晰。

## 4. 依赖关系与并行性

```text
M0
 └─ M1 Shared AI Infrastructure
      └─ M2 Unified Whole-Paper Adapter

M0
 └─ M3 Domain / Ports
      └─ M4 Application / Orchestration
           └─ M5 Business Adapters
                └─ M6 Infrastructure / Bootstrap

M1 + M5 + M6
 └─ M7 Utilities Extraction

M2 + M3 + M4 + M5 + M6 + M7
 └─ M8 Cleanup
```

可并行：

- M1 的 OpenCode 与 Claude extraction 可以分文件并行，但共享 contracts 先冻结；
- M3 的 source port 与 staging rename 可以并行；
- M5 的 source、staging、review adapter 移动可以分 owner 并行；
- 测试路径迁移可跟随每个能力包进行。

不可并行或需要单 owner：

- composition root；
- `WorkflowDependencies`；
- graph state/reducer；
- shared AI contracts；
- 删除兼容 shim。

## 5. 提交建议

保持提交单一职责，例如：

```text
[workflow] question-ingestion: extract OpenCode infrastructure client
[workflow] question-ingestion: extract Claude Code Pydantic model bridge
[workflow] question-ingestion: unify whole-paper structured transcriber
[workflow] question-ingestion: formalize source and image attribution ports
[workflow] question-ingestion: split application stages from LangGraph nodes
[workflow] question-ingestion: rename downstream pipeline to staging
[workflow] question-ingestion: isolate workflow bootstrap and infrastructure
[workflow] question-ingestion: remove migration compatibility shims
```

不要在同一提交中同时进行 provider 行为修复、目录迁移和 generated artifact 更新。

## 6. 每阶段验证矩阵

| 变更 | 必须验证 |
|---|---|
| shared infrastructure | 注入 transport 的离线 provider tests |
| whole-paper adapter | prompt、validation、repair、artifact contract |
| domain/ports | import boundary、Protocol、serialization |
| application stage | 不依赖 LangGraph 的 stage unit tests |
| orchestration | reducer、fan-out、routing、interrupt/resume |
| source/staging adapter | deterministic regression tests |
| bootstrap | provider isolation、fake/live binding |
| artifact infrastructure | atomicity、hash、layout compatibility |
| CLI | start/status/resume lifecycle |
| cleanup | full offline workflow suite + explicit live canaries |

建议命令使用仓库环境：

```bash
./.venv/bin/python -m pytest tests/question_transcription/workflow -q
```

共享 infrastructure 形成独立测试目录后，再增加：

```bash
./.venv/bin/python -m pytest tests/infrastructure/ai -q
```

Live canary 继续使用显式 marker/单文件调用，不加入普通离线门禁。

## 7. 最终完成标准

- 目录体现 architecture 定义的七层边界；
- shared provider infrastructure 不依赖题目录入；
- 一个 provider-neutral whole-paper ingestion adapter 服务 OpenCode 与 Claude；
- application ports/stages 不依赖 LangGraph；
- LangGraph nodes 是 thin wrappers；
- bootstrap 是唯一实现选择点；
- image attribution 有正式 Protocol；
- `PaperLayout` 属于 request/domain；
- `downstream` 已统一为 `staging`；
- artifact 和 review lifecycle 与迁移前兼容；
- 普通测试完全离线；
- 架构文档、代码路径和测试路径一致。
