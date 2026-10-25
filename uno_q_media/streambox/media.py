import mimetypes, re
from pathlib import Path
from flask import Blueprint, Response, abort, current_app as app, send_file
from . import config as C

bp = Blueprint("media", __name__)


def _item(i):
    return app.lib.index.get(i) or abort(404)


@bp.get("/api/thumb/<i>")
def thumb(i):
    _item(i)
    p = app.lib.thumb(i)
    if not p:
        abort(404)
    return send_file(p, max_age=86400)


@bp.get("/api/img/<name>")                       # posters/backdrops cached from TMDB
def img(name):
    if not re.fullmatch(r"[a-f0-9]{12}_[pb]\.jpg", name) or not (C.POSTERS / name).exists():
        abort(404)
    return send_file(C.POSTERS / name, max_age=604800)


@bp.get("/api/subs/<i>/<int:n>")
def subs(i, n):
    m = _item(i)
    if n >= len(m["_subs"]):
        abort(404)
    t = Path(m["_subs"][n]).read_text(encoding="utf-8-sig", errors="replace").replace("\r", "")
    if not t.startswith("WEBVTT"):               # SRT -> WebVTT
        t = "WEBVTT\n\n" + re.sub(r"(\d+:\d+:\d+),(\d+)", r"\1.\2", t)
    return Response(t, mimetype="text/vtt")


@bp.get("/stream/<i>")                           # "Original" quality: the file itself, with seeking
def stream(i):
    m = _item(i)
    return send_file(m["path"], mimetype=mimetypes.guess_type(m["path"])[0] or "video/mp4", conditional=True)
