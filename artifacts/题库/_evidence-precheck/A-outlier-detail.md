# A 卷 outlier 诊断明细 (outlier detail)

只读诊断：每卷仅读取 representative `paper.draft.yaml`，提取 25 题
`question_word_evidence` 首页 (question_starts) 与
`official_solution.word_evidence` 首页 (solution_starts)，
检测破坏升序 / 跳进答案区的 outlier，并用主仓库
`word_evidence_pages.coerce_question_seeds(layout='separated')` 模拟钳位。
**未修改任何 draft / source.yaml。**

---

## 2013-CHANGNING-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,1,1,1,1,2,2,2,2,2,2,2,2,3,3,3,21,4,4,4,5,5,6,7
```

**solution_starts 全序列 (按题号):**

```
8,9,9,10,11,11,13,13,13,14,15,15,16,17,18,19,20,21,23,23,24,26,28,31,35
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q018 | 17 | 21 | answer-block | 7 |
| Q019 | 18 | 4 | inversion | 7 |
| Q020 | 19 | 4 | inversion | 7 |
| Q021 | 20 | 4 | inversion | 7 |
| Q022 | 21 | 5 | inversion | 7 |
| Q023 | 22 | 5 | inversion | 7 |
| Q024 | 23 | 6 | inversion | 7 |
| Q025 | 24 | 7 | inversion | 7 (不变) |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,1,1,1,2,2,2,2,2,2,2,2,3,3,3,7,7,7,7,7,7,7,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 17 | 21 | 7 |
  | 18 | 4 | 7 |
  | 19 | 4 | 7 |
  | 20 | 4 | 7 |
  | 21 | 5 | 7 |
  | 22 | 5 | 7 |
  | 23 | 6 | 7 |

**推荐 layout:** `separated`

---

## 2013-HUANGPU-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,2,1,1,2,2,2,2,3,3,3,3,3,4,4,4,4,5,5,5,5,6,7,7
```

**solution_starts 全序列 (按题号):**

```
8,8,9,10,11,12,14,14,15,16,16,17,18,19,20,20,21,23,25,26,26,28,31,33,36
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q004 | 3 | 1 | inversion | 2 |
| Q005 | 4 | 1 | inversion | 2 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,2,2,2,2,2,2,2,3,3,3,3,3,4,4,4,4,5,5,5,5,6,7,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 3 | 1 | 2 |
  | 4 | 1 | 2 |

**推荐 layout:** `separated`

---

## 2015-MINHANG-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **9**

**question_starts 全序列 (按题号):**

```
1,1,2,1,2,2,2,2,2,3,3,3,3,3,3,3,4,4,5,5,5,5,6,6,7
```

**solution_starts 全序列 (按题号):**

