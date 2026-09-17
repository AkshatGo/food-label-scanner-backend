# LabelLens — Government Compliance Checklist Reference

Source: **FSSAI Compendium of Labelling & Display Regulations, Version VII (03.04.2025)** — the consolidated Food Safety and Standards (Labelling and Display) Regulations, 2020, with amendments. This is the source the **Compliance Report PDF generator** should implement directly, one row per checklist item, each carrying its regulation citation.

The compliance report has exactly the two sections the brief asked for:

- **Section A — Font size checklist** (Regulation 6(3) + Regulation 7(1))
- **Section B — Mandatory declaration checklist** (tabular, pass/fail, one row per requirement)

---

## Section A — Font / letter size checklist

### A.1 General numeral/letter height (Regulation 6(3), Table I)

Applies to information on the Principal Display Panel generally.

| Area of Principal Display Panel | Min height — normal case | Min height — blown/formed/moulded/perforated on container |
|---|---|---|
| Up to 200 cm² | 1 mm | 2 mm |
| Above 200 cm² up to 500 cm² | 2 mm | 4 mm |
| Above 500 cm² up to 2500 cm² | 3 mm | 5 mm |
| Above 2500 cm² | 6 mm | 8 mm |

- Width of any letter/numeral ≥ 1/3 of its height (exceptions: "1", "i", "I", "l").
- Net weight, retail sale price, expiry/best-before/use-by date, and Consumer Care details follow the **Legal Metrology Act, 2009 and its rules** instead of this table (flag as a separate, Legal-Metrology-sourced check — out of scope for v1 per doc 01 §4, but leave the row in the report as "Not evaluated in this version").
- On the crown/closure of a returnable glass bottle: minimum 1 mm for all declarations, regardless of the table above.

### A.2 Ingredient / Schedule-II declarations (Regulation 7(1)) — **this is the specific "ingredients font size" check named in the brief**

- Numerals and letters for declarations/specific requirements listed in **Schedule-II** (which includes the ingredients/additives declarations) must be **≥ 3 mm**, based on the letter "l".
- **Exception**: packages with surface area up to 30 cm² containing a caloric/non-caloric sweetener (or mixture) → minimum reduces to **1 mm**.

### A.3 INR / FOPNL logo size (if the product carries a star rating — Regulation 14(2)(c))

| Area of Principal Display Panel | Min height (mm) | Min width (mm) |
|---|---|---|
| Above 100 to 500 cm² | 15 | 15 |
| Above 500 to 2500 cm² | 20 | 20 |
| Above 2500 cm² | 25 | 25 |

### A.4 Veg / Non-veg symbol size (Regulation 5(4)(c))

| Area of Principal Display Panel | Min circle diameter (mm) | Min triangle side (mm) | Min square side (mm) |
|---|---|---|---|
| Up to 100 cm² | 3 | 2.5 | 6 |
| Above 100 to 500 cm² | 4 | 3.5 | 8 |
| Above 500 to 2500 cm² | 6 | 5 | 12 |
| Above 2500 cm² | 8 | 7 | 16 |

> Engineering note: measuring these against a photo requires a scale-calibration method — see the open question flagged in doc 05 §4. The report should state its calibration method and confidence, not present an uncalibrated estimate as a definitive legal PASS/FAIL.

---

## Section B — Mandatory declaration checklist (tabular)

Each row below becomes one line item in the report: **Requirement | Found on label? | Regulation citation | Status**

