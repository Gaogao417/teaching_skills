# 2026上海二模 Wave 1 并行录入方案

## 约束
- **最多3个agent并发**，避免限流
- 每完成1个agent，立即检查队列，启动下一个
- 直到13区全部完成

## 待处理队列（倒序优先级）

| # | 区 | paper_id | 归档目录 | 源文件路径 |
|---|-----|----------|----------|-----------|
| 1 | 奉贤 | 2026-FENGXIAN-ERMO | documents/初三/2026届-上海市奉贤区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市奉贤区中考二模数学试卷（教师版）.docx |
| 2 | 宝山 | 2026-BAOSHAN-ERMO | documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市宝山区中考二模数学试卷（教师版）.docx |
| 3 | 徐汇 | 2026-XUHUI-ERMO | documents/初三/2026届-上海市徐汇区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市徐汇区中考二模数学试卷（教师版）.docx |
| 4 | 杨浦 | 2026-YANGPU-ERMO | documents/初三/2026届-上海市杨浦区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市杨浦区中考二模数学试卷（教师版）.docx |
| 5 | 松江 | 2026-SONGJIANG-ERMO | documents/初三/2026届-上海市松江区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市松江区中考二模数学试卷（教师版）.docx |
| 6 | 浦东 | 2026-PUDONG-ERMO | documents/初三/2026届-上海市浦东新区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市浦东新区中考二模数学试卷（教师版）.docx |
| 7 | 虹口 | 2026-HONGKOU-ERMO | documents/初三/2026届-上海市虹口区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市虹口区中考二模数学试卷（教师版）.docx |
| 8 | 金山 | 2026-JINSHAN-ERMO | documents/初三/2026届-上海市金山区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市金山区中考二模数学试卷（教师版）.docx |
| 9 | 长宁 | 2026-CHANGNING-ERMO | documents/初三/2026届-上海市长宁区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市长宁区中考二模数学试卷（教师版）.docx |
| 10 | 闵行 | 2026-MINHANG-ERMO | documents/初三/2026届-上海市闵行区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市闵行区中考二模数学试卷（教师版）.docx |
| 11 | 青浦 | 2026-QINGPU-ERMO | documents/初三/2026届-上海市青浦区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市青浦区中考二模数学试卷（教师版）.docx |
| 12 | 静安 | 2026-JINGAN-ERMO | documents/初三/2026届-上海市静安区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市静安区中考二模数学试卷（教师版）.docx |
| 13 | 黄浦 | 2026-HUANGPU-ERMO | documents/初三/2026届-上海市黄浦区-初三二模数学-试卷及解析/ | 精品解析：2026年上海市黄浦区中考二模数学试卷（教师版）.docx |

源文件统一在: `documents/初三/上海二模/2026年上海市中考数学二模试卷（16份）/精品解析：2026年上海市<区名>区中考二模数学试卷/`

## 编排逻辑

```
主控:
  初始化队列 = [奉贤, 宝山, 徐汇, 杨浦, 松江, 浦东, 虹口, 金山, 长宁, 闵行, 青浦, 静安, 黄浦]
  活跃agents = {}
  
  while 队列非空 or 活跃agents非空:
    # 启动新agent
    while len(活跃agents) < 3 and 队列非空:
      区 = 队列.pop(0)
      agent = spawn(区)
      活跃agents[区] = agent
    
    # 等待任一agent完成
    wait(活跃agents中的任意一个)
    
    # 完成后检查
    区, 结果 = 收到完成通知
    活跃agents.pop(区)
    
    if 结果 == "成功":
      记录: ✓ 区名
    else:
      记录: ✗ 区名 (失败原因)
      # 可选: 重新入队
    
    # 立即启动下一个
    if 队列非空 and len(活跃agents) < 3:
      区 = 队列.pop(0)
      agent = spawn(区)
      活跃agents[区] = agent
```

## 单区Agent提示词模板

