"""Chatly - a WhatsApp-Web-style messenger. FastAPI app entrypoint."""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import account, auth, chats, db, realtime
from .config import BASE_DIR
from .util import ApiError, origin_allowed

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self' ws: wss:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")


async def _janitor():
    while True:
        now = int(time.time())
        db.run("DELETE FROM sessions WHERE expires_at<?", (now,))
        db.run("DELETE FROM tickets WHERE expires_at<?", (now,))
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_janitor())
    yield
    task.cancel()


app = FastAPI(title="Chatly", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(ApiError)
async def api_error(_, e: ApiError):
    return JSONResponse({"error": e.message, **e.extra}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_, e):
    return JSONResponse({"error": "Please fill in every field correctly."}, status_code=400)


@app.exception_handler(StarletteHTTPException)
async def http_error(_, e: StarletteHTTPException):
    return JSONResponse({"error": "Not found." if e.status_code == 404 else "Request failed."}, status_code=e.status_code)


@app.exception_handler(Exception)
async def unhandled(_, e: Exception):
    import logging
    logging.getLogger("chatly").exception("Unhandled error", exc_info=e)
    return JSONResponse({"error": "Something went wrong on our side."}, status_code=500)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF defence in depth (cookies are also SameSite=Lax): reject cross-origin state changes.
    if request.method not in ("GET", "HEAD", "OPTIONS") and not origin_allowed(request.headers.get("origin"), request.headers.get("host")):
        return JSONResponse({"error": "Cross-origin request blocked."}, status_code=403)
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    else:
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.include_router(auth.router)
app.include_router(account.router)
app.include_router(chats.router)
app.include_router(realtime.router)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"], include_in_schema=False)
async def api_404(rest: str):
    raise ApiError(404, "Not found.")


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
