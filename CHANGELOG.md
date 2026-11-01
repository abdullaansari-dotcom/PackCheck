# Changelog

## 2.10

- The AI-quoted fields now also cover **MRP (with tax wording)**, **manufacture date** and **manufacturer block**, besides product name and net quantity. Each quote is checked against the transcription (it must be printed there) and re-read with the rules' own finders; it is used only when the pattern finder found nothing, or a clearly more complete answer (same amount for MRP). A field located this way says so in its detail line.
- `HANDOFF.md`: project context and a ready-to-paste opening prompt for continuing in a new chat.

## 2.9

- **Back first.** The scanner's main slot is now the **Back** of the pack (where most declarations are printed); the **Front** is optional. A back-only scan is enough. `POST /api/scan` takes `file_back` and an optional `file_front` (the old `file` still means the front).
- **The AI labels the fields; the rules still decide.** The AI reader now also returns the product name and the net-quantity declaration it sees, copied from the label. The engine only uses a value if it is really printed in the transcription (verified), and only when its own patterns found nothing better.
- **Not found in a photo = Needs review, not Fail.** A declaration that is not found in a photograph (it may be on another face, or missed by the readers) now goes to review. FAIL is kept for pasted text and for wrong formats (for example an MRP without the tax wording).
- Fixes from the Origami tissue-box label: the product name is read from an `Item :` / `Product :` line; `Net Quantity (Box) : 1 N` beats `Number of usable Sheets : 100 N`; `+ 91 80 4346 2000` is recognised as a phone number; a `Regd. Office:` prefix is dropped from the business name; "tissue" and a few more everyday product words are known.
- `python -m scripts.batch_check <folder>` checks many labels in one run and writes a CSV and a Markdown summary.

## 2.8

- **Front and back photos.** The scanner now has a Front slot and an optional Back slot. When both are given, each
  photo is read on its own (AI and/or OCR) and the two are checked together as one label, so a declaration on either
  side counts. `POST /api/scan` accepts `file` (front) and an optional `file_back`; one photo works exactly as before.
- Geometry checks stay honest: Rule 8 (clear space) and Rule 9 (contrast) are measured on the photo the declaration is
  printed on, using only that photo's text and pixels, never across the two photos.
- Each piece of evidence, region and AI line is tagged Front or Back in the report. If one photo has no readable text
  the other is still checked and the report says so; if the AI reader fails on one photo only, that photo falls back to OCR.
- New `pipeline.scan_images_bytes([...])`; `scan_image_bytes` is now a thin wrapper around it. Tests: `tests/test_two_photos.py`.
- Only the front photo is stored when Supabase logging is on.

## 2.7

- Overloaded Gemini (429/503) is retried with a short wait, then the app switches to another model the key can use (lite models last).

## 2.6

- Gemini fallback: if the configured model stalls (45 s) or is retired, the app tries the next-newest flash models the key can use (40 s each) and remembers the one that answered.

## 2.5

- AI reader: Gemini is asked for a low thinking level (fixes timeouts), a timeout is no longer retried, default timeout 90 s, image sent at 1400 px.
- If the configured Gemini model is retired, the app asks Google which models the key can use and switches to the newest flash model by itself (`VISION_MODEL_STRICT=true` turns this off).
- "Test AI reader" link in the scanner and `GET /api/vision-test` / `python -m scripts.check_ai` report the exact AI error and timing.
- `run.bat` / `run.sh` start the server without auto-reload (the reload watcher loops on the `.venv` folder).
- OCR model pre-loading is opt-in (`OCR_WARMUP=true`).

## 2.4

- Speed: in hybrid mode OCR now runs lean (English only, no fallback variant, image scaled to `HYBRID_OCR_MAX_SIDE`, default 1400). OCR models load in the background when the server starts.
- Categories: added "Packaged food / snacks" and "Personal care / household" (no Rule 7 table, handled like "other"). The rulebook only has commodity-specific rules for the listed categories, so everything else belongs in one of these or "other".
- Classifier ignores the ingredients list (an "Iodised Salt" ingredient no longer makes a snack a salt pack).
- Dates printed as dd.mm.yy (e.g. 10.09.26) are now recognised as a manufacture date.
- AI prompt: label/value table columns (MFG. DATE | 10.09.26) are paired into one line.
- Default Gemini model is now gemini-3.8-flash.

## 2.2

- UI restyled to match the Veris look: cream paper, navy uppercase display type, amber accent, floating pill nav, viewfinder-ring hero that tilts with the pointer, scroll reveals.
- Added the PackCheck logo (nav, footer, favicon) in `static/`.

