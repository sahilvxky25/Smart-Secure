"""Shared helpers: errors, validation, throttling, auth dependency."""
import re
import time
import unicodedata

from fastapi import Depends, Request

from . import db
from .config import ALLOWED_ORIGINS
from .security import hash_token


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        self.status, self.message, self.extra = status, message, extra


# ---- validation -----------------------------------------------------------
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What was the name of your primary school?",
    "In what city were you born?",
    "What was your childhood nickname?",
    "What is the name of your favourite teacher?",
    "What was the make of your first car or bike?",
]


def norm_email(v: str) -> str:
    return (v or "").strip().lower()


def valid_email(v: str) -> bool:
    return len(v) <= 254 and bool(EMAIL_RE.match(v))


def check_email(v: str) -> str:
    e = norm_email(v)
    if not valid_email(e):
        raise ApiError(400, "Enter a valid email address.")
    return e


def check_name(v: str, what="Name", maxlen=40) -> str:
    v = re.sub(r"\s+", " ", (v or "")).strip()
    if not 1 <= len(v) <= maxlen:
        raise ApiError(400, f"{what} must be 1–{maxlen} characters.")
    return v


def check_password(v: str) -> str:
    v = v or ""
    if len(v) < 8 or len(v) > 128:
        raise ApiError(400, "Password must be 8–128 characters.")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ApiError(400, "Password must contain at least one letter and one number.")
    return v


def check_question(q: str, a: str) -> tuple[str, str]:
    q = re.sub(r"\s+", " ", (q or "")).strip()
    if not 8 <= len(q) <= 120:
        raise ApiError(400, "Security question must be 8–120 characters.")
    na = normalize_answer(a)
    if not 2 <= len(na) <= 100:
        raise ApiError(400, "Security answer must be 2–100 characters.")
    return q, na


def normalize_answer(a: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", a or "").strip().lower())


# ---- throttling -----------------------------------------------------------
_buckets: dict[str, list] = {}


def hit(key: str, window: int) -> int:
    now = time.time()
    b = _buckets.get(key)
    if not b or b[1] < now:
        b = _buckets[key] = [0, now + window]
    b[0] += 1
    if len(_buckets) > 50_000:
        for k in [k for k, v in _buckets.items() if v[1] < now]:
            _buckets.pop(k, None)
    return b[0]


def count(key: str) -> int:
    b = _buckets.get(key)
    return b[0] if b and b[1] >= time.time() else 0


def retry_after(key: str) -> int:
    b = _buckets.get(key)
    return max(1, int(b[1] - time.time())) if b else 1


def reset(key: str):
    _buckets.pop(key, None)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window: int):
    async def dep(request: Request):
        key = f"rl:{name}:{client_ip(request)}"
        if hit(key, window) > limit:
            raise ApiError(429, "Too many requests. Please wait a moment and try again.")
    return Depends(dep)


# ---- sessions / auth dependency --------------------------------------------
def parse_cookie_sid(cookies) -> str | None:
    return cookies.get("sid")


def session_for_token(token: str | None):
    if not token:
        return None
    return db.one("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?", (hash_token(token), int(time.time())))


class Ctx:
    def __init__(self, user, sess):
        self.user, self.sess = user, sess

    @property
    def id(self) -> int:
        return self.user["id"]


async def auth(request: Request) -> Ctx:
    sess = session_for_token(request.cookies.get("sid"))
    if not sess:
        raise ApiError(401, "Please sign in.")
    user = db.one("SELECT * FROM users WHERE id=?", (sess["user_id"],))
    if not user:
        raise ApiError(401, "Please sign in.")
    return Ctx(user, sess)


def origin_allowed(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    origin = origin.rstrip("/")
    if origin in ALLOWED_ORIGINS:
        return True
    from urllib.parse import urlparse
    return urlparse(origin).netloc == (host or "")
