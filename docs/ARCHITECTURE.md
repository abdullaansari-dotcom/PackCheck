# PackCheck architecture

## Pipeline

```
IMAGE UPLOAD (POST /api/scan)
 └─ app/preprocess.py   decode (EXIF, pixel cap) → text-height-driven upscale → conditional
                         illumination correction → conditional gentle denoise → CLAHE → deskew
                         → detect printed vertical rules (column separators)
 └─ app/ocr.py          EasyOCR: detect boxes ONCE (CRAFT) → recognise every box with the English
                         model → (optional) recognise the SAME boxes with the Devanagari model →
                         per-box arbitration → one fallback preprocessing variant if the pass is weak
 └─ app/layout.py       recursive XY-cut over boxes → regions (blocks) and columns → lines in
                         reading order; every line keeps its bbox, region, column and tokens
 └─ app/normalize.py    (inside LabelText) contextual, length-preserving normalization; original
                         text kept; every change recorded, value-changing ones flagged "uncertain"
 └─ app/extract.py      declaration extraction with spatial association (same region / adjacent line)
 └─ app/classify.py     product category: user choice, or inferred with evidence (category="auto")
 └─ app/rules.py        rule registry: reference, applicability per category, limitation
 └─ app/engine.py       Rule 26 exemptions first → each registry rule → verdict
 └─ app/geometry.py     Rule 8 clear-space estimate and Rule 9 contrast from the photo
 └─ app/main.py         FastAPI routes (unchanged paths) + Supabase logging (app/db.py)
 └─ static/index.html   results UI
```

`app/pipeline.py` wires these stages together so scripts and tests can call them without the web layer.

## Original architecture (v1) and where information was lost

| Stage | v1 behaviour | Loss / misinterpretation |
|---|---|---|
| Preprocess | upscale only if longest side < 1000 px; always `fastNlMeansDenoising(h=7)` + CLAHE | 1280 px photo of a thin label kept ~17–20 px text; strong denoise smears decimal points and thin strokes |
| OCR | `easyocr.Reader(['en','hi'])` → `readtext` | With `hi` listed, EasyOCR recognises **every** box with its Devanagari model. On English text it emits Devanagari digits (`२६७`, `₹ ६0.0०`) and sometimes wrong digits (`140` → `२४०` = 240) |
| Grouping | sort all boxes by y-centre, merge everything on a visual row | logo, address, price and barcode columns fused into lines like `Kiadb Industrial Area, २४० Pages MRP: ₹ ६0.0०`; bounding boxes discarded afterwards |
| Extraction | regex over one joined string, fixed character windows | tax regex required the word "all" (label says "Incl. of Taxes"); manufacturer required "Manufactured by"; `Size 30x18Cms` failed the dimension regex (`cms`); email needed a dot the OCR dropped; barcode digits could match the phone regex |
| Category | user dropdown only, default "other"; no stationery categories | the notebook was evaluated as "other" |
| Engine | 10 fields, statuses PASS/FAIL/REVIEW/N.A./EXEMPT; Rule 7 and Rule 8 both simply "not checked" (limitations text) | Rule 8 silently dropped with Rule 7; no NOT_CONFIGURED; "not found" on a decent photo = MISSING even when the OCR text visibly contained evidence |

## Root causes of the Bhaskar Book Tech results

1. **Devanagari digits** — model selection (`['en','hi']` → Devanagari recogniser for English text), not EasyOCR's detector. Fixed by English-primary recognition with a Devanagari secondary pass on the same boxes and arbitration (`app/ocr.py`), plus contextual normalization that flags any remaining Devanagari digit inside English text as uncertain (`app/normalize.py`).
2. **Mixed columns** — row grouping ignored horizontal gaps and printed rules. Fixed by XY-cut layout using gutters that run through ≥ 2 rows and detected separator lines (`app/layout.py`, `find_vertical_rules`).
3. **MRP "MISSING"** — with the exact text in the screenshot, v1 actually returns `FORMAT_ERROR` (its tax regex needs "all"); a `MISSING` result requires the ₹ sign and digits to have been unreadable to its regexes in that run. Either way: digits in another script, a rupee glyph the English model cannot output, and a too-narrow tax phrase. Fixed by normalization, cross-model ₹ restoration, rupee-glyph handling in price context, and a three-way tax-wording classification (accepted / without "all" / unreadable).
4. **Manufacturer "MISSING"** — the label has no "Manufactured by" wording; v1 looked only for that wording. Now the business name and full address are extracted and reported, and the unstated legal role goes to review (PackCheck does not assign a role on its own).
5. **Net quantity "MISSING"** — correct that no net-quantity declaration exists, but `140 Pages` was ignored entirely. It is now recorded as product information and, for paper products, the result is REVIEW with an open legal question (can a page count serve as net quantity?).
6. **Generic name review** — category "other". The label is now classified as a notebook from evidence (`140 Pages`, `end sheets`); the brand word "BOOK" is not accepted as a generic name.

