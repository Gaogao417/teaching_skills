# Diagram Workflow 时序图

## 参与者分类

| 类型 | 参与者 | 说明 |
|------|--------|------|
| **Skill** | `math-structure-analysis` | 结构分析 |
| **Skill** | `math-student-explanation-latex-data` / `math-practice-latex-data` | 生成 plan YAML + DiagramSlot |
| **Skill** | `math-homework-pipeline` | 端到端调度器，编排所有 diagram 阶段 |
| **Skill** | `math-yaml-review` | 渲染前 YAML 审查 |
| **Skill** | `math-assignment-latex` | resolved YAML → TeX/PDF |
| **Skill** | `math-homework-review` | 最终独立审核 |
| **Python** | `collect_diagram_jobs.py` | slot → jobs manifest |
| **Python** | `run_diagram_batch.py` | 按 job graph 调度单图任务 |
| **Python** | `workflow.py` | 单图 agentic 生成（Wolfram GeometricScene） |
| **Python** | `render_geometry_spec.py` | spec → SVG/PNG 确定性渲染 |
| **Python** | `build_diagram_artifacts.py` | 汇总所有 job 结果为 artifact manifest |
| **Python** | `resolve_assignment_diagrams.py` | plan YAML + artifacts → resolved YAML |
| **Python** | `check_diagram_gate.py` | required 图 / policy / 路径检查 |

## 时序图

