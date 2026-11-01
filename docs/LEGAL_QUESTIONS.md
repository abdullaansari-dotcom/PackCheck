# Open questions for the legal research team

The PackCheck Compliance Rulebook (v4) does not settle the following. PackCheck does **not** invent an answer: each case is routed to human review (or marked NOT_CONFIGURED) and the question is shown in the result. Once answered, change the value in `app/data.py`; no engine code needs to change.

| ID | Question | Current handling | Where to change |
|---|---|---|---|
| `MANUFACTURER_ROLE_NOT_STATED` | A business name and full address are printed but the label does not say "Manufactured / Packed / Imported by". Does that satisfy Rule 6(1)(a)? (The rulebook's implementation note asks only for "a name string AND an address string"; Part A says the party must be the one who made, packed or imported it.) | REVIEW, sub_case `ROLE_NOT_STATED` | `check_manufacturer` in `app/engine.py` |
| `PAGE_COUNT_AS_NET_QUANTITY` | For notebooks and other paper products, can a page count ("140 Pages") serve as the net-quantity declaration, or is a unit count ("1 N") required? | REVIEW, sub_case `PAGE_COUNT_ONLY` | `check_net_quantity` |
| `STATIONERY_DIMENSIONS` | Does Rule 6(1)(f) (dimensions) apply to notebooks and other stationery? The rulebook's whitelist examples are bedsheets and towels. | NOT_CONFIGURED; any printed size shown as evidence | `CATEGORY_INFO[...]["dimensions"]` |
| `TAX_PHRASE_WITHOUT_ALL` | Is "Inclusive of Taxes" / "Incl. of Taxes" (without "all") an accepted equivalent of "inclusive of all taxes"? | REVIEW | `TAX_PHRASE_WITHOUT_ALL_POLICY` (`review` / `accept` / `format_error`) |

Other points the team should be aware of:

* **Rule 8 under Rule 26 partial exemption (10–20 g/ml):** PackCheck still evaluates Rule 8, because net quantity remains mandatory for these packs. Confirm.
* **Rule 8 is evaluated** (estimated from ratios in the photo). The finalized team decision covers Rule 7 only. If the team wants Rule 8 skipped as well, record that decision in the rulebook and set its applicability to `SKIPPED_BY_TEAM_DECISION` in `app/rules.py`.
* **Rule 9 contrast** is measured in the photo (luminance contrast around declarations). Low values go to review, never fail.
