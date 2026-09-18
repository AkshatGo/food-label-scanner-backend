# LabelLens — Data Validation & QA Checklist

This is a pre-ship QA pass over the rating engine, OCR pipeline, and personalization logic — run this before every release that touches scoring, extraction, or rule tables.

## 1. Methodology & assumption review

- [ ] **Question framing check**: is the INR score being computed on a normalized per-100g/100ml basis, "as sold"? (Not per-serving, not per-pack — see doc 04 §6.1.) Pull 5 random scored products and manually re-derive from the raw OCR'd label to confirm.
- [ ] **Category assignment correctness**: spot-check 10 products' Category-I/II/III assignment against the Schedule-IV list (doc 04 §5) and the FSS 2011 category codes (6.8.1, 14.0 → Category-II; everything else scoreable → Category-I). Misclassification silently produces a wrong star rating.
- [ ] **Zero-energy/zero-sugar beverage exclusion**: confirm at least one test case where a diet/zero-cal soft drink correctly shows "not eligible for star rating" rather than a fabricated 5-star.
- [ ] **Exempt-category handling**: confirm the app never shows a star rating for a Category-III product (e.g. plain milk, salt, honey) — it should show the exemption message from doc 04 §1, not "0 stars" or blank.

## 2. Calculation / unit-test checklist (scoring engine)

- [ ] Worked example from doc 04 §3 passes exactly (baseline points = 19, final score = 13, 2 stars).
- [ ] Boundary tests: a value exactly on a table boundary (e.g. Energy = 480 kcal exactly) scores the lower band, per the `>` operator rule (doc 04 §6.2) — write one test per nutrient column confirming this.
- [ ] Category-II (liquid) test case scores only Energy + Total Sugar (baseline) and FV + Protein (positive) — confirm Sat Fat/Sodium/NLM/Fibre fields are ignored/absent from the liquid calculation path, not defaulted to 0 and silently included.
- [ ] Capping logic test: construct a product with baseline points = 25 (>20) and verify Protein points are capped at 7 and FV/NLM/Fibre at 5 each, even if the raw table lookup would give more.
- [ ] Star-mapping boundary test for every row of Table 6 (both solid and liquid columns) — 10 stars-worth of thresholds, both edges of each range.
- [ ] Round-trip test: re-running the same structured input twice produces an identical score (pure-function determinism, per doc 03 §6).
- [ ] Formula-version test: if `inr_formula_version` changes, old persisted scans still report their original score/version; a re-scan uses the new version. Confirm no accidental global re-scoring of history on deploy.

## 3. OCR / extraction accuracy checks

