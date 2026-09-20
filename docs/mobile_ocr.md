# Mobile photo processing

OCR corrects EXIF orientation and retains the deployment's 900,000-pixel
budget, enlarging small inputs by at most 4x. OpenCV handles blur detection,
deskewing and adaptive thresholding for uneven lighting. Ruled nutrition
tables printed as white lettering on saturated backgrounds (orange/red/green
packaging) are detected and re-assembled cell-by-cell into a black-on-white
canvas before OCR (app/services/table_image.py); row and column order are
preserved and no values are invented. Difficult inputs get
quarter-turn rotation and sparse-text retries, within a 120-second OCR budget
per image (at most 60 seconds per Tesseract call, plus preparation overhead).
These limits retain the upstream fixes for hosts with limited CPU; confident
readings — including a read with six or more clean nutrition fields — exit
early. Images are processed locally; no cloud service is required.

The result uses one complete OCR candidate, ranked by confidence and readable
nutrition fields. Combining different readings can mix serving headers and
values, so alternatives are not appended. Each uploaded photo is checked for
missing or low-confidence text; a clear front photo cannot hide an unreadable
back photo behind the average confidence.

Text reconstruction handles adjacent nutrient rows separated by units. Nutrition
extraction accepts units before values and decimal commas. Ambiguous comma
numbers, symbolic less-than bounds, percentage-only values, incompatible units and mixed
per-serving/per-100 columns require review. Multi-column table selection is
not yet automatic. OCR confidence is a heuristic, not a guarantee of accuracy.

For capture, fill the frame with the label, tap to focus and avoid glare. Use the
optional nutrition photo for a close-up of small print. Severe blur, curved
packaging, perspective distortion and reflections may still require a retake.
JPEG, PNG and WebP remain the supported upload formats.

Run `pytest tests/test_ocr_service.py tests/test_nutrition_extractor.py` for the
targeted regressions, or `pytest` for the full suite. Actual OCR tests require
Tesseract and DejaVu Sans; they skip explicitly when these are unavailable.
Synthetic rotated labels exercise mechanics. `tests/fixtures/` contains real
phone photos of a Dabur Glucoplus-C carton (white-on-orange ruled table) —
the regression pins all seven core values read from it. Real phone photos
are still needed to measure accuracy across more production packaging.
