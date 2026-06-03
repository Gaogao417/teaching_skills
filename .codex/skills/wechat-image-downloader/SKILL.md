---
name: wechat-image-downloader
description: Open a WeChat public-account article URL and save the article images locally. Use when the user provides a mp.weixin.qq.com or WeChat article link and asks to download, extract, collect, or save all images/pictures from the link.
---

# wechat-image-downloader

## Workflow

Use the bundled script for deterministic extraction:

```bash
python3 .codex/skills/wechat-image-downloader/scripts/download_wechat_images.py "<WECHAT_URL>"
```

Default output goes under `documents/wechat-images/<timestamp>-<page-title-or-hash>/`.

## Path Rules

Wechat source documents belong under `documents/`, not `downloads/`.

- For one-off/raw article image extraction, use `documents/wechat-images/<timestamp>-<page-title-or-hash>/`.
- For identified exam or worksheet documents, retitle and move/store them under `documents/<学段>/<document-title>/`, for example `documents/初三/虹口区-2025-学年度初三年级第一次学生学习能力诊断练习-数学-练习卷/`.
- Keep only the final named document directory after inspection. Delete only temporary check/raw directories created in the current run, such as `title-check-*`, `script-check-*`, and timestamp-only duplicates, after the final PDF/images are verified.
- When moving an existing directory, update `manifest.json` so `output_dir` matches the new absolute path.

If the user gives a preferred destination, pass it with `--out`:

```bash
python3 .codex/skills/wechat-image-downloader/scripts/download_wechat_images.py "<WECHAT_URL>" --out "<OUTPUT_DIR>"
```

When the user wants a printable worksheet/exam PDF, do not blindly trim the
first/last image. First download the images, then inspect the downloaded images
or a contact sheet. Select only the pages that contain the questions and
answers/solutions, identify the exam title from the content, and run the script
again from `manifest.json` to make the PDF and retitle the output directory:

```bash
python3 .codex/skills/wechat-image-downloader/scripts/download_wechat_images.py \
  --manifest "<OUTPUT_DIR>/manifest.json" \
  --document-title "<EXAM_TITLE>" \
  --pdf-images "2-8" \
  --print-pdf
```

`--print-pdf` without a value writes `<EXAM_TITLE>.pdf` in the retitled output
directory.

## Behavior

- Treat pasted text as acceptable input; the script extracts the first `http://` or `https://` URL.
- Prefer the WeChat article body (`#js_content` / `.rich_media_content`) to avoid UI icons.
- Save image URLs from `data-src`, lazy-load attributes, `src`, CSS `background-image`, and article cover metadata.
- Write `manifest.json` with the source URL, page title, discovered image count, saved file paths, content type, bytes, SHA-256, and any failed downloads.
- Write `page.html` beside the images by default so the extraction can be audited.

## Options

- Use `--scope all` if the user explicitly wants page chrome, share thumbnails, or every image-like URL on the page.
- Use `--include-embedded` when article images are hidden in inline JavaScript instead of normal tags.
- Use `--fail-on-error` when partial downloads should be treated as failure.
- Use `--no-save-html` when the raw page should not be kept.
- Use `--manifest <manifest.json>` to post-process an existing download without fetching the article again.
- Use `--document-title <TITLE>` after inspecting content; this title is used for the output directory and PDF metadata/name.
- Use `--print-pdf [NAME_OR_PATH]` to export the selected saved images as an A4 printable PDF. If no name/path is provided, the PDF filename comes from `--document-title`.
- Use `--pdf-images <SPEC>` to choose PDF pages after inspecting image content. The spec accepts 1-based indexes/ranges (`2-8`) and filenames (`002.png,003.png`).
- Use `--trim-edge-images` only as a legacy/manual shortcut after confirming the first and last selected image are not useful content.

Example:

```bash
python3 .codex/skills/wechat-image-downloader/scripts/download_wechat_images.py \
  --manifest documents/wechat-images/raw/manifest.json \
  --document-title "虹口区 2025 学年度初三年级第一次学生学习能力诊断练习 数学练习卷" \
  --pdf-images "2-8" \
  --print-pdf
```

## Notes

WeChat commonly stores article images in `data-src` rather than `src`, and file extensions are often only available from `Content-Type` or the `wx_fmt` query parameter. Do not rewrite the script ad hoc for this; run it first, then inspect `manifest.json` if anything is missing.
