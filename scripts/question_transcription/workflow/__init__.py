"""题库录入 LangGraph / LangSmith 工作流（G0 骨架）。

本 package 是 ``docs/question-ingestion-architecture.md`` 所描述的当前实现；
目标分层与迁移顺序见 ``docs/question-ingestion-implementation-plan.md``。
LangGraph 管理完整生命周期（启动、分支、逐页并发、汇合、重试、缓存、两个审核
interrupt、终止条件）；模型 provider 与现有确定性脚本通过业务端口执行具体工作；
文件 artifact 保持权威、可审核、可重建。

依赖方向（固定不变量）::

    CLI / deployment config
      -> bootstrap/composition.py   # 唯一选择 adapter 的模块
        -> build_graph(bound deps)  # 业务节点只见已绑定端口
           graph nodes -> business ports <- provider/script adapters

- :mod:`.contracts`：跨 DOCX/PDF 的 domain 生命周期类型 + artifact 引用，**不含**
  provider/host 选择；权威 Pydantic schema（``SourcePaper``、
  ``QuestionTranscriptionBundle`` 等）复用
  :mod:`scripts.question_transcription.{source_contracts,contracts,
  review_issue_contracts}`，不在此重定义。
- :mod:`.orchestration.langgraph.state`：``WorkflowState`` 只保存小型可序列化状态与
  ``ArtifactRef``，不保存页图/PDF/模型响应大对象。
- :mod:`.ports`：业务端口（``Protocol``），fake adapter 与真实 adapter 实现同一端口。
- :mod:`.bootstrap.config`：``RuntimeAdapterConfig``，仅 ``composition`` import；state/node
  不得 import。
- :mod:`.bootstrap.composition`：唯一 adapter 选择与装饰（retry/cache/limiter）。
- :mod:`.graph`：``build_graph(deps)``，StateGraph + 两条 interrupt 点。
- :mod:`.bootstrap.cli`：``start / status / resume``。
- :mod:`.infrastructure.artifact_store` / :mod:`.checkpoint` / :mod:`.tracing`：内核支撑。
- :mod:`.adapters`：provider/script 适配器（优先 import 现有 Python 函数）。
- :mod:`.nodes` / :mod:`.subgraphs`：业务节点与子图。
- :mod:`.testsupport`：fake adapter（无任何网络调用）。
"""

GRAPH_VERSION = "question-ingestion-langgraph/v0"
