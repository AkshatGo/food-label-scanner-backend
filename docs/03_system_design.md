# LabelLens — System Design

## 1. Requirements

### Functional
- Capture front + back photos → OCR → structured data.
- Compute INR star rating (per 100 g / 100 ml, "as sold").
- Compute personalized verdict for the logged-in user's selected condition(s), from {Sugar, Diabetes, Migraine, Fever}.
- Generate a downloadable Government Compliance Report PDF per product.
- Let a user compare two previously scanned products.
- Auth + a minimal health-profile (condition multi-select).

### Non-functional
- End-to-end scan → result target: < 8s on a typical mobile connection (OCR is the dominant cost — plan for async processing with a client-side spinner/poll, not a blocking synchronous call).
- Deterministic scoring: identical structured nutrition input must always produce the identical INR score and personalization verdict (critical — this is a regulated-formula computation, not a probabilistic one).
- Every score/verdict/compliance line must be traceable to the rule/regulation clause that produced it (supports ADR-1).
- Rule tables (INR thresholds, compliance checklist, personalization rules) must be updatable without a mobile app release (server-side config, versioned).

## 2. High-level component diagram

```
┌──────────────┐     photos      ┌───────────────────┐
│  Mobile App   │ ───────────────▶│  API Gateway /     │
│ (capture, UI, │                 │  Backend (REST)    │
│  results, PDF │◀─────────────── │                     │
│  viewer)      │   JSON result   └─────────┬───────────┘
└──────────────┘                            │
                                             ▼
                              ┌───────────────────────────┐
                              │  Image Preprocessing        │
                              │  (crop/deskew/denoise)      │
                              └─────────────┬───────────────┘
                                            ▼
                              ┌───────────────────────────┐
                              │  OCR Engine (PaddleOCR/     │
                              │  EasyOCR/Tesseract)          │
                              └─────────────┬───────────────┘
                                            ▼
                              ┌───────────────────────────┐
                              │  Information Extraction     │
                              │  Model (OCR text → entities) │
                              └─────────────┬───────────────┘
                                            ▼
                              ┌───────────────────────────┐
                              │  STRUCTURED PRODUCT DATA    │
                              └───┬────────────┬────────────┘
                     ┌────────────┘            └─────────────┐
                     ▼                                        ▼
         ┌───────────────────────┐              ┌───────────────────────────┐
         │ Compliance Rule Engine │              │ Nutrition Scoring Engine   │
         │ (Legal Metrology +     │              │ (INR formula, Schedule III)│
         │  FSSAI Labelling rules)│              └─────────────┬──────────────┘
         └───────────┬─────────────┘                           ▼
                     │                              ┌───────────────────────────┐
                     │                              │ Personalization Rule Engine│
                     │                              │ (Sugar/Diabetes/Migraine/  │
                     │                              │  Fever rule tables)        │
                     │                              └─────────────┬──────────────┘
                     ▼                                            ▼
         ┌───────────────────────┐                   ┌───────────────────────────┐
         │ Compliance PDF Generator│                  │  In-app Result (JSON)      │
         └───────────────────────┘                   └───────────────────────────┘
                     │                                            │
                     └───────────────┬────────────────────────────┘
                                     ▼
                        ┌────────────────────────────┐
                        │  Product / Ingredient / Rules │
                        │  Databases (Postgres)          │
                        └────────────────────────────┘
```

## 3. Data flow (step by step)

