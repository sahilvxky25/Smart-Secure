import os
import re
import time
from urllib.parse import quote

EXT_MIME = {
    "txt": "text/plain", "md": "text/markdown", "csv": "text/csv", "json": "application/json",
    "xml": "application/xml", "html": "text/html", "css": "text/css", "js": "text/javascript",
    "ts": "text/typescript", "py": "text/x-python", "pdf": "application/pdf", "zip": "application/zip",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "svg": "image/svg+xml", "bmp": "image/bmp", "avif": "image/avif", "ico": "image/x-icon",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "mkv": "video/x-matroska",
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "m4a": "audio/mp4", "flac": "audio/flac",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

TEXT_EXT = {
    "txt", "md", "log", "csv", "json", "xml", "yml", "yaml", "toml", "ini", "env", "html", "css", "js", "mjs",
    "ts", "tsx", "jsx", "py", "rb", "go", "rs", "java", "c", "h", "cpp", "cs", "php", "sh", "sql", "swift", "kt",
}

_MIME_RE = re.compile(r"^[A-Za-z0-9][\w.+-]*/[A-Za-z0-9][\w.+-]*$")
_BAD_NAME_RE = re.compile(r"[/\\\x00-\x1f]")


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def now_ms() -> int:
    return int(time.time() * 1000)


def ext(name: str) -> str:
    return os.path.splitext(name)[1][1:].lower()


def mime_for(name: str, reported: str | None) -> str:
    """Prefer the browser-reported type (if well formed), fall back to the extension."""
    if reported and reported != "application/octet-stream" and _MIME_RE.match(reported) and len(reported) <= 127:
        return reported.lower()
    return EXT_MIME.get(ext(name), "application/octet-stream")


def preview_kind(item: dict) -> str | None:
    """Which kinds of files may be shown in the browser instead of downloaded."""
    mime = item.get("mime") or ""
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("text/") or mime in ("application/json", "application/xml") or ext(item["name"]) in TEXT_EXT:
        return "text"
    return None


def clean_name(value) -> str | None:
    """Validates a file or folder name; returns the cleaned name or None."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > 255 or name in (".", ".."):
        return None
    if _BAD_NAME_RE.search(name):
        return None
    return name


def content_disposition(kind: str, name: str) -> str:
    ascii_name = re.sub(r'[^\x20-\x7e]', "_", name).replace('"', "_").replace("\\", "_")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


def to_int(value):
    """Parses an integer from a string/number, returning None if it isn't one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    return None
