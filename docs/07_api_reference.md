# LabelLens — API Reference (v1 draft)

Base URL: `https://api.labellens.app/v1` (placeholder — replace at implementation time)
Auth: Bearer JWT on all endpoints except `/auth/*`.

Frontend can build against the mocked JSON shapes below before the backend/OCR/ML pipeline is ready (per the team-split recommendation in doc 01 §7).

---

## Auth

### `POST /auth/signup`
```json
// Request
{ "email": "user@example.com", "password": "..." }
// Response 201
{ "user_id": "u_123", "token": "jwt..." }
```

### `POST /auth/login`
```json
{ "email": "user@example.com", "password": "..." }
// Response 200
{ "user_id": "u_123", "token": "jwt..." }
```

### `PUT /users/{user_id}/conditions`
Sets the health-condition profile. Only the 4 supported values are valid.
```json
// Request
{ "conditions": ["diabetes", "migraine"] }  // subset of ["sugar", "diabetes", "migraine", "fever"]
// Response 200
{ "user_id": "u_123", "conditions": ["diabetes", "migraine"] }
```

---

## Scan & extraction

### `POST /scan`
`multipart/form-data`: `front_image`, `back_image` (required), `nutrition_image` (optional, if separate panel).

```json
// Response 202 (accepted, processing async — see ADR/system-design §6)
{ "scan_id": "s_456", "status": "processing" }
```

### `GET /scan/{scan_id}`
Poll until `status` is `done` or `failed`.
```json
// Response 200 — while processing
{ "scan_id": "s_456", "status": "processing" }

// Response 200 — done
{
  "scan_id": "s_456",
  "status": "done",
  "needs_review": false,
  "ocr_confidence_avg": 0.94,
  "product": {
    "product_id": "p_789",
    "product_name": "Example Biscuits",
    "brand": "ABC",
    "category": "I",
    "mrp": "₹40",
    "net_quantity": "100g",
    "manufacturer": "XYZ Foods Pvt Ltd",
    "fssai_license_no": "12345678901234",
    "ingredients": [
      { "name": "Wheat Flour", "position": 1 },
      { "name": "Sugar", "position": 2 },
      { "name": "Palm Oil", "position": 3 },
      { "name": "Sodium Benzoate", "ins_number": "211", "function": "Preservative", "position": 4 }
    ],
    "allergens": ["Cereals containing gluten (Wheat)"],
    "nutrition_per_100g": {
      "energy_kcal": 480,
      "protein_g": 6,
      "carbohydrate_g": 60,
      "total_sugar_g": 18,
      "added_sugar_g": 15,
      "total_fat_g": 20,
      "saturated_fat_g": 6.0,
      "trans_fat_g": 0,
      "sodium_mg": 420,
      "fibre_g": 0,
      "fv_percent": 0,
      "nlm_percent": 0
    },
    "inr": {
      "eligible": true,
      "baseline_points": 19,
      "positive_points": { "fv": 0, "nlm": 0, "fibre": 0, "protein": 6 },
      "final_score": 13,
      "stars": 2.0,
      "formula_version": "FSSAI-INR-2022-draft-v1"
    }
  }
}
```

### `GET /product/{product_id}`
Same `product` object shape as above, for previously scanned/stored products (no re-scan).

---

## Personalization

### `POST /personalize`
```json
// Request
{ "product_id": "p_789", "conditions": ["diabetes", "migraine"] }

// Response 200
{
  "product_id": "p_789",
  "disclaimer": "LabelLens is not a medical device and does not diagnose or treat any condition. Consult your doctor.",
  "verdicts": [
    {
      "condition": "diabetes",
      "verdict": "AVOID",
      "reasons": [
        "Total sugar (18g/100g) exceeds the Diabetes caution threshold and Sugar is among the first 3 ingredients."
      ]
    },
    {
      "condition": "migraine",
      "verdict": "GOOD_FIT",
      "reasons": [
        "No known migraine-trigger ingredients (MSG, aspartame, nitrites, tyramine sources) detected."
      ]
    }
  ]
}
```

---

## Compliance report

### `GET /compliance-report/{product_id}`
Generates and returns a PDF (`Content-Type: application/pdf`), built per doc 06.
Query param `?regenerate=true` forces a fresh generation instead of returning a cached one (rules/format may have changed since last generated).

```
Response 200
Content-Type: application/pdf
<binary PDF>
```

### `GET /compliance-report/{product_id}/summary` (optional convenience endpoint)
JSON summary without generating the PDF, useful for an in-app preview before download:
```json
{
  "product_id": "p_789",
  "regulation_version": "FSSAI Compendium Version VII (03.04.2025)",
  "font_size_summary": { "pass": 3, "fail": 1, "could_not_verify": 0 },
  "declarations_summary": { "pass": 15, "fail": 1, "could_not_verify": 2, "not_applicable": 2 },
  "overall_note": "Automated pre-check only — not a legal compliance certification."
}
```

---

## Compare

### `POST /compare`
```json
// Request
{ "product_id_a": "p_789", "product_id_b": "p_800" }

// Response 200
{
  "product_a": { "product_id": "p_789", "product_name": "Example Biscuits", "inr_stars": 2.0, "sodium_mg": 420, "total_sugar_g": 18 },
  "product_b": { "product_id": "p_800", "product_name": "Whole Wheat Crackers", "inr_stars": 3.5, "sodium_mg": 280, "total_sugar_g": 4 }
}
```

---

## Error shape (all endpoints)
```json
{
  "error": {
    "code": "LOW_OCR_CONFIDENCE",
    "message": "Ingredients panel could not be read reliably. Please retake the photo in better lighting.",
    "http_status": 422
  }
}
```

Suggested error codes to standardize on: `INVALID_IMAGE` (blur/resolution check failed client- or server-side), `LOW_OCR_CONFIDENCE`, `UNSUPPORTED_CATEGORY` (Category-III, no star rating available), `INVALID_CONDITION` (not one of the 4 supported), `NOT_FOUND`, `UNAUTHORIZED`.
