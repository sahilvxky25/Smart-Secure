"""Two-step verification: TOTP (RFC 6238, works with Google Authenticator, 1Password, Authy, ...)
plus one-time recovery codes. Standard library only (QR images come from segno)."""
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

import segno

from . import config, db
from .util import now_ms

ISSUER = "Harbor"
STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1            # accept the previous and next code too, to allow for clock drift
RECOVERY_COUNT = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no look-alikes (i, l, o, 0, 1)


def _now() -> float:   # separate function so tests can control the clock
    return time.time()


# ------------------------------------------------------------------ TOTP
def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def _hotp(key: bytes, counter: int) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    number = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return f"{number:0{DIGITS}d}"


def totp_at(secret: str, t: float | None = None) -> str:
    return _hotp(_key(secret), int((_now() if t is None else t) // STEP_SECONDS))


def check_totp(secret: str, code: str, last_step: int | None):
    """Returns ('ok', step) | ('replay', None) | ('bad', None). A step can only be used once."""
    code = re.sub(r"[\s-]", "", str(code or ""))
    if not re.fullmatch(rf"\d{{{DIGITS}}}", code):
        return "bad", None
    key, current = _key(secret), int(_now() // STEP_SECONDS)
    matched = None
    for step in range(current - WINDOW, current + WINDOW + 1):   # no early exit: constant work
        if hmac.compare_digest(_hotp(key, step), code):
            matched = step
    if matched is None:
        return "bad", None
    if last_step is not None and matched <= last_step:
        return "replay", None
    return "ok", matched


def otpauth_uri(secret: str, email: str) -> str:
    label = quote(f"{ISSUER}:{email}", safe=":")
    return f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"


def qr_data_uri(uri: str) -> str:
    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2, dark="#000000", light="#ffffff")


def _claim_step(user_id: int, step: int) -> bool:
    """Atomically remember the step so the same code can't be replayed (even by a racing request)."""
    cur = db.run("UPDATE users SET totp_last_step = ? WHERE id = ? AND (totp_last_step IS NULL OR totp_last_step < ?)",
                 (step, user_id, step))
    return cur.rowcount == 1


# ------------------------------------------------------------------ recovery codes
def _norm(code: str) -> str:
    return re.sub(r"[\s-]", "", str(code or "")).lower()


def _hash(code: str) -> str:
    return hmac.new(config.SECRET.encode(), _norm(code).encode(), hashlib.sha256).hexdigest()


def replace_recovery_codes(user_id: int) -> list[str]:
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    db.run("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    for c in codes:
        db.run("INSERT INTO recovery_codes (user_id, code_hash) VALUES (?, ?)", (user_id, _hash(c)))
    return codes


def recovery_codes_left(user_id: int) -> int:
    return db.one("SELECT COUNT(*) AS n FROM recovery_codes WHERE user_id = ? AND used_at IS NULL", (user_id,))["n"]


def _use_recovery_code(user_id: int, code: str) -> bool:
    cur = db.run("UPDATE recovery_codes SET used_at = ? WHERE user_id = ? AND code_hash = ? AND used_at IS NULL",
                 (now_ms(), user_id, _hash(code)))
    return cur.rowcount == 1


# ------------------------------------------------------------------ verification
def verify_second_factor(user: dict, code: str, allow_recovery: bool = True):
    """Checks an authenticator code (or, optionally, a recovery code) for a user with 2FA on.
    Returns 'totp' | 'recovery' | 'replay' | None."""
    if user.get("totp_secret"):
        result, step = check_totp(user["totp_secret"], code, user["totp_last_step"])
        if result == "ok":
            return "totp" if _claim_step(user["id"], step) else "replay"
        if result == "replay":
            return "replay"
    if allow_recovery and len(_norm(code)) == 10 and _use_recovery_code(user["id"], code):
        return "recovery"
    return None
