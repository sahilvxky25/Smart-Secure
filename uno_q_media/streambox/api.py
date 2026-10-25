import shutil, time
from flask import Blueprint, Response, abort, current_app as app, g, jsonify, request
from . import config as C

bp = Blueprint("api", __name__, url_prefix="/api")
ACTIVE = {}         # user key -> (video id, last heartbeat time)


@bp.get("/library")
def library():
    return Response(app.lib.public_json, mimetype="application/json")


@bp.get("/meta")
def meta():
    return jsonify(app.meta.d)


@bp.get("/state")
def get_state():
    return jsonify(app.store.get_state(g.user["key"]))


@bp.put("/state")
def put_state():
    try:
        app.store.put_state(g.user["key"], request.get_json(force=True))
    except (ValueError, TypeError, AttributeError):
        abort(400)
    return jsonify(ok=True)


@bp.post("/heartbeat")
def heartbeat():
    ACTIVE[g.user["key"]] = (str((request.get_json(silent=True) or {}).get("id", "")), time.time())
    return jsonify(ok=True)


def _admin():
    if not g.user["admin"]:
        abort(403)


@bp.get("/admin/stats")
def stats():
    _admin()
    now = time.time()
    watching = [dict(user=app.store.users[k]["name"], title=app.lib.index[i]["title"] if i in app.lib.index else "?")
                for k, (i, t) in list(ACTIVE.items()) if now - t < 45]
    return jsonify(users=len(app.store.users), files=len(app.lib.items), watching=watching,
                   tmdb=bool(C.TMDB_KEY), meta=len([v for v in app.meta.d.values() if v]), ffmpeg=bool(C.FFMPEG))


@bp.post("/admin/rescan")
def rescan():
    _admin()
    n = app.lib.scan()
    app.lib.warm()
    app.meta.fetch_missing(app.lib)
    return jsonify(count=n)


@bp.get("/admin/duplicates")
def duplicates():
    _admin()
    groups = [[dict(id=m["id"], title=m["title"], h=m["height"], size=m["size"],
                    path=str(m["path"])[len(str(C.MOVIES_DIR)):].lstrip("/\\")) for m in grp] for grp in app.lib.dups]
    return jsonify(groups=groups, waste=sum(f["size"] for g_ in groups for f in g_[1:]))


@bp.post("/admin/clear_cache")
def clear_cache():
    _admin()
    for d in (C.HLS, C.EXPORTS):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    return jsonify(ok=True)
