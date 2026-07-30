# 脚本架构梳理与重构方案

> 范围：math-assignment-latex 渲染工具并入 skill；题库工具全部收进 skill；根 scripts/ 与孤儿文件清理。
> 本轮只产出本方案，不动代码。执行时按文末分批进行。

## 0. 现状诊断（已逐项验证，非推断）

### 0.1 关于"题库工具混进 math-assignment-latex"的澄清

**不成立。** `math-assignment-latex/scripts/review_server.py` 对 `question_bank|exam_item|staging|bulk|approve|SourceQuestion` 的 grep 命中数为 0。它只做讲义/作业 YAML 的 LaTeX 渲染审核。题库审核 UI 实际在 `.codex/skills/math-topic-question-bank/scripts/question_bank_review_server.py`。

### 0.2 真正的三个结构性问题

**问题 A — 存在两套 `math-assignment-latex`，身份与代码分离**

| 位置 | 内容 | git | 谁在用 |
|---|---|---|---|
| 根 `math-assignment-latex/` | 8 脚本 + templates + texmf + references + 仅含生成物的 examples + 一份旧 `SKILL.md` | ✅ 跟踪 | `.codex` 下的 SKILL.md 用仓库相对路径 `math-assignment-latex/scripts/...` 引用 |
| `.codex/skills/math-assignment-latex/` | 仅 `SKILL.md` + `agents/`，**无 scripts** | ✅ 跟踪 | skill 系统加载此目录 |

skill 的"身份"和"代码"被拆进两个目录，仅靠路径字符串硬连。根目录和 `.codex` 目录中的两份 `SKILL.md` 内容已经分叉，迁移时不能把旧文件覆盖到新位置；以 `.codex/skills/math-assignment-latex/SKILL.md` 为权威版本，删除根目录旧副本。`.zcode/skills/math-assignment-latex` 是指向 `.codex/skills/math-assignment-latex` 的 symlink。

**问题 B — 两个平行 scripts 根，仅靠 subprocess 通信**

- `/scripts/`：题库录入 / 几何图 / 模型规则 / skill-trace / exam-source。无 `__init__.py`，只是 namespace 包。13 个散文件 + 5 个子包。
- `/math-assignment-latex/scripts/`：纯 LaTeX 渲染；templates/texmf 用相对路径定位，但 `compile_latex.sh` 还用固定层级推算仓库根和 `.venv`，并非完全自包含。
- 两者互不 import，只靠 `scripts/workflow_gate.py`、`scripts/diagram_workflow/live_assignment_diagram_e2e.py` shell out 调用。

**问题 C — 题库工具被劈成两半，靠 sys.path hack 粘合**

- 审核 UI / 契约 / sampler 主体在 `.codex/skills/math-topic-question-bank/scripts/`（24 个 py）。
- exam-source builder 在 `/scripts/`：`build_exam_source_items.py`、`normalize_staged_exam_items.py`、`recrop_exam_source_items.py`、`build_minhang_term.py`、`crop_assignment_assets.py`、`concatenate_sampled_assignments.py`。
- `/scripts/sample_mixed_question_banks.py:19` 与 `/scripts/generate_similarity_model_question_banks.py:20` 用 `sys.path.insert(0, ROOT/".codex/skills/math-topic-question-bank/scripts")` 桥接 —— 最易断的耦合。

### 0.3 顺带发现的噪声

7 个可清理候选文件未发现有效代码引用（历史日志中的提及不算运行时依赖）：

| 文件 | 性质 |
|---|---|
| `hd01_problems.json` | 独立数据 blob |
| `print-all.mjs` | 一次性 puppeteer 批打印脚本 |
| `transcription_output.md` | 临时转录输出 |
| `explanation样图.png`（1.3MB） | 散落大图 |
| `test_plot.pdf` | 临时测试图 |
| `一次函数练习.rar` | 压缩包（已被 .gitignore `*.rar` 忽略但文件还在） |
| `.tmp-fontconfig-xuhui.xml` | XeLaTeX/fontconfig 残留 |

