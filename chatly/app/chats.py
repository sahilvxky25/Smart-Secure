"""Chats: 1:1 conversations, groups, messages, receipts."""
import time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from . import db, realtime
from .config import MAX_GROUP_MEMBERS, MAX_MESSAGE_LEN
from .security import decrypt_message, encrypt_message
from .util import ApiError, auth, check_email, check_name, hit, norm_email, rate_limit

router = APIRouter(prefix="/api")
emit = realtime.emit


def ms() -> int:
    return int(time.time() * 1000)


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------
def pub(u) -> dict:
    return {"id": u["id"], "name": u["name"], "about": u["about"], "email": u["email"]}


def members_of(chat_id: int) -> list[dict]:
    rows = db.all_("""SELECT u.id,u.name,u.about,u.email,u.last_seen,m.role,m.last_delivered_id d,m.last_read_id r
                      FROM chat_members m JOIN users u ON u.id=m.user_id
                      WHERE m.chat_id=? ORDER BY m.joined_at, u.id""", (chat_id,))
    return [{**pub(r), "role": r["role"], "delivered": r["d"], "read": r["r"],
             "online": realtime.manager.is_online(r["id"]), "lastSeen": r["last_seen"]} for r in rows]


def get_membership(chat_id: int, uid: int):
    return db.one("SELECT * FROM chat_members WHERE chat_id=? AND user_id=?", (chat_id, uid))


def require_member(chat_id: int, uid: int):
    m = get_membership(chat_id, uid)
    if not m:
        raise ApiError(404, "Chat not found.")
    return m


def require_group(chat_id: int, uid: int, admin=False):
    m = require_member(chat_id, uid)
    chat = db.one("SELECT * FROM chats WHERE id=?", (chat_id,))
    if chat["type"] != "group":
        raise ApiError(400, "This action is only available in groups.")
    if admin and m["role"] != "admin":
        raise ApiError(403, "Only group admins can do that.")
    return chat, m


def serialize_message(r) -> dict:
    text = None if r["deleted"] else decrypt_message(r["chat_id"], r["enc"])
    reply = None
    if r["reply_to"]:
        p = db.one("SELECT * FROM messages WHERE id=? AND chat_id=?", (r["reply_to"], r["chat_id"]))
        if p:
            reply = {"id": p["id"], "senderId": p["sender_id"],
                     "text": None if p["deleted"] else decrypt_message(p["chat_id"], p["enc"])[:140]}
    return {"id": r["id"], "chatId": r["chat_id"], "senderId": r["sender_id"], "kind": r["kind"], "text": text,
            "replyTo": reply, "createdAt": r["created_at"], "deleted": bool(r["deleted"])}


def chat_summary(chat_id: int, uid: int):
    m = get_membership(chat_id, uid)
    chat = db.one("SELECT * FROM chats WHERE id=?", (chat_id,))
    if not m or not chat:
        return None
    members = members_of(chat_id)
    last = db.one("SELECT * FROM messages WHERE chat_id=? AND id>? ORDER BY id DESC LIMIT 1", (chat_id, m["from_msg_id"]))
    unread = db.one("""SELECT COUNT(*) c FROM messages WHERE chat_id=? AND id>? AND kind='text' AND deleted=0
                       AND sender_id!=?""", (chat_id, max(m["last_read_id"], m["from_msg_id"]), uid))["c"]
    out = {"id": chat_id, "type": chat["type"], "description": chat["description"], "createdBy": chat["created_by"],
           "createdAt": chat["created_at"], "members": members, "myRole": m["role"], "unread": unread,
           "last": serialize_message(last) if last else None}
    if chat["type"] == "dm":
        peer = next((x for x in members if x["id"] != uid), None)
        out.update(name=peer["name"] if peer else "Deleted user", peerId=peer["id"] if peer else None)
    else:
        out["name"] = chat["name"]
    return out


def broadcast_chat(chat_id: int):
    for uid in realtime.member_ids(chat_id):
        s = chat_summary(chat_id, uid)
        if s:
            emit(uid, "chat", s)


def insert_message(chat_id: int, sender_id, kind: str, text: str, reply_to=None):
    cur = db.run("INSERT INTO messages(chat_id,sender_id,kind,enc,reply_to,created_at) VALUES(?,?,?,?,?,?)",
                 (chat_id, sender_id, kind, encrypt_message(chat_id, text), reply_to, ms()))
    return db.one("SELECT * FROM messages WHERE id=?", (cur.lastrowid,))


