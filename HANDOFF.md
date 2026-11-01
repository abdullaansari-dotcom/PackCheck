# PackCheck: handoff / context file

Upload this file (or paste the prompt below) when you continue in a new chat. It says what the project is, what has
been decided, how it is run, and what is still open, so nothing has to be re-explained.

## Ready-to-paste opening prompt

> I'm continuing work on **PackCheck**, my Smart India Hackathon 2026 project (problem statement SIH26034): a web app
> that checks product-label photos against India's Legal Metrology (Packaged Commodities) Rules, 2011. I'm attaching
> `HANDOFF.md` and the latest zip (`PackCheck_FINAL6.zip`). Read HANDOFF.md first, unzip the project, and work from
> that zip, not from memory. Rules for this chat: (1) when you change code, give me ONE complete new zip with a new
> name (I do not want to replace files one by one; I add my own `.env`); (2) run the tests and tell me the result;
> (3) say plainly what you could not test; (4) keep answers short and in plain words. Today I want to: <WHAT YOU WANT>.

## What it is

- FastAPI backend (`app/`), single-page UI (`static/index.html`, cream/navy editorial style modelled on the Veris
  site, PackCheck logo in `static/`), tests (`tests/`), scripts (`scripts/`).
- A label photo (back of pack = main, front optional) is read by an **AI vision model** (Gemini or Claude) and by
  **EasyOCR** at the same time. The AI text is placed on the OCR boxes (fusion). A **rules engine** (plain code, no
  model) then decides every PASS / FAIL / NEEDS REVIEW and cites the clause. The AI never judges.
- 13 checks: legibility, contrast, language, manufacturer, generic name, net quantity, month/year of manufacture, MRP,
  dimensions, consumer care, standard pack size, numeral height (Rule 7, skipped by team decision: a photo has no
  real-world scale), clear space around net quantity (Rule 8, estimated from the photo, never an automatic pass).

## Key design decisions (do not undo without asking)

1. **The AI reads, the rules decide.** AI output is a transcription plus quoted fields (product name, net quantity,
   MRP, manufacture date, manufacturer). A quote is used only if it is really printed in the transcription, and only
   when the pattern finders found nothing better. Never let a model decide compliance.
2. **Not found in a photo = NEEDS REVIEW, not FAIL.** FAIL stays for pasted text and for wrong formats (e.g. MRP
   without "inclusive of all taxes").
3. **Exemption categories are never guessed** (fast food, scheduled drugs, LPG, bidi, incense, agri produce): only
   when the user picks them.
4. **Categories are the commodities the rulebook has specific rules for** (tea, biscuits, salt, cement, toilet soap,
   aerated drinks, stationery, textiles). Everything else is "Packaged food / snacks", "Personal care / household" or
   "Other": they behave the same and show NOT_CONFIGURED for pack size. Do not invent rules.
5. **Two photos**: each is read on its own; geometry checks (clear space, contrast) run on the photo the
   declaration is printed on; text checks see both. Order is fixed front, back; API: `file_back`, `file_front`
   (old `file` = front). Max two photos.
6. Classifier ignores the ingredients list ("Iodised Salt" in a snack's ingredients must not make it a salt pack).

## How it is run (Windows, VS Code)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then put ONE key in .env: GEMINI_API_KEY=...  (or ANTHROPIC_API_KEY=...)
python -m uvicorn app.main:app          # or run.bat
```
Open http://127.0.0.1:8000 in Chrome/Edge and press Ctrl+Shift+R (the VS Code built-in browser caches the old page).
**Do not use `--reload`** with the venv inside the project folder: the watcher loops on `.venv`.
Scanner has a **Test AI reader** link (also `GET /api/vision-test`, `python -m scripts.check_ai`).
Batch test: `python -m scripts.batch_check <folder>` -> `batch_report.csv` / `.md`.
Tests: `python -m pytest -q` (expected: all pass; 3 skipped when EasyOCR/FastAPI are not installed). `tests/conftest.py`
keeps tests independent of the user's `.env` key.

## Environment facts learned the hard way

- The user's project is under OneDrive on Windows; first scan is slow (OCR models load). `HYBRID_OCR_MAX_SIDE=1400`
  makes OCR lean when the AI is on; `OCR_WARMUP=true` preloads models (only without --reload).
- Gemini models come and go and are sometimes overloaded (503) or stall. The app tries the configured/default model
  (`gemini-3.8-flash` at the time of writing), then asks Google which flash models the key can use and falls back
  (45 s first wait, 40 s per backup), and remembers the one that answered. `VISION_MODEL=` pins one;
  `VISION_MODEL_STRICT=true` disables fallback. `GEMINI_THINKING_LEVEL=low` keeps answers fast.
- The assistant's sandbox has no internet and no FastAPI/EasyOCR/httpx: the live AI, real OCR and the real server have
  **never been run by the assistant**. All tests use stand-ins. Ask the user to run one real photo and report back.

## Version history (see CHANGELOG.md)

2.1 AI reader + new UI · 2.2 Veris-style UI + logo · 2.4 snacks category, ingredients fix, date dd.mm.yy, lean OCR ·
2.5-2.7 Gemini timeouts, model discovery/fallback, 503 handling, test button · 2.8 front+back photos ·
2.9 back-first upload, AI-quoted fields, review-not-fail, Origami fixes, batch script · 2.10 AI fields for MRP/date/
manufacturer.

## Open items / ideas

- Origami tissue-box back (real photo): check that Rule 8 now measures around "Net Quantity (Box) : 1 N" and not the
  sheet count; units A and B addresses are still merged into one business name/address; role "Mfd. & Pkd." is not
  followed by a name, so manufacturer stays NEEDS REVIEW (correct: the label does not state the role clearly);
  category came out as "Other countable paper product" (a tissue/hygiene category may fit better if the rulebook says so).
- Run `batch_check` on 15-20 different real labels and fix the patterns that show up (each fix generalises).
- Consider extending AI quoted fields to consumer care and dimensions.
- Optional: Supabase logging (`supabase/schema.sql`), deployment, a short demo script for the hackathon.
- Open legal questions are listed in `docs/LEGAL_QUESTIONS.md` and in each report; they need the legal team, not code.

## Team

Abdulla Ansari (lead), Abhishek Gadiya, Abhijit Kumar Singh, Aayush Aaditya.
