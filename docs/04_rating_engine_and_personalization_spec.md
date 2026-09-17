# LabelLens — Rating Engine & Personalization Spec

Source: FSSAI Gazette Notification, F.No. Std./SP-08/T(FoPNL-N-01), 13 Sept 2022 — draft amendment to the Food Safety and Standards (Labelling & Display) Regulations, 2020, inserting **Chapter 6 (Regulation 14 — Indian Nutrition Rating)** and **Schedules III & IV**. This is the "Indian Nutrition Rating" (INR) — India's Front-of-Pack Nutrition Labelling (FOPNL) star system, analogous to Australia's Health Star Rating.

> ⚠️ Implementation note: this was published as a **draft** regulation with a 48-month voluntary-then-mandatory compliance runway from final notification. Before shipping, the Rules & Scoring owner must confirm against the current FSSAI site whether this has since been finalized/amended, and record the confirmed version + date in `nutrition_rules.csv`'s `effective_date`/`last_verified` columns (per ADR-1/ADR-6). Implement the version below as v1; do not hardcode it as permanently authoritative.

## 1. Category classification (required before scoring)

Every product is classified as:

- **Category-I — Solid foods** (includes dairy products and beverages that aren't Category-II): all FSS (Food Products Standards & Food Additives) Regulations 2011 food categories **except** category no. 6.8.1 and 14.0.
- **Category-II — Liquid foods (non-dairy)**: food category no. 6.8.1 and 14.0 specifically.
- **Category-III — Exempted from FOPNL**: the explicit list in Schedule-IV (full list in §5 below) — e.g. plain milk, plain fermented milk, ghee/butter oil, vegetable oils/fats, fresh fruit & vegetables, cocoa mass, flours/starches, fresh meat/poultry/fish, eggs, sugars/honey/table-top sweeteners, salt, herbs/spices/seasonings, vinegar, mustard, yeast, infant formula/medical-purpose foods, water, alcoholic beverages.
- Additionally: **any beverage/carbonated beverage with zero energy and zero sugar is not eligible for an INR star rating**, regardless of category (explicit proviso in the regulation).

`Category-III → do not compute a star score.` Show: *"This product category is exempt from FOPNL star rating under FSSAI Schedule-IV."* Do not fabricate a number.

## 2. The formula (verbatim from Schedule III)

All values are **per 100 g (solid) or per 100 ml (liquid), on an "as sold" basis** — this satisfies the brief's "per 100g" requirement exactly and is not optional/approximate; nutrition values pulled from a per-serving label must be normalized to per-100g/100ml before scoring (see §6, common implementation bug).

### Table 1 — Baseline reference values (health-risk factors) and minimum % (positive factors)

| Food risk factor | Solid foods | Liquid foods (non-dairy) |
|---|---|---|
| Energy, kcal | 400 | 30 |
| Total Sugars, g | 21 | 6 |
| Saturated fat, g | 5 | *(not scored for liquid)* |
| Sodium, mg | 450 | *(not scored for liquid)* |

| Positive factor | Minimum % |
|---|---|
| Fruits & Vegetables (FV) | 10% (solid) / 5% (liquid) |
| Nuts, Legumes & Millets (NLM) | 10% (solid only) |
| Dietary Fibre | 3% (solid only) |
| Protein | 1.5% |

### Table 2 — INR baseline points, Category-I (Solid), per 100 g

| Pts | Energy kcal | Sat. fat g | Total sugars g | Sodium mg | **Positive pts** FV | NLM | Fibre | Protein |
|---|---|---|---|---|---|---|---|---|
| 0 | ≤80 | ≤1.0 | ≤4.2 | ≤90 | ≤10 | ≤10 | ≤3 | ≤1.5 |
| 1 | >80 | >1.0 | >4.2 | >90 | >10 | >10 | >3 | >1.5 |
| 2 | >160 | >2.0 | >8.4 | >180 | >15 | >15 | >6 | >2.0 |
| 3 | >240 | >3.0 | >12.6 | >270 | >20 | >20 | >9 | >2.5 |
| 4 | >320 | >4.0 | >16.8 | >360 | >25 | >25 | >12 | >3.0 |
| 5 | >400 | >5.0 | >21 | >450 | >30 | >30 | >15 | >5 |
| 6 | >480 | >6.0 | >25.2 | >540 | >35 | >35 | >18 | >7 |
| 7 | >560 | >7 | >29.4 | >630 | >40 | >40 | >21 | >10 |
| 8 | >640 | >8 | >33.6 | >720 | >45 | >45 | >24 | >15 |
| 9 | >720 | >9 | >37.8 | >810 | >50 | >50 | >27 | >20 |
| 10 | >800 | >10 | >42 | >900 | >55 | >55 | >30 | >25 |
| 11 | | >12 | >46.2 | >990 | | | | >30 |
| 12 | | >14 | >50.4 | >1080 | | | | >35 |
| 13 | | >16 | >54.6 | >1170 | | | | >40 |
| 14 | | >18 | >58.8 | >1260 | | | | >45 |
| 15 | | >20 | >63 | >1350 | | | | >50 |
| 16 | | >22 | >67.2 | >1440 | | | | |
| 17 | | >24 | >71.4 | >1530 | | | | |
| 18 | | >26 | >75.6 | >1620 | | | | |
| 19 | | >28 | >79.8 | >1710 | | | | |
| 20 | | >30 | >84 | >1800 | | | | |
| 21 | | >32 | | >1890 | | | | |
| 22 | | >34 | | >1980 | | | | |
| 23 | | >36 | | >2070 | | | | |
| 24 | | >38 | | >2160 | | | | |
| 25 | | >40 | | >2250 | | | | |

**Baseline points for a product = sum of the individual points scored independently for Energy, Saturated Fat, Total Sugars, and Sodium** against this table (each nutrient is looked up in its own column and its point value added; this is standard for HSR-family formulas and matches how Table 5's formula references a single combined "INR baseline points").

### Table 3 — INR baseline points, Category-II (Liquid, non-dairy), per 100 ml

| Pts | Energy kcal | Total sugars g | **Positive pts** FV | Protein |
|---|---|---|---|---|
| 0 | ≤6 | ≤0.1 | ≤5 | ≤1.5 |
| 1 | >6 | >0.1 | >5 | >1.5 |
| 2 | >12 | >1.6 | >10 | >2.0 |
| 3 | >18 | >3.1 | >15 | >2.5 |
| 4 | >24 | >4.6 | >20 | >3.0 |
| 5 | >30 | >6.1 | >25 | >5 |
| 6 | >36 | >7.6 | >30 | >7 |
| 7 | >42 | >9.1 | >35 | >10 |
| 8 | >48 | >10.6 | >40 | >15 |
| 9 | >54 | >12.1 | >45 | >20 |
| 10 | >60 | >13.6 | >55 | >25 |
| 11 | | | | >30 |
| 12 | | | | >35 |
| 13 | | | | >40 |
| 14 | | | | >45 |
| 15 | | | | >50 |

### Table 4 — Capping of positive points

| Category | Capping rule |
|---|---|
| Solid foods | if baseline points ≤ 20 → up to **15** for Protein, up to **10 each** for FV, NLM, Fibre |
| Solid foods | if baseline points > 20 → up to **7** for Protein, up to **5 each** for FV, NLM, Fibre |
| Liquid foods | if baseline points ≤ 10 → up to **10** for FV, up to **15** for Protein |
| Liquid foods | if baseline points > 10 → up to **5** for FV, up to **7** for Protein |

### Table 5 — Final formula

```
Final INR score = (INR baseline points) − [ (FV points) + (NLM points) + (Protein points) + (Fibre points) ]
```

(NLM and Fibre points only apply to solid foods — omit those two terms for Category-II liquids.)

### Table 6 — Star mapping

| Stars | Final score — Solid foods | Final score — Liquid foods |
|---|---|---|
| 5 | ≤ -11 | ≤ 0 |
| 4.5 | -10 to -7 | 1 to 2 |
| 4 | -6 to -2 | 3 to 4 |
| 3.5 | -1 to 2 | 5 to 6 |
| 3 | 3 to 6 | 7 to 9 |
| 2.5 | 7 to 11 | 10 to 12 |
| 2 | 12 to 15 | 13 to 15 |
| 1.5 | 16 to 20 | 16 to 18 |
| 1 | 21 to 24 | 18 to 20 |
| 0.5 | ≥ 25 | ≥ 20 |

More stars = healthier. ½ star is the floor, 5 stars the ceiling.

## 3. Worked example (solid food, per 100 g)

Say OCR/extraction returns, per 100 g: Energy 480 kcal, Sat. fat 6.0 g, Total sugar 18 g, Sodium 420 mg, Protein 6 g, no declared FV/NLM/Fibre.

- Energy 480 → Table 2 band ">480" → **6 pts**
- Sat fat 6.0 → band ">6.0" → **wait, exactly 6.0 falls on the ">5, ≤6" boundary → 5 pts** (implementation must use the exact `>` operators as written — see §6 boundary-handling note)
- Total sugar 18 → band ">16.8, ≤21" → **4 pts**
- Sodium 420 → band ">360, ≤450" → **4 pts**
- **Baseline points = 6 + 5 + 4 + 4 = 19**
- Baseline ≤ 20 → capping allows up to 15 (protein) / 10 each (FV, NLM, fibre).
- Protein 6g → Table 2 protein column: ">5, ≤7" → **6 pts** (within the 15-pt cap, no adjustment needed)
- FV/NLM/Fibre not declared → **0 pts** each.
- **Final score = 19 − (0 + 0 + 6 + 0) = 13**
- Table 6, solid: score 12–15 → **2 stars**

This exact worked example should become the first unit test in the scoring engine (doc 05 §2).

## 4. Personalization rule engine (4 launch conditions)

**Framing shown to every user, every time (non-negotiable UI requirement):** *"LabelLens is not a medical device and does not diagnose or treat any condition. These are general dietary flags based on your selected conditions and the product's declared ingredients/nutrition. Always consult your doctor or a registered dietitian."*

Each condition below is a **rule table**, not a model. `AVOID` requires at least one hard trigger; `CAUTION` is a softer threshold; otherwise `GOOD_FIT`. All thresholds are per-100g/100ml, matching the INR normalization already computed.

### 4.1 Sugar-sensitivity / high-sugar-intake management
| Trigger | Verdict |
|---|---|
| Total sugar > 21 g/100g (solid) or > 6g/100ml (liquid, non-dairy) — the same INR baseline threshold | AVOID |
| Total sugar between the INR "0-point" band and the AVOID threshold, OR added sugar present as one of the first 3 ingredients (descending-order list) | CAUTION |
| Otherwise | GOOD_FIT |

### 4.2 Diabetes
| Trigger | Verdict |
|---|---|
| Total sugar > 21 g/100g (solid) / 6g/100ml (liquid) **or** added sugar/high-glycemic sweeteners (glucose syrup, dextrose, maltodextrin, honey) among first 3 ingredients **or** Sodium > 450 mg/100g (comorbidity risk factor) | AVOID |
| Total sugar 10–21 g/100g **or** carbohydrate > 30g/100g with low fibre (<3g/100g) | CAUTION |
| Otherwise | GOOD_FIT |

### 4.3 Migraine
Migraine triggers are ingredient-flag driven (well-documented common dietary triggers), not primarily a nutrient-threshold problem:
| Trigger | Verdict |
|---|---|
| Contains any of: MSG / monosodium glutamate / INS 621, aspartame / INS 951, nitrites/nitrates (INS 249–252, common in processed/cured meat), tyramine-associated ingredients (aged cheese, yeast extract) | AVOID |
| Contains caffeine, cocoa/chocolate solids, or artificial sweeteners other than aspartame (e.g. acesulfame potassium) | CAUTION |
| Otherwise | GOOD_FIT |

### 4.4 Fever
General guidance during fever favors easily-digestible, low-processed, low-sodium food and adequate hydration; avoids heavy fat/spice load:
| Trigger | Verdict |
|---|---|
| Sodium > 450 mg/100g **or** Saturated fat > 5g/100g (both above INR's own risk thresholds) **or** contains chilli/heavy-spice seasoning as a primary declared ingredient | AVOID |
| Total fat > 10g/100g **or** highly processed indicator (≥5 additive-class ingredients, e.g. multiple INS-numbered items) | CAUTION |
| Otherwise | GOOD_FIT |

> These four tables are a v1 starting point for the Rules & Scoring owner and a nutrition/medical reviewer to validate and sign off before launch — flag in doc 05 as a required QA/review gate, not just an engineering unit test.

## 5. Schedule-IV — Category-III (FOPNL-exempt) reference list

Used to short-circuit scoring (§1). Category numbers refer to FSS (Food Products Standards & Food Additives) Regulations, 2011:

Milk & buttermilk (plain); fermented/renneted milk (plain); condensed milk & analogues (plain); cream/malai (plain); milk & cream powder (plain); whey products (excl. whey cheese); fats & oils essentially free from water (ghee, vegetable oils/fats, animal fats); fat emulsions (oil-in-water type); fresh fruit (all forms incl. frozen); fresh vegetables/mushrooms/roots/tubers/pulses/legumes/aloe vera/seaweed/nuts/seeds (all forms incl. frozen); cocoa mixes/mass/cake; whole/broken/flaked grain incl. rice; flours & starches; batters; fresh meat & poultry (whole or comminuted, incl. frozen processed); edible casings; fresh fish/molluscs/crustaceans/echinoderms; eggs & egg products (all forms); sweeteners incl. honey (refined/raw sugars, brown sugar, sugar solutions/syrups, table-top sweeteners incl. high-intensity sweeteners); salt & salt substitutes; herbs/spices/seasonings/condiments (incl. instant-noodle seasoning sachets); vinegars; mustards; salad & sandwich spreads (excl. cocoa/nut-based); yeast & similar; non-soy protein products; foods for particular nutritional uses (infant formula, follow-on formula, medical-purpose infant formula, complementary infant/child foods, dietetic/medical foods, slimming formula, food supplements); waters (natural mineral, source, table, soda); alcoholic beverages (beer, cider, wines, mead, spirits, aromatized alcoholic beverages).

## 6. Common implementation pitfalls (flag for code review)

1. **Per-100g normalization** — if OCR extracts nutrition per serving (e.g. "per 30g pack"), the extraction step MUST normalize to per-100g/100ml before it reaches the scoring engine. Never score a per-serving value directly — this is the single most likely silent bug in the whole system given the brief's explicit "per 100g" requirement.
2. **Boundary operators** — every band in Tables 2/3 is a strict `>` (open lower bound). A value exactly equal to a band's lower bound scores the *lower* band, not the higher one. Write this as an explicit, tested comparator, not an eyeballed `if`.
3. **Category-II never scores Sat. Fat, Sodium, NLM, or Fibre** — don't reuse the Category-I column mapping for liquids.
4. **Zero-energy/zero-sugar beverages** are ineligible for a star rating entirely (§1) — must be checked before, not after, running the formula.
5. **Missing positive-nutrient declarations** (FV%, NLM%, Fibre) should score 0 points for that factor, not be treated as "unknown/skip the whole calc" — the regulation's own worked structure assumes 0 unless declared.
