# LabelLens — Mobile app and API

The mobile-first app is served at `/ui` (browser visits to `/` redirect there).
It includes camera photo capture, an account-backed shelf, nutrition results,
comparison, optional dietary preferences, PDF reports, data export and account
deletion. Install it from a supported mobile browser as a PWA. The offline cache
stores only the public interface; scans and personal information require a connection.

Production deployment instructions and outstanding release gates:
[`docs/08_production_release.md`](docs/08_production_release.md).
Visual direction: [`DESIGN.md`](DESIGN.md). Replit configuration is included.
The release is not yet deployed or verified against a managed production database.

**API privacy change:** scan uploads, polling, images, products and PDF reports now
require authentication and are scoped to the signed-in owner. The browser uses an
HttpOnly cookie; API clients may use the bearer JWT. Existing unowned development
records are intentionally not exposed to authenticated users.

OCR-based food label scanner implementing the full LabelLens spec: **FSSAI Indian Nutrition Rating (INR) star formula**, **4-condition personalization rule engine**, and the **Government Compliance Report (PDF)** — all as a transparent, versioned, auditable **rules/formula engine, not a health-verdict model** (ADR-1).

The full engineering documentation set lives in [`docs/`](docs/) (00_README → 07_api_reference).

## What's implemented

| Spec item | Source | Status |
|---|---|---|
| INR star rating (Schedule III, Tables 1–6) — strict `>` boundaries, capping, star mapping | doc 04 §2–3 | ✅ `app/services/fssai_rating.py` |
| Category-I/II/III classification + Schedule-IV exempt list + zero-energy/zero-sugar proviso | doc 04 §1, §5 | ✅ `app/services/category_classifier.py` |
| Nutrition extraction with **per-100g/100ml normalization** (per-serving → per-100) | doc 04 §6.1 | ✅ `app/services/nutrition_extractor.py` |
| OCR (off-the-shelf Tesseract behind a swappable interface) + preprocessing | ADR-2 | ✅ `app/services/ocr_service.py` |
| Ingredient curation: dedupe, INS-number resolution (FSSAI-sourced), allergen flags | ADR-6 | ✅ `app/services/ingredient_service.py` |
| Personalization rules: Sugar / Diabetes / Migraine / Fever — verdict + fired-rule reasons + mandatory disclaimer | doc 04 §4, ADR-4 | ✅ `app/services/personalization.py` |
| Compliance Section A (font sizes, Reg. 6(3) Table I / 7(1) / 14(2)(c) / 5(4)(c)) with **calibration honesty gate** | doc 06 §A, doc 05 §4 | ✅ `app/services/compliance.py` |
| Compliance Section B (20-row mandatory-declaration checklist with citations, PASS/FAIL/CNV/NA) | doc 06 §B | ✅ `app/services/compliance.py` |
| Compliance Report PDF | doc 06 | ✅ `app/services/compliance_pdf_service.py` |
| Auth (JWT, PBKDF2) + health-conditions profile (4 fixed values only) | doc 07 | ✅ `app/services/auth_service.py` |
| `POST /scan` (front+back mandatory, async) → poll `GET /scan/{id}` | doc 03 §6, ADR-3 | ✅ `app/api/routes.py` |
| `/product/{id}`, `/compare`, `/personalize`, `/compliance-report/{id}` | doc 07 | ✅ `app/api/routes.py` |
| Two-photo capture gate (third nutrition photo optional) | ADR-3 | ✅ |
| `needs_review` flag when OCR confidence is low — never silently guess a number feeding a health formula | doc 01 §8.2 | ✅ |
| Formula/rule version stamps on every score (`FSSAI-INR-2022-draft-v1`, `FSSAI Compendium Version VII (03.04.2025)`) | doc 03 §6 | ✅ |

Deliberate scope cuts (documented, not missing): Legal-Metrology MRP/net-quantity verification stays "Not evaluated in this version" (doc 01 §4), ingredient descending-order verification is COULD NOT VERIFY (not automatable in v1, doc 06), font-size rows are COULD NOT VERIFY without a scale calibration (doc 05 §4 honesty gate).

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env              # defaults work with zero external services
.venv/bin/python -m uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Swagger docs: http://127.0.0.1:8000/docs
- Requires the `tesseract` binary (`apt install tesseract-ocr` / `pacman -S tesseract`).

