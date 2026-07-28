# P4 汇合验收记录（2026-07-28）

## 1. 结论

P4 目前是**部分通过，不是整卷验收完成**：

- 同一道数学题分别走 DOCX/PDF adapter、共享 DraftAssembler 和真实
  expand → materialize → audit 链路后，来源无关的题目结构完全等价；
- 2024 年普陀区初三数学二模的 Q1–Q3 真实 DOCX 子集通过结构审计；
- 同卷 38 页、25 题的盲跑观察完整，但 17 题存在未解决的重叠窗口冲突，默认
  adapter 正确拒绝继续生成标准 Bundle；
- 因此不得把“25 题均形成完整候选”或“Q1–Q3 结构审计通过”表述为整卷通过。

## 2. 盲测约束

两个独立 agent 并行执行：

1. 同题 DOCX/PDF 等价测试；
2. 2024 年二模真实试卷验收。

真实试卷 agent 在冻结新产物前不得读取既有 staging、paper YAML、答案 YAML、
golden fixture 或其他题库结果。冻结后才由主 agent 将盲跑结果与既有结果对照。

真实输入为：

```text
documents/初三/2024届-上海市普陀区-初三二模数学-试卷及解析/source.docx
```

输入 SHA-256：

```text
4fe3d16978becbb1676840df00c818f061871bcfd7cfaee0ddbd2237d05ad317
```

## 3. 同题 DOCX/PDF 等价测试

测试位于：

```text
tests/question_transcription/test_same_question_equivalence.py
```

它没有复用现有 golden，而是在测试内构造一题含坐标图的数学题：

- DOCX 路径使用整页 evidence、`word/media` 原图和 `crop: full`；
- PDF 路径使用 region evidence、页面 bbox 和人工确认后的 region crop；
- 两路分别经过真实 transcription/image adapter；
- 两路分别进入同一个 DraftAssembler；
- 去除 evidence variant、来源路径和 crop 几何后，标准 Bundle 与 draft 的语义结构
  必须完全相等；
- 两份未归一化 draft 都实际执行 expand、materialize、audit；
- 最终题图像素必须一致。

结果：通过。

## 4. 真实试卷盲验

### 4.1 来源规范化

- LibreOffice 从原始 DOCX 重新生成 PDF；
- `pdftoppm` 重新生成 38 页 PNG；
- Provider 为 `mimo-v2.5`；
- 使用 19 个标准重叠窗口 `1–3, 3–5, …, 35–37, 37–38`，另加
  `20–22` 补充窗口；
- 每个已通过 contract 的窗口立即原子落盘，支持 `--page-start/--page-end`
  断点续跑。

### 4.2 Q1–Q3 子集

Q1–Q3 完成：

```text
MiMo observation
→ merge（3 题，0 conflict）
→ QuestionTranscriptionBundle
→ 空 ImageAttributionBundle
→ DraftAssembler
→ word evidence
→ expand
→ materialize
→ audit
```

结构审计结果：

```text
STAGING VALID: 2024-PUTUO-ERMO-BLIND-Q001-Q003 | items=3 | gate=structural
```

这只证明三题结构链路可运行，人工内容审核仍为 pending。

### 4.3 25 题整卷

整卷观察结果：

| 指标 | 结果 |
|---|---:|
| 页面 | 38 |
| 标准窗口 | 19/19 完成 |
| 补充窗口 | 1 |
| 最终完整题目候选 | 25 |
| incomplete question | 0 |
| 存在冲突的题 | 17 |
| merge 返回码 | 2 |
| 默认 adapter | 拒绝 unresolved conflict |
| assemble/materialize/audit | 未运行，未绕过门禁 |

冲突题号：

```text
3, 5, 6, 9, 11, 12, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25
```

冲突字段统计：

| 字段类别 | 涉及题数 |
|---|---:|
| content | 17 |
| evidence | 14 |
| question_type | 2 |
| section_ref | 1 |
| section_title | 1 |

该结果说明 partial window contract 和互补字段合并已经可用，但模型输出的跨窗口内容
一致性还不足以自动批准整卷。

