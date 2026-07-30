# Review UI 题目级图片管理修改计划

## 1. 修改目标

Review UI 只按题目管理图片，不再要求用户把解答图关联到某个
`solution_steps[index]`。

页面保留三块：

1. 题图：可新增、替换、移除；
2. 解答图：可新增多张、替换、移除；
3. 原题来源与官方解答整页：只读来源凭证。

解题步骤继续正常显示文字，但不参与图片编辑。

## 2. 最小改动原则

本次不增加 YAML 字段，不增加 API，不修改 assignment schema，不做存量审计或迁移。

直接复用现有能力：

- 题图使用现有 `prompt` 图片目标；
- 解答图使用现有 `official_solution` 图片目标；
- 解答图继续保存到现有 `source_solution_images`；
- 来源记录继续保存到现有 `source.yaml.crops.official_solution`；
- 教师版已经会在文字解答后渲染 `source_solution_images`；
- 学生版派生已经会移除 `source_solution_images`；
- 现有图片写接口已经支持 `official_solution` 的新增、替换和删除。

这里的“官方解答”整页凭证仍由 `word_evidence.official_solution` 提供，因此开放
`source_solution_images` 的裁图编辑不会删除原始整页来源。

## 3. 前端修改

### 3.1 题图

- 保留现有题图区域；
- 无图时明确显示“添加题图”；
- 有图时显示“替换题图”和“移除题图”；
- 点击槽位后继续使用 `⌘V` / `Ctrl+V` 粘贴。

本轮不增加文件选择器，避免扩大改动。

### 3.2 解答图

在解题步骤之后增加独立的“解答图”图库：

- 使用单题详情已有的 `official_solution_previews`；
- 空图库也显示“添加解答图”；
- 已有图片可逐张替换或移除；
- 点击空白区域时选中追加位置；
- 图片编辑目标统一使用 `official_solution`；
- 不再给 `solution_steps[].diagram_col` 渲染可编辑槽；
- 不显示“step 1”“解析图 1”或“属于哪一步”等交互。

已有 `solution_steps[].diagram_col` 仍可作为只读内容显示，避免改变旧题的视觉结果；
Review UI 不再通过它新增或替换图片。

### 3.3 来源凭证

- 顶部“原题来源”和“官方解答”胶囊继续打开整页来源图；
- 胶囊保持只读；
- 可编辑“解答图”指裁出的题目级解答图片，与整页来源凭证分区显示。

### 3.4 提示文案

- 题图：“点击选中，粘贴题图”；
- 解答图：“点击选中，粘贴解答图”；
- 保存成功：“解答图已保存，原审核已过期”；
- 保存失败：直接显示服务端返回原因。

## 4. 后端修改

不新增路由，不修改请求格式。

继续调用现有接口：

```text
POST   /api/banks/{bank_id}/items/{item_id}/images/prompt/{index}
DELETE /api/banks/{bank_id}/items/{item_id}/images/prompt/{index}

POST   /api/banks/{bank_id}/items/{item_id}/images/official_solution/{index}
DELETE /api/banks/{bank_id}/items/{item_id}/images/official_solution/{index}
```

现有接口已经完成：

- 图片解码和安全检查；
- 追加或替换 `source.yaml.crops.official_solution`；
- 同步 `teacher.resolved.assignment.yaml` 的 `source_solution_images`；
- 重新派生学生版；
- 刷新 `content_hash`；
- 使旧 review 自动过期；
- 返回更新后的单题详情。

后端只需确认单题详情为每个 `official_solution_previews` 返回现有的
`edit_target` 和 `edit_index`；若已经返回，则无需修改 Python。

## 5. 契约文档修改

只修改 Review UI 的交互说明：

- 手工补充解答图按题目管理；
- 前端不要求选择解题步骤；
- `source_solution_images` 是题目级解答图片列表；
- `word_evidence.official_solution` 是不可变整页来源凭证；
- `solution_steps[].diagram_col` 保留给既有逐步教学图和旧数据，不作为 Review UI
  的图片编辑入口。

不修改 assignment schema。

## 6. 预计涉及文件

主要修改：

- `.codex/skills/math-topic-question-bank/static/question-bank-review.js`
- `.codex/skills/math-topic-question-bank/static/question-bank-review.css`
- `.codex/skills/math-topic-question-bank/templates/question-bank-review.html`
- `.codex/skills/math-topic-question-bank/SKILL.md`
- `tests/test_question_bank_review.py`

仅在详情数据缺少编辑元数据时修改：

- `.codex/skills/math-topic-question-bank/scripts/question_bank_review_server.py`

明确不修改：

- `.codex/skills/math-assignment-latex/references/assignment-schema.md`
- `.codex/skills/math-assignment-latex/scripts/validate_assignment.py`
- `.codex/skills/math-assignment-latex/templates/exam-zh-practice.tex.j2`
- `.codex/skills/math-topic-question-bank/scripts/derive_student_assignment.py`

## 7. 实施步骤

1. 在 HTML 中增加独立“解答图”区域。
2. 前端用 `official_solution_previews` 渲染可编辑图库。
3. 把图库的新增、替换、删除接到现有 `official_solution` 接口。
4. 移除解题步骤下方的可编辑空图槽和粘贴提示。
5. 保留旧逐步图的只读显示。
6. 更新 Review UI 契约文档。
7. 补充回归测试并在真实浏览器中验证。

## 8. 测试范围

- 无题图时添加题图；
- 替换和移除题图；
- 无解答图时添加第一张；
- 连续添加多张解答图；
- 替换和移除指定解答图；
- 0、1、多条解题步骤都不影响解答图入口；
- 解题步骤中的旧图只读显示；
- 官方解答整页胶囊仍可查看且不可编辑；
- 图片变化后旧审核决定过期；
- 学生版不含 `source_solution_images`；
- 正式题库不显示图片编辑入口。

## 9. 验收标准

1. 用户只需知道当前是哪一道题，即可添加题图和解答图。
2. 页面不再要求选择解题步骤。
3. 不增加字段，不增加 API，不迁移存量数据。
4. 教师版继续在文字解答后显示解答图。
5. 原题和官方解答整页来源凭证不受图片编辑影响。
6. 现有后端测试、前端回归和真实浏览器验证全部通过。