**Storage:** set `MONGODB_URI` in `.env` for MongoDB (scans/users/products + GridFS images). Leave it empty to use the built-in in-memory store (dev only — data resets on restart).

## End-to-end example

```bash
.venv/bin/python scripts/smoke_test.py http://127.0.0.1:8000
```

The script signs up, sets a conditions profile, scans a rendered label image (real OCR), polls to completion, fetches the product, compares two products, personalizes for all 4 conditions, and downloads the compliance PDF.

## API surface (doc 07)

```
POST   /api/v1/auth/signup                       201 {user_id, token}
POST   /api/v1/auth/login                        200 {user_id, token}
PUT    /api/v1/users/{user_id}/conditions        {conditions: [sugar|diabetes|migraine|fever]}
GET    /api/v1/users/{user_id}/conditions
POST   /api/v1/scan                              multipart: front_image, back_image [, nutrition_image] → 202 {scan_id, status}
GET    /api/v1/scan/{scan_id}                    poll → {status, needs_review, ocr_confidence_avg, product}
GET    /api/v1/product/{product_id}              full structured product + INR + compliance
POST   /api/v1/compare                           {product_id_a, product_id_b} → side-by-side
POST   /api/v1/personalize                       {product_id, conditions?} → verdicts + disclaimer
GET    /api/v1/compliance-report/{product_id}    PDF (Content-Type: application/pdf)
GET    /api/v1/compliance-report/{product_id}/summary   JSON preview
```

Errors follow the doc 07 shape: `{"error": {"code", "message", "http_status"}}` with codes `INVALID_IMAGE`, `LOW_OCR_CONFIDENCE`, `INVALID_CONDITION`, `NOT_FOUND`, `UNAUTHORIZED`.

## Tests (doc 05 QA checklist)

220 tests covering: the doc 04 §3 worked example, every Table 2/3 band boundary (strict `>`), Table 4 capping (both regimes), every Table 6 star edge (solid + liquid), determinism (round-trip), Category-III exemption, the zero-energy/zero-sugar beverage proviso, per-serving → per-100g normalization, INS resolution, allergen detection, personalization AVOID/CAUTION/GOOD_FIT per condition, the font-size calibration honesty gate, checklist citations, and the full API surface.

```bash
.venv/bin/python -m pytest tests/ -q
```

## Engineering notes

- **The doc's worked example has two arithmetic slips against its own tables** (energy 480 kcal sits exactly on the ">480" boundary → 5 pts by the strict-`>` rule, not 6; protein 6 g → 5 pts, not 6). The engine implements the printed tables faithfully; the final score (13) and 2.0★ rating match the doc under either derivation. See `tests/test_fssai_rating.py`.
- **Table 6 liquid rows print "1.5★: 16–18" and "1★: 18–20"** (overlapping at 18). Resolved as contiguous bands (1.5★ = 16–17, 1★ = 18–19, 0.5★ ≥ 20), preserving every non-overlapping edge. Documented in the engine docstring.
- Sat-fat bands step by 1 up to >10 (10 pts) then by 2 (12, 14, … 40 → 25 pts), per the printed Table 2 column.
- The INR gazette is a **draft** (13 Sept 2022, 48-month runway). `formula_version` is stamped on every result so historic scans show what was true when scanned; update the rules table (not a model) when FSSAI finalizes amendments.
- Before launch, the 4 personalization rule tables require sign-off from a nutrition/medical reviewer (doc 05 §5 — a human gate, not a test).

## Layout

```
app/
  api/routes.py            REST surface (doc 07)
  services/
    fssai_rating.py        INR formula engine (pure function)
    category_classifier.py Category I/II/III + Schedule-IV
    nutrition_extractor.py OCR text → normalized per-100 nutrition
    ingredient_service.py  INS database, allergen groups, curation
    personalization.py     4-condition rule tables
    compliance.py          Section A + Section B engines
    compliance_pdf_service.py  ReportLab PDF
    scan_pipeline.py       orchestration (OCR → product → compliance)
    ocr_service.py         Tesseract wrapper (swappable, ADR-2)
    nlp_cleanup.py         OCR noise cleanup
    auth_service.py        JWT + PBKDF2 + conditions profile
  database/store.py        MongoDB or in-memory (identical API)
  models/scan_model.py     scan document factory
tests/                     220 tests (doc 05 QA checklist)
docs/                      LabelLens engineering documentation set
scripts/smoke_test.py      live end-to-end verification
```