```
9,9,10,11,12,13,14,15,15,16,16,17,18,19,20,21,23,23,24,25,27,29,31,33,37
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q004 | 3 | 1 | inversion | 2 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,2,2,2,2,2,2,2,3,3,3,3,3,3,3,4,4,5,5,5,5,6,6,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 3 | 1 | 2 |

**推荐 layout:** `separated`

---

## 2016-PUTUO-YIMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **9**

**question_starts 全序列 (按题号):**

```
1,1,1,13,14,3,3,3,3,3,3,3,3,3,4,4,4,4,5,5,5,6,6,7,7
```

**solution_starts 全序列 (按题号):**

```
9,10,12,13,14,15,16,17,17,18,18,19,20,21,22,23,24,26,29,31,32,33,35,36,40
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q004 | 3 | 13 | answer-block | 8 |
| Q005 | 4 | 14 | answer-block | 8 |
| Q006 | 5 | 3 | inversion | 8 |
| Q007 | 6 | 3 | inversion | 8 |
| Q008 | 7 | 3 | inversion | 8 |
| Q009 | 8 | 3 | inversion | 8 |
| Q010 | 9 | 3 | inversion | 8 |
| Q011 | 10 | 3 | inversion | 8 |
| Q012 | 11 | 3 | inversion | 8 |
| Q013 | 12 | 3 | inversion | 8 |
| Q014 | 13 | 3 | inversion | 8 |
| Q015 | 14 | 4 | inversion | 8 |
| Q016 | 15 | 4 | inversion | 8 |
| Q017 | 16 | 4 | inversion | 8 |
| Q018 | 17 | 4 | inversion | 8 |
| Q019 | 18 | 5 | inversion | 8 |
| Q020 | 19 | 5 | inversion | 8 |
| Q021 | 20 | 5 | inversion | 8 |
| Q022 | 21 | 6 | inversion | 8 |
| Q023 | 22 | 6 | inversion | 8 |
| Q024 | 23 | 7 | inversion | 8 |
| Q025 | 24 | 7 | inversion | 8 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 3 | 13 | 8 |
  | 4 | 14 | 8 |
  | 5 | 3 | 8 |
  | 6 | 3 | 8 |
  | 7 | 3 | 8 |
  | 8 | 3 | 8 |
  | 9 | 3 | 8 |
  | 10 | 3 | 8 |
  | 11 | 3 | 8 |
  | 12 | 3 | 8 |
  | 13 | 3 | 8 |
  | 14 | 4 | 8 |
  | 15 | 4 | 8 |
  | 16 | 4 | 8 |
  | 17 | 4 | 8 |
  | 18 | 5 | 8 |
  | 19 | 5 | 8 |
  | 20 | 5 | 8 |
  | 21 | 6 | 8 |
  | 22 | 6 | 8 |
  | 23 | 7 | 8 |
  | 24 | 7 | 8 |

**推荐 layout:** `separated`

---

## 2017-CHANGNING-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,2,1,2,2,3,3,3,3,3,3,3,3,4,4,4,4,4,5,5,5,6,6,7
```

**solution_starts 全序列 (按题号):**

```
8,9,9,11,12,13,14,15,15,16,16,17,18,18,20,20,21,22,24,25,26,28,29,32,36
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q004 | 3 | 1 | inversion | 2 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,2,2,2,2,3,3,3,3,3,3,3,3,4,4,4,4,4,5,5,5,6,6,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 3 | 1 | 2 |

**推荐 layout:** `separated`

---

## 2017-SONGJIANG-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,2,2,1,2,2,2,2,2,2,2,3,3,3,3,3,4,4,4,4,5,5,6,6
```

**solution_starts 全序列 (按题号):**

```
8,8,9,10,11,11,12,13,14,14,15,16,16,17,18,19,20,21,23,24,25,27,28,31,35
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q005 | 4 | 1 | inversion | 2 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,2,2,2,2,2,2,2,2,2,2,3,3,3,3,3,4,4,4,4,5,5,6,6
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 4 | 1 | 2 |

**推荐 layout:** `separated`

---

## 2017-SONGJIANG-YIMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,1,1,1,2,2,2,2,2,3,3,3,3,3,3,3,22,4,4,5,5,6,6,7
```

**solution_starts 全序列 (按题号):**

```
8,9,9,10,11,12,14,14,15,15,16,17,18,19,19,20,21,22,25,25,27,29,32,35,38
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q018 | 17 | 22 | answer-block | 7 |
| Q019 | 18 | 4 | inversion | 7 |
| Q020 | 19 | 4 | inversion | 7 |
| Q021 | 20 | 5 | inversion | 7 |
| Q022 | 21 | 5 | inversion | 7 |
| Q023 | 22 | 6 | inversion | 7 |
| Q024 | 23 | 6 | inversion | 7 |
| Q025 | 24 | 7 | inversion | 7 (不变) |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,1,1,2,2,2,2,2,3,3,3,3,3,3,3,7,7,7,7,7,7,7,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 17 | 22 | 7 |
  | 18 | 4 | 7 |
  | 19 | 4 | 7 |
  | 20 | 5 | 7 |
  | 21 | 5 | 7 |
  | 22 | 6 | 7 |
  | 23 | 6 | 7 |