```mermaid
sequenceDiagram
    autonumber

    participant Pipeline as 🎯 math-homework-pipeline<br/><b>SKILL · 调度器</b>
    participant Struct as 🔬 math-structure-analysis<br/><b>SKILL</b>
    participant LatexData as 📝 latex-data skills<br/><b>SKILL</b>
    participant Collector as 📦 collect_diagram_jobs.py<br/><b>PYTHON</b>
    participant Batch as ⚡ run_diagram_batch.py<br/><b>PYTHON</b>
    participant WF as 🧮 workflow.py<br/><b>PYTHON</b>
    participant Renderer as 🎨 render_geometry_spec.py<br/><b>PYTHON</b>
    participant ArtifactBuilder as 📋 build_diagram_artifacts.py<br/><b>PYTHON</b>
    participant Resolver as 🔗 resolve_assignment_diagrams.py<br/><b>PYTHON</b>
    participant Gate as 🚦 check_diagram_gate.py<br/><b>PYTHON</b>
    participant Review as 📖 math-yaml-review<br/><b>SKILL</b>
    participant LaTeX as 🖨️ math-assignment-latex<br/><b>SKILL</b>
    participant FinalReview as ✅ math-homework-review<br/><b>SKILL</b>

    %% ── S1: 结构分析 ──
    rect rgb(230, 245, 255)
        Note over Pipeline, Struct: S1 结构分析
        Pipeline ->> Struct: 调用 skill
        Struct -->> Pipeline: 01-structure-analysis.md
        Note right of Struct: 输出 diagram_plan_packet<br/>(needs_diagram, given_objects,<br/>clean_forbidden 等)
    end

    %% ── S2: 生成 plan YAML ──
    rect rgb(230, 255, 230)
        Note over Pipeline, LatexData: S2 批量生成 plan YAML
        Pipeline ->> LatexData: 传入 structure-analysis
        LatexData -->> Pipeline: assignment.plan.yaml
        Note right of LatexData: 包含 <b>DiagramSlot</b><br/>slot_id / variant / required<br/>layout_role / width_hint<br/>semantic_constraints<br/><i>不写 image_path</i>
    end

    %% ── S2.5: 收集 jobs ──
    rect rgb(255, 245, 230)
        Note over Pipeline, Collector: S2.5 Slot → Job 收集
        Pipeline ->> Collector: assignment.plan.yaml
        Collector ->> Collector: 扫描所有 diagram_slot
        Collector ->> Collector: 构建 job graph<br/>(depends_on / reuse_geometry_from)
        Collector -->> Pipeline: diagram_jobs.json
        Note right of Collector: <b>DiagramJobsManifest</b><br/>→ <b>DiagramJob[]</b><br/>job_id / slot_path / content_hash<br/>request_path / out_dir
    end

    %% ── S2.6: 批量生成 ──
    rect rgb(255, 230, 230)
        Note over Pipeline, Renderer: S2.6 批量 diagram 生成
        Pipeline ->> Batch: diagram_jobs.json
        loop 每个 job (按拓扑排序，prompt 并行)
            Batch ->> Batch: 生成 request.json
            Note right of Batch: <b>DiagramJobRequest</b><br/>teaching_intent / engine<br/>semantic_constraints<br/>reuse / engine_options<br/><i>不含 layout / image_path</i>

            Batch ->> WF: request.json
            activate WF
            WF ->> WF: text model 写 GeometricScene
            WF ->> WF: Wolfram 求解
            WF -->> Batch: workflow_result.json
            deactivate WF
            Note right of WF: <b>DiagramJobResult</b><br/>status / wolfram summary<br/>policy_warnings

            WF -->> Batch: final_renderer_spec.json
            Note right of WF: <b>GeometryRenderSpec</b><br/>points / segments / markers<br/>labels / teaching_focus

            Batch ->> Renderer: final_renderer_spec.json
            activate Renderer
            Renderer ->> Renderer: SVG 生成 → PNG 转换
            Renderer -->> Batch: renderer_result.json
            deactivate Renderer
            Note right of Renderer: <b>GeometryRendererResult</b><br/>image_path / preview_svg<br/>width_px / height_px / checks

            Batch ->> Batch: 输出到 jobs/<job_id>/
        end
        Batch -->> Pipeline: 所有 job 完成
    end

    %% ── S2.7: 汇总 artifacts ──
    rect rgb(245, 230, 255)
        Note over Pipeline, ArtifactBuilder: S2.7 Artifact 汇总
        Pipeline ->> ArtifactBuilder: jobs/ 目录
        ArtifactBuilder ->> ArtifactBuilder: 读取每个 job 的<br/>renderer_result.json<br/>计算 hash / 判断 bindable
        ArtifactBuilder -->> Pipeline: diagram_artifacts.json
        Note right of ArtifactBuilder: <b>DiagramArtifactsManifest</b><br/>→ dict[str, <b>DiagramArtifact</b>]<br/>key = diagram_ref<br/>status / image_path / artifact_hash<br/>bindable
    end

    %% ── S2.8: Gate 检查 ──
    rect rgb(255, 255, 220)
        Note over Pipeline, Gate: S2.8 Diagram Gate
        Pipeline ->> Gate: plan + jobs + artifacts + resolved?
        Gate ->> Gate: 检查 required 图 bindable<br/>检查 clean policy<br/>检查路径可访问<br/>检查 hash 一致性
        Gate -->> Pipeline: gate report
        Note right of Gate: <b>DiagramGateReport</b><br/>pass / warn / block<br/>→ <b>DiagramGateCheck[]</b>
        alt gate = block
            Pipeline -->> Pipeline: ⛔ 阻断渲染
        end
    end

    %% ── S2.9: 回填 resolved YAML ──
    rect rgb(220, 255, 240)
        Note over Pipeline, Resolver: S2.9 Plan → Resolved 回填
        Pipeline ->> Resolver: assignment.plan.yaml<br/>+ diagram_artifacts.json
        Resolver ->> Resolver: 按 slot_path 定位<br/>DiagramSlot → ResolvedDiagramImage
        Resolver -->> Pipeline: assignment.resolved.yaml
        Note right of Resolver: <b>ResolvedDiagramImage</b><br/>image_path / width / caption<br/>diagram_ref / diagram_job_id<br/>artifact_hash<br/><i>模板可直接消费</i>
    end

    %% ── S7: YAML 审查 ──
    rect rgb(240, 240, 255)
        Note over Pipeline, Review: S7 YAML 审查
        Pipeline ->> Review: assignment.resolved.yaml
        Review ->> Review: plan 审查: required slot 存在?<br/>prompt → clean 配对?<br/>resolved 审查: image_path 可访问?<br/>manifest 一致?
        Review -->> Pipeline: 审查结果
    end

    %% ── S8: LaTeX 渲染 ──
    rect rgb(255, 240, 240)
        Note over Pipeline, LaTeX: S8 LaTeX 渲染 + 编译
        Pipeline ->> LaTeX: assignment.resolved.yaml
        LaTeX ->> LaTeX: Jinja2 template → .tex
        Note right of LaTeX: 模板消费 diagram_col /<br/>diagram_row / type: diagram<br/>中的 image_path + width
        LaTeX ->> LaTeX: XeLaTeX / tectonic → .pdf
        LaTeX -->> Pipeline: .tex + .pdf
    end

    %% ── S9: 最终审核 ──
    rect rgb(240, 255, 240)
        Note over Pipeline, FinalReview: S9 最终审核
        Pipeline ->> FinalReview: artifact 目录
        FinalReview ->> FinalReview: 图是否完整可见?<br/>布局是否溢出?<br/>prompt 图是否泄露解答?
        FinalReview -->> Pipeline: 质量印象报告
    end
```