`package.json` 和 `package-lock.json` **不属于孤儿文件**：`tests/e2e/test_question_bank_filters_ui.mjs` 直接 import `puppeteer`，并明确以仓库 `package.json` 作为依赖声明。二者保留；只单独删除无调用方的 `print-all.mjs`。

### 0.4 四套独立 FastAPI review UI（零共享代码）

| 文件 | 领域 |
|---|---|
| `math-assignment-latex/scripts/review_server.py` | 讲义/作业 YAML LaTeX 审核 |
| `scripts/skill_trace/review_server.py` | SkillTraceDraft JSON 审核（SQLite） |
| `.codex/skills/math-topic-question-bank/scripts/question_bank_review_server.py` | 题库/staging/bulk-approve |
| `.codex/skills/math-topic-question-bank/scripts/training_number_review_server.py` | 训练号游戏/审核 |

四套互相独立、无共享代码。本方案不合并它们（领域不同），但搬迁后各自留在正确归属内。

---

## 1. 目标布局

原则：**skill 自包含**。skill 自己的脚本进 skill 目录；skill 系统加载 `.codex/skills/*`，所以 skill 脚本的最终归宿是 `.codex/skills/<skill>/scripts/`。

```text
.codex/skills/math-assignment-latex/
  SKILL.md                      # 路径改为相对 skill 根
  agents/                       # 不动
  scripts/                      # ★ 新增：从根目录迁入全部 8 脚本
    render_assignment.py
    validate_assignment.py
    check_latex.py
    sanitize_latex.py
    batch_yaml_review.py
    review_server.py
    review_ui_common.py
    compile_latex.sh
    review_templates/           # 随 review_server 迁入
    review_static/              # 随 review_server 迁入
  templates/                    # ★ 从根目录迁入（render_assignment 依赖）
  texmf/                        # ★ 从根目录迁入（compile_latex.sh 依赖 ../texmf）
  references/                   # ★ 从根目录迁入（SKILL.md 引用）
  README.md
  requirements.txt

.codex/skills/math-topic-question-bank/
  scripts/                      # 已有 24 py，再吸收根 scripts/ 的题库脚本
    question_bank_review_server.py   # 已在
    ... (已有)
    # ★ 从 /scripts/ 迁入：
    build_exam_source_items.py
    normalize_staged_exam_items.py
    recrop_exam_source_items.py
    build_minhang_term.py
    crop_assignment_assets.py
    concatenate_sampled_assignments.py
    sample_mixed_question_banks.py          # 原 sys.path hack 改为同目录 import
    generate_similarity_model_question_banks.py  # 同上
    author_auxiliary_ratio_50_bank.py
    author_auxiliary_ratio_explanation_v2.py
    author_quadratic_completion_bank.py

scripts/                        # 瘦身后：只留跨 skill 的通用工具
  question_transcription/       # v1 转录管线，self-contained，暂留
  diagram_workflow/             # 几何图，暂留（可后续评估是否进 diagram-renderer skill）
  diagram_monitor/
  model_rules/
  skill_trace/
  workflow_gate.py              # 通用 gate，留
  extract_docx_simple.py        # 通用 DOCX 工具，留
  (题库相关 11 个文件全部迁出)
```

**搬迁后 /scripts/ 从 13 散文件降到 2 个**（`workflow_gate.py`、`extract_docx_simple.py`），其余 5 个子包保留。

根 `math-assignment-latex/examples/` 当前只有 PDF、PNG、日志、生成的 TeX 和复制出的 `.sty/.cls`，没有示例输入源。它不并入 skill；作为可再生成的构建输出删除。若以后补充真正的最小输入示例，再在 skill 内新建 `examples/`。

---

## 2. 关键约束（搬迁时必须遵守）

### 2.1 render_assignment.py 的 TEMPLATE_DIR 推算方式