## 5. 冻结后与已有结果对照

对照基线：

```text
artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2024-PUTUO-ERMO
```

该目录未发现独立人工 approval/review 凭证，因此这里只称为“已有结构化基线”，不把
它当作已经人工确认的标准答案。

对盲跑 merge 选中的 answer 字段做 LaTeX 格式归一后，表面上约 23/25 与基线一致。
但答案不一致时必须回到原始来源页裁决，不能默认任一侧正确。核对重新渲染的原始
DOCX 页面后，两个实质差异的归因如下：

| 题号 | 原始来源页 | 已有基线 | 盲跑选中候选 | 裁决 |
|---|---|---|---|---|
| Q18 | 第 18 页明确是“等腰三角形翻折、两圆外切、求 `BD`”，答案为 `$4-\frac{\sqrt6}{4}$` 或 `$4+\frac{\sqrt6}{4}$` | 是另一道“平面直角坐标系求 `\tan\angle CDE`”题，答案 `$8-3\sqrt7$` | 题干和答案均与原始第 18 页一致 | **已有基线题目错配，盲跑正确** |
| Q25 | 第 33、36、37 页均给出根式内 `-3x^3+36x^2+108x`，边数 `12` | 负号和边数均与来源一致 | 最终答案的边数 `12` 正确，但根式内选成 `+3x^3+36x^2+108x`；合并后的部分详解也混入错误候选 | **已有基线正确，盲跑候选选择错误** |

Q21 的多个窗口还出现 `CD/BD`、`3/4` 与 `2/3` 等不同候选；最终选中值与基线数值
一致。原始第 21 题解析也明确为 `BD=10`、`\tan C=2/3`，所以两边最终值都正确，
但不能据此忽略其他错误候选或绕过冲突门禁。

## 6. 工程判断

1. DraftAssembler、来源 adapter 和下游结构链路满足 P4 的“同题双来源等价”目标。
2. strict conflict gate 的行为正确；本次真实验收证明它确实阻止了错误内容进入 staging。
3. 不能用“最高自报置信度 + 字典序”自动决定数学内容。Q25 是直接反例。
4. 已有 staging 也不能充当无需核对的真值。Q18 的整题错配是直接反例。
5. 整卷进入标准 Bundle 前至少需要：
   - 对格式差异做公式/文本规范化，减少伪冲突；
   - 对实质冲突保留所有候选和对应页面证据，交给 agent 或人工选择；
   - 对最终答案增加来源答案页复核或独立数学一致性检查；
   - 选择完成后重新执行 assemble → materialize → audit → Review UI。

## 7. 回归测试

独立执行：

```text
./.venv/bin/python -m pytest \
  tests/question_transcription \
  tests/test_exam_source_pipeline.py \
  tests/test_pdf_question_bank_ingestion.py -q
```

结果：100 项测试全部通过。相关 Python 文件通过 `py_compile`，相关 diff 通过
`git diff --check`。

## 8. 冻结产物

本次临时盲测产物保存在：

```text
/tmp/p4-real-2024-putuo-blind/subset
/tmp/p4-real-2024-putuo-blind/full-partial-v2
```

子集文件清单摘要的 SHA-256：

```text
bc6ee103401e71f323b47c1b31549bef6c791e9312a1f14a9aac3df71ba11bc4
```

复核时，子集清单中位于共享 `windows-incremental` 目录的 4 个后续窗口文件已在整卷
续跑中被覆盖，因此整份子集清单不能再整体通过 `shasum -c`。Q1–Q3 子集目录内的
report、Bundle、draft、staging 和来源页仍逐项通过原清单校验。此处保留该事实，不把
清单文件自身的摘要误写成整份子集仍然完全不可变。

整卷文件清单摘要的 SHA-256：

```text
9d26f85bc3e3a775a4502f20effe36e116d5fb84ef0d45e06c537f66c004bde0
```

整卷清单当前逐项通过 `shasum -a 256 -c SHA256SUMS-FULL`。