## 数据结构流转总览

```mermaid
flowchart LR
    subgraph plan ["📋 Plan 阶段"]
        DS[DiagramSlot]
    end

    subgraph batch ["⚡ Batch 阶段"]
        DJ[DiagramJob]
        DJR[DiagramJobRequest]
        DJRes[DiagramJobResult]
        GRS[GeometryRenderSpec]
        GRR[GeometryRendererResult]
    end

    subgraph artifact ["📦 Artifact 阶段"]
        DA[DiagramArtifact]
        RDI[ResolvedDiagramImage]
    end

    subgraph gate ["🚦 Gate 阶段"]
        DGR[DiagramGateReport]
    end

    DS -->|"collector<br/>扫描 slot"| DJ
    DJ -->|"batch runner<br/>生成 request"| DJR
    DJR -->|"workflow.py<br/>agentic 生成"| DJRes
    DJR -->|"workflow.py<br/>输出 spec"| GRS
    GRS -->|"renderer<br/>确定性渲染"| GRR
    GRR -->|"artifact builder<br/>汇总"| DA
    DJRes -->|"artifact builder<br/>汇总"| DA
    DS -.->|"gate 检查 required"| DGR
    DA -.->|"gate 检查 bindable"| DGR
    DS -->|"resolver<br/>绑定 artifact"| RDI
    DA -->|"resolver<br/>提供 image_path"| RDI
```

## 关键模块边界

### Skill 与 Python 的分工原则

| 原则 | Skill 负责 | Python 负责 |
|------|-----------|------------|
| **决策权** | 判断"哪里需要图"、"图的教学用途"、"失败策略" | 执行"生成这一张图"、"渲染这个 spec"、"检查这些路径" |
| **数据所有权** | 写入 DiagramSlot（声明意图） | 写入 DiagramJob / Artifact / GateReport（事实记录） |
| **可审计性** | skill 输出的 YAML 是人类可审查的计划 | Python 输出的 JSON 是机器可验证的 manifest |
| **幂等性** | skill 可能产生不同措辞 | Python 脚本对相同输入必须产生相同输出 |

### 调用方向

```text
math-homework-pipeline (skill, 调度器)
  │
  ├── S1  调用 math-structure-analysis (skill)
  │       └── 输出: diagram_plan_packet
  │
  ├── S2  调用 latex-data skills (skill)
  │       └── 输出: assignment.plan.yaml [DiagramSlot]
  │
  ├── S2.5 调用 collect_diagram_jobs.py (python)
  │        └── 输出: diagram_jobs.json [DiagramJobsManifest]
  │
  ├── S2.6 调用 run_diagram_batch.py (python)
  │        ├── 内部调 workflow.py (python) × N
  │        └── 内部调 render_geometry_spec.py (python) × N
  │        └── 输出: per-job files [DiagramJobRequest → DiagramJobResult + GeometryRenderSpec → GeometryRendererResult]
  │
  ├── S2.7 调用 build_diagram_artifacts.py (python)
  │        └── 输出: diagram_artifacts.json [DiagramArtifactsManifest]
  │
  ├── S2.8 调用 check_diagram_gate.py (python)
  │        └── 输出: gate report [DiagramGateReport]
  │        └── ⛔ block → 终止流水线
  │
  ├── S2.9 调用 resolve_assignment_diagrams.py (python)
  │        └── 输出: assignment.resolved.yaml [ResolvedDiagramImage]
  │
  ├── S7  调用 math-yaml-review (skill)
  │       └── 审查 plan + resolved YAML
  │
  ├── S8  调用 math-assignment-latex (skill)
  │       └── 输出: .tex → .pdf
  │
  └── S9  调用 math-homework-review (skill)
          └── 输出: 质量印象报告
```
