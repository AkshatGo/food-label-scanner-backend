"""Same-origin browser protection, security headers and single-instance quotas."""
from collections import defaultdict, deque
from time import monotonic
from urllib.parse import urlparse
from fastapi.responses import JSONResponse
from . import config

_windows = defaultdict(deque)


async def security_middleware(request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host") and origin not in config.ALLOWED_ORIGINS:
            return JSONResponse({"error": {"message": "Request origin is not allowed"}}, status_code=403)
        if config.PRODUCTION and request.url.path in {"/api/v1/auth/signup", "/api/v1/auth/login", "/api/v1/scan"}:
            # Behind the documented single trusted Replit proxy; Uvicorn validates forwarding.
            client = request.client.host if request.client else "unknown"
            now = monotonic()
            for key in list(_windows):
                if not _windows[key] or _windows[key][-1] <= now - 60:
                    del _windows[key]
            window = _windows[(client, request.url.path)]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= 10:
                return JSONResponse({"error": {"message": "Too many attempts. Try again in a minute."}},
                                    status_code=429, headers={"Retry-After": "60"})
            window.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if request.url.path not in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if config.PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response
