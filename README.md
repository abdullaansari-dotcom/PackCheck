# Quick start (Windows)

1. `python -m venv .venv` then `.venv\Scripts\activate` then `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and put ONE key in it: `GEMINI_API_KEY=...` or `ANTHROPIC_API_KEY=...`
3. Double-click `run.bat` (or run `python -m uvicorn app.main:app`). Open http://localhost:8000
4. In the scanner click **Test AI reader**. It must say "AI reader works". If it fails, the message says why.

Do not use `--reload` with the venv inside the project folder: it restarts forever.

# PackCheck

Checks a photo of a product label against the **Legal Metrology (Packaged Commodities) Rules, 2011** and
flags each finding with the exact rule it relates to. Built from the team's *PackCheck Compliance Rulebook* (v4)
for Smart India Hackathon 2026, problem statement **SIH26034**.

```
photo -> AI vision reader (Claude or Gemini: transcription + category hint) ---+
      -> OpenCV clean-up -> EasyOCR (English + Hindi, box positions) -----------+-> fusion (AI text on OCR boxes,
                                                                                   number conflicts flagged)
      -> layout -> normalization -> declaration extraction -> category -> rule applicability -> rules engine
      -> JSON report (+ Supabase log)
```

The AI model only **reads** the label. Every pass / fail / review still comes from the deterministic rules engine.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · open legal points: [docs/LEGAL_QUESTIONS.md](docs/LEGAL_QUESTIONS.md) ·
what changed from the original version: [CHANGELOG.md](CHANGELOG.md)

## Run it

Python 3.11 is the target version.

```bash
python3.11 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt                           # easyocr pulls in PyTorch (big download)
cp .env.example .env                                      # fill Supabase values if you want logging
uvicorn app.main:app --reload
```

Open http://localhost:8000 (web UI) or http://localhost:8000/docs (API docs).
The first photo scan downloads the EasyOCR model weights (one time, needs internet): the English model and,
with `OCR_LANGS=en,hi`, the Devanagari model.

No Supabase yet? Leave those env vars empty. Everything works; scans just are not logged.

Command line: `python -m scripts.scan_image path/to/label.jpg [category]`.

## AI vision reader (recommended)

OCR alone struggles with small print, glare, curved packs and Hindi. Add one API key to `.env` and scans switch to
**hybrid** mode: the AI model transcribes the label, EasyOCR reads it independently and supplies box positions,
and any number the two readers disagree on is flagged in the report.

| Provider | Key | Default model | Notes |
|---|---|---|---|
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | `claude-sonnet-5-5` | pay as you go, console.anthropic.com |
| Gemini (Google) | `GEMINI_API_KEY` | `gemini-3.8-flash` | has a free tier, aistudio.google.com |

Override with `VISION_PROVIDER` and `VISION_MODEL`. `READER_MODE` (or the `reader` field of `/api/scan`) is
`auto` (default), `hybrid`, `ai` (no EasyOCR needed, but clear-space and contrast checks are limited) or `ocr`.
If the AI service fails in hybrid mode the scan falls back to OCR and says so in the report.

Privacy: label photos are sent to the provider you choose. The key is read on the server only and is never
returned by any endpoint (`/health` shows provider and model, not the key).

## Supabase (optional)

1. Create a project, open **SQL editor**, paste and run `supabase/schema.sql`.
2. Put `SUPABASE_URL` and the **service role** key in `.env`. Backend only. Never in frontend code, never in git.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/scan` | multipart: `file` (jpg/png/webp; the front), optional `file_back` (the back, checked together with the front as one label), `category` (default `auto`), optional `pack_type` (`can`/`bottle`/`other`), optional `reader` (`auto`/`hybrid`/`ai`/`ocr`) |
| POST | `/api/check-text` | JSON `{text, category, pack_type}`. Rules engine only, no OCR. Best for testing |
| GET | `/api/categories` | category keys (with group) for the dropdown; `auto` = detect from the label |
| GET | `/api/rules` | rule registry (references, limitations) and open legal questions |
| GET | `/api/samples` | demo labels |
| GET | `/api/history`, `/api/scans/{id}` | logged scans (needs Supabase) |

Per-field output (superset of the rulebook schema; older fields unchanged):

```json
{ "field": "mrp", "status": "REVIEW", "violation_code": "LOW_CONFIDENCE", "sub_case": "TAX_PHRASE_WITHOUT_ALL",
  "rule_reference": "Rule 6(1)(e)", "detected_text": "MRP: ₹ 60.00",
  "original_text": "MRP: ₹ ६0.0०", "normalized_text": "MRP: ₹ 60.00", "confidence": 0.86,
  "evidence": [{"label": "Price", "text": "MRP: ₹ 60.00", "original": "...", "confidence": 0.86, "bbox": [...],
                "normalizations": [...]},
               {"label": "Tax wording", "text": "Incl. of Taxes", "confidence": 0.91}],
  "detail": "...", "legal_question": "...", "limitation": "...", "applicability": "applicable" }
```

