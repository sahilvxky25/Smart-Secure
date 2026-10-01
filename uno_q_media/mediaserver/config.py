"""Constants, MIME registration and command-line configuration."""
import argparse
import mimetypes
import os
from dataclasses import dataclass
from typing import Optional

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")

CHUNK = 256 * 1024  # bytes per write while streaming

VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi")
AUDIO_EXTS = (".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

KINDS = {}
KINDS.update({e: "video" for e in VIDEO_EXTS})
KINDS.update({e: "audio" for e in AUDIO_EXTS})
KINDS.update({e: "image" for e in IMAGE_EXTS})

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".opus")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("text/javascript", ".js")


@dataclass
class Config:
    root: str
    host: str
    port: int
    token: Optional[str]
    rescan: int


def parse_args(argv=None) -> Config:
    ap = argparse.ArgumentParser(description="UNO Q Media Server")
    ap.add_argument("--root", default=os.path.expanduser("~/media"), help="media folder (default ~/media)")
    ap.add_argument("--host", default="0.0.0.0", help="bind address")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--token", default=os.environ.get("MEDIA_TOKEN"),
                    help="optional access token (or set MEDIA_TOKEN)")
    ap.add_argument("--rescan", type=int, default=60, help="library cache lifetime in seconds")
    a = ap.parse_args(argv)
    return Config(a.root, a.host, a.port, a.token, a.rescan)
