import time
from flask import Blueprint, current_app as app, g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from . import config as C

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
FAILS = {}          # ip -> recent failed-login timestamps
DAYS = 60 * 86400


def _ser():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])


def load_user():
    """Called before every request: reads the session cookie into g.user."""
    g.user = None
    tok = request.cookies.get("sb_token")
    if tok:
        try:
            key = _ser().loads(tok, max_age=DAYS)
            u = app.store.users.get(key)
            if u:
                g.user = {**u, "key": key}
        except BadSignature:
            pass


def _pub(u):
    return {"name": u["name"], "admin": u["admin"]}


def _ok(key):
    r = jsonify(user=_pub(app.store.users[key]))
    r.set_cookie("sb_token", _ser().dumps(key), max_age=DAYS, httponly=True, samesite="Lax")
    return r


def _creds():
    j = request.get_json(silent=True) or {}
    return str(j.get("name", "")), str(j.get("pw", ""))[:200]


@bp.get("/me")
def me():
    return jsonify(user=_pub(g.user) if g.user else None,
                   signup=C.ALLOW_SIGNUP or not app.store.users)


@bp.post("/signup")
def signup():
    if not (C.ALLOW_SIGNUP or not app.store.users):
        return jsonify(error="Sign-ups are disabled"), 403
    name, pw = _creds()
    try:
        app.store.create(name, pw)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return _ok(name.strip().lower())


@bp.post("/login")
def login():
    ip, now = request.remote_addr, time.time()
    recent = [t for t in FAILS.get(ip, []) if now - t < 300]
    if len(recent) >= 10:
        return jsonify(error="Too many attempts. Wait a few minutes."), 429
    name, pw = _creds()
    if not app.store.verify(name, pw):
        FAILS[ip] = recent + [now]
        return jsonify(error="Wrong username or password"), 401
    return _ok(name.strip().lower())


@bp.post("/logout")
def logout():
    r = jsonify(ok=True)
    r.delete_cookie("sb_token")
    return r