1. **Capture** — app validates front + back photos client-side (blur/resolution/glare check per ADR-3); uploads to `POST /scan`.
2. **Preprocess** — crop to label region (front) and ingredients/nutrition panel (back), deskew, denoise, boost contrast.
3. **OCR** — raw text extraction with bounding boxes and per-token confidence.
4. **Information Extraction** — OCR text → entity-tagged fields: `PRODUCT_NAME, BRAND, MRP, NET_QUANTITY, MANUFACTURER, DATE(S), FSSAI_LICENSE, INGREDIENT[], ADDITIVE[], ALLERGEN[], ENERGY, PROTEIN, CARBOHYDRATE, TOTAL_SUGAR, ADDED_SUGAR, TOTAL_FAT, SATURATED_FAT, TRANS_FAT, SODIUM, FIBRE`. Low-confidence numeric fields (esp. nutrition values) are flagged for user confirmation rather than silently trusted (see ADR risk note in doc 05).
5. **Ingredient Curation** — dedupe, resolve INS numbers via the Ingredient Database (`ingredients.csv`), attach `function`, `category`, `plain_language_explanation`, `allergen_information`.
6. **Category classification** — determine Category-I (solid), Category-II (liquid, non-dairy), or Category-III (exempt) per Schedule-IV of the FSS Regulations (full exempt list in doc 04 §5). Category-III short-circuits the INR scoring path.
7. **Compliance Rule Engine** — evaluates the structured data against the mandatory-declaration checklist (doc 06) and the font-size table (Regulation 6(3), Table I) — the latter requires the OCR step to also report **measured font height in mm** for key declarations (derived from bounding-box pixel height + a known reference object or the app's photo-capture calibration; see Open Question in doc 05 §4). Produces a per-line PASS/REVIEW/FAIL with citation.
8. **Nutrition Scoring Engine** — computes the INR star rating exactly per Schedule III Tables 1–6 (formula reproduced verbatim in doc 04 §2).
9. **Personalization Rule Engine** — for each condition on the user's profile, evaluates the condition's rule table against structured nutrition + ingredient/allergen data, producing a verdict (`GOOD_FIT / CAUTION / AVOID`) + the specific reason(s).
10. **Persist** — write to `products` table (with images, structured data, scores) for later compare/history.
11. **Respond** — JSON result to the app (nutrition card + personalization card); PDF generated on-demand via a separate endpoint (not pre-generated for every scan, to save compute).

## 4. Data model (core tables)

```
products
  product_id (pk), barcode, brand, product_name, mrp, net_quantity,
  manufacturer, packer, importer, manufacturing_date, best_before, use_by,
  fssai_license_no, category (I|II|III),
  energy_kcal, protein_g, carbohydrate_g, total_sugar_g, added_sugar_g,
  total_fat_g, saturated_fat_g, trans_fat_g, sodium_mg, fibre_g,
  fv_percent, nlm_percent,                      -- fruit/veg %, nuts-legumes-millets %
  image_front, image_back, image_nutrition,
  ocr_confidence_avg, needs_review (bool),
  inr_score, inr_stars, inr_formula_version,
  created_at, updated_at

ingredients
  ingredient_id (pk), ingredient_name, ins_number, common_names[],
  function, food_category, regulatory_status, conditions,
  allergen_information, plain_language_explanation,
  source, source_date

product_ingredients (join table)
  product_id (fk), ingredient_id (fk), position (int, for descending-order display), raw_ocr_text

legal_metrology_rules / fssai_labelling_rules / nutrition_rules
  rule_id (pk), authority, regulation, category, field, requirement,
  condition (structured IF/AND expression), severity, points,
  source_document, source_page, effective_date, last_verified

personalization_rules
  rule_id (pk), condition (Sugar|Diabetes|Migraine|Fever),
  trigger_type (nutrient_threshold | ingredient_flag | allergen),
  field, operator, threshold_value, ingredient_list[],
  verdict (AVOID|CAUTION|GOOD_FIT), reason_template,
  source, last_verified

users
  user_id (pk), email, auth_hash, conditions[] (subset of {sugar, diabetes, migraine, fever}),
  created_at

scans
  scan_id (pk), user_id (fk), product_id (fk), personalization_result (jsonb), created_at
```

## 5. API contracts

Full endpoint-by-endpoint reference is in `07_api_reference.md`. Summary:

```
POST /scan             multipart: front_image, back_image → { scan_id, status: "processing" }
GET  /scan/{scan_id}   poll for result → { status, product, ocr_confidence, needs_review }
GET  /product/{id}     structured product data + INR score
POST /personalize      { product_id, conditions[] } → { verdicts: [...] }
GET  /compliance-report/{product_id}  → generates + returns PDF
POST /compare           { product_id_a, product_id_b } → side-by-side diff
POST /auth/login, /auth/signup, PUT /users/{id}/conditions
```

## 6. Scaling & reliability notes

- OCR + extraction is the expensive step — run as an **async job queue** (e.g., product images → queue → worker pool), not inline in the request/response cycle, so the mobile app polls `GET /scan/{id}` rather than holding a connection open.
- Cache the Ingredient Database and Rules tables in-memory/edge-cached in the scoring service — they change rarely (rule updates are a deliberate, reviewed process per ADR-1) and are read on every single scan.
- The INR scoring function should be a **pure function** (`nutrition_input → {score, stars, breakdown}`) with no side effects, so it's trivially unit-testable and safe to run identically in a batch backfill if a formula version changes.
- Store `inr_formula_version` and `rule_version` per product/scan record — if FSSAI amends the formula, old scans should still show what was true when they were scanned, while new scans use the new version (this mirrors the source doc's caution to track `effective_date`/`last_verified` per rule, not just take a snapshot as permanent truth).

## 7. Trade-offs explicitly made

| Decision | Trade-off accepted |
|---|---|
| Async OCR pipeline | Slightly more infra complexity (queue + polling) vs. a much better perceived latency and no blocked HTTP connections |
| Rules engine over ML for scoring/compliance | More manual rule-table maintenance vs. full auditability and regulatory traceability (non-negotiable given the domain) |
| Fixed 4-condition personalization | Less "impressive" than free-text disease input vs. dramatically lower medical-liability and higher trustworthiness |
| Off-the-shelf OCR | Slightly lower ceiling on accuracy vs. weeks/months saved not building OCR from scratch |
| Client-side capture quality gates | A bit more mobile engineering vs. much lower downstream OCR failure rate |
