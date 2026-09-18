"""LabelLens application configuration.

Loads .env from the project root regardless of the process working directory,
provides resilient defaults so the app boots without external services.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
ENVIRONMENT = os.getenv("APP_ENV", "development")
PRODUCTION = ENVIRONMENT == "production"

# --- MongoDB (optional) ----------------------------------------------------
MONGODB_URI = os.getenv("MONGODB_URI", "").strip() or None
DATABASE_NAME = os.getenv("DATABASE_NAME", "labelens")

# --- Security --------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "labelens-dev-secret-change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "72"))

if PRODUCTION:
    if not MONGODB_URI:
        raise RuntimeError("Production requires MONGODB_URI; temporary storage is disabled")
    if len(JWT_SECRET) < 32 or JWT_SECRET.startswith(("change-me", "labelens-dev")):
        raise RuntimeError("Production requires a random JWT_SECRET of at least 32 characters")

# --- CORS ------------------------------------------------------------------
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

# --- Extraction ------------------------------------------------------------
LOW_OCR_CONFIDENCE_THRESHOLD = float(os.getenv("LOW_OCR_CONFIDENCE_THRESHOLD", "55"))
