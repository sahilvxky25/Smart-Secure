"""Registration, login (+2FA), logout and the security-question password reset flow."""
import json
import re
import sqlite3
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from . import db, realtime
from .config import APP_NAME, SESSION_DAYS
from .security import (DUMMY_HASH, check_totp, fake_index, hash_backup_code, hash_secret, hash_token,
                       open_secret, random_token, verify_secret)
from .util import (SECURITY_QUESTIONS, ApiError, check_email, check_name, check_password, check_question, count, hit,
                   client_ip, normalize_answer, norm_email, rate_limit, reset, retry_after, valid_email)

router = APIRouter(prefix="/api/auth")


# ---- helpers ----------------------------------------------------------------
def me_dict(u) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "about": u["about"],
            "twoFactor": bool(u["totp_enabled"]), "securityQuestion": u["sq_question"], "createdAt": u["created_at"]}


async def start_session(request: Request, response: Response, user_id: int):
    token = random_token()
    now = int(time.time())
    db.run("INSERT INTO sessions(token_hash,user_id,created_at,expires_at,user_agent,ip) VALUES(?,?,?,?,?,?)",
           (hash_token(token), user_id, now, now + SESSION_DAYS * 86400,
            (request.headers.get("user-agent") or "")[:200], client_ip(request)))
    response.set_cookie("sid", token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", path="/")


def create_ticket(user_id: int, purpose: str, ttl: int) -> str:
    token = random_token()
    db.run("DELETE FROM tickets WHERE user_id=? AND purpose=?", (user_id, purpose))
    db.run("INSERT INTO tickets(token_hash,user_id,purpose,expires_at) VALUES(?,?,?,?)",
           (hash_token(token), user_id, purpose, int(time.time()) + ttl))
    return token


def get_ticket(token: str, purpose: str):
    row = db.one("SELECT * FROM tickets WHERE token_hash=? AND purpose=? AND expires_at>?",
                 (hash_token(token or ""), purpose, int(time.time())))
    if not row:
        raise ApiError(400, "This step has expired. Please start again.", restart=True)
    return row


def fail_ticket(row, max_attempts=5):
    if row["attempts"] + 1 >= max_attempts:
        db.run("DELETE FROM tickets WHERE token_hash=?", (row["token_hash"],))
    else:
        db.run("UPDATE tickets SET attempts=attempts+1 WHERE token_hash=?", (row["token_hash"],))


def check_second_factor(user, code: str) -> bool:
    """Accepts a 6-digit authenticator code or a one-time backup code."""
    code = (code or "").strip()
    if not user["totp_enabled"] and not user["totp_secret_enc"]:
        return False
    digits = code.replace(" ", "")
    if re.fullmatch(r"\d{6}", digits):
        step = check_totp(open_secret(user["totp_secret_enc"]), digits, user["totp_last_step"])
        if step:
            db.run("UPDATE users SET totp_last_step=? WHERE id=?", (step, user["id"]))
            return True
        return False
    h = hash_backup_code(code)
    codes = json.loads(user["backup_codes"])
    if h in codes:
        codes.remove(h)
        db.run("UPDATE users SET backup_codes=? WHERE id=?", (json.dumps(codes), user["id"]))
        return True
    return False


# ---- models -------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: str
    name: str
    password: str
    question: str
    answer: str


class LoginIn(BaseModel):
    email: str
    password: str


class TicketCodeIn(BaseModel):
    ticket: str
    code: str


class EmailIn(BaseModel):
    email: str


class VerifyIn(BaseModel):
    email: str
    answer: str


class ResetIn(BaseModel):
    resetToken: str
    newPassword: str


# ---- routes -------------------------------------------------------------------
@router.get("/questions")
async def questions():
    return {"questions": SECURITY_QUESTIONS}


@router.post("/register", dependencies=[rate_limit("register", 10, 3600)])
async def register(body: RegisterIn, request: Request, response: Response):
    email = check_email(body.email)
    name = check_name(body.name)
    check_password(body.password)
    question, answer = check_question(body.question, body.answer)
    if db.one("SELECT 1 FROM users WHERE email=?", (email,)):
        raise ApiError(409, "An account with this email already exists.")
    pw_hash = await hash_secret(body.password)
    ans_hash = await hash_secret(answer)
    try:
        uid = db.run("""INSERT INTO users(email,name,password_hash,sq_question,sq_answer_hash,created_at)
                        VALUES(?,?,?,?,?,?)""", (email, name, pw_hash, question, ans_hash, int(time.time() * 1000))).lastrowid
    except sqlite3.IntegrityError:
        raise ApiError(409, "An account with this email already exists.")
    await start_session(request, response, uid)
    return {"user": me_dict(db.one("SELECT * FROM users WHERE id=?", (uid,)))}


@router.post("/login", dependencies=[rate_limit("login", 60, 900)])
async def login(body: LoginIn, request: Request, response: Response):
    email = norm_email(body.email)
    k1, k2 = f"login:{email}:{client_ip(request)}", f"loginacct:{email}"
    if count(k1) >= 8 or count(k2) >= 20:
        raise ApiError(429, f"Too many failed attempts. Try again in {retry_after(k1) // 60 + 1} minutes.")
    user = db.one("SELECT * FROM users WHERE email=?", (email,))
    ok = await verify_secret(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok:
        hit(k1, 900)
        hit(k2, 900)
        raise ApiError(401, "Incorrect email or password.")
    reset(k1)
    if user["totp_enabled"]:
        return {"twoFactor": True, "ticket": create_ticket(user["id"], "login2fa", 300)}
    await start_session(request, response, user["id"])
    return {"user": me_dict(user)}


@router.post("/login/2fa", dependencies=[rate_limit("login2fa", 30, 900)])
async def login_2fa(body: TicketCodeIn, request: Request, response: Response):
    t = get_ticket(body.ticket, "login2fa")
    user = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    if not check_second_factor(user, body.code):
        fail_ticket(t)
        raise ApiError(401, "That code is not valid. Check your authenticator app and try again.")
    db.run("DELETE FROM tickets WHERE token_hash=?", (t["token_hash"],))
    await start_session(request, response, user["id"])
    return {"user": me_dict(user)}


@router.post("/logout")
async def logout(request: Request, response: Response):
    tok = request.cookies.get("sid")
    if tok:
        h = hash_token(tok)
        db.run("DELETE FROM sessions WHERE token_hash=?", (h,))
        realtime.manager.disconnect_session(h)
    response.delete_cookie("sid", path="/")
    return {"ok": True}


# ---- forgot password: email -> security question -> (2FA) -> new password -------
@router.post("/forgot/question", dependencies=[rate_limit("fq", 20, 900)])
async def forgot_question(body: EmailIn):
    email = norm_email(body.email)
    if not valid_email(email):
        raise ApiError(400, "Enter a valid email address.")
    u = db.one("SELECT sq_question FROM users WHERE email=?", (email,))
    # Unknown emails get a stable fake question so the form doesn't reveal who has an account.
    q = u["sq_question"] if u else SECURITY_QUESTIONS[fake_index(email, len(SECURITY_QUESTIONS))]
    return {"question": q}


@router.post("/forgot/verify", dependencies=[rate_limit("fv", 20, 900)])
async def forgot_verify(body: VerifyIn):
    email = norm_email(body.email)
    if not valid_email(email):
        raise ApiError(400, "Enter a valid email address.")
    key = f"fp:{email}"
    if count(key) >= 5:
        raise ApiError(429, f"Too many incorrect answers. Try again in {retry_after(key) // 60 + 1} minutes.")
    u = db.one("SELECT * FROM users WHERE email=?", (email,))
    ok = await verify_secret(normalize_answer(body.answer), u["sq_answer_hash"] if u else DUMMY_HASH)
    if not u or not ok:
        hit(key, 1800)
        raise ApiError(400, "That answer doesn't match our records.")
    reset(key)
    if u["totp_enabled"]:  # a security question must never be a way around 2FA
        return {"needs2fa": True, "ticket": create_ticket(u["id"], "reset2fa", 300)}
    return {"resetToken": create_ticket(u["id"], "reset", 600)}


@router.post("/forgot/2fa", dependencies=[rate_limit("f2", 20, 900)])
async def forgot_2fa(body: TicketCodeIn):
    t = get_ticket(body.ticket, "reset2fa")
    u = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    if not check_second_factor(u, body.code):
        fail_ticket(t)
        raise ApiError(401, "That code is not valid. Check your authenticator app and try again.")
    db.run("DELETE FROM tickets WHERE token_hash=?", (t["token_hash"],))
    return {"resetToken": create_ticket(u["id"], "reset", 600)}


@router.post("/forgot/reset", dependencies=[rate_limit("fr", 20, 900)])
async def forgot_reset(body: ResetIn):
    t = get_ticket(body.resetToken, "reset")
    check_password(body.newPassword)
    pw = await hash_secret(body.newPassword)
    db.run("UPDATE users SET password_hash=? WHERE id=?", (pw, t["user_id"]))
    db.run("DELETE FROM sessions WHERE user_id=?", (t["user_id"],))
    db.run("DELETE FROM tickets WHERE user_id=?", (t["user_id"],))
    realtime.manager.disconnect_user(t["user_id"])
    return {"ok": True}
