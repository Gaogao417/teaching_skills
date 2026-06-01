#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "documents" / "高一"
OUT_DIR = SOURCE_DIR / "topic-archives"
OCR_SCRIPT = ROOT / "scripts" / "ocr_vision.swift"

TOPICS = {
    "复数": [
        "复数",
        "虚数",
        "纯虚数",
        "实部",
        "虚部",
        "共轭",
        "复平面",
    ],
    "平面向量": [
        "向量",
        "投影",
        "数量积",
        "单位向",
    ],
    "三角函数": [
        "sin",
        "cos",
        "tan",
        "arctan",
        "arcsin",
        "周期",
        "单调",
        "三角",
        "ω",
        "扇形",
        "弧长",
    ],
    "立体几何": [
        "立体",
        "空间",
        "棱锥",
        "棱柱",
        "四面体",
        "正方体",
        "长方体",
        "球",
        "体积",
        "表面积",
        "异面",
        "二面角",
        "直线与平面",
        "平面与平面",
    ],
}

@dataclass
class Observation:
    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def top(self) -> float:
        return self.y + self.h


@dataclass
class QuestionBlock:
    number: int
    source_dir: str
    source_title: str
    image_path: Path
    crop_path: Path
    text: str
    topics: list[str]


def title_from_html(article_dir: Path) -> str:
    html = article_dir / "page.html"
    if not html.exists():
        return article_dir.name
    text = html.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"var msg_title = '(.*?)'\.html", text)
    return match.group(1) if match else article_dir.name


