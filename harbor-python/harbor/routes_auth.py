import re

from flask import Blueprint, g, jsonify, request

from . import config, db, items, security
from .util import HttpError, now_ms

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"]}


def _limit():
    security.auth_limiter.check(request.remote_addr or "?")


@bp.post("/register")
def register():
    _limit()
    body = security.json_body()
    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if not name or len(name) > 80:
        raise HttpError(400, "Enter your name.")
    if not EMAIL_RE.match(email):
        raise HttpError(400, "Enter a valid email address.")
    if len(password) < 8:
        raise HttpError(400, "Use a password with at least 8 characters.")
    if len(password) > 200:
        raise HttpError(400, "Use a password with at most 200 characters.")
    if db.one("SELECT 1 FROM users WHERE email = ?", (email,)):
        raise HttpError(409, "An account with this email already exists.")
    cur = db.run("INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                 (name, email, security.hash_password(password), now_ms()))
    user = {"id": cur.lastrowid, "name": name, "email": email}
    resp = jsonify({"user": public_user(user)})
    resp.status_code = 201
    security.start_session(resp, user["id"])
    return resp


@bp.post("/login")
def login():
    _limit()
    body = security.json_body()
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    row = db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not row or not security.check_password(password[:200], row["password_hash"]):
        raise HttpError(401, "Email or password is incorrect.")
    resp = jsonify({"user": public_user(row)})
    security.start_session(resp, row["id"])
    return resp


@bp.post("/logout")
def logout():
    resp = jsonify({"ok": True})
    security.end_session(resp)
    return resp


@bp.get("/me")
def me():
    security.require_user()
    return jsonify({"user": public_user(g.user),
                    "storage": {"used": items.used_bytes(g.user["id"]), "quota": config.QUOTA_BYTES}})
