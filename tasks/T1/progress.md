## §1 Task identity
- task_id: T1
- short summary: Ingest 2026-BAOSHAN-ERMO math exam paper into question bank staging

## §2 Subagent intent
Ingest the 2026年上海市宝山区初三二模数学试卷 from a teacher-version DOCX into the question bank staging system. Steps: create archive directory, copy source docx, extract Word content/paragraphs/media, render DOCX to PDF then to page PNGs for formula reference, hand-write paper.draft.yaml with all 25 questions (6 choice + 12 fill-in + 7 problem), then run expand/materialize/audit scripts.

## §3 Files and code sections
- `documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/source.docx`: Copied teacher-version docx (~4.2MB)
- `documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word/word-source.yaml`: Extracted 460 paragraphs, 431 images (mostly .wmf formula objects)
- `documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word/media/`: 431 extracted media files
- `documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word/pages/page-*.png`: 35 rendered page PNGs via LibreOffice→PDF→pdftoppm
- `scripts/extract_docx_simple.py`: Custom python-docx extraction script (official extract_docx_source.py does not exist)
- `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO/paper.draft.yaml`: Complete 25-question draft
- `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO/paper.yaml`: Expanded paper
- `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO/paper-map.yaml`: Page map
- `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO/items/Q001-Q025/`: All 25 items materialized
- `artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO/qa/contact-sheet-*.png`: 4 contact sheets

## §4 Verbatim commands
```
mkdir -p "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析"
cp "documents/初三/上海二模/2026年上海市中考数学二模试卷（16份）/精品解析：2026年上海市宝山区中考二模数学试卷/精品解析：2026年上海市宝山区中考二模数学试卷（教师版）.docx" "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/source.docx"
./.venv/bin/pip install python-docx
./.venv/bin/python scripts/extract_docx_simple.py "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/source.docx" "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word"
/opt/homebrew/bin/soffice --headless --convert-to pdf --outdir "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word/pages" "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/source.docx"
pdftoppm -png -r 200 "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word/pages/source.pdf" "documents/初三/2026届-上海市宝山区-初三二模数学-试卷及解析/word/pages/page"
mkdir -p "artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO"
./.venv/bin/python .codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py "artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO/paper.draft.yaml"
./.venv/bin/python .codex/skills/math-pdf-question-bank-ingestion/scripts/materialize_staging.py "artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO" --repo-root .
./.venv/bin/python .codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py "artifacts/题库/2026-07-24-上海初三试卷原题库/staging/2026-BAOSHAN-ERMO" --repo-root .
```

## §5 Outcome and discoveries
- Outcome: success — all 25 questions ingested, expanded, materialized, and structural audit passed (gate=structural)
- paper_id: 2026-BAOSHAN-ERMO, 25 items (6 choice + 12 fill-in + 7 problem), total 150 points
- Official `extract_docx_source.py` does NOT exist in the skill; used custom `scripts/extract_docx_simple.py` with python-docx
- `references/word-source-contract.md` also missing from skill references
- WMF formula objects dominate the images (431 total); PNG geometry figures used as prompt images for Q4, Q5, Q6, Q15, Q16, Q17, Q21, Q22, Q23, Q24, Q25
- LibreOffice at `/opt/homebrew/bin/soffice` for DOCX→PDF conversion, `pdftoppm` for PDF→PNG
- All 25 items have `human_review: pending` awaiting user approval
- Contact sheets generated at `qa/contact-sheet-001.png` through `contact-sheet-004.png`
