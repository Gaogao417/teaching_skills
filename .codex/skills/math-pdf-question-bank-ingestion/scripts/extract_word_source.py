#!/usr/bin/env python3
"""Normalize a DOC/DOCX source and extract ordered Word media with paragraph anchors."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image
import yaml


NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
RELATIONSHIP_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def normalize_doc(source: Path, temporary: Path, soffice: str | None) -> Path:
    if source.suffix.lower() == ".docx":
        target = temporary / "normalized.docx"
        shutil.copy2(source, target)
        return target

    executable = soffice or shutil.which("soffice")
    if executable is None:
        raise ValueError("DOC input requires soffice; pass --soffice or add it to PATH")
    profile = temporary / "soffice-profile"
    profile.mkdir()
    conversion_dir = temporary / "converted"
    conversion_dir.mkdir()
    subprocess.run(
        [
            executable,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(conversion_dir),
            str(source),
        ],
        check=True,
    )
    candidates = sorted(conversion_dir.glob("*.docx"))
    if len(candidates) != 1:
        raise ValueError(f"soffice produced {len(candidates)} DOCX files; expected one")
    target = temporary / "normalized.docx"
    candidates[0].replace(target)
    return target


def read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise ValueError(f"normalized DOCX is missing {name}") from exc


def relationship_map(xml_bytes: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    return {
        node.attrib["Id"]: node.attrib["Target"]
        for node in root.findall(f"{{{RELATIONSHIP_NAMESPACE}}}Relationship")
        if "Id" in node.attrib and "Target" in node.attrib
    }


def paragraph_records(document_xml: bytes, relationships: dict[str, str]) -> list[dict]:
    root = ET.fromstring(document_xml)
    records: list[dict] = []
    rel_key = f"{{{NAMESPACES['r']}}}embed"
    vml_rel_key = f"{{{NAMESPACES['r']}}}id"
    for index, paragraph in enumerate(root.findall(".//w:p", NAMESPACES)):
        text = "".join(
            node.text or "" for node in paragraph.findall(".//w:t", NAMESPACES)
        ).strip()
        relation_ids = [
            node.attrib.get(rel_key)
            for node in paragraph.findall(".//a:blip", NAMESPACES)
        ]
        relation_ids.extend(
            node.attrib.get(vml_rel_key)
            for node in paragraph.findall(".//v:imagedata", NAMESPACES)
        )
        images: list[str] = []
        for relation_id in relation_ids:
            target = relationships.get(str(relation_id), "")
            if target.startswith("media/") and target not in images:
                images.append(target)
        records.append({"index": index, "text": text, "images": images})

    previous_text = ""
    for record in records:
        record["previous_text"] = previous_text
        if record["text"]:
            previous_text = record["text"]
    next_text = ""
    for record in reversed(records):
        record["next_text"] = next_text
        if record["text"]:
            next_text = record["text"]
    return [record for record in records if record["text"] or record["images"]]


def extract(source: Path, output_dir: Path, soffice: str | None) -> dict:
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_file():
        raise ValueError(f"Word source not found: {source}")
    if source.suffix.lower() not in {".doc", ".docx"}:
        raise ValueError(f"input must be DOC or DOCX: {source}")
    if output_dir.exists():
        raise ValueError(f"output directory already exists; refusing overwrite: {output_dir}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}-", dir=output_dir.parent) as name:
        temporary = Path(name)
        normalized = normalize_doc(source, temporary, soffice)
        with zipfile.ZipFile(normalized) as archive:
            document_xml = read_zip_member(archive, "word/document.xml")
            rels_xml = read_zip_member(archive, "word/_rels/document.xml.rels")
            relationships = relationship_map(rels_xml)
            paragraphs = paragraph_records(document_xml, relationships)
            media_names = sorted(
                name for name in archive.namelist() if name.startswith("word/media/")
            )

            output_dir.mkdir()
            try:
                source_copy = output_dir / f"source{source.suffix.lower()}"
                shutil.copy2(source, source_copy)
                normalized_copy = output_dir / "normalized.docx"
                shutil.copy2(normalized, normalized_copy)
                ooxml_dir = output_dir / "ooxml"
                ooxml_dir.mkdir()
                (ooxml_dir / "document.xml").write_bytes(document_xml)
                (ooxml_dir / "document.xml.rels").write_bytes(rels_xml)
                media_dir = output_dir / "media"
                media_dir.mkdir()
                media_records = []
                for archive_name in media_names:
                    target = media_dir / Path(archive_name).name
                    target.write_bytes(archive.read(archive_name))
                    width = height = None
                    try:
                        with Image.open(target) as image:
                            image.verify()
                        with Image.open(target) as image:
                            width, height = image.size
                    except OSError:
                        pass
                    media_records.append(
                        {
                            "path": f"media/{target.name}",
                            "sha256": sha256(target),
                            "width_px": width,
                            "height_px": height,
                        }
                    )

                manifest = {
                    "schema": "math_word_source_extract/v1",
                    "source": {
                        "path": source_copy.name,
                        "format": source.suffix.lower().lstrip("."),
                        "sha256": sha256(source_copy),
                    },
                    "normalized_docx": {
                        "path": normalized_copy.name,
                        "sha256": sha256(normalized_copy),
                    },
                    "media": media_records,
                    "paragraphs": paragraphs,
                }
                (output_dir / "word-source.yaml").write_text(
                    yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=1000),
                    encoding="utf-8",
                )
            except BaseException:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--soffice")
    args = parser.parse_args()
    try:
        manifest = extract(args.source, args.output_dir, args.soffice)
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    image_paragraphs = sum(bool(row["images"]) for row in manifest["paragraphs"])
    print(
        f"WORD SOURCE EXTRACTED: media={len(manifest['media'])} "
        f"image_paragraphs={image_paragraphs} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
