"""Runtime configuration (all overridable with environment variables)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = os.getenv("APP_NAME", "Chatly")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))
# Comma separated list of extra allowed origins (e.g. https://chat.example.com).
# Leave empty to allow only same-origin requests.
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
MAX_MESSAGE_LEN = 4000
MAX_GROUP_MEMBERS = 256
