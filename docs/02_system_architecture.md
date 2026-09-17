# LabelLens — Architecture Decision Records

---

## ADR-1: Rules/formula engine for scoring & compliance, not a trained "healthy/unhealthy" model

**Status:** Accepted
**Date:** 17 Sep 2026
**Deciders:** Tech lead, ML lead, Rules & Scoring owner

### Context
The nutrition rating and the government-compliance verdict both have official, published, deterministic definitions (the FSSAI INR formula; the FSSAI Labelling & Display checklist). A learned model mapping image → verdict would be unauditable, would drift from regulation updates, and is unnecessary since the ground truth is already a formula.

### Decision
Only **one** ML model is trained: OCR-text → structured entities. Everything downstream (compliance pass/fail, INR star score, personalization verdict) is implemented as versioned, testable, deterministic code/config (a "rules engine" + "scoring engine"), each line traceable to a specific regulation clause or documented product rule.

### Consequences
- ✅ Every verdict shown to a user can be explained with a citation ("Regulation 6(3), Table I").
- ✅ When FSSAI updates a threshold (as it has repeatedly — 2021/2023/2025/2026 amendments per the source conversation doc), only the rules table changes, not a retrained model.
- ✅ Testable with plain unit tests (given nutrition values → expect exact star score).
- ⚠️ Requires disciplined rule-table maintenance with a `source_document`, `source_page`, `effective_date`, `last_verified` column on every rule row (see doc 03, data model) — this is a process cost the Dataset/Research owner must actively carry.

---

## ADR-2: OCR/vision engine — off-the-shelf, not custom-trained

**Status:** Accepted

### Context
Building a custom OCR model is a multi-year research problem; open-source OCR (PaddleOCR, EasyOCR, Tesseract) already handles printed Latin+Devanagari text reasonably well, and the project's differentiator is the extraction→rules pipeline, not OCR itself.

### Decision
Use an off-the-shelf OCR engine (spike PaddleOCR vs EasyOCR vs Tesseract vs a managed cloud OCR API in week 1; pick by measured accuracy on a 20-image sample of real Indian packaging). Invest engineering time instead in **image preprocessing** (crop to label region, deskew, denoise, contrast-enhance) and in the **information-extraction** step that turns raw OCR text into structured fields — this is the one place a trained model earns its keep.

### Consequences
- ✅ Faster time-to-working-pipeline.
- ✅ Swappable: OCR engine sits behind an internal interface so it can be replaced without touching downstream code.
- ⚠️ Multi-language (Hindi Devanagari + English) mixed labels are a known harder case; budget extra QA time here specifically, since Regulation 4(5) requires English or Hindi (Devanagari) declarations.

---

## ADR-3: Capture UX enforces two mandatory photos (front + back/ingredients), with client-side quality gates

**Status:** Accepted

### Decision
The app requires exactly two photos before submission — **Front** (product/brand identification) and **Back** (ingredients + nutrition table; a third "nutrition table" photo is optional if it's on a separate panel). Before upload, run a lightweight client-side check (blur score via Laplacian variance, minimum resolution, basic glare detection) and reject/re-prompt on failure, rather than sending a bad image to the server and failing OCR silently downstream.

### Consequences
- ✅ Reduces OCR failure rate at the source — cheaper than fixing bad OCR output after the fact.
- ✅ Matches the exact requirement in the brief ("no unclear pictures").
- ⚠️ Adds a small amount of client-side CV logic (acceptable — OpenCV/ML-Kit-class libraries handle this cheaply on-device).

---

## ADR-4: Personalization is a per-condition rule table, capped at 4 launch conditions

**Status:** Accepted

### Context
"Personalized health verdict" is the highest-risk feature in the product from a correctness/liability standpoint. Free-text disease entry + an LLM-generated verdict would be unauditable and could constitute unlicensed medical advice.

### Decision
Support exactly 4 conditions at launch (**Sugar-sensitivity, Diabetes, Migraine, Fever**), each defined by an explicit, versioned rule table mapping nutrient thresholds / ingredient flags → a verdict + plain-language reason (full tables in doc 04). No free-text condition entry. Every verdict displays a "not medical advice, consult a doctor" disclaimer and a "why" breakdown listing exactly which rule fired.

### Consequences
- ✅ Auditable, extensible one condition at a time (adding condition #5 later = adding one rule table + review by the Rules & Scoring owner, not a model retrain).
- ✅ Lower liability surface than a generative "is this good for me" answer.
- ⚠️ Won't cover conditions outside the 4 — UI must make this limitation obvious, not silently degrade.

---

## ADR-5: Two distinct output artifacts, not one blended report

**Status:** Accepted

### Decision
Keep the **Nutrition/Personalization result** (in-app, real-time, INR star + personalized verdict) and the **Government Compliance Report** (PDF, generated on demand, per-product legal checklist) as two separate pipelines sharing the same structured-data input. They have different audiences (consumer vs. compliance-minded user/brand), different regulatory bases (FSS Labelling & Display Ch.6/Schedule III-IV vs. the full Compendium checklist), and different output cadences (instant vs. generate-and-download).

### Consequences
- ✅ Each can evolve/version independently (INR formula changes don't touch the compliance checklist code, and vice versa).
- ✅ Compliance PDF can be regenerated/re-versioned when FSSAI amends the Compendium, without touching the nutrition-scoring path.

---

## ADR-6: Data architecture — four+one dataset layers (carried from source doc, adopted as-is)

**Status:** Accepted

### Decision
Maintain five distinct data assets, not one blob:
1. **Product Images** (Open Food Facts bulk download + own-photographed Indian products — Open Food Facts explicitly recommends bulk download over heavy API use).
2. **AI Training Data** (OCR text + human annotations of entities — the only dataset that trains a model).
3. **Ingredient Database** (INS number → name → function → category → explanation, sourced from FSSAI regulations, never from unverified blogs).
4. **Government Rules Database**, split into `legal_metrology_rules.csv`, `fssai_labelling_rules.csv`, `nutrition_rules.csv` — each row carries `source_document`, `source_page`, `effective_date`, `last_verified`.
5. **Product Database** (`products.csv`) — the operational store of everything the app has extracted/scored, not a training set.

Full schema detail lives in doc 03.
