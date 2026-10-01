"""Passwords, sessions, rate limiting and request guards."""
import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from flask import g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config, db
from .util import HttpError

_serializer = URLSafeTimedSerializer(config.SECRET, salt="harbor-session")

# ------------------------------------------------------------------ passwords (scrypt, stdlib)
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P, dklen=32)
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ sessions
def start_session(response, user_id: int, version: int = 0):
    """`version` is the user's session_version; bumping it in the DB signs out every other device."""
    token = _serializer.dumps({"uid": user_id, "v": version})
    response.set_cookie(config.COOKIE_NAME, token, max_age=config.SESSION_DAYS * 86400, httponly=True,
                        samesite="Lax", secure=config.COOKIE_SECURE, path="/")


def end_session(response):
    response.delete_cookie(config.COOKIE_NAME, path="/")


def load_user():
    """before_request: attach g.user when a valid session cookie is present."""
    g.user = None
    token = request.cookies.get(config.COOKIE_NAME)
    if token:
        try:
            payload = _serializer.loads(token, max_age=config.SESSION_DAYS * 86400)
            user = db.one("SELECT id, name, email, session_version FROM users WHERE id = ?", (payload["uid"],))
            g.user = user if user and user["session_version"] == payload.get("v", 0) else None
        except (BadSignature, KeyError, TypeError):
            g.user = None


def require_user():
    if not g.user:
        raise HttpError(401, "Sign in to continue.")


def same_origin():
    """before_request: reject state-changing requests that come from another site."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("Origin")
    if origin:
        try:
            if urlparse(origin).netloc != request.host:
                raise HttpError(403, "Cross-site request blocked.")
        except ValueError:
            raise HttpError(403, "Bad origin.")


# ------------------------------------------------------------------ rate limiting (in-memory)
class RateLimiter:
    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise HttpError(429, "Too many attempts. Try again in a few minutes.")
            q.append(now)

    def reset(self):
        with self.lock:
            self.hits.clear()


auth_limiter = RateLimiter(limit=60, window_s=15 * 60)      # per IP: register / login
second_factor_limiter = RateLimiter(limit=10, window_s=15 * 60)  # per user: 2FA codes
sensitive_limiter = RateLimiter(limit=10, window_s=15 * 60)      # per user: password re-checks in Security settings

# ------------------------------------------------------------------ 2FA sign-in challenge
_challenges = URLSafeTimedSerializer(config.SECRET, salt="harbor-2fa-challenge")
CHALLENGE_SECONDS = 300


def make_challenge(user_id: int) -> str:
    """Proof that the password step succeeded; only good for the second step, for five minutes."""
    return _challenges.dumps({"uid": user_id})


def read_challenge(token) -> int:
    try:
        return int(_challenges.loads(str(token or ""), max_age=CHALLENGE_SECONDS)["uid"])
    except (BadSignature, KeyError, TypeError, ValueError):
        raise HttpError(401, "Your sign-in took too long. Start again.", code="challenge_expired")


def json_body() -> dict:
    """The request's JSON object ({} when there's no body)."""
    if request.content_length and request.content_length > 100_000:
        raise HttpError(413, "Request too large.")
    if not request.get_data(cache=True):
        return {}
    data = request.get_json(silent=True, force=True)
    if not isinstance(data, dict):
        raise HttpError(400, "Malformed request.")
    return data
