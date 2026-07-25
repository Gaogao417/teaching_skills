---
name: math-topic-question-bank
description: "从数学 explanation 或原卷图片建立可复用的单题库，并从题库抽取或按原卷顺序组装学生版/教师版。Use when: 用户要求专题题库、原卷图片题库、逐题来源凭证、批量保存题干与答案、以后随机抽题或还原整卷。Skip when: 用户只要当次 1-3 道自适应练习、只要讲解，或只要渲染现有 assignment.yaml。"
---

# math-topic-question-bank

## 职责

把已审核的 explanation 或不可变原卷归档适配成长期复用题库。题库中的每一道题都是独立、可验证、可直接抽取的学生/教师 assignment 单题包；抽题或还原整卷时只组合现成题，不重新生成题干、答案或图。

默认输出：

```text
artifacts/题库/<专题>/
├── question-bank.yaml
├── coverage-plan.yaml
└── items/
    ├── Q001/
    │   ├── teacher.plan.assignment.yaml
    │   ├── teacher.resolved.assignment.yaml
    │   └── student.resolved.assignment.yaml
    └── ...
```

详细字段读取 `references/question-bank-schema.md`。生成 30 题时读取 `references/generation-contract.md`；涉及图形时再读取 `references/diagram-contract.md`。需要分数、根式、勾股数或特殊角边长时，读取 `references/training-number-database.md`，只能选 review 后仍可用的数值组。

## 输入边界

- 专题模式必需：一份完整 explanation 文档，可为 Markdown、`02-student-explanation.assignment.yaml` 或 resolved YAML。
- 原卷归档模式必需：不可变的原题页图、官方解答页图，以及保存题号、页码和像素裁切框的来源记录。
- 可选：对应的 `01-structure-analysis.md`、model rules、年级与题型偏好。
- explanation 是本题库的教学范围和方法来源，不是要被改写成 30 份讲解。
- 不要求用户另给 structure analysis；若存在则用于补足变式边界和计算预算，若不存在则只依据 explanation 可见内容出题。

## 模式 A：建立或扩充题库

1. 全文读取 explanation，提取知识点、典型动作、前置动作、常见错误、表示方式和允许的计算范围。
2. 写 `coverage-plan.yaml`，先锁定 30 个题位，再写题。默认分布是基础 10、标准 12、挑战 8；同一题位只改变一个主维度。
   - 题位若使用数值库，先通过 `select_training_numbers.py` 取得未禁用条目，并在题位冻结 `database_id`、`family_id`、`entry_id`。
   - 不得直接使用 `training-number-review.yaml` 中已禁用的条目。
3. 为每个题位生成一个 `teacher.plan.assignment.yaml`。每个文件只含一道题；教师题块必须含答案和验算后的解析。
4. 题目需要图时声明 prompt/clean slot；只有教师解答确实需要辅助对象时再声明 solution/annotated slot。不得在 plan YAML 中写最终图片或 TikZ。
5. 用仓库解释器逐个校验 plan YAML：

   ```bash
   ./.venv/bin/python math-assignment-latex/scripts/validate_assignment.py <teacher.plan.assignment.yaml>
   ```

6. 对含 `diagram_slot` 的教师 plan 调用 `math-geometry-diagram-renderer`，得到 `teacher.resolved.assignment.yaml`。无图题可直接把已验证的教师 assignment 作为 resolved 单题包。
   - 默认执行“一题一图”：每道题必须拥有独立的 prompt job、独立的 solution job、独立的 resolved TikZ 路径和独立预览；不得在不同题目之间共享母图资产。
   - 同一题的 solution 必须通过 `reuse_geometry_from` 复用该题自己的 prompt 几何，再增加教师标注；不得复用其他题目的 prompt。
   - 规则化专题使用 `engine: geometric_scene` 配合 `engine_options.scene_payload`：程序确定性生成 GeometricScene spec，跳过模型推理，但仍交给 Wolfram 求解/校验，再逐题通过 TikZ、batch/gate/resolve。不要用 `renderer_spec` 绕过 Wolfram。
7. 从教师 resolved 单题包派生学生版，避免维护两套题干：

   ```bash
   ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/derive_student_assignment.py \
     <teacher.resolved.assignment.yaml> \
     --out <student.resolved.assignment.yaml>
   ```

