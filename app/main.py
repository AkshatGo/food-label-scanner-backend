"""LabelLens API entrypoint."""

import logging
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api.routes import router
from .database.store import storage_backend, test_connection
from .security import security_middleware

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app):
    task = None
    if config.PRODUCTION:
        from .services.scan_worker import run_worker
        task = asyncio.create_task(run_worker())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    lifespan=lifespan,
    title="LabelLens API",
    version="1.0.0",
    description=(
        "OCR-based food label scanner: FSSAI INR star rating, 4-condition "
        "personalization, and FSSAI compliance reporting. Rules/formula "
        "engine, not a health-verdict model (ADR-1)."
    ),
)
app.middleware("http")(security_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
def root(request: Request):
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/ui")
    return {
        "message": "LabelLens API is running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/ui", include_in_schema=False)
def web_app():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


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
                "error": "Storage is unavailable",
            },
        )
