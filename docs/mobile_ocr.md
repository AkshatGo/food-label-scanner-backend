# Mobile photo processing

OCR corrects EXIF orientation and retains the deployment's 900,000-pixel
budget, enlarging small inputs by at most 4x. OpenCV handles blur detection,
deskewing, adaptive thresholding and flat-field correction for uneven or
gradient lighting. Ruled nutrition tables printed as white lettering on
saturated backgrounds (orange/red/green packaging) are detected and
re-assembled cell-by-cell — as per-row strips (cheap calls that survive
throttled hosts) and a full canvas — before OCR
(app/services/table_image.py); row and column order are preserved and no
values are invented. Difficult inputs get quarter-turn rotation and
sparse-text retries, within a 120-second OCR budget per image (at most 60
seconds per Tesseract call, plus preparation overhead). Confident readings
exit early, with two accuracy guards: a half-read panel (heading present,
fewer than six core fields) keeps the rescue variants running, and the
final reading is chosen with core panel rows weighted above raw OCR
confidence so a complete-but-noisier read beats a cleaner truncated one.
Images are processed locally; no cloud service is required.

Accuracy was swept across packaging print styles (plain paper, kraft
texture, white-on-red, dark gradient; pristine and JPEG-degraded): all 48
ground-truth fields recovered. The sweep lives in this repo's history as
tests/test_ocr_service.py regressions; real-phone photos of new packaging
styles remain the best way to extend coverage.

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
