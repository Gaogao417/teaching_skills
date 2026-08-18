# ai_teaching_contracts — canonical 合同 Python adapter（P1-04）

对 PRD 仓 `contracts/`（10 个 JSON Schema + 26 个正反例 fixture + mappings）
的可执行化。**只做 parse / validate / resolve**：

| 模块 | 职责 |
|---|---|
| `models.py` | Pydantic v2 模型，逐字段对应 `contracts/schemas/*/v1/*.schema.json` |
| `validation.py` | 按 `schema` 常量分派校验入口 `validate_payload` |
| `artifact_uri.py` | `artifact://` URI 解析 + 本地路径 resolver（P1-03） |
| `publication.py` | 发布门禁 `validate_for_publication`（未批准 / 绝对路径 fail closed） |
| `fixtures/` | PRD 仓 `contracts/fixtures/` 的 vendored 副本（sha256 由 manifest 锁定） |

约束（ADR-004）：

- **不存在也不允许添加原地更新 API**——Approved artifact 修改只能新建 version；
  `tests/integrations/ai_teaching_contracts/test_api_surface.py` 用公开 API
  白名单做结构性自证。
- fixture/schema 变更流程见 PRD 仓 `contracts/README.md` §5：改 PRDS →
  重新生成 manifest → 拷贝本目录 → `./.venv/bin/python -m pytest tests/integrations`。
