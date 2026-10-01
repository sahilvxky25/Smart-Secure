"""HTTP request handler and URL routing."""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

from . import auth, streaming
from .config import STATIC_DIR
from .library import safe_join


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "UNOQMedia/2.0"

    # Injected by server.run()
    library = None
    token = None
    ffmpeg = None

    _set_cookie = None

    # ----- response helpers (also used by streaming.py) ------------------- #
    def log_message(self, fmt, *args):
        print("[%s] %s %s" % (self.log_date_time_string(), self.client_address[0], fmt % args))

    def respond_head(self, status, ctype, length=None, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        if self._set_cookie:
            self.send_header("Set-Cookie", self._set_cookie)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def respond(self, status, ctype, body, head_only=False, extra=None):
        self.respond_head(status, ctype, len(body), extra)
        if not head_only:
            self.wfile.write(body)

    def error(self, status, msg, head_only=False):
        self.respond(status, "text/plain; charset=utf-8", msg.encode(), head_only)

    # ----- routing -------------------------------------------------------- #
    def do_HEAD(self):
        self._dispatch(True)

    def do_GET(self):
        self._dispatch(False)

    def _dispatch(self, head_only):
        self._set_cookie = None
        try:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            path = unquote(url.path)

            ok, self._set_cookie = auth.check(self.token, self.headers, query)

            # ---- public routes (the UI shell must load to show a login box) ----
            if path == "/healthz":
                return self.respond(200, "text/plain", b"ok", head_only)
            if path == "/":
                return streaming.serve_file(self, os.path.join(STATIC_DIR, "index.html"),
                                            head_only, cache="no-cache")
            if path.startswith("/static/"):
                f = safe_join(STATIC_DIR, path[len("/static/"):])
                if not f:
                    return self.error(404, "Not found", head_only)
                return streaming.serve_file(self, f, head_only, cache="no-cache")

            # ---- protected routes ---------------------------------------------
            if not ok:
                return self.error(401, "Unauthorized", head_only)

            if path == "/api/library":
                items = self.library.items(force="rescan" in query)
                body = json.dumps({"items": items, "ffmpeg": bool(self.ffmpeg)}).encode()
                return self.respond(200, "application/json", body, head_only,
                                    {"Cache-Control": "no-store"})

            for prefix, action in (("/media/", "file"), ("/sub/", "sub"), ("/remux/", "remux")):
                if path.startswith(prefix):
                    if action == "remux" and not self.ffmpeg:
                        return self.error(501, "ffmpeg not installed", head_only)
                    f = self.library.resolve(path[len(prefix):])
                    if not f:
                        return self.error(404, "Not found", head_only)
                    if action == "file":
                        return streaming.serve_file(self, f, head_only)
                    if action == "sub":
                        return streaming.serve_subtitle(self, f, head_only)
                    return streaming.serve_remux(self, f, head_only, self.ffmpeg)

            self.error(404, "Not found", head_only)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True  # client went away mid-stream
