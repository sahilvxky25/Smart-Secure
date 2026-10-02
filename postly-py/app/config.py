import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Config:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "Postly")
        self.host = os.getenv("HOST", "127.0.0.1")
        self.port = _int("PORT", 3000)
        self.domain = os.getenv("MAIL_DOMAIN", "localhost").strip().lower()
        self.cookie_secure = _bool("COOKIE_SECURE", False)
        self.allow_signup = _bool("ALLOW_SIGNUP", True)
        self.trust_proxy = _bool("TRUST_PROXY", False)

        self.smtp_enabled = _bool("SMTP_ENABLED", True)
        self.smtp_port = _int("SMTP_PORT", 2525)
        self.smtp_bind = os.getenv("SMTP_BIND", "0.0.0.0")
        self.tls_key = os.getenv("TLS_KEY") or None
        self.tls_cert = os.getenv("TLS_CERT") or None

        self.relay = None
        if os.getenv("RELAY_HOST"):
            self.relay = {
                "host": os.environ["RELAY_HOST"],
                "port": _int("RELAY_PORT", 587),
                "secure": _bool("RELAY_SECURE", False),
                "user": os.getenv("RELAY_USER") or None,
                "password": os.getenv("RELAY_PASS") or None,
            }

        self.dkim = None
        key_path, selector = os.getenv("DKIM_PRIVATE_KEY_PATH"), os.getenv("DKIM_SELECTOR")
        if key_path and selector:
            self.dkim = {
                "selector": selector.encode(),
                "domain": self.domain.encode(),
                "private_key": Path(key_path).read_bytes(),
            }

        self.max_attachment_bytes = _int("MAX_ATTACHMENT_MB", 25) * 1024 * 1024
        self.db_path = Path(os.getenv("DB_PATH", str(ROOT / "data" / "postly.db"))).resolve()
        self.public_dir = ROOT / "public"


config = Config()
