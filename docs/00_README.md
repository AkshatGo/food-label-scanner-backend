# LabelLens — Engineering Documentation Set

**Project:** LabelLens — OCR-based food label scanner, FSSAI-formula nutrition rating, disease-based personalization, and government compliance report generator.
**Version:** v1.0 (draft for build)
**Date:** 17 Sep 2026

This is the full documentation package for handing LabelLens to an engineering team. It is derived from three source documents you supplied:

1. `LabelLens_Exact_Conversation_From_Dataset_Question.pdf` → data-architecture guidance (what to collect, what to train, what stays a rules engine).
2. `rating_system_by_govt_of_india.pdf` → the **actual FSSAI Gazette notification** defining the Indian Nutrition Rating (INR) star-rating formula (Sept 2022 draft, Chapter 6 + Schedule III/IV of the Labelling & Display Regulations, 2020).
3. `Comp_Labelling_Display_Version_VII_03042025.pdf` → the FSSAI **Compendium of Labelling & Display Regulations** (font-size table, ingredient-list rules, allergen rules, veg/non-veg symbol rules, nutrition-panel rules) used to build the compliance checklist.

## Reading order

| # | File | Purpose |
|---|------|---------|
| 1 | `01_product_brief_brainstorm.md` | Problem framing, users, scope decisions, what's in/out of v1 |
| 2 | `02_system_architecture.md` | ADR-style architecture decisions (OCR engine, rules-vs-ML split, hosting) |
| 3 | `03_system_design.md` | Component diagram, data flow, API contracts, data model, scaling |
| 4 | `04_rating_engine_and_personalization_spec.md` | The exact INR formula, worked example, disease-flag rule engine |
| 5 | `05_data_validation_qa.md` | QA checklist for the scoring engine, OCR pipeline, and personalization logic before shipping |
| 6 | `06_government_compliance_checklist.md` | The checklist the compliance-report PDF is built from (font size table, ingredient rules, etc.) |
| 7 | `07_api_reference.md` | REST API reference for backend team |

## One-paragraph summary of the product

A user photographs the **front** and **back** (ingredients + nutrition panel) of a packaged food product. OCR extracts raw text → an information-extraction step structures it into `{ingredients[], nutrition{energy, sugar, sat_fat, sodium, protein, fibre, FV%, NLM%}, mrp, net_qty, mfg/exp dates, fssai_license, allergens}`. Two outputs are generated per product:

- **A. Nutrition + Personalized Rating** — a 0.5–5★ **Indian Nutrition Rating (INR)** computed per the official FSSAI formula (per 100 g / 100 ml, "as sold"), plus a personalized "Good for you / Avoid" verdict for the four supported conditions (Sugar-sensitivity, Diabetes, Migraine, Fever), driven by a transparent, editable rule table — **not** a trained health-verdict model.
- **B. Government Compliance Report (PDF)** — a checklist-based report per product: (1) is ingredient/declaration font size ≥ the FSSAI-mandated minimum for that pack's principal-display-panel area, (2) a tabular pass/fail against the full mandatory-declaration checklist (ingredient order, allergens, veg/non-veg symbol, nutrition panel completeness, FSSAI license, dates, etc.).

**Core engineering principle carried through every document below (from your source PDF):** *don't train an AI to output "healthy/unhealthy."* OCR and one information-extraction model turn images into structured data; everything after that — compliance, nutrition score, personalization — is a **transparent, versioned rules/formula engine**, so every verdict is explainable and auditable against a cited regulation.