`status`: `PASS`, `FAIL`, `REVIEW` (needs review), `NOT_APPLICABLE`, `EXEMPT`, `SKIPPED_BY_TEAM_DECISION`, `NOT_CONFIGURED`.
`violation_code`: MISSING, FORMAT_ERROR, UNIT_ERROR, NONSTANDARD_PACK, VAGUE_LANGUAGE, LANGUAGE_ERROR, LOW_CONFIDENCE.
Overall `verdict`: COMPLIANT, NON_COMPLIANT, NEEDS_REVIEW, EXEMPT.
The scan result also carries `classification`, `product_info` (business name, address, page count, printed size,
contacts, barcode digits), `legal_questions`, `original_text` and `ocr` (engines, preprocessing report, regions, tokens).

## Where things are

| File | Role |
|---|---|
| `app/preprocess.py` | OpenCV clean-up, deskew, separator-line detection |
| `app/vision.py` | AI vision reader: Claude / Gemini calls, prompt, response parsing |
| `app/fusion.py` | AI text placed on OCR boxes, AI-vs-OCR number comparison |
| `app/ocr.py` | EasyOCR: detect once, English + Devanagari recognition, arbitration, fallback variant |
| `app/layout.py` | boxes → regions, columns, lines in reading order |
| `app/normalize.py` | contextual numeral / rupee / punctuation normalization (original preserved) |
| `app/extract.py` | finders for each declaration (text + geometry, testable without images) |
| `app/classify.py` | product category (user choice or evidence-based inference) |
| `app/data.py` | categories, applicability config, keywords, standard pack sizes (Part C), legal questions |
| `app/rules.py` | rule registry (reference, applicability, limitation) |
| `app/engine.py` | one check function per rule + Rule 26 exemptions + verdict |
| `app/geometry.py` | Rule 8 clear-space estimate, Rule 9 contrast |
| `app/pipeline.py` | image → result orchestration |
| `app/db.py`, `supabase/schema.sql` | audit log + image storage |
| `static/index.html` | web UI |

Order of work: exemptions (Rule 26) → Rule 9 → Rule 6 → Rule 5 → Rule 7 (skipped) → Rule 8.

## Tests

```bash
pytest -q                              # full suite
pytest tests/test_regression_bhaskar.py -v   # primary regression sample (notebook label photo)
python -m scripts.run_samples          # regenerates samples/sample_results.json
python -m scripts.record_ocr_fixture tests/fixtures/bhaskar_label.jpg tests/fixtures/bhaskar_easyocr_tokens.json
```

`tests/test_pipeline_image.py` and the photo test in `tests/test_api.py` run the real EasyOCR pipeline; they are
skipped automatically when EasyOCR / FastAPI are not installed.

## Decisions and known limits (say these out loud in the demo)

- **Rule 7 is skipped by team decision** (`SKIPPED_BY_TEAM_DECISION`): a photo has no real-world scale. Only the
  measurement is skipped. Notebooks and every other category are still fully checked.
- **Rule 8 is evaluated separately**, as an estimate from ratios inside the photo, passed only with a clear margin
  and pixel evidence; otherwise REVIEW. Never auto-failed. Text input cannot be assessed.
- **Category** comes from the user or, with "Detect automatically", from evidence on the label (shown in the result).
  Exemption categories are never inferred.
- **"Not read" is not "missing".** Low confidence, partially read declarations and values that depend on uncertain
  normalization go to REVIEW.
- **A business name without "Manufactured / Packed / Imported by"** is reported with its address but not given a
  legal role (REVIEW, open legal question).
- **Page counts are product information**, not net quantity. Dimensions are dimensions.
- **Standard pack sizes** exist only for the six Part C commodities; other categories show NOT_CONFIGURED.
- **Language** is checked on the whole label. The MRP paise rounding rule is not implemented.
- See [docs/LEGAL_QUESTIONS.md](docs/LEGAL_QUESTIONS.md) for questions waiting on the legal team.


## Testing many labels at once

```
python -m scripts.batch_check path\to\labels
```

Put one photo per label in the folder, or make a sub-folder per product holding `back.jpg` (and `front.jpg` if it has details). The script writes `batch_report.csv` and `batch_report.md` and prints a verdict per label, so you can test 15-20 products in one session and see which patterns are still missing.
