"""Single-instance durable OCR worker for the documented Reserved VM deployment.

Images and accepted jobs live in MongoDB. On process restart, unfinished jobs
are replayed with stable product IDs. Run one Uvicorn worker/one VM replica.
"""
import asyncio
import logging
from ..database import store

logger = logging.getLogger(__name__)


async def run_worker():
    from ..api.routes import _process_scan

    while True:
        try:
            jobs = sorted(store.scans.find({"status": "processing"}),
                          key=lambda job: job["created_at"])
            for job in jobs:
                await asyncio.to_thread(_process_scan, job["scan_id"])
        except Exception:
            logger.exception("OCR worker could not read the durable queue; retrying")
        await asyncio.sleep(1)