def publish_message(row):
    chat_id, mid = row["chat_id"], row["id"]
    payload = serialize_message(row)
    members = realtime.member_ids(chat_id)
    delivered = []
    if row["kind"] == "text" and row["sender_id"]:
        db.run("""UPDATE chat_members SET last_delivered_id=MAX(last_delivered_id,?), last_read_id=MAX(last_read_id,?)
                  WHERE chat_id=? AND user_id=?""", (mid, mid, chat_id, row["sender_id"]))
        for u in members:
            if u != row["sender_id"] and realtime.manager.is_online(u):
                db.run("UPDATE chat_members SET last_delivered_id=MAX(last_delivered_id,?) WHERE chat_id=? AND user_id=?",
                       (mid, chat_id, u))
                delivered.append(u)
    for u in members:
        emit(u, "message", payload)
    for u in delivered:
        realtime.emit_receipt(chat_id, u)


def system_message(chat_id: int, text: str):
    row = insert_message(chat_id, None, "system", text)
    broadcast_chat(chat_id)
    publish_message(row)


def resolve_emails(emails: list[str], exclude=()):
    found, missing, seen = [], [], set()
    for raw in emails[:MAX_GROUP_MEMBERS]:
        e = norm_email(raw)
        if not e or e in seen:
            continue
        seen.add(e)
        u = db.one("SELECT * FROM users WHERE email=?", (e,))
        if not u:
            missing.append(e)
        elif u["id"] not in exclude:
            found.append(u)
    return found, missing


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
class DmIn(BaseModel):
    email: str


class GroupIn(BaseModel):
    name: str
    description: str = ""
    emails: list[str] = []


class GroupPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class EmailsIn(BaseModel):
    emails: list[str]


class RoleIn(BaseModel):
    role: str


class MessageIn(BaseModel):
    text: str
    replyTo: int | None = None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.get("/users/lookup", dependencies=[rate_limit("lookup", 40, 60)])
async def lookup(email: str, ctx=Depends(auth)):
    u = db.one("SELECT * FROM users WHERE email=?", (check_email(email),))
    if not u:
        raise ApiError(404, "No Chatly user with that email address.")
    return {"user": pub(u)}


@router.get("/chats")
async def list_chats(ctx=Depends(auth)):
    out = []
    for r in db.all_("SELECT chat_id FROM chat_members WHERE user_id=?", (ctx.id,)):
        s = chat_summary(r["chat_id"], ctx.id)
        # an empty DM started by somebody else stays hidden until they actually write
        if s and not (s["type"] == "dm" and s["last"] is None and s["createdBy"] != ctx.id):
            out.append(s)
    return {"chats": out}


@router.post("/chats/dm", dependencies=[rate_limit("dm", 40, 60)])
async def create_dm(body: DmIn, ctx=Depends(auth)):
    peer = db.one("SELECT * FROM users WHERE email=?", (check_email(body.email),))
    if not peer:
        raise ApiError(404, "No Chatly user with that email address.")
    if peer["id"] == ctx.id:
        raise ApiError(400, "That's your own email address.")
    a, b = sorted((ctx.id, peer["id"]))
    row = db.one("SELECT id FROM chats WHERE dm_key=?", (f"{a}:{b}",))
    if row:
        cid = row["id"]
    else:
        with db.tx():
            cid = db.run("INSERT INTO chats(type,dm_key,created_by,created_at) VALUES('dm',?,?,?)",
                         (f"{a}:{b}", ctx.id, ms())).lastrowid
            for u in (ctx.id, peer["id"]):
                db.run("INSERT INTO chat_members(chat_id,user_id,joined_at) VALUES(?,?,?)", (cid, u, ms()))
    return {"chat": chat_summary(cid, ctx.id)}


@router.post("/chats/group", dependencies=[rate_limit("group", 20, 60)])
async def create_group(body: GroupIn, ctx=Depends(auth)):
    name = check_name(body.name, "Group name", 60)
    desc = (body.description or "").strip()[:200]
    found, missing = resolve_emails(body.emails, exclude={ctx.id})
    if not found:
        raise ApiError(400, "Add at least one other person who has a Chatly account.", notFound=missing)
    if len(found) + 1 > MAX_GROUP_MEMBERS:
        raise ApiError(400, f"Groups can have at most {MAX_GROUP_MEMBERS} members.")
    with db.tx():
        cid = db.run("INSERT INTO chats(type,name,description,created_by,created_at) VALUES('group',?,?,?,?)",
                     (name, desc, ctx.id, ms())).lastrowid
        db.run("INSERT INTO chat_members(chat_id,user_id,role,joined_at) VALUES(?,?,'admin',?)", (cid, ctx.id, ms()))
        for u in found:
            db.run("INSERT INTO chat_members(chat_id,user_id,joined_at) VALUES(?,?,?)", (cid, u["id"], ms()))
    system_message(cid, f"{ctx.user['name']} created the group “{name}”")
    return {"chat": chat_summary(cid, ctx.id), "notFound": missing}


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: int, ctx=Depends(auth)):
    require_member(chat_id, ctx.id)
    return {"chat": chat_summary(chat_id, ctx.id)}


