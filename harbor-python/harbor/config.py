"""Runtime configuration, read from environment variables once at import time."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR") or BASE_DIR / "data").resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
TMP_DIR = UPLOAD_DIR / ".tmp"
PUBLIC_DIR = BASE_DIR / "public"

TMP_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret() -> str:
    """Signing secret: from the environment, or generated once and kept on disk."""
    if os.environ.get("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    f = DATA_DIR / ".jwt_secret"
    if f.exists():
        return f.read_text().strip()
    secret = secrets.token_hex(48)
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secret)
    return secret


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


HOST = os.environ.get("HOST", "127.0.0.1")
PORT = _int("PORT", 3000)
SECRET = _load_secret()
COOKIE_NAME = "harbor_session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "true"
SESSION_DAYS = 7
QUOTA_BYTES = _int("STORAGE_QUOTA_BYTES", 5 * 1024**3)      # per user
MAX_FILE_BYTES = _int("MAX_FILE_BYTES", 2 * 1024**3)        # per file
TRASH_RETENTION_DAYS = _int("TRASH_RETENTION_DAYS", 30)
MAX_FILES_PER_UPLOAD = 200

_tp = os.environ.get("TRUST_PROXY", "")
# Number of reverse proxies in front of Harbor (0 = none). "true" means one.
TRUST_PROXY = 1 if _tp == "true" else (int(_tp) if _tp.isdigit() else (1 if _tp else 0))