**推荐 layout:** `separated`

---

## 2018-QINGPU-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,1,1,1,1,2,2,2,2,2,2,2,2,3,3,3,22,4,4,4,5,5,5,6
```

**solution_starts 全序列 (按题号):**

```
8,8,9,10,11,11,13,13,14,15,15,16,17,18,18,20,21,22,24,25,26,27,29,32,36
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q018 | 17 | 22 | answer-block | 7 |
| Q019 | 18 | 4 | inversion | 7 |
| Q020 | 19 | 4 | inversion | 7 |
| Q021 | 20 | 4 | inversion | 7 |
| Q022 | 21 | 5 | inversion | 7 |
| Q023 | 22 | 5 | inversion | 7 |
| Q024 | 23 | 5 | inversion | 7 |
| Q025 | 24 | 6 | inversion | 7 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,1,1,1,2,2,2,2,2,2,2,2,3,3,3,7,7,7,7,7,7,7,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 17 | 22 | 7 |
  | 18 | 4 | 7 |
  | 19 | 4 | 7 |
  | 20 | 4 | 7 |
  | 21 | 5 | 7 |
  | 22 | 5 | 7 |
  | 23 | 5 | 7 |
  | 24 | 6 | 7 |

**推荐 layout:** `separated`

---

## 2018-YANGPU-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **4**

> **first_solution 可信度告警:** min(solution)=4 only from ['Q018'] whose question seed is also an outlier/answer-block (q=[4]); 2nd-min solution=8. Genuine answer block likely starts at ~8; the separated coerce below used the artifact 4 (question_ceiling=3) and is therefore too aggressive. Treat coerce result for this volume as lower-bound only.

**question_starts 全序列 (按题号):**

```
1,1,1,1,1,12,13,13,14,3,3,3,3,3,3,3,4,4,4,4,4,5,6,6,7
```

**solution_starts 全序列 (按题号):**

```
8,9,10,10,11,12,13,14,14,15,16,16,17,18,19,19,21,4,23,24,25,27,29,31,35
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q006 | 5 | 12 | answer-block | 3 |
| Q007 | 6 | 13 | answer-block | 3 |
| Q008 | 7 | 13 | answer-block | 3 |
| Q009 | 8 | 14 | answer-block | 3 |
| Q010 | 9 | 3 | inversion | 3 (不变) |
| Q011 | 10 | 3 | inversion | 3 (不变) |
| Q012 | 11 | 3 | inversion | 3 (不变) |
| Q013 | 12 | 3 | inversion | 3 (不变) |
| Q014 | 13 | 3 | inversion | 3 (不变) |
| Q015 | 14 | 3 | inversion | 3 (不变) |
| Q016 | 15 | 3 | inversion | 3 (不变) |
| Q017 | 16 | 4 | answer-block | 3 |
| Q018 | 17 | 4 | answer-block | 3 |
| Q019 | 18 | 4 | answer-block | 3 |
| Q020 | 19 | 4 | answer-block | 3 |
| Q021 | 20 | 4 | answer-block | 3 |
| Q022 | 21 | 5 | answer-block | 3 |
| Q023 | 22 | 6 | answer-block | 3 |
| Q024 | 23 | 6 | answer-block | 3 |
| Q025 | 24 | 7 | answer-block | 3 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,1,1,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 5 | 12 | 3 |
  | 6 | 13 | 3 |
  | 7 | 13 | 3 |
  | 8 | 14 | 3 |
  | 16 | 4 | 3 |
  | 17 | 4 | 3 |
  | 18 | 4 | 3 |
  | 19 | 4 | 3 |
  | 20 | 4 | 3 |
  | 21 | 5 | 3 |
  | 22 | 6 | 3 |
  | 23 | 6 | 3 |
  | 24 | 7 | 3 |

**推荐 layout:** `separated`

---

## 2019-CHANGNING-ERMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,1,2,1,2,2,2,2,2,3,3,3,3,3,3,3,4,4,4,4,5,5,6,6
```