def run_ocr(images: list[Path], cache_path: Path) -> list[dict]:
    if cache_path.exists():
        return [json.loads(line) for line in cache_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    rows: list[dict] = []
    chunk_size = 8
    for i in range(0, len(images), chunk_size):
        chunk = images[i : i + chunk_size]
        cmd = ["swift", str(OCR_SCRIPT), *[str(p) for p in chunk]]
        result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
        for line in result.stdout.splitlines():
            if line.strip():
                rows.append(json.loads(line))
    cache_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return rows


def is_question_page(observations: list[Observation]) -> bool:
    joined = "\n".join(obs.text for obs in observations)
    if "参考答案" in joined or "答案" in joined[:80] or re.search(r"\d{1,2}\.\s*解[：:（(]", joined):
        return False
    return any(re.match(r"^\s*\d{1,2}[.．、](?!\d)", obs.text) for obs in observations)


def detect_question_starts(observations: list[Observation]) -> list[tuple[int, Observation]]:
    starts: list[tuple[int, Observation]] = []
    for obs in observations:
        if any(marker in obs.text for marker in ["本试卷", "考生注意", "考试时间", "满分"]):
            continue
        match = re.match(r"^\s*(\d{1,2})[.．、](?!\d)", obs.text)
        if match:
            starts.append((int(match.group(1)), obs))
    starts.sort(key=lambda item: item[1].top, reverse=True)
    deduped: list[tuple[int, Observation]] = []
    seen: set[int] = set()
    for num, obs in starts:
        if num not in seen:
            deduped.append((num, obs))
            seen.add(num)
    return deduped


def classify_question(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    topics: list[str] = []
    for topic, keywords in TOPICS.items():
        if topic == "复数":
            if any(word in compact for word in ["复数", "虚数", "纯虚数", "实部", "虚部", "共轭"]):
                topics.append(topic)
            continue
        if topic == "平面向量" and (
            re.search(r"(OA|OB|OC|OD|OP|OM|ON|OQ).*(OA|OB|OC|OD|OP|OM|ON|OQ)", compact)
            or re.search(r"AD.*AB.*AC", compact)
            or re.search(r"AD.*DB", compact)
            or re.search(r"(AB|AC|BC).*(方向上|数量投影)", compact)
        ):
            topics.append(topic)
            continue
        if any(keyword in compact for keyword in keywords):
            topics.append(topic)
    return topics


def crop_question(image: Image.Image, crop_path: Path, top_norm: float, bottom_norm: float) -> None:
    width, height = image.size
    left = 110
    right = width - 100
    top_px = max(0, int((1 - top_norm) * height) - 24)
    bottom_px = min(height - 110, int((1 - bottom_norm) * height) + 20)
    if bottom_px <= top_px + 40:
        bottom_px = min(height - 110, top_px + 180)
    crop = image.crop((left, top_px, right, bottom_px))
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(crop_path)


def image_rows() -> tuple[list[Path], dict[str, str]]:
    article_titles: dict[str, str] = {}
    images: list[Path] = []
    for article_dir in sorted(p for p in SOURCE_DIR.iterdir() if p.is_dir() and re.match(r"\d{2}-", p.name)):
        article_titles[article_dir.name] = title_from_html(article_dir)
        images.extend(sorted(article_dir.glob("*.png")))
    return images, article_titles


def build_archive() -> list[QuestionBlock]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    crops_dir = OUT_DIR / "crops"
    if crops_dir.exists():
        for old_crop in crops_dir.glob("*.png"):
            old_crop.unlink()
    images, titles = image_rows()
    rows = run_ocr(images, OUT_DIR / "ocr.jsonl")

    blocks: list[QuestionBlock] = []
    stopped_articles: set[str] = set()
    for row in rows:
        image_path = ROOT / row["path"]
        article_name = image_path.parent.name
        if article_name in stopped_articles:
            continue
        observations = [
            Observation(
                text=obs["text"],
                x=obs["bbox"]["x"],
                y=obs["bbox"]["y"],
                w=obs["bbox"]["w"],
                h=obs["bbox"]["h"],
            )
            for obs in row.get("observations", [])
        ]
        joined_page_text = "\n".join(obs.text for obs in observations)
        if "参考答案" in joined_page_text:
            stopped_articles.add(article_name)
            continue
        if not is_question_page(observations):
            continue

        starts = detect_question_starts(observations)
        if not starts:
            continue

        with Image.open(image_path) as image:
            for idx, (number, start_obs) in enumerate(starts):
                next_start_top = starts[idx + 1][1].top if idx + 1 < len(starts) else 0.08
                top = min(0.94, start_obs.top + 0.01)
                bottom = max(0.08, next_start_top + 0.005)
                in_block = [
                    obs
                    for obs in observations
                    if obs.top <= top + 0.015 and obs.top > bottom
                ]
                in_block.sort(key=lambda obs: (-obs.top, obs.x))
                text = "\n".join(obs.text for obs in in_block)
                topics = classify_question(text)
                if not topics:
                    continue
                crop_name = f"{article_name}-{image_path.stem}-q{number:02d}.png"
                crop_path = crops_dir / crop_name
                crop_question(image, crop_path, top, bottom)
                blocks.append(
                    QuestionBlock(
                        number=number,
                        source_dir=article_name,
                        source_title=titles.get(article_name, article_name),
                        image_path=image_path.relative_to(ROOT),
                        crop_path=crop_path.relative_to(OUT_DIR),
                        text=text,
                        topics=topics,
                    )
                )
    return blocks


def tex_escape(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("$", r"\$")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def write_tex(topic: str, blocks: list[QuestionBlock]) -> Path:
    tex_path = OUT_DIR / f"{topic}.tex"
    lines = [
        r"\documentclass[UTF8,12pt]{ctexart}",
        r"\usepackage[a4paper,margin=1.5cm]{geometry}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{caption}",
        r"\setlength{\parindent}{0pt}",
        r"\captionsetup{font=small,labelformat=empty}",
        r"\begin{document}",
        rf"\section*{{高一数学专题题目归档：{tex_escape(topic)}}}",
        rf"来源：\verb|documents/高一|，按 OCR 关键词筛选后裁剪原题图。共 {len(blocks)} 题。",
        "",
    ]
    for i, block in enumerate(blocks, 1):
        lines.extend(
            [
                rf"\subsection*{{{i}. 原卷第 {block.number} 题}}",
                rf"\textbf{{来源}}：{tex_escape(block.source_title)}",
                "",
                r"\begin{figure}[H]",
                r"\centering",
                rf"\includegraphics[width=0.96\linewidth]{{{block.crop_path.as_posix()}}}",
                rf"\caption{{原图：\detokenize{{{block.image_path.as_posix()}}}}}",
                r"\end{figure}",
                r"\vspace{0.4em}",
            ]
        )
    lines.append(r"\end{document}")
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tex_path


def compile_pdf(tex_path: Path) -> None:
    subprocess.run(
        ["tectonic", "--keep-logs", "--keep-intermediates", tex_path.name],
        cwd=OUT_DIR,
        text=True,
        check=True,
    )


def main() -> int:
    blocks = build_archive()
    by_topic: dict[str, list[QuestionBlock]] = {topic: [] for topic in TOPICS}
    for block in blocks:
        for topic in block.topics:
            by_topic[topic].append(block)

    manifest = {
        topic: [
            {
                "number": block.number,
                "source_dir": block.source_dir,
                "source_title": block.source_title,
                "image_path": block.image_path.as_posix(),
                "crop_path": block.crop_path.as_posix(),
                "ocr_text": block.text,
            }
            for block in topic_blocks
        ]
        for topic, topic_blocks in by_topic.items()
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for topic, topic_blocks in by_topic.items():
        tex_path = write_tex(topic, topic_blocks)
        compile_pdf(tex_path)
        print(f"{topic}: {len(topic_blocks)} questions -> {tex_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