## 2.1.0: AI vision reader and new UI

- New `app/vision.py`: a multimodal model (Claude or Gemini, over plain HTTPS) transcribes the label photo and
  suggests a category. It reads only; the rules engine still decides everything.
- New `app/fusion.py`: AI text is placed on the OCR boxes (so Rules 8 and 9 keep their geometry); numbers the OCR
  did not see are flagged as AI/OCR disagreements (`AI_DISAGREEMENT_CONF`).
- Reader modes `auto` / `hybrid` / `ai` / `ocr` (`READER_MODE`, and a `reader` field on `/api/scan`). Hybrid falls
  back to OCR if the AI service fails, and to AI-only if EasyOCR is missing; both are stated in the report.
- AI category hint feeds `classify` with the same limits as text inference (never an exemption category, never
  over a user's choice). `/health` reports the AI provider and model (never the key).
- New single-page UI (editorial style): reader selection, AI/OCR reader cards, agreement flags, the AI
  transcription, rulebook grid loaded from `/api/rules`, light and dark themes.
- Tests: `tests/test_vision.py` (no network needed).

## 2.0.0 — PackCheck (project renamed)

Root causes and the reasoning behind each change: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### OCR and preprocessing
- English recognition is now primary; the Devanagari model reads the same boxes as a secondary pass and wins only
  where a box contains Devanagari letters. This removes the Devanagari digits (`२६७`, `₹ ६0.0०`) and wrong digits
  (`140` read as `२४०`) seen on English labels. The ₹ sign is restored when both models agree on the amount.
- One fallback preprocessing variant is tried only when the first OCR pass is weak.
- Preprocessing: upscaling driven by text height, conditional illumination correction and denoising (the old
  unconditional strong denoise erased decimal points), deskew, printed-separator detection, optional perspective
  correction (off by default), pixel cap for very large uploads.

### Layout
- New `app/layout.py`: bounding boxes are kept; an XY-cut separates columns (logo | address | price | barcode),
  regions and reading order; label/value pairs on one row stay together.

### Normalization
- New `app/normalize.py`: contextual, length-preserving normalization of Devanagari digits, letter/digit confusions
  inside numbers, rupee-glyph confusions in price context and typographic punctuation. The original text is kept;
  value-changing substitutions are flagged as uncertain and push the field to review.

### Extraction and semantics
- MRP: wider price and rupee formats; tax wording associated by layout region or adjacent line; three cases
  (accepted "all taxes" wording / wording without "all" / tax word only partly read) instead of found/not found.
- Manufacturer: business name and full address extracted without a "Manufactured by" keyword; the legal role is
  never assumed.
- Page counts recorded as product information; count declarations for countable goods ("10 notebooks", "1 N").
- Dimensions accept `Cms`, `mm`, `in` etc.; emails read without a dot are evidence flagged for review; barcode
  digits (valid EAN check digit) can no longer be taken for phone numbers.

### Categories and rules
- New stationery categories: notebook, exercise book, textbook, drawing book, register, diary, writing pad, other
  paper products. `auto` category with evidence-based inference.
- Rule registry (`app/rules.py`) and applicability data (`app/data.py`); new statuses `SKIPPED_BY_TEAM_DECISION`
  and `NOT_CONFIGURED`.
- New checks: Rule 7 (explicitly skipped by team decision), Rule 8 (estimated clear space), Rule 9 contrast.
- Rule 26 quantity exemptions need a clearly declared, confidently read quantity.
- Open legal questions are listed in each result and in `docs/LEGAL_QUESTIONS.md`.

### API and UI
- All routes unchanged. `category` now defaults to `auto` for `/api/scan` and `/api/check-text`. New `/api/rules`.
- Result adds `classification`, `product_info`, `legal_questions`, `original_text`, `ocr` and per-field
  `evidence`, `original_text`, `normalized_text`, `title`, `applicability`, `limitation`, `legal_question`.
- UI shows evidence (original vs normalized OCR text and confidence), new statuses, detected category, OCR regions
  and open legal questions.

### Tests
- Existing tests kept. `tests/test_api.py` now skips when FastAPI is not installed, and its title assertion reads
  "PackCheck" after the rename.
- New stage tests (normalize, layout, preprocess, classify, OCR arbitration, Rule 8 geometry), category and rule tests,
  the Bhaskar Book Tech regression suite over three independent inputs, and an end-to-end EasyOCR image test.
