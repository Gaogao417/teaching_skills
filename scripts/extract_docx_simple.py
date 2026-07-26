#!/usr/bin/env python3
"""Extract paragraphs and media from a DOCX file into a word-source.yaml + media/ directory."""

import sys, os, yaml, hashlib
from pathlib import Path

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def extract(docx_path, out_dir):
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    doc = Document(docx_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    media_dir = out / "media"
    media_dir.mkdir(exist_ok=True)

    # Collect images from relationships
    images = {}
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            blob = rel.target_part.blob
            ext = os.path.splitext(rel.target_ref)[1] or ".png"
            # Find a unique name
            base = os.path.basename(rel.target_ref)
            if base in images:
                base = f"img_{len(images)}{ext}"
            img_path = media_dir / base
            img_path.write_bytes(blob)
            images[rel.rId] = {
                "path": str(img_path.relative_to(out)),
                "sha256": sha256_file(img_path),
                "size": len(blob),
            }

    # Walk paragraphs, tracking images
    paragraphs = []
    img_counter = 0
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        # Find images in this paragraph's runs
        para_images = []
        for run in para.runs:
            for child in run._element:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "drawing":
                    # Find the relationship ID
                    for blip in child.iter():
                        blip_tag = blip.tag.split("}")[-1] if "}" in blip.tag else blip.tag
                        if blip_tag == "blip":
                            rId = blip.get(
                                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
                                blip.get("r:embed", ""),
                            )
                            if rId in images:
                                para_images.append(images[rId]["path"])
        paragraphs.append({
            "index": i,
            "text": text,
            "images": para_images,
            "style": para.style.name if para.style else None,
        })

    # Build output
    result = {
        "source_file": str(Path(docx_path).name),
        "total_paragraphs": len(paragraphs),
        "total_images": len(images),
        "images": images,
        "paragraphs": paragraphs,
    }

    with open(out / "word-source.yaml", "w", encoding="utf-8") as f:
        yaml.dump(result, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"Extracted {len(paragraphs)} paragraphs, {len(images)} images to {out}")
    return result

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.docx> <output_dir>")
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2])
