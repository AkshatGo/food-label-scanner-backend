FROM python:3.11-slim

# Tesseract is the OCR system binary the scan pipeline depends on (ADR-2).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pinned dependency set (same install doc 08 prescribes for Replit).
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

# PWA install icons are generated at build time, not committed.
RUN python scripts/build_icons.py

# Run as an unprivileged user.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=8080
# One worker: the scan worker serially processes persisted jobs (doc 08 —
# do not scale horizontally without a distributed queue with leases).
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