@router.get("/chats/{chat_id}/messages")
async def list_messages(chat_id: int, before: int | None = None, limit: int = Query(40, ge=1, le=100), ctx=Depends(auth)):
    m = require_member(chat_id, ctx.id)
    rows = db.all_("""SELECT * FROM messages WHERE chat_id=? AND id>? AND (? IS NULL OR id<?)
                      ORDER BY id DESC LIMIT ?""", (chat_id, m["from_msg_id"], before, before, limit + 1))
    more = len(rows) > limit
    return {"messages": [serialize_message(r) for r in rows[:limit][::-1]], "hasMore": more}


@router.post("/chats/{chat_id}/messages")
async def send_message(chat_id: int, body: MessageIn, ctx=Depends(auth)):
    require_member(chat_id, ctx.id)
    if hit(f"send:{ctx.id}", 10) > 30:
        raise ApiError(429, "You're sending messages too fast.")
    text = (body.text or "").replace("\r\n", "\n").strip()
    if not text:
        raise ApiError(400, "Message is empty.")
    if len(text) > MAX_MESSAGE_LEN:
        raise ApiError(400, f"Messages can be at most {MAX_MESSAGE_LEN} characters.")
    reply = None
    if body.replyTo:
        p = db.one("SELECT id FROM messages WHERE id=? AND chat_id=? AND kind='text'", (body.replyTo, chat_id))
        reply = p["id"] if p else None
    chat = db.one("SELECT type FROM chats WHERE id=?", (chat_id,))
    if chat["type"] == "dm" and len(realtime.member_ids(chat_id)) < 2:
        raise ApiError(400, "This person is no longer on Chatly.")
    row = insert_message(chat_id, ctx.id, "text", text, reply)
    publish_message(row)
    return {"message": serialize_message(row)}


@router.delete("/chats/{chat_id}/messages/{mid}")
async def delete_message(chat_id: int, mid: int, ctx=Depends(auth)):
    require_member(chat_id, ctx.id)
    r = db.one("SELECT * FROM messages WHERE id=? AND chat_id=? AND sender_id=? AND kind='text'", (mid, chat_id, ctx.id))
    if not r:
        raise ApiError(404, "Message not found.")
    db.run("UPDATE messages SET deleted=1, enc=? WHERE id=?", (encrypt_message(chat_id, ""), mid))
    for u in realtime.member_ids(chat_id):
        emit(u, "message_deleted", {"chatId": chat_id, "id": mid})
    return {"ok": True}


@router.patch("/chats/{chat_id}")
async def update_group(chat_id: int, body: GroupPatch, ctx=Depends(auth)):
    chat, _ = require_group(chat_id, ctx.id, admin=True)
    note = None
    if body.name is not None:
        name = check_name(body.name, "Group name", 60)
        if name != chat["name"]:
            db.run("UPDATE chats SET name=? WHERE id=?", (name, chat_id))
            note = f"{ctx.user['name']} renamed the group to “{name}”"
    if body.description is not None:
        db.run("UPDATE chats SET description=? WHERE id=?", (body.description.strip()[:200], chat_id))
    if note:
        system_message(chat_id, note)
    else:
        broadcast_chat(chat_id)
    return {"chat": chat_summary(chat_id, ctx.id)}


@router.post("/chats/{chat_id}/members", dependencies=[rate_limit("addm", 30, 60)])
async def add_members(chat_id: int, body: EmailsIn, ctx=Depends(auth)):
    require_group(chat_id, ctx.id, admin=True)
    found, missing = resolve_emails(body.emails)
    existing = set(realtime.member_ids(chat_id))
    new = [u for u in found if u["id"] not in existing]
    if not new:
        raise ApiError(400, "Nobody new to add. Check the email addresses.", notFound=missing)
    if len(existing) + len(new) > MAX_GROUP_MEMBERS:
        raise ApiError(400, f"Groups can have at most {MAX_GROUP_MEMBERS} members.")
    mx = db.one("SELECT COALESCE(MAX(id),0) m FROM messages WHERE chat_id=?", (chat_id,))["m"]
    with db.tx():
        for u in new:
            db.run("""INSERT INTO chat_members(chat_id,user_id,joined_at,from_msg_id,last_delivered_id,last_read_id)
                      VALUES(?,?,?,?,?,?)""", (chat_id, u["id"], ms(), mx, mx, mx))
    system_message(chat_id, f"{ctx.user['name']} added " + ", ".join(u["name"] for u in new))
    return {"chat": chat_summary(chat_id, ctx.id), "notFound": missing}