`math-assignment-latex/scripts/render_assignment.py:24-25`：
```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "templates")
```
→ 模板必须在 `<skill根>/templates/`，即 scripts 的父目录。**迁移时 templates/ 必须与 scripts/ 平级放在一起。**

### 2.2 compile_latex.sh 对 texmf 的依赖

从 artifacts/build 日志可见，编译引用 `math-assignment-latex/scripts/../texmf/...`，即 scripts 父目录下的 `texmf/`。**texmf 必须随 scripts 一起迁。**

### 2.3 review_ui_common.py 的 REPO_ROOT

`review_ui_common.py:20`：`REPO_ROOT = SCRIPT_DIR.parents[1]`。迁移到 `.codex/skills/math-assignment-latex/scripts/` 后，`parents[1]` 变成 `.codex/skills/` 而非仓库根。**必须改为显式计算仓库根**：从脚本目录逐级向上查找仓库标记（支持 `.git` 为目录或 worktree 文件，并以根 `AGENTS.md` 作为辅助校验），找不到则明确报错，不静默使用错误目录。

### 2.4 compile_latex.sh 的 REPO_ROOT

`compile_latex.sh` 当前用 `SCRIPT_DIR/../..` 推算 `REPO_ROOT`，迁移后会得到 `.codex/skills`，导致 `${REPO_ROOT}/.venv/bin/python` 查找失败并静默回退到系统 `python3`。迁移时必须改成与 Python 脚本等价的向上发现逻辑，并在烟测中断言实际使用仓库 `./.venv/bin/python`。`LOCAL_TEXMF="${SCRIPT_DIR}/../texmf"` 保持不变。

### 2.5 题库脚本的 REPO_ROOT 与 sys.path

以下 7 个待迁脚本都把 `parents[1]` 当作仓库根，迁移后会错误指向 skill 根：

```
build_exam_source_items.py
recrop_exam_source_items.py
build_minhang_term.py
crop_assignment_assets.py
sample_mixed_question_banks.py
generate_similarity_model_question_banks.py
author_auxiliary_ratio_50_bank.py
```

在 `math-topic-question-bank/scripts/` 内增加一个小型公共 repo-root helper，上述脚本统一调用；不要分别改成另一个固定 `parents[N]`。为 documents/artifacts/data 三类默认路径各写至少一个回归断言。

`sample_mixed_question_banks.py`、`generate_similarity_model_question_banks.py` 迁入 skill scripts/ 后，与 `question_bank_contracts`、`sample_question_bank` 同目录，可直接 `from question_bank_contracts import ...`，删除 `sys.path.insert` 两行。

---

## 3. 影响面清单（搬迁必须同步改的引用点）

### 3.1 SKILL / 文档内的资源路径

当前扫描基线：

- `.codex/skills/**/*.md`：15 条 `scripts/` 引用；连同 `references/`、`templates/` 共 23 条。
- `.claude/skills/**/*.md`：11 条真实命令或 schema 引用。`.claude` 仍是已跟踪兼容入口，本轮同步更新，不能忽略。
- `docs/diagram-workflow-architecture.md`：6 条当前组件路径。
- 搬迁后的 `.codex/skills/math-assignment-latex/README.md`：内部命令和示例路径也要更新。
- `docs/archive/**` 作为历史快照不改，并在残留扫描中显式排除。

路径约定分两类：

1. 从仓库根执行的 shell 命令使用仓库相对路径 `.codex/skills/math-assignment-latex/scripts/X`。
2. SKILL.md 中供 agent 读取的 reference 使用相对 skill 根的 `references/X`；不要把 `.codex/...` 称为“绝对路径”。

迁移后对 `scripts|references|templates|texmf|examples` 全部做残留扫描，不能只 grep `scripts`。

### 3.2 Python 代码引用（subprocess 调用，2 个文件、5 个调用点）

```
scripts/workflow_gate.py:155,158                                # os.path.join(repo_root,"math-assignment-latex","scripts",...)
scripts/diagram_workflow/live_assignment_diagram_e2e.py:240,249,260  # REPO_ROOT/"math-assignment-latex"/"scripts"/...
```
**改法**：路径前缀改为 `.codex/skills/math-assignment-latex/scripts`。

