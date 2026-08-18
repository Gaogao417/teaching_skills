"""integrations — 外部合同/系统的 adapter 边界。

子包：
- ``ai_teaching_contracts``：PRD 仓 ``contracts/`` canonical 合同的 Python 侧
  validation adapter（Phase 1 / P1-04）。只做 parse/validate/resolve，
  不提供任何对 Approved artifact 的原地更新 API（ADR-004）。
"""
