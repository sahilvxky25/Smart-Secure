"""Streaming files and folder-zips to the client."""
import os
import time
import zipfile

from flask import Response, send_file, stream_with_context

from . import config, db
from .util import HttpError, content_disposition, preview_kind

SANDBOX_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


class _Sink:
    """A write-only, non-seekable file object that zipfile can stream into."""

    def __init__(self):
        self._chunks, self._pos = [], 0

    def write(self, data):
        self._chunks.append(bytes(data))
        self._pos += len(data)
        return len(data)

    def tell(self):
        return self._pos

    def flush(self):
        pass

    def drain(self):
        chunks, self._chunks = self._chunks, []
        return chunks


def _collect(folder, prefix, out, used):
    children = db.all_("SELECT * FROM items WHERE parent_id = ? AND trashed_at IS NULL ORDER BY id", (folder["id"],))
    if not children:
        out.append((prefix, None, folder))  # keeps empty folders in the archive
    for child in children:
        if child["kind"] == "folder":
            _collect(child, f"{prefix}{child['name']}/", out, used)
        else:
            path = config.UPLOAD_DIR / child["storage_key"]
            if path.is_file():
                name, n = f"{prefix}{child['name']}", 1
                while name in used:  # zip archives dislike duplicate names
                    n += 1
                    stem, dot, ext = child["name"].rpartition(".")
                    name = f"{prefix}{stem} ({n}).{ext}" if dot and stem else f"{prefix}{child['name']} ({n})"
                used.add(name)
                out.append((name, path, child))


def _zip_stream(folder):
    entries = []
    _collect(folder, f"{folder['name']}/", entries, set())
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for name, path, meta in entries:
            date = time.localtime(max(meta["updated_at"], 315_532_800_000) / 1000)[:6]  # zip can't go before 1980
            if path is None:
                zi = zipfile.ZipInfo(name, date)
                zi.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(zi, b"")
            else:
                zi = zipfile.ZipInfo(name, date)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                try:
                    zi.file_size = path.stat().st_size  # lets zipfile decide on zip64 up front
                    src = open(path, "rb")
                except OSError:
                    continue
                with src, zf.open(zi, "w") as dest:
                    while chunk := src.read(1 << 16):
                        dest.write(chunk)
                        yield from sink.drain()
            yield from sink.drain()
    yield from sink.drain()


def send_item(item, inline=False):
    """Streams a file (or a folder as .zip). `inline` shows previewable types in the browser;
    everything else is always a download."""
    if item["kind"] == "folder":
        resp = Response(stream_with_context(_zip_stream(item)), mimetype="application/zip")
        resp.headers["Content-Disposition"] = content_disposition("attachment", f"{item['name']}.zip")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "private, no-store"
        return resp

    path = config.UPLOAD_DIR / item["storage_key"]
    if not path.is_file():
        raise HttpError(404, "The stored file is missing.")

    kind = preview_kind(item)
    show_inline = bool(inline and kind)
    ctype = "text/plain; charset=utf-8" if (kind == "text" and show_inline) else (item["mime"] or "application/octet-stream")
    resp = send_file(path, mimetype="application/octet-stream", conditional=True, etag=True, max_age=60)
    resp.headers["Content-Type"] = ctype
    resp.headers["Content-Disposition"] = content_disposition("inline" if show_inline else "attachment", item["name"])
    resp.headers["Cache-Control"] = "private, max-age=60"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    # Never let an uploaded file run scripts on our origin.
    if kind != "pdf":
        resp.headers["Content-Security-Policy"] = SANDBOX_CSP
    return resp
