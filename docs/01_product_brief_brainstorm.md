# LabelLens — Product Brief & Brainstorm

## 1. Problem statement

Indian consumers face packaged-food labels that are (a) hard to read (tiny, dense, sometimes non-compliant font sizes), (b) full of ingredient codes (INS numbers, additive names) nobody understands, and (c) impossible to relate to their own health conditions in the ten seconds they spend holding the pack in a store aisle. Separately, brands/regulators have no easy consumer-facing way to check whether a specific SKU's label is actually compliant with FSSAI's Legal Metrology and Labelling & Display rules.

**Job to be done:** "In the aisle, in under 10 seconds, tell me whether this product is good for *me*, specifically — and tell me, later, whether the label itself is even legal."

## 2. Users

| User | Need |
|---|---|
| Health-conscious shopper / patient managing sugar, diabetes, migraine, or fever-related diet | Fast personalized verdict + plain-language ingredient explanation |
| Power user / dietitian / researcher | Full nutrition breakdown, INR star score, per-100g comparison across products |
| Brand / QA team (secondary, later phase) | Auto-generated compliance PDF against FSSAI checklist, to self-audit before print |
| Regulator / consumer-affairs body (aspirational, out of scope v1) | Aggregate compliance data across scanned SKUs |

## 3. In scope for v1

- Capture flow: front photo + back photo (ingredients panel), with in-app guidance to avoid blur/glare/crop (this directly protects OCR accuracy downstream).
- OCR → cleaned ingredient list (deduplicated, INS-numbers resolved to names, allergens flagged).
- Nutrition Rating: **Indian Nutrition Rating (INR)**, computed exactly per the FSSAI Sept-2022 gazette formula, per 100 g / 100 ml, "as sold" basis. Category-I (solid) and Category-II (liquid, non-dairy) supported at launch; Category-III (exempt list) short-circuits to "Not required to carry FOPNL rating" rather than a fabricated score.
- Personalization for exactly 4 conditions at launch: **High Sugar Intake / Sugar-sensitivity, Diabetes, Migraine, Fever** — each backed by an explicit, editable rule table (Section 4 below and detailed in doc 04), not a black-box model.
- Login + a simple health-conditions profile (multi-select from the 4 supported conditions + "none").
- Government Compliance Report (PDF) per product: font-size checklist + tabular mandatory-declaration checklist, both sourced directly from the FSSAI Labelling & Display Compendium (Version VII, 03.04.2025).

## 4. Explicitly out of scope for v1 (write these down so the team doesn't scope-creep)

- Diagnosing or treating any condition. LabelLens is a **label-literacy and compliance tool**, not a medical device. Every personalized verdict carries "not medical advice; consult your doctor" language, and the condition list stays a fixed, curated set — never free-text disease entry, to avoid uncontrolled medical claims.
- Training any model to map "image → healthy/unhealthy." (See doc 02, ADR-1.)
- Cosmetics / household / personal-care products — food-only at launch (the source data-architecture doc explicitly recommends this staging).
- Full legal-metrology audit (net-quantity-vs-price verification, MRP tamper checks) — the v1 compliance report covers **labelling & display** rules (font size + mandatory declarations) only; Legal Metrology weight/price verification is a documented Phase 2 item.
- Non-Indian products / non-FSSAI-regulated categories.

## 5. Why "rules engine, not a health-verdict model" is the right call

Straight from the sourced conversation doc: a model trained on `image → Healthy/Unhealthy` (a) can't explain itself, (b) can't be audited against a regulation, (c) drifts silently as government thresholds change, and (d) is a much bigger, riskier ML problem than the one actually being solved. The right split is:

```
IMAGE → OCR → STRUCTURED DATA → [RULES: compliance] + [FORMULA: nutrition score] + [RULES: personalization]
```

Only the OCR→structured-data step is genuinely "AI you train." Everything downstream is deterministic, versioned, and explainable — which is also what lets the compliance PDF cite a specific regulation clause per checklist line, and what lets the personalization verdict say *why* ("this product exceeds INR's 90 mg/100 ml sodium threshold and contains added sugar; flagged for Diabetes").

## 6. Success metrics (first milestone, ~50 products)

- OCR extraction accuracy on ingredient list (word-level) ≥ 90% on a 50-product pilot set (mix of Open Food Facts + your own Indian-product photos, per the source data doc's recommended sourcing split).
- INR score computed matches a manually-computed reference score for 100% of a 20-product hand-checked validation set (this is a deterministic formula — it should be exact, not "close enough"; see doc 05).
- Compliance checklist correctly flags at least the font-size violation and 2 of the most common missing-declaration violations on a small set of intentionally-flawed sample labels.

## 7. Team split (carried over from the source data-architecture doc, mapped to this project)

| Role | Owns |
|---|---|
| Frontend | Capture UX, results screens, PDF viewer — build first against mocked JSON (see doc 07 for the exact shape) |
| Backend | `/scan`, `/analyze`, `/product`, `/compare`, `/compliance-report`, `/personalize` endpoints (doc 07) |
| OCR | Image preprocessing (crop/deskew/denoise/contrast) + PaddleOCR/EasyOCR/Tesseract — do **not** train a custom OCR model |
| ML/NLP | The one model worth training: OCR-text → structured entities (INGREDIENT, ENERGY, SUGAR, SODIUM, PROTEIN, FIBRE, MRP, NET_QUANTITY, DATE, MANUFACTURER, ALLERGEN) |
| Rules & Scoring | INR formula implementation + Legal Metrology/FSSAI compliance rule tables + personalization rule tables |
| Dataset/Research | Product image collection (Open Food Facts + own Indian photos), ingredient reference database (FSSAI-sourced), rules database with citations, source/version tracking |

## 8. Open questions for the team to resolve before build

1. Which OCR engine (PaddleOCR vs EasyOCR vs Tesseract vs a cloud OCR API) gives the best accuracy on Indian packaging fonts/scripts (Hindi + English mixed labels are legally required per Regulation 4(5))? → spike in week 1.
2. Confidence-threshold behavior: what does the app show when OCR confidence is low on a nutrition value — a warning + manual-correction UI, or a blocked result? (Recommendation: warn + allow manual correction, never silently guess a number that feeds a health formula.)
3. Where does "Category-III exempt" detection come from — do we maintain the full FSS (Food Products Standards & Food Additives) Regulations 2011 category-code list, or start with a smaller curated exempt list (milk, oils, fresh produce, salt, etc. — see Schedule-IV, fully enumerated in doc 04) and expand?