- [ ] Word-level ingredient extraction accuracy ≥ 90% on the pilot 50-product set (mix of Open Food Facts + own Indian photos per the source data doc's sourcing split) — measure against hand-transcribed ground truth, not eyeballed.
- [ ] Confirm low-confidence numeric fields (nutrition values especially) are actually surfaced to the user for confirmation, not silently passed into the scoring engine — pick 5 deliberately blurry test photos and confirm the "needs review" flag fires and blocks auto-scoring.
- [ ] Mixed Hindi (Devanagari) + English label test: at least 5 real products with bilingual declarations (required per Regulation 4(5)) correctly extract the English-language values used for scoring, without duplicating/conflating the Hindi text as a separate ingredient.
- [ ] INS-number resolution: confirm INS codes (e.g. INS 211, INS 322, INS 330) correctly resolve to ingredient names via the Ingredient Database and are not left as unresolved codes in the user-facing ingredient list.
- [ ] Per-100g normalization check: run a product whose nutrition panel is declared "per 30g serving" and confirm the extraction step correctly multiplies to per-100g before scoring (this is the #1 flagged pitfall in doc 04 — test it explicitly, don't assume the format is always per-100g already).
- [ ] **OCR-ambiguous digit gate** (introduced 2026-09): a nutrition value read on a line with no unit token whose text ends in `9` / `.59` may be Tesseract's `g`→`9` substitution ("54g" read as "549"). The extractor must **never silently rewrite** such a value (the earlier rewrite corrupted valid unit-less numbers like "Energy 549"); instead it keeps the value intact, lists the field in `nutrition_extraction.ocr_ambiguous_fields`, sets `needs_review`, and appends the substitution warning to the extraction note — which withholds the prominent rating and personalized verdicts until the scan is verified. QA: confirm (a) "Energy 549" with no unit extracts as 549 and is flagged, (b) "Protein 9 g" with a unit is not flagged, (c) an ambiguous field alone forces `needs_review` even on a confidently per-100g panel, and (d) the review reasons surfaced by `GET /scan/{id}` name the affected field. Regression tests live in `tests/test_nutrition_extractor.py`.

## 4. Compliance report checklist accuracy

- [ ] Font-size measurement: confirm the reported mm height for a checked declaration is derived correctly for at least 3 different principal-display-panel area bands (≤200cm², 200–500cm², 500–2500cm², >2500cm² — Table I in doc 06). **Open engineering question, flag before launch**: font-height-in-mm requires either (a) a physical reference/calibration object in-frame at capture time, or (b) a user-entered pack dimension, since a photo alone has no absolute scale. Do not ship a font-size check that silently assumes a fixed, unverified pixels-per-mm ratio — this would produce false PASS/FAIL results on a legally meaningful checklist item. Document the chosen calibration method and its accuracy limits in the compliance PDF itself.
- [ ] Run the checklist (doc 06) against at least 2 intentionally-flawed sample labels (one missing an allergen declaration, one with undersized ingredient-list font) and confirm both are correctly flagged FAIL with the correct regulation citation, not just a generic "non-compliant."
- [ ] Confirm every checklist line in the generated PDF cites a specific regulation/clause (per ADR-1) — spot check 5 lines against doc 06's source table.
- [ ] Confirm the report doesn't claim compliance ("PASS") for a checklist item the extraction step genuinely couldn't determine (e.g., a declaration present but off-camera) — that item should show "COULD NOT VERIFY," never a false PASS.

## 5. Personalization rule engine checks

- [ ] Every rule in doc 04 §4 has been reviewed and signed off by a nutrition/medical-content reviewer before launch (this is a required human gate, not just an engineering test — flag explicitly in the release checklist).
- [ ] For each of the 4 conditions, construct one product that should clearly AVOID, one CAUTION, one GOOD_FIT, and confirm the verdict + displayed "why" reason matches the specific rule that fired (not a generic message).
- [ ] Confirm the "not medical advice" disclaimer renders on every personalization result screen, unconditionally.
- [ ] Confirm a user with no conditions selected sees no personalization card at all (rather than a default/generic verdict that could be misread as medical guidance).
- [ ] Confirm multiple selected conditions (e.g. both Diabetes + Migraine) show each condition's verdict distinctly, not merged/averaged into one score.

## 6. Bias / reasonableness checks (per data:validate-data framework)

- [ ] Sanity-check the INR score distribution across the pilot 50-product set — does it roughly match intuition (ultra-processed snacks score low stars, fresh/whole-ingredient products score high)? A systematic skew (e.g. everything landing at 2.5–3 stars) suggests a boundary/calculation bug worth investigating before trusting the pipeline at scale.
- [ ] Confirm the rule tables and Ingredient Database are sourced only from FSSAI/DoCA official material (per ADR-6) — spot-check 5 ingredient entries in `ingredients.csv` against their `source`/`source_date` fields; reject any entry sourced from an unverified blog or AI-generated guess (this was an explicit anti-pattern called out in the source data-architecture doc: "don't ask an AI 'is INS 211 dangerous' — go through your verified database instead").
- [ ] Confirm rule tables carry `effective_date`/`last_verified` and that a re-verification cadence (e.g. quarterly) is actually scheduled with the Dataset/Research owner, not just documented once.

## 7. Presentation / UX checks

- [ ] Star rating and personalization verdict are visually and functionally distinct on screen (users should not confuse "2 stars, generally moderate nutrition" with "AVOID for your condition" — a product can be a fine general-nutrition score but still be flagged AVOID for a specific condition, or vice versa; the UI must not blend these into one number).
- [ ] Compliance PDF is clearly labelled as a checklist against FSSAI's Labelling & Display Compendium (Version VII, 03.04.2025) and the INR gazette notification, with the source version stated on the document itself, so it's clear what it was checked against if regulations later change.
