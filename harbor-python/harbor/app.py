"""Harbor: a small Google Drive-style file storage app (Flask + SQLite)."""
import logging
import os
import tempfile
import threading
import time

from flask import Flask, Request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config, db, items, security
from . import routes_auth, routes_items, routes_public, routes_sharing
from .util import HttpError

log = logging.getLogger("harbor")


class _UploadTemp:
    """Upload spool that lives inside DATA_DIR (so it can be renamed into place without a copy)
    and enforces the per-file size limit while the upload streams in."""

    def __init__(self):
        self._f = tempfile.NamedTemporaryFile(dir=config.TMP_DIR, delete=False)
        self.name = self._f.name
        self._size = 0

    def write(self, data):
        self._size += len(data)
        if self._size > config.MAX_FILE_BYTES:
            self.discard()  # the request is being aborted, so nobody else will clean this up
            raise RequestEntityTooLarge()
        return self._f.write(data)

    def discard(self):
        try:
            self._f.close()
        finally:
            try:
                os.unlink(self.name)
            except OSError:
                pass

    def __getattr__(self, attr):  # read, seek, tell, flush, close, ...
        return getattr(self._f, attr)


class HarborRequest(Request):
    max_form_parts = config.MAX_FILES_PER_UPLOAD + 50
    max_form_memory_size = 1_000_000

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return _UploadTemp()


def sweep_tmp(max_age_s=86_400):
    """Remove upload spool files left behind by interrupted uploads."""
    cutoff = time.time() - max_age_s
    for f in config.TMP_DIR.iterdir():
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def purge_trash():
    try:
        n = items.purge_expired_trash(config.TRASH_RETENTION_DAYS)
        if n:
            log.info("Purged %d expired item(s) from the trash.", n)
        sweep_tmp()
    except Exception:
        log.exception("Trash purge failed")


def start_background_jobs(interval_s=6 * 3600):
    def loop():
        while True:
            purge_trash()
            time.sleep(interval_s)
    threading.Thread(target=loop, name="harbor-purge", daemon=True).start()


def create_app() -> Flask:
    db.init()
    app = Flask(__name__, static_folder=None)
    app.request_class = HarborRequest
    app.json.sort_keys = False
    if config.TRUST_PROXY:
        n = config.TRUST_PROXY
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    app.before_request(security.same_origin)
    app.before_request(security.load_user)

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    # ---- API
    @app.get("/api/health")
    def health():
        return jsonify(ok=True)

    @app.get("/api/storage")
    def storage():
        security.require_user()
        from flask import g
        return jsonify(used=items.used_bytes(g.user["id"]), quota=config.QUOTA_BYTES)

    for bp in (routes_auth.bp, routes_public.bp, routes_items.bp, routes_sharing.bp):
        app.register_blueprint(bp)

    @app.route("/api/<path:_rest>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_404(_rest):
        raise HttpError(404, "Not found.")

    # ---- Frontend
    @app.get("/")
    @app.get("/s/<token>")
    def index(token=None):
        return send_from_directory(config.PUBLIC_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(config.PUBLIC_DIR, filename)

    # ---- Errors
    @app.errorhandler(HttpError)
    def _http_error(e):
        body = {"error": e.message}
        if e.code:
            body["code"] = e.code
        return jsonify(body), e.status

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_e):
        return jsonify(error="That file is larger than the upload limit."), 413

    @app.errorhandler(HTTPException)
    def _werkzeug_error(e):
        messages = {400: "Malformed request.", 404: "Not found.", 405: "Method not allowed."}
        return jsonify(error=messages.get(e.code, e.description)), e.code

    @app.errorhandler(Exception)
    def _unexpected(e):
        log.exception("Unhandled error", exc_info=e)
        return jsonify(error="Something went wrong on the server."), 500

    return app
