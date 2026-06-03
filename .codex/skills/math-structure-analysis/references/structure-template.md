# Structure Analysis Template

Use this full template when writing `01-structure-analysis.md`.

```markdown
# 结构分析：<题目短标题>

## 原题
<完整题目；必要时补充图形文字描述>

## 一、题目场景
- 数学对象：
- 变量/参数：
- 函数/图形：
- 已知条件：
- 要求目标：

## 二、核心结构
- 表面考点：
- 本质考点：
- 一句话问题模式：

## 三、关键转化
- 最关键的转化：
- 为什么降低计算量：
- 不转化时的低效路径：

## 四、标准路径骨架
1. 先做什么：
2. 再做什么：
3. 建立什么关系：
4. 如何求解：
5. 需要检查什么：

## 四点五、标准完整解与验算
- 关键交点/关键量：
- 面积/方程/关系式：
- 完整求解过程：
- 最终答案：
- 排除值：
- 退化情形：
- 验算：
- 本题最短可靠路径：

## 五、出题人逻辑
- 诱导学生硬算的位置：
- 真正的捷径：
- 训练的可迁移能力：

## 六、学生卡点预测
- 读题/入手动作卡点：
- 建模/关系入口卡点：
- 求解/检查卡点：

## 七、变式原则
- 核心不变量：
- 表层特征：
- 可变维度：
- 深化阶梯：
- 允许的变换：
- 禁止的变换：
- 表征切换：
- 包装方式：
- 近迁移例子：
- 远迁移例子：
- 反例/伪变式：

## 八、计算复杂度预算
- 原题计算层级：
- 允许小步上升到：
- 禁止引入的计算负担：
- 必须保留的可见支架：

## 九、推荐讲题任务包
- 建议的本轮教学入口：
- 本题讲解目标：
- 不要直接讲的抽象话：
- 必须先问的问题：
- 关键讲解顺序：
- 最适合的具体数值例子：
- 讲到哪里停下来让学生回答：

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：
- 若卡在建模或关系入口，出什么题：
- 若卡在求解和检查，出什么题：
- 若原题已稳，如何小步迁移：
- 若结构识别已稳，如何深化/抽象/包装：
- 禁止出的跑偏变式：

## 十点五、推荐图形请求包（可选）
- 是否需要图：
- 图形类型：`synthetic_geometry` / `coordinate_geometry` / `function_graph` / `auto`
- 用图意图：`student_explanation` / `practice_prompt` / `teacher_reference`
- 需要出现的对象：
- 需要突出给学生看的关系：
- 图中不能暗示的错误性质：
- 图失败时的降级方案：

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "",
  "core_transformation": "",
  "solution_skeleton": ["", "", ""],
  "canonical_solution": {
    "key_quantities": [],
    "equation": "",
    "answer_set": [],
    "excluded_values": [],
    "degenerate_cases": [],
    "verification": "",
    "shortest_reliable_path": ""
  },
  "common_blockers": {
    "read_context_or_find_entry": [],
    "build_relation": [],
    "solve_and_check": []
  },
  "variation_rules": {
    "core_invariant": "",
    "surface_features": [],
    "variation_dimensions": [],
    "depth_ladder": [],
    "allowed_transforms": [],
    "forbidden_transforms": [],
    "cognitive_load_budget": "",
    "representation_options": [],
    "packaging_options": [],
    "near_transfer_examples": [],
    "far_transfer_examples": [],
    "non_examples": []
  },
  "complexity_budget": {
    "original_level": "",
    "max_next_step": "",
    "forbidden_load": [],
    "required_scaffolds": []
  },
  "explanation_task_packet": {
    "target_teaching_entries": [],
    "goal": "",
    "avoid_abstract_phrases": [],
    "must_ask_first": [],
    "teaching_sequence": [],
    "concrete_probe_example": "",
    "pause_points": []
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": [],
    "build_relation_tasks": [],
    "solve_and_check_tasks": [],
    "transfer_tasks": [],
    "hidden_structure_or_reverse_tasks": [],
    "forbidden_variations": []
  },
  "diagram_request_packet": {
    "needs_diagram": false,
    "diagram_type": "synthetic_geometry | coordinate_geometry | function_graph | auto",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": [],
      "segments": [],
      "curves": [],
      "constraints": []
    },
    "teaching_focus": [],
    "must_not_imply": [],
    "fallback": "textual_diagram_description"
  }
}
```
```
