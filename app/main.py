import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database.mongodb import test_connection
from .api.scan_routes import router as scan_router


app = FastAPI(
    title="Food Label Scanner API",
    version="1.0.0"
)


# Flutter will communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(scan_router)


@app.get("/")
def root():
    return {
        "message": "Food Label Scanner API is running"
    }


@app.get("/health", status_code=200)
def health():
    try:
        test_connection()

        return {
            "status": "healthy",
            "mongodb": "connected"
        }

    except Exception as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "mongodb": "disconnected",
                "error": str(error),
            },
        )