"""ai_teaching canonical contracts 的 Python validation adapter（P1-04）。

对应 PRD 仓 `contracts/` 的 10 个 JSON Schema；正反例 fixture 与 TypeScript
侧（teaching-tools `web/shared/canonical/`）共用同一批文件，期望结果表
见 `fixtures/fixtures-manifest.json`。

本包只提供 parse / validate / resolve 能力：Approved artifact 不可变
（ADR-004 §3），因此这里不存在也不会添加任何原地更新 API。
"""

from integrations.ai_teaching_contracts.artifact_uri import (
    ArtifactUri,
    ArtifactUriError,
    LocalArtifactResolver,
    parse_artifact_uri,
    resolver_from_env,
)
from integrations.ai_teaching_contracts.publication import (
    PublicationError,
    validate_for_publication,
)
from integrations.ai_teaching_contracts.validation import (
    SchemaKind,
    canonical_schema_for,
    validate_payload,
)

__all__ = [
    "ArtifactUri",
    "ArtifactUriError",
    "LocalArtifactResolver",
    "PublicationError",
    "SchemaKind",
    "canonical_schema_for",
    "parse_artifact_uri",
    "resolver_from_env",
    "validate_for_publication",
    "validate_payload",
]
