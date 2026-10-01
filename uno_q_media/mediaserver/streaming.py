"""Response bodies: ranged file streaming, subtitle conversion, live remux.

Each function takes the request handler `h` (see handler.py) as its first argument.
"""
import mimetypes
import os
import re
import subprocess

from .config import CHUNK

DEFAULT_CACHE = "public, max-age=3600"


def serve_file(h, path, head_only, cache=DEFAULT_CACHE):
    """Serve a file honouring HTTP Range requests (needed for seeking)."""
    size = os.path.getsize(path)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    start, end, status = 0, size - 1, 200

    rng = h.headers.get("Range")
    if rng and size > 0:
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:  # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end or start >= size:
                return h.respond_head(416, "text/plain", 0, {"Content-Range": "bytes */%d" % size})
            status = 206

    length = max(0, end - start + 1)
    extra = {"Accept-Ranges": "bytes", "Cache-Control": cache}
    if status == 206:
        extra["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
    h.respond_head(status, ctype, length, extra)
    if head_only or length == 0:
        return

    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            data = fh.read(min(CHUNK, remaining))
            if not data:
                break
            h.wfile.write(data)
            remaining -= len(data)


def serve_subtitle(h, path, head_only):
    """Serve .vtt as-is; convert .srt to WebVTT on the fly."""
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8-sig", errors="replace")
    if path.lower().endswith(".srt"):
        text = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
    h.respond(200, "text/vtt; charset=utf-8", text.encode(), head_only)


def serve_remux(h, path, head_only, ffmpeg):
    """Remux MKV/AVI/MOV to fragmented MP4 (video copied, audio -> AAC)."""
    h.close_connection = True
    h.respond_head(200, "video/mp4", None, {"Cache-Control": "no-store", "Connection": "close"})
    if head_only:
        return
    cmd = [
        ffmpeg, "-v", "error", "-i", path,
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            data = proc.stdout.read(CHUNK)
            if not data:
                break
            h.wfile.write(data)
    finally:
        proc.kill()
        proc.wait()