```
你是数学试卷录入 agent。任务：把 {区名}2026年上海市{区名}区初三二模数学试卷 录入题库 staging。

## 源文件
- 教师版 docx: documents/初三/上海二模/2026年上海市中考数学二模试卷（16份）/精品解析：2026年上海市{区名}区中考二模数学试卷/精品解析：2026年上海市{区名}区中考二模数学试卷（教师版）.docx
- paper_id: 2026-{区拼音大写}-ERMO
- 归档目录: documents/初三/2026届-上海市{区名}区-初三二模数学-试卷及解析/
- staging目录: artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-{区拼音大写}-ERMO/

## 固定6步

### 步骤1: 建归档 + 复制源文件
mkdir -p <归档目录>/word
cp <docx路径> <归档目录>/source.docx

### 步骤2: 双通道提取
rmdir <归档目录>/word 2>/dev/null
./.venv/bin/python .codex/skills/math-docx-question-bank-ingestion/scripts/extract_docx_source.py <归档目录>/source.docx <归档目录>/word
等待完成。记录 media 数量和 PDF 页数。

### 步骤3: 读 word-source.yaml + PDF 渲染页
读 <归档目录>/word/word-source.yaml 的段落列表。
- 用正则 ^(\d+)． 匹配题目编号（全角句号）
- 用 re.match(r'[一二三]、', text) 匹配章节标题
- 记录每题的段落起始位置
- 找 PNG 图片: 遍历段落的 images 列表，筛选 .png 文件

读 <归档目录>/word/pages/*.png PDF 渲染页，逐题转写公式为 LaTeX。

### 步骤4: 写 paper.draft.yaml
mkdir -p <staging目录>/items

draft 格式要点:
- schema: math_exam_staging_draft/v1
- paper.id: 2026-{区拼音大写}-ERMO
- paper.source_archive: <归档目录>

每题必须有:
- question_word_evidence: [{page_image: <归档目录>/word/pages/NNN.png, page_number: N}]
- official_solution.word_evidence: [{page_image: <归档目录>/word/pages/NNN.png, page_number: N}]
- prompt: [{source: <归档目录>/word/media/imageN.png, box_px: [0, 0, w, h], width: 120mm}] (有图的题)
- block.stem_latex: LaTeX 公式
- block.answer: 答案
- block.solution_steps: 解答步骤（逐条复刻，不得简化）
- block.clue: 解题思路提示
- 选择题恰好4个选项

题目结构（上海二模标准）:
- 选择题6题(Q001-Q006), 每题4分, 共24分
- 填空题12题(Q007-Q018), 每题4分, 共48分
- 解答题7题(Q019-Q025), 分值: 10+10+10+10+12+12+14=78分
- 总分150分, 共25题

注意: 中文引号" "在YAML中会导致解析错误，必须使用 \u201c \u201d

### 步骤5: 展开 + 物化 + 审计
./.venv/bin/python .codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py <staging目录>/paper.draft.yaml
./.venv/bin/python .codex/skills/math-pdf-question-bank-ingestion/scripts/materialize_staging.py <staging目录> --repo-root .
./.venv/bin/python .codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py <staging目录> --repo-root .

### 步骤6: 汇报
报告: paper_id, items数, gate状态, contact sheet路径。不要 commit。

## 关键注意事项
- 从PDF渲染页读取公式，不要从WMF二进制猜测
- 题图以Word媒体原图为准，box_px使用完整像素范围 [0, 0, width, height]
- 每个question_word_evidence和official_solution.word_evidence都要有page_image和page_number
- 如果extract失败，检查word目录是否已存在（需先rmdir）
- draft写完后验证YAML能解析再运行expand
```

## 已完成
- ✓ 2026-CHONGMING-ERMO (崇明) 25 items
- ✓ 2026-PUTUO-ERMO (普陀) 24 items
- ✓ 2026-JIADING-ERMO (嘉定) 25 items
- ✓ 2026-BAOSHAN-ERMO (宝山) 25 items
- ✓ 2026-FENGXIAN-ERMO (奉贤) 25 items
- ✓ 2026-XUHUI-ERMO (徐汇) 25 items
- ✓ 2026-YANGPU-ERMO (杨浦) 25 items
- ✓ 2026-SONGJIANG-ERMO (松江) 25 items
- ✓ 2026-PUDONG-ERMO (浦东) 25 items
- ✓ 2026-HONGKOU-ERMO (虹口) 25 items
- ✓ 2026-JINSHAN-ERMO (金山) 23 items (5+10+8 structure)
- ✓ 2026-CHANGNING-ERMO (长宁) 25 items
- ✓ 2026-MINHANG-ERMO (闵行) 25 items
- ✓ 2026-QINGPU-ERMO (青浦) 25 items
- ✓ 2026-JINGAN-ERMO (静安) 25 items
- ✓ 2026-HUANGPU-ERMO (黄浦) 25 items
