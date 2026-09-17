"""LabelLens API entrypoint."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .api.routes import router
from .database.store import storage_backend, test_connection

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LabelLens API",
    version="1.0.0",
    description=(
        "OCR-based food label scanner: FSSAI INR star rating, 4-condition "
        "personalization, and FSSAI compliance reporting. Rules/formula "
        "engine, not a health-verdict model (ADR-1)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "http_status": 500,
        }},
    )


@app.get("/")
def root():
    return {
        "message": "LabelLens API is running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    try:
        test_connection()
        return {
            "status": "healthy",
            "storage_backend": storage_backend(),
        }
    except Exception as error:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "storage_backend": storage_backend(),
                "error": str(error),
            },
        )
