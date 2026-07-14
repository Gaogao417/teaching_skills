# Question Bank Schema

题库清单使用 `math_topic_question_bank/v1`。路径都相对 `question-bank.yaml` 所在目录。

```yaml
schema: math_topic_question_bank/v1
bank:
  id: parallel-line-ratio
  topic: 平行线对应边比例
  grade: 八年级
  subject: 数学
  source_explanation: ../../专题/某目录/02-student-explanation.resolved.assignment.yaml
  status: ready            # plan | ready
  target_count: 30
items:
  - id: Q001
    title: 基础比例识别
    question_type: fillin  # choice | fillin | problem | short_answer
    difficulty: foundation # foundation | standard | challenge
    skill_tags: [比例式识别, 对应边]
    variation_dimension: changed_numbers
    diagram_requirement: prompt_and_solution # none | prompt_only | prompt_and_solution
    student_assignment: items/Q001/student.resolved.assignment.yaml
    teacher_assignment: items/Q001/teacher.resolved.assignment.yaml
    weight: 1.0
    enabled: true
```

## Ready 的含义

`bank.status: ready` 时必须同时满足：

- `items` 数量等于 `target_count`，默认 30。
- item id 唯一，格式为 `Q001`、`Q002` 等。
- 每个 student/teacher 文件存在，且各自只有一道 practice 题。
- 学生版无 `answer`、`explanation`、`solution_steps`、`teaching`。
- 教师版有 `answer`；解答题另有 `solution_steps`。
- 两版的题型和题干一致。
- 文件中不再残留 `diagram_slot`。
- `prompt_only` 有学生 prompt 图和教师 prompt 图；`prompt_and_solution` 另有教师 solution 图。
- 所有 `image_path` / `tikz_path` 指向真实资产。

`plan` 状态允许文件尚未 resolved，但不能用于随机抽题脚本。

## 单题 assignment

每个 item 的 assignment 只允许一个题目 block，block id 与 item id 相同。教师版可以额外带一个 `answer_key` section 和 solution 图；这些不是第二道题。
