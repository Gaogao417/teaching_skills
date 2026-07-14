---
name: math-topic-question-bank
description: "从数学 explanation 文档或 explanation assignment YAML 批量生成可复用的专题题库，并从题库抽取现成题目组成学生版/教师版作业。Use when: 用户要求专题题库、一次生成约 30 道题、保存题干与答案、保存学生 prompt 图与教师 solution 图、以后随机抽题出作业。Skip when: 用户只要当次 1-3 道自适应练习、只要讲解、只要渲染现有 assignment.yaml，或没有可作为教学范围依据的 explanation 文档。"
---

# math-topic-question-bank

## 职责

把一份已审核的 explanation 适配成长期复用的专题题库。题库中的每一道题都是独立、可验证、可直接抽取的学生/教师 assignment 单题包；抽题阶段只组合现成题，不重新生成题干、答案或图。

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

- 必需：一份完整 explanation 文档，可为 Markdown、`02-student-explanation.assignment.yaml` 或 resolved YAML。
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

## 硬约束

- 题库保存“现成题”，不是保存 prompt 模板或变式规则后临时再生成。
- 每个 item 的学生版与教师版题干必须一致；学生版不得含答案、解析、solution 图或教学备注。
- 教师版必须含答案；`problem` / `short_answer` 必须含 `solution_steps`。
- 有“如图/图中/下图”或几何条件难以纯文字解析时必须有 prompt 图。
- 题库生成与作业抽题是两个阶段。抽题不得触发重新画图。
- 数值库选择发生在题库生成阶段；抽题不得换数、重新缩放或绕过 review 禁用状态。
- 不把 30 道题装进一个大 assignment 作为题库；一个坏题不能阻塞其余 29 题的维护和替换。

## Handoff

- 生成图：`math-geometry-diagram-renderer`
- 审核抽题结果：`math-assignment-latex` 的 assignment review UI
- 渲染/编译：`math-assignment-latex`