def _ensure_admin(chat_id: int):
    if not db.one("SELECT 1 FROM chat_members WHERE chat_id=? AND role='admin'", (chat_id,)):
        nxt = db.one("SELECT user_id FROM chat_members WHERE chat_id=? ORDER BY joined_at, user_id LIMIT 1", (chat_id,))
        if nxt:
            db.run("UPDATE chat_members SET role='admin' WHERE chat_id=? AND user_id=?", (chat_id, nxt["user_id"]))


@router.delete("/chats/{chat_id}/members/{user_id}")
async def remove_member(chat_id: int, user_id: int, ctx=Depends(auth)):
    _, me = require_group(chat_id, ctx.id)
    if user_id != ctx.id and me["role"] != "admin":
        raise ApiError(403, "Only group admins can remove members.")
    target = get_membership(chat_id, user_id)
    if not target:
        raise ApiError(404, "That person isn't in this group.")
    tname = db.one("SELECT name FROM users WHERE id=?", (user_id,))["name"]
    with db.tx():
        db.run("DELETE FROM chat_members WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        remaining = realtime.member_ids(chat_id)
        if not remaining:
            db.run("DELETE FROM chats WHERE id=?", (chat_id,))
        else:
            _ensure_admin(chat_id)
    emit(user_id, "chat_removed", {"chatId": chat_id})
    if remaining:
        system_message(chat_id, f"{tname} left" if user_id == ctx.id else f"{ctx.user['name']} removed {tname}")
    return {"ok": True}


@router.post("/chats/{chat_id}/members/{user_id}/role")
async def set_role(chat_id: int, user_id: int, body: RoleIn, ctx=Depends(auth)):
    require_group(chat_id, ctx.id, admin=True)
    if body.role not in ("admin", "member"):
        raise ApiError(400, "Invalid role.")
    t = get_membership(chat_id, user_id)
    if not t:
        raise ApiError(404, "That person isn't in this group.")
    if t["role"] == body.role:
        return {"chat": chat_summary(chat_id, ctx.id)}
    if body.role == "member":
        n = db.one("SELECT COUNT(*) c FROM chat_members WHERE chat_id=? AND role='admin'", (chat_id,))["c"]
        if n <= 1:
            raise ApiError(400, "A group needs at least one admin. Make someone else admin first.")
    db.run("UPDATE chat_members SET role=? WHERE chat_id=? AND user_id=?", (body.role, chat_id, user_id))
    tname = db.one("SELECT name FROM users WHERE id=?", (user_id,))["name"]
    system_message(chat_id, f"{ctx.user['name']} made {tname} an admin" if body.role == "admin"
                   else f"{ctx.user['name']} removed {tname} as admin")
    return {"chat": chat_summary(chat_id, ctx.id)}


# --------------------------------------------------------------------------
# Account deletion support
# --------------------------------------------------------------------------
def purge_user(uid: int, name: str):
    """Delete a user and everything of theirs. DMs disappear, groups keep going without them."""
    chats = db.all_("""SELECT c.id, c.type FROM chats c JOIN chat_members m ON m.chat_id=c.id WHERE m.user_id=?""", (uid,))
    gone_dm, groups = [], []
    with db.tx():
        for c in chats:
            if c["type"] == "dm":
                peers = [r["user_id"] for r in db.all_("SELECT user_id FROM chat_members WHERE chat_id=? AND user_id!=?", (c["id"], uid))]
                db.run("DELETE FROM chats WHERE id=?", (c["id"],))
                gone_dm += [(p, c["id"]) for p in peers]
            else:
                db.run("DELETE FROM chat_members WHERE chat_id=? AND user_id=?", (c["id"], uid))
                if not realtime.member_ids(c["id"]):
                    db.run("DELETE FROM chats WHERE id=?", (c["id"],))
                else:
                    _ensure_admin(c["id"])
                    groups.append(c["id"])
        db.run("DELETE FROM users WHERE id=?", (uid,))
    realtime.manager.disconnect_user(uid)
    for peer, cid in gone_dm:
        emit(peer, "chat_removed", {"chatId": cid})
    for cid in groups:
        system_message(cid, f"{name} deleted their account")