## Status vocabulary

`PASS`, `FAIL`, `REVIEW` (displayed "Needs review"; value kept for API compatibility), `NOT_APPLICABLE`, `EXEMPT`, `SKIPPED_BY_TEAM_DECISION` (Rule 7 only), `NOT_CONFIGURED` (no rulebook mapping yet — never a legal exemption).

Verdict: `EXEMPT` (full Rule 26 exemption) › `NON_COMPLIANT` (any FAIL) › `NEEDS_REVIEW` (any REVIEW, or a FAIL while a possible exemption is unconfirmed) › `COMPLIANT`. Skipped and not-configured checks never make a label look compliant or non-compliant.

## OCR engine decision

EasyOCR is kept. Evidence gathered while rebuilding:

* the Devanagari digits and the `140 → 240` error come from which recognition model was used, which is a configuration choice;
* column mixing and missed declarations came from grouping and parsing, which any engine would hit;
* Tesseract (used only as a test harness here, not added to the app) also mis-reads the ₹ sign (`7 60.00`) and drops words on this photo.

No second engine was added, so there is no new dependency. A real EasyOCR-vs-alternative comparison should be run with `scripts/record_ocr_fixture.py` on 10+ labels before considering one.

## Preprocessing decisions (measured on the Bhaskar photo)

| Technique | Decision | Reason |
|---|---|---|
| Upscale | by estimated text height to ~36 px, max 2560 px (EasyOCR canvas) | text was ~17 px |
| Illumination correction | only when background unevenness > 0.08 | avoids altering evenly lit labels |
| Denoise | only when estimated noise σ > 6, at most h=7 | v1's unconditional h=7 erased decimal points |
| CLAHE | kept | local contrast for small text |
| Deskew | 0.5°–15° only | measured on the text-line mask; tested at −6°, 4°, 10° |
| Adaptive threshold / sharpening | fallback variants only | hard thresholds destroy anti-aliasing the recogniser needs |
| Perspective correction | implemented, off by default (`PERSPECTIVE_CORRECTION`) | warping to a sticker crops text outside it |
| Curved surfaces | not corrected | needs 3-D modelling; documented limitation |

## Rule applicability (data, not code)

Defined in `app/data.py` (`CATEGORY_INFO`, `SIZE_TABLE_UNIT`, `DATE_EXEMPT_CATEGORIES`, `FULL_EXEMPT_CATEGORIES`, `TAX_PHRASE_WITHOUT_ALL_POLICY`) and read by `app/rules.py`.

* Notebooks and all stationery are normal categories: Rule 6 and Rule 9 run, Rule 8 runs, Rule 7 is `SKIPPED_BY_TEAM_DECISION` (Table II named in the explanation), Rule 5 is `NOT_CONFIGURED`, Rule 6(1)(f) is `NOT_CONFIGURED` pending a legal answer.
* Exemption-bearing categories (fast food, scheduled drugs, bidis, incense, LPG, agricultural produce) are never inferred, only user-selected.
* Quantity-based Rule 26 exemptions need a labelled, confidently read quantity; otherwise `UNCONFIRMED` and every check still runs.


## Front and back photos (2.8)

`pipeline.scan_images_bytes` takes one or two photos. Each is read independently (AI reader and OCR, same fusion as
before) into a `_Read`. The photos' lines are then stacked in one coordinate space (`Panel.y0` offsets, `PANEL_GAP`
apart) so the declaration finders see the whole label while every `Line`, `Hit` and `Evidence` remembers its `image`
(0 front, 1 back). Geometry-based checks (Rule 8, Rule 9 contrast) call `Ctx.locate()` to find the photo a box is on and
measure there in that photo's own coordinates, with that photo's grayscale; nothing is ever measured across photos.
A single photo takes the same path with no panels, so its output is unchanged.