| # | Requirement | Regulation |
|---|---|---|
| 1 | Name of food (true nature; on front of pack) | Reg. 5(1) |
| 2 | List of ingredients present, titled "Ingredients"/"List of Ingredients" (unless single-ingredient food) | Reg. 5(2)(a) |
| 3 | Ingredients listed in **descending order of composition** by weight/volume at time of manufacture | Reg. 5(2)(b) |
| 4 | Compound ingredients declared correctly (either bracketed sub-list, or all sub-ingredients listed individually; exempt if compound ingredient <5% of food and non-functional additives) | Reg. 5(2)(e) |
| 5 | Added water declared where applicable | Reg. 5(2)(f) |
| 6 | Food additives declared with functional class + specific name or INS number | Reg. 5(5) |
| 7 | Allergen declaration present as "Contains…" for any of: gluten cereals, crustaceans, milk, eggs, fish, peanuts/tree nuts, soybeans, sulphites ≥10mg/kg | Reg. 5(14) |
| 8 | Veg/Non-veg symbol present, correct colour (green circle/brown triangle) and correctly sized per Section A.4, placed near product/brand name | Reg. 5(4) |
| 9 | Nutritional information panel present (Energy, Protein, Carbohydrate + Total Sugars + Added Sugars, Total Fat + Sat Fat + Trans Fat + Cholesterol where applicable, Sodium) per 100g/100ml **and** per serving/pack, plus %RDA | Reg. 5(3) |
| 10 | INR / FOPNL star rating displayed where the product is not Category-III exempt (doc 04 §1) | Reg. 14 |
| 11 | Net Quantity declared | Legal Metrology Rules, 2011 (out of scope v1 — see doc 01 §4) |
| 12 | MRP declared | Legal Metrology Rules, 2011 (out of scope v1) |
| 13 | Name & complete address of manufacturer/packer/importer (country of origin if imported) | Reg. 5, Legal Metrology |
| 14 | FSSAI Logo + License Number present | Reg. 10(1)(c) (non-retail); general requirement for retail packs |
| 15 | Batch/Lot/Code Number present | Reg. 10(1)(e) (non-retail); general requirement |
| 16 | Date of Manufacture/Packaging AND Best Before/Use By/Expiry declared, grouped together | Reg. 5(10) |
| 17 | Consumer care details present | General requirement |
| 18 | Instructions for use present, where applicable (e.g. reconstitution, "Refrigerate after opening") | Reg. 5(13) |
| 19 | Language: declarations in English or Hindi (Devanagari); any other language present does not contradict the English/Hindi text | Reg. 4(5) |
| 20 | Label content is clear, unambiguous, prominent, legible, not misleading | Reg. 4(3), 4(7) |

### Status values used in the report

- **PASS** — requirement clearly satisfied from extracted structured data.
- **FAIL** — requirement clearly absent or violated (e.g. ingredients not in descending order can't be verified automatically in v1, so this specific sub-check may need to stay "Not evaluated" — be explicit about what's actually automatable vs. what needs a human reviewer).
- **COULD NOT VERIFY** — OCR/extraction confidence too low, or the relevant panel wasn't photographed/visible; never silently defaulted to PASS or FAIL.
- **NOT APPLICABLE** — e.g. allergen row when no allergens are present at all, veg/non-veg exemptions (mineral water, packaged drinking water, carbonated water, alcoholic beverages, liquid milk, milk powder, honey per Reg. 5(4)).

### Exemptions to apply before running the full checklist

- Packages with surface area ≤ 100 cm²: exempt from ingredients list, lot/batch number, nutritional information, food-additive declaration, importer name/address, instructions for use (still required on any accompanying multi-unit package) — Reg. 8(1).
- Packages with surface area < 30 cm²: date of manufacture and use-by/expiry may be omitted (still required on multi-unit package) — Reg. 8(1)(a).
- Foods with shelf life ≤ 7 days: date of manufacture may be omitted, expiry/use-by still required — Reg. 8(3).
- Single-ingredient unprocessed foods, waters, salt, table-top sweeteners, coffee/tea extracts, herbal infusions, vinegars, alcoholic beverages, chewing gum, FSDU/FSMP foods: exempt from mandatory nutritional labelling — Reg. 5(3)(c).

---

## How this maps into the PDF report

The Compliance Report PDF (per ADR-5, generated separately from the nutrition/personalization result) should render as:

1. **Header**: product name, scan date, source regulation version ("Checked against FSSAI Labelling & Display Compendium, Version VII, 03.04.2025").
2. **Section A table**: Font-size checklist — item, measured/estimated mm, required mm (by PDP area band), PASS/FAIL/COULD NOT VERIFY, citation.
3. **Section B table**: the 20-row mandatory-declaration checklist above — requirement, found (Y/N/COULD NOT VERIFY), citation, notes.
4. **Overall summary**: count of PASS / FAIL / COULD NOT VERIFY / NOT APPLICABLE, with a clear statement that this is an automated pre-check, not a legal compliance certification, and a human/legal review is recommended before relying on it for regulatory submission.
