"""P1-03：artifact:// URI 语法与本地路径 resolver（Python 侧）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ai_teaching_contracts.artifact_uri import (  # noqa: E402
    ArtifactUriError,
    LocalArtifactResolver,
    parse_artifact_uri,
    resolver_from_env,
)


def test_parse_full_uri_with_version_and_path():
    uri = parse_artifact_uri("artifact://page-image/pack-A-minhang-2020-yimo@v1/pages/page-004.png")
    assert uri.namespace == "page-image"
    assert uri.artifact_id == "pack-A-minhang-2020-yimo"
    assert uri.version == "v1"
    assert uri.path == ("pages", "page-004.png")


def test_parse_versionless_uri():
    uri = parse_artifact_uri("artifact://source-evidence/SE-SMV-001")
    assert uri.version is None
    assert uri.path == ()


@pytest.mark.parametrize(
    "bad",
    [
        "/Users/gaochong/develop/some/file.png",  # 绝对本地路径不是 artifact URI
        "file:///Users/gaochong/x.png",
        "artifact://Unknown-Ns/id@v1",  # namespace 未登记（大小写敏感）
        "artifact://question-truth/",  # 缺 artifact id
        "artifact://question-truth/QT-SMV-001@v2/../../escape",  # 路径越界
        "http://example.com/x",
        "",
    ],
)
def test_rejects_malformed_uris(bad):
    with pytest.raises(ArtifactUriError):
        parse_artifact_uri(bad)


def test_resolver_maps_namespace_to_local_root(tmp_path: Path):
    (tmp_path / "QT-SMV-001" / "v1").mkdir(parents=True)
    target = tmp_path / "QT-SMV-001" / "v1" / "truth.json"
    target.write_text("{}", encoding="utf-8")
    resolver = LocalArtifactResolver({"question-truth": tmp_path})
    resolved = resolver.resolve("artifact://question-truth/QT-SMV-001@v1/truth.json")
    assert resolved == target.resolve()


def test_resolver_fails_closed_on_unconfigured_namespace():
    resolver = LocalArtifactResolver({})
    with pytest.raises(ArtifactUriError, match="no local root"):
        resolver.resolve("artifact://question-truth/QT-SMV-001@v1")


def test_resolver_rejects_traversal_escape(tmp_path: Path):
    # symlink 逃逸：namespace root 内的链接指向外部目录，resolve 后必须被拒
    outside = tmp_path.parent / "outside-root"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    resolver = LocalArtifactResolver({"question-truth": tmp_path})
    with pytest.raises(ArtifactUriError, match="escapes"):
        resolver.resolve("artifact://question-truth/escape@v1/secret.txt")


def test_resolver_rejects_unknown_roots(tmp_path: Path):
    with pytest.raises(ArtifactUriError, match="unregistered namespaces"):
        LocalArtifactResolver({"no-such-namespace": tmp_path})


def test_resolver_from_env():
    resolver = resolver_from_env({"AI_TEACHING_ARTIFACT_ROOTS": ""})
    with pytest.raises(ArtifactUriError):
        resolver.resolve("artifact://tutor-plan/TP-SMV-001@v1")
    resolver = resolver_from_env(
        {"AI_TEACHING_ARTIFACT_ROOTS": f"tutor-plan=/tmp/tp;audio=/tmp/audio"}
    )
    assert resolver.resolve("artifact://tutor-plan/TP-SMV-001@v1").is_absolute()
