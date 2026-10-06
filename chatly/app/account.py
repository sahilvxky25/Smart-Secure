"""Profile, password change, security question, 2FA, sessions, account deletion."""
import json
import time

import segno
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from . import chats, db, realtime
from .auth import check_second_factor, me_dict
from .config import APP_NAME
from .security import (check_totp, hash_backup_code, hash_secret, new_backup_codes, new_totp_secret, open_secret,
                       seal_secret, totp_uri, verify_secret)
from .util import ApiError, auth, check_name, check_password, check_question, count, hit, reset, retry_after

router = APIRouter(prefix="/api")


async def require_password(ctx, password: str):
    key = f"pw:{ctx.id}"
    if count(key) >= 5:
        raise ApiError(429, f"Too many wrong passwords. Try again in {retry_after(key) // 60 + 1} minutes.")
    if not await verify_secret(password or "", ctx.user["password_hash"]):
        hit(key, 900)
        raise ApiError(403, "Incorrect password.")
    reset(key)


def fresh(ctx):
    return db.one("SELECT * FROM users WHERE id=?", (ctx.id,))


class ProfileIn(BaseModel):
    name: str | None = None
    about: str | None = None


class PasswordIn(BaseModel):
    current: str
    new: str


class QuestionIn(BaseModel):
    password: str
    question: str
    answer: str


class CodeIn(BaseModel):
    code: str


class DisableIn(BaseModel):
    password: str
    code: str


class DeleteIn(BaseModel):
    password: str
    code: str = ""
    confirm: str


@router.get("/me")
async def me(ctx=Depends(auth)):
    return {"user": me_dict(ctx.user)}


@router.patch("/me")
async def update_me(body: ProfileIn, ctx=Depends(auth)):
    if body.name is not None:
        db.run("UPDATE users SET name=? WHERE id=?", (check_name(body.name), ctx.id))
    if body.about is not None:
        about = " ".join(body.about.split())[:140]
        db.run("UPDATE users SET about=? WHERE id=?", (about or "Hey there! I am using Chatly.", ctx.id))
    realtime.broadcast_profile(ctx.id)
    return {"user": me_dict(fresh(ctx))}


@router.post("/account/password")
async def change_password(body: PasswordIn, ctx=Depends(auth)):
    await require_password(ctx, body.current)
    check_password(body.new)
    if body.new == body.current:
        raise ApiError(400, "Choose a password you haven't used just now.")
    db.run("UPDATE users SET password_hash=? WHERE id=?", (await hash_secret(body.new), ctx.id))
    db.run("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (ctx.id, ctx.sess["token_hash"]))
    realtime.manager.disconnect_user(ctx.id, keep_hash=ctx.sess["token_hash"])
    return {"ok": True}


@router.post("/account/security-question")
async def change_question(body: QuestionIn, ctx=Depends(auth)):
    await require_password(ctx, body.password)
    q, a = check_question(body.question, body.answer)
    db.run("UPDATE users SET sq_question=?, sq_answer_hash=? WHERE id=?", (q, await hash_secret(a), ctx.id))
    return {"user": me_dict(fresh(ctx))}


# ---- two-factor authentication ------------------------------------------------
@router.post("/account/2fa/setup")
async def tfa_setup(ctx=Depends(auth)):
    if ctx.user["totp_enabled"]:
        raise ApiError(400, "Two-factor authentication is already on.")
    secret = new_totp_secret()
    db.run("UPDATE users SET totp_secret_enc=? WHERE id=?", (seal_secret(secret), ctx.id))
    uri = totp_uri(secret, ctx.user["email"], APP_NAME)
    qr = segno.make(uri, error="m").svg_data_uri(scale=6, border=2, dark="#111b21", light="#ffffff")
    return {"secret": secret, "uri": uri, "qr": qr}


@router.post("/account/2fa/enable")
async def tfa_enable(body: CodeIn, ctx=Depends(auth)):
    u = fresh(ctx)
    if u["totp_enabled"] or not u["totp_secret_enc"]:
        raise ApiError(400, "Start the setup again.")
    if hit(f"tfa:{ctx.id}", 600) > 10:
        raise ApiError(429, "Too many attempts. Try again later.")
    step = check_totp(open_secret(u["totp_secret_enc"]), body.code.replace(" ", ""), u["totp_last_step"])
    if not step:
        raise ApiError(400, "That code is not valid. Check your authenticator app and try again.")
    codes = new_backup_codes()
    db.run("UPDATE users SET totp_enabled=1, totp_last_step=?, backup_codes=? WHERE id=?",
           (step, json.dumps([hash_backup_code(c) for c in codes]), ctx.id))
    return {"backupCodes": codes, "user": me_dict(fresh(ctx))}


@router.post("/account/2fa/disable")
async def tfa_disable(body: DisableIn, ctx=Depends(auth)):
    u = fresh(ctx)
    if not u["totp_enabled"]:
        raise ApiError(400, "Two-factor authentication is not on.")
    await require_password(ctx, body.password)
    if hit(f"tfa:{ctx.id}", 600) > 10 or not check_second_factor(u, body.code):
        raise ApiError(403, "That code is not valid.")
    db.run("UPDATE users SET totp_enabled=0, totp_secret_enc=NULL, backup_codes='[]', totp_last_step=0 WHERE id=?", (ctx.id,))
    return {"user": me_dict(fresh(ctx))}


# ---- sessions -----------------------------------------------------------------
@router.get("/account/sessions")
async def sessions(ctx=Depends(auth)):
    rows = db.all_("SELECT * FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC",
                   (ctx.id, int(time.time())))
    return {"sessions": [{"createdAt": r["created_at"] * 1000, "userAgent": r["user_agent"], "ip": r["ip"],
                          "current": r["token_hash"] == ctx.sess["token_hash"]} for r in rows]}


@router.post("/account/sessions/revoke-others")
async def revoke_others(ctx=Depends(auth)):
    db.run("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (ctx.id, ctx.sess["token_hash"]))
    realtime.manager.disconnect_user(ctx.id, keep_hash=ctx.sess["token_hash"])
    return {"ok": True}


# ---- delete account -----------------------------------------------------------
@router.post("/account/delete")
async def delete_account(body: DeleteIn, ctx=Depends(auth)):
    if body.confirm.strip() != "DELETE":
        raise ApiError(400, "Type DELETE to confirm.")
    await require_password(ctx, body.password)
    u = fresh(ctx)
    if u["totp_enabled"] and (hit(f"tfa:{ctx.id}", 600) > 10 or not check_second_factor(u, body.code)):
        raise ApiError(403, "That two-factor code is not valid.")
    chats.purge_user(ctx.id, u["name"])
    return {"ok": True}
