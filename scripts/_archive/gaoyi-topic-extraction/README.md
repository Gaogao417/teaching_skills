# 高一 Topic Extraction Archive

These scripts were one-off helpers for extracting and rebuilding 高一 topic
archives from source images under `documents/高一`.

They are kept here for reproducibility, but they are not part of the active
skill or diagram-rendering workflows.

## Scripts

- `archive_gaoyi_topics.py`: OCR-based topic extraction into
  `documents/高一/topic-archives`.
- `build_gaoyi_pure_tex.py`: hard-coded pure TeX rebuild into
  `documents/高一/topic-archives-pure`.
- `ocr_vision.swift`: local macOS Vision OCR helper used by
  `archive_gaoyi_topics.py`.

## Usage

Run from the repository root:

```bash
python3 scripts/_archive/gaoyi-topic-extraction/archive_gaoyi_topics.py
python3 scripts/_archive/gaoyi-topic-extraction/build_gaoyi_pure_tex.py
```

The scripts still write to their original `documents/高一` output directories.
