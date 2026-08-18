"""``artifact://`` URI 语法与本地路径 resolver（P1-03，ADR-004 §4）。

语法：``artifact://<namespace>/<artifact-id>[@<version>][/<path>]``
本地路径只存在于 resolver 配置；canonical 对象内出现绝对路径会被
publication 校验拒绝（fail closed）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_URI_RE = re.compile(
    r"^artifact://(?P<namespace>[a-z][a-z0-9-]*)"
    r"/(?P<artifact_id>[A-Za-z0-9._~!$&'()*+,;=:%-]+)"
    r"(?:@v(?P<version>[0-9]+))?"
    r"(?P<path>(?:/[A-Za-z0-9._~!$&'()*+,;=:%-]+)*)$"
)

# id-registry.yaml 登记的 namespace；新增必须先改 registry。
KNOWN_NAMESPACES = frozenset(
    {
        "question-truth",
        "question-candidate",
        "source-evidence",
        "teaching-approach",
        "tutor-plan",
        "page-image",
        "audio",
        "transcript",
        "sut-config",
        "benchmark-output",
    }
)


class ArtifactUriError(ValueError):
    """URI 语法非法、namespace 未登记或路径越界——一律 fail closed。"""


@dataclass(frozen=True)
class ArtifactUri:
    raw: str
    namespace: str
    artifact_id: str
    version: str | None  # "v1" 形式；None = 未版本化引用
    path: tuple[str, ...]  # 逐段（不含前导 /）

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.raw


def parse_artifact_uri(value: str) -> ArtifactUri:
    match = _URI_RE.match(value) if isinstance(value, str) else None
    if match is None:
        raise ArtifactUriError(f"invalid artifact URI: {value!r}")
    namespace = match.group("namespace")
    if namespace not in KNOWN_NAMESPACES:
        raise ArtifactUriError(f"unregistered artifact namespace: {namespace!r} (see contracts/mappings/id-registry.yaml)")
    path = tuple(seg for seg in (match.group("path") or "").split("/") if seg)
    for seg in path:
        if seg in {".", ".."}:
            raise ArtifactUriError(f"path traversal not allowed in artifact URI: {value!r}")
    return ArtifactUri(
        raw=value,
        namespace=namespace,
        artifact_id=match.group("artifact_id"),
        version=f"v{match.group('version')}" if match.group("version") else None,
        path=path,
    )


class LocalArtifactResolver:
    """把 artifact URI 映射到本仓本地路径。

    roots: namespace → 该 namespace 的根目录。解析结果必须落在根目录内
    （resolve 后再做 relative_to 校验），否则抛 ArtifactUriError。
    """

    def __init__(self, roots: dict[str, Path]) -> None:
        unknown = set(roots) - KNOWN_NAMESPACES
        if unknown:
            raise ArtifactUriError(f"unregistered namespaces in roots: {sorted(unknown)}")
        self._roots = {ns: Path(p).resolve() for ns, p in roots.items()}

    def resolve(self, uri: str | ArtifactUri) -> Path:
        parsed = parse_artifact_uri(uri) if isinstance(uri, str) else uri
        root = self._roots.get(parsed.namespace)
        if root is None:
            raise ArtifactUriError(
                f"no local root configured for namespace {parsed.namespace!r}"
            )
        # 本地布局：<root>/<artifact-id>/<version>/<path…>；versionless 引用直接 <root>/<artifact-id>/<path…>
        segments = ([parsed.version] if parsed.version else []) + list(parsed.path)
        target = root.joinpath(parsed.artifact_id, *segments).resolve()
        if not target.is_relative_to(root):
            raise ArtifactUriError(f"resolved path escapes namespace root: {uri!r}")
        return target


def resolver_from_env(env: dict[str, str] | None = None) -> LocalArtifactResolver:
    """从 AI_TEACHING_ARTIFACT_ROOTS 构建 resolver。

    格式：``namespace=/abs/path;namespace2=/abs/path2``（分隔符 ``;``）。
    未设置时返回空 resolver（任何 resolve 都 fail closed）。
    """
    source = os.environ if env is None else env
    raw = source.get("AI_TEACHING_ARTIFACT_ROOTS", "").strip()
    roots: dict[str, Path] = {}
    for chunk in filter(None, (c.strip() for c in raw.split(";"))):
        if "=" not in chunk:
            raise ArtifactUriError(f"bad AI_TEACHING_ARTIFACT_ROOTS entry: {chunk!r}")
        ns, _, path = chunk.partition("=")
        roots[ns] = Path(path)
    return LocalArtifactResolver(roots)
