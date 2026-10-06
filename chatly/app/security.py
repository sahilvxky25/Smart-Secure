"""Cryptography helpers: password hashing, message encryption, TOTP 2FA."""
import asyncio
import base64
import functools
import hashlib
import hmac
import os
import secrets
import struct
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import DATA_DIR


# --------------------------------------------------------------------------
# Master key (used to derive per-chat message keys and the 2FA secret key)
# --------------------------------------------------------------------------
def _load_master_key() -> bytes:
    env = os.getenv("MASTER_KEY")
    if env:
        return hashlib.sha256(env.encode()).digest()
    path = DATA_DIR / "master.key"
    if path.exists():
        return bytes.fromhex(path.read_text().strip())
    key = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex())
    return key


_MASTER = _load_master_key()


@functools.lru_cache(maxsize=4096)
def _subkey(label: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=label.encode()).derive(_MASTER)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _seal(label: str, text: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_subkey(label)).encrypt(nonce, text.encode(), label.encode())
    return f"v1.{_b64(nonce)}.{_b64(ct)}"


def _open(label: str, sealed: str) -> str:
    v, nonce, ct = sealed.split(".")
    if v != "v1":
        raise ValueError("unknown format")
    return AESGCM(_subkey(label)).decrypt(base64.b64decode(nonce), base64.b64decode(ct), label.encode()).decode()


# Messages: AES-256-GCM, a different key per chat, chat id bound as AAD.
def encrypt_message(chat_id: int, text: str) -> str:
    return _seal(f"chat:{chat_id}", text)


def decrypt_message(chat_id: int, sealed: str) -> str:
    try:
        return _open(f"chat:{chat_id}", sealed)
    except Exception:
        return "⚠️ Message could not be decrypted"


def seal_secret(text: str) -> str:
    return _seal("totp", text)


def open_secret(sealed: str) -> str:
    return _open("totp", sealed)


# --------------------------------------------------------------------------
# Passwords / security answers (scrypt, salted)
# --------------------------------------------------------------------------
_N, _R, _P = 2**14, 8, 1


def _scrypt(secret: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    import unicodedata
    return hashlib.scrypt(unicodedata.normalize("NFKC", secret).encode(), salt=salt, n=n, r=r, p=p,
                          maxmem=128 * 1024 * 1024, dklen=64)


def _hash_secret(secret: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(_scrypt(secret, salt, _N, _R, _P))}"


def _verify_secret(secret: str, stored: str) -> bool:
    try:
        alg, n, r, p, salt, digest = stored.split("$")
        if alg != "scrypt":
            return False
        got = _scrypt(secret, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(got, base64.b64decode(digest))
    except Exception:
        return False


async def hash_secret(secret: str) -> str:
    return await asyncio.to_thread(_hash_secret, secret)


async def verify_secret(secret: str, stored: str) -> bool:
    return await asyncio.to_thread(_verify_secret, secret, stored)


DUMMY_HASH = _hash_secret("dummy-password-for-timing")  # equalises timing for unknown emails


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
def random_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def safe_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# --------------------------------------------------------------------------
# TOTP (RFC 6238) - compatible with Google Authenticator, Authy, 1Password...
# --------------------------------------------------------------------------
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = digest[19] & 15
    code = (struct.unpack(">I", digest[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(secret_b32, int((at or time.time()) // 30))


def check_totp(secret_b32: str, code: str, last_step: int) -> int:
    """Return the matched time-step (>0) or 0. Steps <= last_step are rejected (replay protection)."""
    cur = int(time.time() // 30)
    for step in (cur, cur - 1, cur + 1):
        if step > last_step and safe_eq(_hotp(secret_b32, step), code):
            return step
    return 0


def totp_uri(secret_b32: str, email: str, issuer: str) -> str:
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")


_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"


def new_backup_codes(n: int = 8) -> list[str]:
    return ["".join(secrets.choice(_ALPHABET) for _ in range(5)) + "-" +
            "".join(secrets.choice(_ALPHABET) for _ in range(5)) for _ in range(n)]


def hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").replace(" ", "").lower().encode()).hexdigest()


def fake_index(email: str, n: int) -> int:
    """Deterministic, unpredictable index so unknown emails get a stable fake security question."""
    mac = hmac.new(_subkey("fakeq"), email.encode(), hashlib.sha256).digest()
    return int.from_bytes(mac[:4], "big") % n
