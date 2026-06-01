#!/usr/bin/env python3
"""Download images from a WeChat public-account article.

The script intentionally uses only the Python standard library so the skill can
run in fresh repository checkouts without installing browser or HTTP packages.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


IMAGE_ATTRS = (
    "data-src",
    "data-original",
    "data-backsrc",
    "data-croporisrc",
    "data-lazy-src",
    "data-actualsrc",
    "data-image",
    "origin-src",
    "src",
)

ARTICLE_IDS = {"js_content", "img-content", "page-content"}
ARTICLE_CLASS_TOKENS = {"rich_media_content", "js_underline_content", "weui-msg__text-area"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

CSS_URL_RE = re.compile(r"url\((['\"]?)(.*?)\1\)", re.IGNORECASE | re.DOTALL)
HTTP_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
DATA_IMAGE_RE = re.compile(r"^data:(image/[a-z0-9.+-]+);base64,(.*)$", re.IGNORECASE | re.DOTALL)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}

MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

DEFAULT_CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)

PDF_IMAGE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    kind: str
    location: str
    source: str


class WechatImageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self._article_stack: list[bool] = []
        self._candidates: list[ImageCandidate] = []

    @property
    def candidates(self) -> list[ImageCandidate]:
        return self._candidates

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        parent_in_article = self._article_stack[-1] if self._article_stack else False
        in_article = parent_in_article or is_article_container(attr_map)

        if tag == "title":
            self._in_title = True

        self._collect_from_tag(tag, attr_map, "article" if in_article else "page")

        if tag not in VOID_TAGS:
            self._article_stack.append(in_article)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        parent_in_article = self._article_stack[-1] if self._article_stack else False
        in_article = parent_in_article or is_article_container(attr_map)
        self._collect_from_tag(tag, attr_map, "article" if in_article else "page")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() not in VOID_TAGS and self._article_stack:
            self._article_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data

    def _collect_from_tag(self, tag: str, attr_map: dict[str, str], location: str) -> None:
        if tag in {"img", "source"}:
            has_lazy_image = any(attr_map.get(attr, "").strip() for attr in IMAGE_ATTRS if attr != "src")
            for attr in IMAGE_ATTRS:
                if attr == "src" and has_lazy_image:
                    continue
                self._add(attr_map.get(attr, ""), tag, location, attr)
            if attr_map.get("srcset"):
                for url in srcset_urls(attr_map["srcset"]):
                    self._add(url, tag, location, "srcset")

        if tag == "meta" and is_image_meta(attr_map):
            self._add(attr_map.get("content", ""), "meta", location, attr_map.get("property") or attr_map.get("name") or "content")

        if attr_map.get("style"):
            for url in css_image_urls(attr_map["style"]):
                self._add(url, "style", location, "background-image")

    def _add(self, raw_url: str, kind: str, location: str, source: str) -> None:
        normalized = normalize_image_url(raw_url, self.base_url)
        if normalized:
            self._candidates.append(ImageCandidate(normalized, kind, location, source))


def is_article_container(attrs: dict[str, str]) -> bool:
    element_id = attrs.get("id", "")
    if element_id in ARTICLE_IDS:
        return True
    class_tokens = set(attrs.get("class", "").split())
    return bool(class_tokens & ARTICLE_CLASS_TOKENS)


def is_image_meta(attrs: dict[str, str]) -> bool:
    key = (attrs.get("property") or attrs.get("name") or "").lower()
    return key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}


def css_image_urls(style: str) -> list[str]:
    urls = []
    for match in CSS_URL_RE.finditer(style):
        raw = match.group(2).strip()
        if raw:
            urls.append(raw)
    return urls


def srcset_urls(srcset: str) -> list[str]:
    urls = []
    for item in srcset.split(","):
        raw = item.strip().split(" ", 1)[0].strip()
        if raw:
            urls.append(raw)
    return urls


def extract_first_url(text: str) -> str:
    match = HTTP_URL_RE.search(text)
    if not match:
        raise ValueError("No http:// or https:// URL found in input.")
    return match.group(0).rstrip(").,，。；;、")


def normalize_image_url(raw_url: str, base_url: str) -> str:
    value = html.unescape((raw_url or "").strip())
    if not value:
        return ""
    while "&amp;" in value:
        value = html.unescape(value)
    if value.startswith("data:image/"):
        return value
    lowered = value.lower()
    if lowered.startswith(("javascript:", "mailto:", "tel:", "about:", "#")):
        return ""
    if value.startswith("//"):
        value = "https:" + value
    value = urllib.parse.urljoin(base_url, value)
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        return ""
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def extract_embedded_image_urls(page_html: str, base_url: str) -> list[ImageCandidate]:
    candidates = []
    for match in HTTP_URL_RE.finditer(page_html):
        raw = html.unescape(match.group(0)).rstrip("\\/")
        normalized = normalize_image_url(raw, base_url)
        if normalized and looks_like_image_url(normalized):
            candidates.append(ImageCandidate(normalized, "embedded", "page", "html"))
    return candidates


def looks_like_image_url(url: str) -> bool:
    if url.startswith("data:image/"):
        return True
    parts = urllib.parse.urlsplit(url)
    suffix = Path(urllib.parse.unquote(parts.path)).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return True
    query = urllib.parse.parse_qs(parts.query)
    if any(query.get(key) for key in ("wx_fmt", "tp", "format")):
        return True
    return parts.netloc.endswith(("mmbiz.qpic.cn", "mmbiz.qlogo.cn"))


def unique_candidates(candidates: Iterable[ImageCandidate]) -> list[ImageCandidate]:
    seen: set[str] = set()
    unique = []
    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        unique.append(candidate)
    return unique


def collect_image_candidates(
    page_html: str,
    base_url: str,
    *,
    scope: str = "article",
    include_embedded: bool = False,
) -> tuple[str, list[ImageCandidate]]:
    parser = WechatImageParser(base_url)
    parser.feed(page_html)
    candidates = parser.candidates
    if include_embedded:
        candidates = [*candidates, *extract_embedded_image_urls(page_html, base_url)]

    if scope == "article":
        article_candidates = [candidate for candidate in candidates if candidate.location == "article"]
        meta_candidates = [candidate for candidate in candidates if candidate.kind == "meta"]
        selected = [*meta_candidates, *article_candidates] if article_candidates else candidates
    else:
        selected = candidates

    title = " ".join(parser.title.split())
    return title, unique_candidates(selected)


def fetch_text(url: str, timeout: float) -> tuple[str, str]:
    req = urllib.request.Request(url, headers=page_headers())
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read()
    charset = charset_from_content_type(content_type) or "utf-8"
    try:
        return raw.decode(charset), response_url(response)
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), response_url(response)


def response_url(response: object) -> str:
    geturl = getattr(response, "geturl", None)
    return str(geturl()) if callable(geturl) else ""


def charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def page_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Cache-Control": "no-cache",
    }


def image_headers(page_url: str) -> dict[str, str]:
    return {
        "User-Agent": page_headers()["User-Agent"],
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Referer": page_url,
    }


def extension_for(url: str, content_type: str) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in MIME_EXTENSIONS:
        return MIME_EXTENSIONS[mime]

    if url.startswith("data:image/"):
        data_mime = url.split(";", 1)[0].removeprefix("data:").lower()
        return MIME_EXTENSIONS.get(data_mime, ".img")

    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parts.query)
    for key in ("wx_fmt", "format", "tp"):
        for value in query.get(key, []):
            normalized = value.lower().split("/", 1)[-1]
            if normalized == "jpeg":
                return ".jpg"
            if normalized in {"jpg", "png", "gif", "webp", "bmp", "svg", "avif"}:
                return f".{normalized}"

    suffix = Path(urllib.parse.unquote(parts.path)).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".img"


def safe_slug(text: str, fallback: str) -> str:
    raw = text.strip() or fallback
    raw = re.sub(r"[\\/:*?\"<>|\s]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-._")
    return raw[:64] or fallback


def default_output_dir(page_title: str, url: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    slug = safe_slug(page_title, digest)
    return Path("documents") / "wechat-images" / f"{timestamp}-{slug}"


def read_image(candidate: ImageCandidate, page_url: str, timeout: float, max_bytes: int) -> tuple[bytes, str]:
    if candidate.url.startswith("data:image/"):
        match = DATA_IMAGE_RE.match(candidate.url)
        if not match:
            raise ValueError("Unsupported data image URL.")
        data = base64.b64decode(match.group(2), validate=False)
        if len(data) > max_bytes:
            raise ValueError(f"Image exceeds max bytes: {len(data)} > {max_bytes}")
        return data, match.group(1).lower()

    req = urllib.request.Request(candidate.url, headers=image_headers(page_url))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        chunks = []
        total = 0
        while True:
            chunk = response.read(1024 * 64)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"Image exceeds max bytes: {total} > {max_bytes}")
            chunks.append(chunk)
    return b"".join(chunks), content_type


def write_manifest(out_dir: Path, manifest: dict) -> None:
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def saved_image_files(manifest: dict) -> list[str]:
    files = []
    for record in manifest.get("images", []):
        if record.get("status") == "saved" and record.get("file"):
            files.append(str(record["file"]))
    return files


def select_print_images(image_files: list[str], *, drop_first: int = 0, drop_last: int = 0) -> list[str]:
    start = max(drop_first, 0)
    end = len(image_files) - max(drop_last, 0)
    if end < start:
        end = start
    return image_files[start:end]


def title_pdf_name(title: str) -> str:
    return f"{safe_slug(title, 'wechat-images')}.pdf"


def parse_pdf_image_spec(spec: str, image_files: list[str]) -> list[str]:
    if not spec.strip():
        return image_files

    selected = []
    seen = set()
    file_by_name = {name: name for name in image_files}
    for raw_token in re.split(r"[\s,，]+", spec.strip()):
        token = raw_token.strip()
        if not token:
            continue
        range_match = re.fullmatch(r"(\d+)-(\d+)", token)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            step = 1 if end >= start else -1
            for index in range(start, end + step, step):
                if not 1 <= index <= len(image_files):
                    raise ValueError(f"PDF image index out of range: {index}")
                name = image_files[index - 1]
                if name not in seen:
                    selected.append(name)
                    seen.add(name)
            continue

        if token.isdigit():
            index = int(token)
            if not 1 <= index <= len(image_files):
                raise ValueError(f"PDF image index out of range: {index}")
            name = image_files[index - 1]
        else:
            if not PDF_IMAGE_TOKEN_RE.fullmatch(token) or token not in file_by_name:
                raise ValueError(f"PDF image not found in manifest: {token}")
            name = file_by_name[token]

        if name not in seen:
            selected.append(name)
            seen.add(name)
    return selected


def unique_output_dir(parent: Path, slug: str) -> Path:
    target = parent / slug
    if not target.exists():
        return target
    for suffix in range(2, 1000):
        candidate = parent / f"{slug}-{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Cannot find available output directory for {slug}")


def retitle_output_dir(manifest: dict, document_title: str) -> dict:
    if not document_title.strip():
        return manifest

    current_dir = Path(manifest["output_dir"])
    desired_dir = current_dir.parent / safe_slug(document_title, current_dir.name)
    target_dir = current_dir if current_dir.resolve() == desired_dir.resolve() else unique_output_dir(current_dir.parent, desired_dir.name)
    if current_dir.resolve() != target_dir.resolve():
        current_dir.rename(target_dir)
        manifest["output_dir"] = str(target_dir.resolve())
    manifest["document_title"] = document_title.strip()
    write_manifest(Path(manifest["output_dir"]), manifest)
    return manifest


def write_print_html(
    out_dir: Path,
    image_files: list[str],
    html_name: str = "print.html",
    *,
    title: str = "wechat-images-print",
) -> Path:
    escaped_images = [html.escape(name, quote=True) for name in image_files]
    escaped_title = html.escape(title, quote=False)
    body = "\n".join(
        f'  <section class="page"><img src="{name}" alt="{name}"></section>'
        for name in escaped_images
    )
    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
  <style>
    @page {{ size: A4 portrait; margin: 0; }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: #fff; }}
    .page {{
      width: 210mm;
      height: 297mm;
      page-break-after: always;
      break-after: page;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #fff;
      overflow: hidden;
    }}
    .page:last-child {{ page-break-after: auto; break-after: auto; }}
    img {{
      display: block;
      width: 210mm;
      max-width: 210mm;
      max-height: 297mm;
      height: auto;
      object-fit: contain;
    }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""
    html_path = out_dir / html_name
    html_path.write_text(page_html, encoding="utf-8")
    return html_path


def find_chrome(chrome_path: str = "") -> str:
    if chrome_path:
        return chrome_path
    for candidate in DEFAULT_CHROME_PATHS:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise FileNotFoundError("Chrome/Chromium not found; pass --chrome-path to enable PDF export.")


def render_pdf_with_chrome(html_path: Path, pdf_path: Path, *, chrome_path: str = "") -> None:
    chrome = find_chrome(chrome_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--print-to-pdf={pdf_path}",
            "--no-pdf-header-footer",
            html_path.resolve().as_uri(),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def build_print_pdf(
    manifest: dict,
    pdf: Path | str | None,
    *,
    image_spec: str = "",
    document_title: str = "",
    trim_edge_images: bool = False,
    drop_first: int = 0,
    drop_last: int = 0,
    chrome_path: str = "",
) -> dict:
    out_dir = Path(manifest["output_dir"])
    title = document_title.strip() or manifest.get("document_title") or manifest.get("page_title") or "wechat-images-print"
    if trim_edge_images:
        drop_first += 1
        drop_last += 1
    image_files = parse_pdf_image_spec(image_spec, saved_image_files(manifest))
    image_files = select_print_images(image_files, drop_first=drop_first, drop_last=drop_last)
    if not image_files:
        raise ValueError("No images selected for PDF export.")

    pdf_path = Path(pdf) if pdf else Path(title_pdf_name(title))
    if pdf_path.exists() and pdf_path.is_dir():
        pdf_path = pdf_path / title_pdf_name(title)
    if not pdf_path.is_absolute():
        pdf_path = out_dir / pdf_path
    html_path = write_print_html(out_dir, image_files, html_name=f"{pdf_path.stem}.print.html", title=title)
    render_pdf_with_chrome(html_path, pdf_path, chrome_path=chrome_path)
    return {
        "pdf": str(pdf_path.resolve()),
        "print_html": str(html_path.resolve()),
        "document_title": title,
        "pdf_image_count": len(image_files),
        "pdf_images": image_files,
        "pdf_image_spec": image_spec,
        "pdf_drop_first": drop_first,
        "pdf_drop_last": drop_last,
    }


def download_images(
    url: str,
    out_dir: Path | None,
    *,
    timeout: float,
    max_bytes: int,
    scope: str,
    include_embedded: bool,
    save_html: bool,
    fail_on_error: bool,
) -> dict:
    input_url = extract_first_url(url)
    page_html, final_url = fetch_text(input_url, timeout)
    page_url = final_url or input_url
    title, candidates = collect_image_candidates(
        page_html,
        page_url,
        scope=scope,
        include_embedded=include_embedded,
    )
    target_dir = out_dir or default_output_dir(title, page_url)
    target_dir.mkdir(parents=True, exist_ok=True)

    if save_html:
        (target_dir / "page.html").write_text(page_html, encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "source_url": input_url,
        "final_url": page_url,
        "page_title": title,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": scope,
        "include_embedded": include_embedded,
        "output_dir": str(target_dir.resolve()),
        "discovered_count": len(candidates),
        "saved_count": 0,
        "failed_count": 0,
        "images": [],
    }

    for index, candidate in enumerate(candidates, start=1):
        record = {
            "index": index,
            "url": candidate.url,
            "kind": candidate.kind,
            "location": candidate.location,
            "source": candidate.source,
            "status": "pending",
        }
        try:
            data, content_type = read_image(candidate, page_url, timeout, max_bytes)
            ext = extension_for(candidate.url, content_type)
            filename = f"{index:03d}{ext}"
            path = target_dir / filename
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            record.update(
                {
                    "status": "saved",
                    "file": filename,
                    "content_type": content_type,
                    "bytes": len(data),
                    "sha256": digest,
                }
            )
            manifest["saved_count"] += 1
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            record.update({"status": "failed", "error": str(exc)})
            manifest["failed_count"] += 1
            if fail_on_error:
                manifest["images"].append(record)
                write_manifest(target_dir, manifest)
                raise
        manifest["images"].append(record)

    write_manifest(target_dir, manifest)
    return manifest


def read_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if "output_dir" not in manifest:
        manifest["output_dir"] = str(path.parent.resolve())
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download images from a WeChat public article")
    parser.add_argument("url", nargs="?", help="WeChat article URL or pasted text containing one")
    parser.add_argument("--manifest", type=Path, help="Use an existing manifest.json instead of downloading again")
    parser.add_argument("--out", type=Path, help="Directory where images and manifest.json are written")
    parser.add_argument("--scope", choices=("article", "all"), default="article", help="Extract article-body images by default")
    parser.add_argument("--include-embedded", action="store_true", help="Also scan raw HTML/JS for image-like URLs")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    parser.add_argument("--max-mb", type=float, default=50.0, help="Maximum bytes per image in MiB")
    parser.add_argument("--no-save-html", action="store_true", help="Do not save page.html")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero if any image fails")
    parser.add_argument("--print-pdf", nargs="?", const="", type=Path, help="Also export saved images as an A4 PDF; omit value to use the document title")
    parser.add_argument("--pdf-images", default="", help="Images for PDF export by index/range/file, e.g. '2-8' or '002.png,003.png'")
    parser.add_argument("--document-title", default="", help="Human title for the worksheet/exam; used for folder/PDF title")
    parser.add_argument("--trim-edge-images", action="store_true", help="Legacy shortcut for PDF export: drop the first and last selected image")
    parser.add_argument("--pdf-drop-first", type=int, default=0, help="For PDF export, drop this many saved images from the front")
    parser.add_argument("--pdf-drop-last", type=int, default=0, help="For PDF export, drop this many saved images from the end")
    parser.add_argument("--chrome-path", help="Chrome/Chromium executable path for --print-pdf")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    started = time.time()
    try:
        if args.manifest:
            manifest = read_manifest(args.manifest)
        else:
            if not args.url:
                raise ValueError("A URL is required unless --manifest is provided.")
            manifest = download_images(
                args.url,
                args.out,
                timeout=args.timeout,
                max_bytes=int(args.max_mb * 1024 * 1024),
                scope=args.scope,
                include_embedded=args.include_embedded,
                save_html=not args.no_save_html,
                fail_on_error=args.fail_on_error,
            )
        if args.document_title:
            manifest = retitle_output_dir(manifest, args.document_title)
        pdf_result = None
        if args.print_pdf is not None:
            pdf_result = build_print_pdf(
                manifest,
                args.print_pdf or None,
                image_spec=args.pdf_images,
                document_title=args.document_title,
                trim_edge_images=args.trim_edge_images,
                drop_first=args.pdf_drop_first,
                drop_last=args.pdf_drop_last,
                chrome_path=args.chrome_path or "",
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    result = {
        "output_dir": manifest["output_dir"],
        "discovered_count": manifest["discovered_count"],
        "saved_count": manifest["saved_count"],
        "failed_count": manifest["failed_count"],
        "manifest": str(Path(manifest["output_dir"]) / "manifest.json"),
        "elapsed_seconds": round(elapsed, 2),
    }
    if pdf_result:
        result.update(pdf_result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if manifest["saved_count"] == 0:
        return 2
    if args.fail_on_error and manifest["failed_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