### 3.3 测试引用（2 处对 latex，以及现有题库测试入口）

对 latex：
```
tests/test_math_topic_question_bank.py:202   # REPO_ROOT/"math-assignment-latex/scripts/validate_assignment.py"
tests/test_exam_source_pipeline.py:32        # sys.path.insert ROOT/"math-assignment-latex/scripts"
```
对题库（**这些路径不变**，因为题库脚本本就在 .codex/skills 下，只是从 /scripts/ 迁入更多文件）：
```
tests/test_question_bank_review_cache.py:27
tests/test_similarity_model_question_banks.py:12-13
tests/test_similarity_triangle_database.py:12-13
tests/test_training_number_database.py:15-16
tests/test_question_bank_review.py:15
tests/test_question_bank_review_filters.py:21
tests/test_math_topic_question_bank.py:11,185,235
tests/e2e/test_question_bank_filters_ui.mjs:36
tests/test_exam_source_pipeline.py:13,28
tests/test_pdf_question_bank_ingestion.py:10
tests/test_promote_exam_paper.py:13
```
**注意**：`test_exam_source_pipeline.py` 同时引用了 latex scripts(行32) 和题库 scripts(行13)。搬迁后两者路径都要核对。

### 3.4 docs / 文档引用

`artifacts/` 下大量 `01-structure-analysis.md` 提到 "math-assignment-latex render/compile" —— 这些是**工作流描述文字**，不是路径，**无需改**。
需要同步更新 `.codex/skills/math-topic-question-bank/docs/review-ui-question-level-images-plan.md` 和 `docs/diagram-workflow-architecture.md` 中的真实组件路径。`docs/archive/**` 保持历史原貌。

---

## 4. 分批执行计划

每批独立可验证、可回滚；每批开始先保存 `git status --short` 基线，每批结束确认只出现本批预期差异，并跑 `./.venv/bin/python -m pytest -q`。当前工作树已有大量未跟踪 artifacts/documents，不能把“工作树全局干净”作为验收条件；必须精确 staging，禁止顺手纳入无关文件。

### 批次 0｜清理已核实噪声
1. 保留 `package.json`、`package-lock.json`，确保 puppeteer E2E 依赖仍可复现。
2. 删除 7 个已核实候选：`hd01_problems.json`、`print-all.mjs`、`transcription_output.md`、`explanation样图.png`、`test_plot.pdf`、`一次函数练习.rar`、`.tmp-fontconfig-xuhui.xml`。
3. 删除根目录散落的 `.DS_Store`（顶层已有一个）。
4. 验证：puppeteer 仍能从保留的 npm 清单解析；`git diff --name-status` 只包含预期删除；pytest 绿。
5. commit：`[workflow] repo-root: remove orphaned scratch files and OS cruft`

### 批次 1｜LaTeX 渲染工具并入 skill
1. `git mv math-assignment-latex/{scripts,templates,texmf,references,README.md,requirements.txt} .codex/skills/math-assignment-latex/`。
2. 以 `.codex/skills/math-assignment-latex/SKILL.md` 为权威版本；删除内容已经分叉的根 `math-assignment-latex/SKILL.md`，不得覆盖目标 SKILL。
3. 删除仅含生成物的 `math-assignment-latex/examples/`，再清理 `.DS_Store`，确认根目录消失。
4. 为 Python 脚本加入可靠的 repo-root helper，修 `review_ui_common.py`；为 `compile_latex.sh` 加入等价的 shell 根发现逻辑。
5. 按 §3.1 同步更新 `.codex`、`.claude`、README 和非归档架构文档中的 scripts/references/templates 路径。
6. 改 §3.2 两个 Python 调用方的路径前缀。
7. 改 §3.3 两个测试的路径，并新增 repo-root/compile 虚拟环境定位测试。
8. 验证：全仓残留扫描（排除 `.git/`、`docs/archive/`、`artifacts/`）；pytest；使用一个最小 YAML 跑完整 `validate → render → check → compile` 烟测，断言使用仓库 `.venv` 且 PDF 生成。
9. commit：`[workflow] math-assignment-latex: inline render/compile scripts into skill`