8. 更新 `question-bank.yaml`。只有 30 个单题包都已 resolved、答案齐全、图形资产存在时，才把 `bank.status` 写为 `ready`。
9. 运行题库校验：

   ```bash
   ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/validate_question_bank.py \
     artifacts/题库/<专题>/question-bank.yaml
   ```

## 模式 B：从题库抽题出作业

使用脚本完成真正的随机抽取。不要让模型凭印象挑题，也不要在抽题阶段改题。

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/sample_question_bank.py \
  artifacts/题库/<专题>/question-bank.yaml \
  --count 5 \
  --output-dir artifacts/<学生名>/YYYY-MM-DD-<专题>抽题
```

- 不传 `--seed` 时每次随机；传入整数 seed 时可复现。
- 可用 `--difficulty foundation|standard|challenge` 或 `--tag <标签>` 限定候选。
- 输出 `sample.student.assignment.yaml` 与 `sample.teacher.assignment.yaml`。
- 抽题脚本会重定位 TikZ/图片路径并记录题库路径、题目 id 和 seed。
- 抽题后进入 `math-assignment-latex` 的 assignment review；用户确认后再渲染或编译。

## 模式 C：原卷图片入库与还原整卷

原卷图片题库先写入 `staging/<paper-id>/`，人工逐题批准前不得登记到正式
`question-bank.yaml`。单题必须同时保存可编辑转写与确定性原图凭证：

```text
staging/<paper-id>/
├── paper.yaml
├── paper-map.yaml                       # PDF 入库的题目/答案页与答案锚点
└── items/Q001/
    ├── source.yaml
    ├── review.yaml                         # 人工决定后才出现
    ├── assets/source-question.png
    ├── assets/prompt-*.png
    ├── assets/solution-*.png
    ├── assets/official-solution-*.png
    ├── teacher.resolved.assignment.yaml
    └── student.resolved.assignment.yaml
```

- `source.yaml` 使用 `math_exam_item_source/v1`，记录源页 SHA-256、裁切框、输出
  SHA-256、转写状态和内容哈希。
- PDF 入库使用 `math_exam_paper_map/v1` 的 `paper-map.yaml` 保存每题原题页、
  官方答案页以及答案 `start_anchor` / `end_anchor`；map 不保存像素框或哈希，
  精确来源证据仍以各题 `source.yaml` 为准。
- 题干与官方解答均转写为可编辑 LaTeX；官方错字、跳步或疑点只写入
  `solution_notes`，不得改写成公众号原文的一部分。
- 题目必要视觉内容用普通 `image_path`；原卷归档模式不使用 `diagram_slot`。
- 官方解答中的逐步图形另裁为 `assets/solution-*.png`，通过对应
  `solution_steps[].diagram_col.image_path` 紧跟该步显示；完整
  `official-solution-*.png` 仍作为逐字转写的来源凭证，两者不能互相替代。
  若图形与相邻正文在原页横向重叠，可在该裁图记录中用裁图坐标
  `whiteout_px` 确定性遮除相邻正文；不得遮除图形、点名或题解内容。
- 材料框、照片、数据表和图形强绑定的复杂原题可用 `stem_image` 直接显示确定性
  原题裁图，同时保留 `stem_latex` 供检索与审核。
- 教师版在文字解答后按顺序渲染 `source_solution_images`；学生版派生时必须移除
  答案、解答、校注和官方解答图。

逐题校验来源证据：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/validate_exam_source.py \
  staging/<paper-id>/items/Q001/source.yaml --repo-root .
```

一整卷全部获得当前 `content_hash` 对应的用户人工批准后，执行整卷原子晋升：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/promote_exam_paper.py \
  artifacts/题库/<原题库>/staging/<paper-id>/paper.yaml \
  artifacts/题库/<原题库>/question-bank.yaml
```

晋升脚本先复制并复验全部单题，最后只通过一次原子替换登记整卷；任何失败都不得
让部分题目出现在正式 manifest。正式入库后按 `paper.yaml` 还原学生版和教师版：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/assemble_exam_paper.py \
  artifacts/题库/<原题库>/papers/<paper-id>/paper.yaml \
  --output-dir artifacts/<输出目录>
```

