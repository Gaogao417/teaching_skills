# Evidence 预检报告（同类 306 膨胀风险扫描）

扫描时间: 2026-08-03

扫描 draft 总数(去重): 328 卷  |  通过: 298 卷  |  有问题: 30 卷

用修复后的 `word_evidence_pages.py` 对每卷 draft 跑 `resolve_draft_payload(layout="auto")`，失败的归入四类：

| 类别 | 卷数 | 根因 | 与 306 关系 | 建议动作 |
|------|------|------|------------|---------|
| A_outlier | 12 | 转录把某题 question 种子标到答案区,破坏升序 | **同类膨胀**:硬塞 separated 会跨页膨胀 | 人工确认 separated 后用 --layout-override-seeds coerce |
| B_layout | 3 | 种子既不像 interleaved 也不像 separated | **同类**:被迫指定 layout 可能触发膨胀 | 人工确认 layout 后重跑 |
| C_empty | 15 | word_evidence 空或 page_number 缺失 | 数据缺陷,非膨胀 | 重新转录或补种子页 |
| D_pages | 0 | 页图目录扫描失败(parent 错或 page-N 命名) | **同类放大**:last_page 错会抬高膨胀上限 | 修 page_image 路径或页图命名 |

每类详细诊断见各自 markdown:
- `A-outlier.md` + `A-outlier-detail.md`（12 卷，已出详细诊断）
- `B-layout.md` + `B-layout-detail.md`（3 卷，已确诊全部 interleaved）
- `C-empty.md` + `C-empty-detail.md`（15 卷，详细诊断待补）
- `D-pages.md` + `D-pages-detail.md`（2 卷进 staging + 15 卷源数据，已出修复方案）

## 诊断要点（已确认）

- **A 类 12 卷全部 separated**，除 2018-YANGPU-ERMO 外 first_solution 可信，
  coerce 结果可直接用 `--layout separated --layout-override-seeds`。
  2018-YANGPU 需人工确认答案区真实起点（约 p8）。
- **B 类 3 卷全部 interleaved**（答案从 p1 起）。2026-CHONGMING / 2026-JIADING
  种子本就合法，仅需 `--layout interleaved`（无需 override）；
  2024-QINGPU 需 `--layout interleaved --layout-override-seeds`。
- **D 类核心 bug**：PDF 提取的 `page-N.png` 命名与 `_last_page_from_evidence`
  的 `isdigit()` 不兼容。只有 2 卷（2026-BAOSHAN-ERMO、2024-QINGPU-ERMO）
  进了 staging 受影响；15 个精品解析卷只是源数据未入库。

## 快速处理命令

```bash
# A 类(12 卷,separated + coerce outlier):
./.venv/bin/python .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py <draft> --layout separated --layout-override-seeds --check
# 确认 changes 合理后去掉 --check 落盘

# B 类(3 卷,interleaved):
./.venv/bin/python .codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py <draft> --layout interleaved --check
# 2024-QINGPU 额外加 --layout-override-seeds

# --check = 只读报告 changes 不改文件;去掉 --check = 落盘改 draft
```