**solution_starts 全序列 (按题号):**

```
8,8,9,10,10,11,13,13,14,15,16,16,17,17,18,19,21,23,25,25,26,29,30,32,37
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q005 | 4 | 1 | inversion | 2 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,2,2,2,2,2,2,2,3,3,3,3,3,3,3,4,4,4,4,5,5,6,6
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 4 | 1 | 2 |

**推荐 layout:** `separated`

---

## 2019-FENGXIAN-YIMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,1,1,2,2,2,2,2,3,3,3,3,3,4,3,4,4,4,4,5,5,6,6,7
```

**solution_starts 全序列 (按题号):**

```
8,8,9,11,12,13,14,14,14,15,15,16,16,18,19,19,20,21,23,24,25,27,30,33,35
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q016 | 15 | 3 | inversion | 4 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,1,1,2,2,2,2,2,3,3,3,3,3,4,4,4,4,4,4,5,5,6,6,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 15 | 3 | 4 |

**推荐 layout:** `separated`

---

## 2021-JIADING-YIMO

- 题数 (items): **25**
- solution 首页最小值 (first_solution_page): **8**

**question_starts 全序列 (按题号):**

```
1,1,2,2,1,2,2,2,2,3,3,3,3,3,3,3,3,4,4,4,5,5,6,6,7
```

**solution_starts 全序列 (按题号):**

```
8,8,10,10,11,12,14,14,15,15,16,17,17,17,18,18,19,20,22,22,24,26,27,29,32
```

**Outlier 清单 (破坏升序或跳进答案区的 question 种子):**

| 题号 (item_id) | 序列位置 index | 原始种子页 | 原因 | 钳位后页 |
|---|---|---|---|---|
| Q005 | 4 | 1 | inversion | 2 |

**coerce_question_seeds(layout='separated') 结果:**

- 钳位后 question_starts：
  ```
  1,1,2,2,2,2,2,2,2,3,3,3,3,3,3,3,3,4,4,4,5,5,6,6,7
  ```
- corrections:
  | index | original | coerced |
  |---|---|---|
  | 4 | 1 | 2 |

**推荐 layout:** `separated`

---

## 汇总 (summary)

| 卷 | 题数 | first_solution | first_solution 可信 | outlier 数 | corrections 数 | coerce | 推荐 layout |
|---|---|---|---|---|---|---|---|
| 2013-CHANGNING-ERMO | 25 | 8 | OK | 8 | 7 | ok (7 clamped) | separated |
| 2013-HUANGPU-ERMO | 25 | 8 | OK | 2 | 2 | ok (2 clamped) | separated |
| 2015-MINHANG-ERMO | 25 | 9 | OK | 1 | 1 | ok (1 clamped) | separated |
| 2016-PUTUO-YIMO | 25 | 9 | OK | 22 | 22 | ok (22 clamped) | separated |
| 2017-CHANGNING-ERMO | 25 | 8 | OK | 1 | 1 | ok (1 clamped) | separated |
| 2017-SONGJIANG-ERMO | 25 | 8 | OK | 1 | 1 | ok (1 clamped) | separated |
| 2017-SONGJIANG-YIMO | 25 | 8 | OK | 8 | 7 | ok (7 clamped) | separated |
| 2018-QINGPU-ERMO | 25 | 8 | OK | 8 | 8 | ok (8 clamped) | separated |
| 2018-YANGPU-ERMO | 25 | 4 | SUSPECT | 20 | 13 | ok (13 clamped) | separated |
| 2019-CHANGNING-ERMO | 25 | 8 | OK | 1 | 1 | ok (1 clamped) | separated |
| 2019-FENGXIAN-YIMO | 25 | 8 | OK | 1 | 1 | ok (1 clamped) | separated |
| 2021-JIADING-YIMO | 25 | 8 | OK | 1 | 1 | ok (1 clamped) | separated |