### 批次 2｜题库工具全部收进 skill
1. 明确 `git mv` §1 列出的 11 个题库脚本（不是 13 个）到 `.codex/skills/math-topic-question-bank/scripts/`；顶层只保留 `workflow_gate.py`、`extract_docx_simple.py`。
2. 新增公共 repo-root helper，把 §2.5 的 7 个脚本从 `parents[1]` 切换到 helper。
3. 删 `sample_mixed_question_banks.py`、`generate_similarity_model_question_banks.py` 中的 `sys.path.insert`，改为同目录直接 import。
4. 核对 `tests/test_exam_source_pipeline.py` 和题库相关测试路径；新增迁移后 documents/artifacts/data 默认路径测试。
5. 验证：先跑 `test_question_bank_*`、`test_exam_source_pipeline`、`test_similarity_*`、`test_training_number_*`、`test_math_topic_question_bank`，再跑全量 pytest；从仓库根以外的 cwd 各烟测一个迁移脚本，防止把 cwd 偶然当 repo root。
6. commit：`[workflow] question-bank: consolidate exam-source builders into skill, drop sys.path hacks`

### 批次 3（可选，后续）｜scripts/ 剩余整理
评估 `diagram_workflow/`（含 `geometry_diagram_workflow/` 内嵌的 `.codex/skills/` 怪味）是否进 `math-geometry-diagram-renderer` skill；为保留的子包补 `__init__.py`/README。本批不在本轮承诺范围。

---

## 5. 风险与回滚

| 风险 | 缓解 |
|---|---|
| `review_ui_common.REPO_ROOT` 层级算错导致 review UI 崩 | 用显式 `find_repo_root()`（向上找 `.git`，并用根 `AGENTS.md` 辅助校验），写单元测试覆盖 |
| `compile_latex.sh` 迁移后找不到仓库 `.venv` 而静默回退系统 Python | shell 端显式发现仓库根；烟测断言解释器路径并完成 PDF 编译 |
| 7 个题库脚本的 `parents[1]` 在迁移后指向 skill 根 | 统一 repo-root helper；从非仓库 cwd 运行默认路径测试 |
| SKILL / README / `.claude` / docs 路径漏改导致调用 404 | 按 §3.1 基线更新；对全部搬迁目录做全仓残留扫描，归档和 artifacts 显式排除 |
| texmf/templates 未随 scripts 一起迁导致编译断裂 | 批次1用 `git mv` 整组迁移，迁移后立即烟测一次完整 render→compile |
| 题库测试因 sys.path 改动红 | 批次2先单跑 §4 列出的题库重点测试集合，绿了再全量 |
| 当前分支正是 `fix/question-bank-review-solution-steps-and-bulk-approve`，且工作树有大量未跟踪产物 | 先完成/保存当前分支工作，再创建专用 `codex/scripts-reorganization` 分支或 worktree；每批只精确 stage 预期文件 |

回滚：每批一个 commit，`git revert <sha>` 即可回到上一状态。

---

## 6. 待确认（执行前需你拍板）

1. **路径写法**：已建议定案——仓库根执行的命令写 `.codex/skills/...`；skill 内 reference 写 `references/...`。两者都不称为“绝对路径”。
2. **批次3 是否纳入本轮**：当前定为“可选/后续”。`diagram_workflow` 体量大且有内嵌 skill 目录的怪味，建议单独评审。
3. **根 `math-assignment-latex/`**：已建议定案——迁移后彻底删除；`.codex/skills/math-assignment-latex/SKILL.md` 是唯一权威版本。
4. **兼容入口 `.claude/skills`**：本计划默认继续支持并同步路径。如果准备正式废弃 `.claude`，应另立清理批次，不应在本次迁移中让它静默失效。
