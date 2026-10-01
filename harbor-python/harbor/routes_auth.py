import re

from flask import Blueprint, g, jsonify, request

from . import config, db, items, security, twofactor
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
    if row["totp_enabled"]:
        # Password was right, but no session yet: the second step decides.
        return jsonify({"twoFactor": True, "challenge": security.make_challenge(row["id"])})
    resp = jsonify({"user": public_user(row)})
    security.start_session(resp, row["id"], row["session_version"])
    return resp


@bp.post("/login/2fa")
def login_second_step():
    _limit()
    body = security.json_body()
    uid = security.read_challenge(body.get("challenge"))
    security.second_factor_limiter.check(f"u{uid}")
    row = db.one("SELECT * FROM users WHERE id = ?", (uid,))
    if not row or not row["totp_enabled"]:
        raise HttpError(401, "Your sign-in took too long. Start again.", code="challenge_expired")
    how = twofactor.verify_second_factor(row, str(body.get("code") or ""))
    if how == "replay":
        raise HttpError(401, "That code was already used. Wait for the next one and try again.")
    if not how:
        raise HttpError(401, "That code is incorrect.")
    resp = jsonify({"user": public_user(row),
                    "usedRecoveryCode": how == "recovery",
                    "recoveryCodesLeft": twofactor.recovery_codes_left(uid)})
    security.start_session(resp, row["id"], row["session_version"])
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


# ---------------------------------------------------------------- two-step verification settings
def _account():
    security.require_user()
    security.sensitive_limiter.check(f"u{g.user['id']}")
    return db.one("SELECT * FROM users WHERE id = ?", (g.user["id"],))


def _confirm_password(row, body):
    if not security.check_password(str(body.get("password") or "")[:200], row["password_hash"]):
        raise HttpError(403, "Your password is incorrect.")


def _reissue(resp, user_id):
    """Bump the session version (signing out every other device) and keep this one signed in."""
    db.run("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (user_id,))
    version = db.one("SELECT session_version FROM users WHERE id = ?", (user_id,))["session_version"]
    security.start_session(resp, user_id, version)


@bp.get("/2fa")
def two_factor_status():
    security.require_user()
    row = db.one("SELECT totp_enabled FROM users WHERE id = ?", (g.user["id"],))
    enabled = bool(row["totp_enabled"])
    return jsonify({"enabled": enabled,
                    "recoveryCodesLeft": twofactor.recovery_codes_left(g.user["id"]) if enabled else 0})


@bp.post("/2fa/setup")
def two_factor_setup():
    """Step 1: after re-entering the password, get a fresh secret (and QR code) to scan."""
    row = _account()
    if row["totp_enabled"]:
        raise HttpError(409, "Two-step verification is already on.")
    _confirm_password(row, security.json_body())
    secret = twofactor.new_secret()
    db.run("UPDATE users SET totp_secret = ?, totp_last_step = NULL WHERE id = ?", (secret, row["id"]))
    uri = twofactor.otpauth_uri(secret, row["email"])
    return jsonify({"secret": secret, "otpauth": uri, "qr": twofactor.qr_data_uri(uri)})


@bp.post("/2fa/enable")
def two_factor_enable():
    """Step 2: prove the authenticator works by entering a code. Returns the recovery codes (shown once)."""
    row = _account()
    if row["totp_enabled"]:
        raise HttpError(409, "Two-step verification is already on.")
    if not row["totp_secret"]:
        raise HttpError(409, "Start the setup again.")
    result, step = twofactor.check_totp(row["totp_secret"], str(security.json_body().get("code") or ""), None)
    if result != "ok":
        raise HttpError(400, "That code doesn't match. Check the time on your phone and try again.")
    db.run("UPDATE users SET totp_enabled = 1, totp_last_step = ? WHERE id = ?", (step, row["id"]))
    codes = twofactor.replace_recovery_codes(row["id"])
    resp = jsonify({"enabled": True, "recoveryCodes": codes})
    _reissue(resp, row["id"])
    return resp


@bp.post("/2fa/disable")
def two_factor_disable():
    row = _account()
    if not row["totp_enabled"]:
        raise HttpError(409, "Two-step verification is already off.")
    body = security.json_body()
    _confirm_password(row, body)
    how = twofactor.verify_second_factor(row, str(body.get("code") or ""))
    if how == "replay":
        raise HttpError(400, "That code was already used. Wait for the next one and try again.")
    if not how:
        raise HttpError(400, "That code is incorrect.")
    db.run("UPDATE users SET totp_enabled = 0, totp_secret = NULL, totp_last_step = NULL WHERE id = ?", (row["id"],))
    db.run("DELETE FROM recovery_codes WHERE user_id = ?", (row["id"],))
    resp = jsonify({"enabled": False})
    _reissue(resp, row["id"])
    return resp


@bp.post("/2fa/recovery-codes")
def two_factor_new_recovery_codes():
    row = _account()
    if not row["totp_enabled"]:
        raise HttpError(409, "Turn on two-step verification first.")
    body = security.json_body()
    _confirm_password(row, body)
    how = twofactor.verify_second_factor(row, str(body.get("code") or ""), allow_recovery=False)
    if how == "replay":
        raise HttpError(400, "That code was already used. Wait for the next one and try again.")
    if how != "totp":
        raise HttpError(400, "That code is incorrect.")
    return jsonify({"recoveryCodes": twofactor.replace_recovery_codes(row["id"])})