## 题库 Review UI

需要逐题查看正式题库，或审核原卷 staging 的原题/转写与官方解答/转写时，启动 Review UI：

```bash
./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/open_question_bank_review.py
```

- 默认地址为 `http://127.0.0.1:8877/`，自动发现正式题库以及其
  `staging/*/paper.yaml`。
- 页面可用下拉框切换题库，并用题目列表或上一题/下一题逐题检查。
- 解析区会在对应文字步骤下显示 `solution_steps[].diagram_col` 的解析图；完整
  官方解答截图仍在来源凭证区显示。
- staging 的原题截图、题图、逐步解析图和官方解答原图都以可选中槽位显示：
  点击槽位使其高亮后，直接用 `⌘V` / `Ctrl+V` 粘贴教师手工截图；悬浮图片时
  右上角 `×` 可把图片移出槽位。题图缺失时显示 `+` 供教师补图；原题截图和
  官方解答原图是固定来源凭证，不显示新增槽位。Review UI 会把手工图保存为新的
  全图来源证据，同步 assignment 图片引用并刷新 `content_hash`；删除只移除
  证据/assignment 引用，不物理删除原图片文件。此前审核决定因此自动过期，
  必须重新核对。
- staging 页面可“通过”或“要求修改”；要求修改时必须填写具体意见。决定绑定内容
  哈希，文字或图片变化后旧决定自动显示为失效。
- 快捷键为 `A` 通过、`R` 要求修改、`←` 上一题、`→` 下一题；通过成功与实际
  翻页分别有确认音和翻页音。
- “通过”或“要求修改”保存成功后自动跳到下一道待审核、审核已过期或记录异常的
  题目；搜索到卷尾后从卷首继续，全部处理完成后停在当前题。
- 右上角“数库”跳到默认 `http://127.0.0.1:8876/`；数库页面的“题库”按钮可跳回。
- 两个地址都可分别用 `--number-review-url` 和 `--question-bank-review-url` 覆盖。

## 硬约束

- 题库保存“现成题”，不是保存 prompt 模板或变式规则后临时再生成。
- 每个 item 的学生版与教师版题干必须一致；学生版不得含答案、解析、solution 图或教学备注。
- 教师版必须含答案；`problem` / `short_answer` 必须含 `solution_steps`。
- 有“如图/图中/下图”或几何条件难以纯文字解析时必须有 prompt 图。
- 题库生成与作业抽题是两个阶段。抽题不得触发重新画图。
- 数值库选择发生在题库生成阶段；抽题不得换数、重新缩放或绕过 review 禁用状态。
- 不把 30 道题装进一个大 assignment 作为题库；一个坏题不能阻塞其余 29 题的维护和替换。
- 所有专题题库的题干都只保留三类信息：完成任务所必需的对象或情境、已知条件、学生要完成的目标。删除不影响作答的背景包装、重复构型描述、教学口吻、方法提示、中间步骤清单、验算要求和答案格式表演；这些内容放在 `teaching`、`solution_steps` 或答案区。
- 有题图时，图中已经清楚呈现的点序、共线关系和内外位置不再写入题干；只补充图上无法可靠表达的数学条件。
- 题干语言必须符合学生当前学段。初中几何不用集合记号 `\in`、`\cap` 表示点在线段上或两线相交，应写成“点 $D$ 在线段 $BC$ 上”“$AD$ 与 $BE$ 交于点 $P$”。
- 题干中的多任务必须都是训练目标。辨错题可以保留“判断并改正”，证明题可以保留证明目标；普通计算题直接问所求量，不附加“先写……再证明……最后验算”等过程指令。
- 题库学生版不预置 `hints`。单张原题图默认不写 caption；只有同题并列多图、且必须区分图意时才允许中性说明。不要借提示框或图注绕过简洁题干规则继续讲方法。
- 相似三角形求边题中，普通题直接点名要求哪条边；提高题可只给三条已知边，要求学生判断唯一可求边并算出长度。

## Handoff

- 生成图：`math-geometry-diagram-renderer`
- 审核抽题结果：`math-assignment-latex` 的 assignment review UI
- 渲染/编译：`math-assignment-latex`
