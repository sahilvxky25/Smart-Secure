import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Body, Depends, FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders

from . import db, mailcore as mail
from .config import config
from .errors import ApiError

log = logging.getLogger("postly")

REAL_FOLDERS = ["inbox", "sent", "drafts", "spam", "trash", "archive"]
PAGE_SIZE = 50
SESSION_MS = 30 * 24 * 3600 * 1000
RESERVED = {"postmaster", "mailer-daemon", "abuse", "admin", "root"}


# ------------------------------------------------------------------ app & middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.run("DELETE FROM sessions WHERE expires_at < ?", mail.now_ms())
    controller = None
    print(f"\n{config.app_name} running")
    print(f"  Web app: http://{'localhost' if config.host in ('0.0.0.0', '127.0.0.1') else config.host}:{config.port}")
    print(f"  Addresses look like: you@{config.domain}")
    if config.smtp_enabled:
        try:
            controller = mail.start_smtp_server()
            print(f"  SMTP inbound listening on {config.smtp_bind}:{config.smtp_port}")
        except Exception as e:
            raise SystemExit(f"Could not start the SMTP server on port {config.smtp_port}: {e}\n"
                             "(Ports below 1024 need extra privileges; try SMTP_PORT=2525.)")
    print(f"  Outbound: {'relay via ' + config.relay['host'] if config.relay else 'direct delivery (MX lookup)'}\n")
    yield
    if controller:
        controller.stop()


app = FastAPI(title=config.app_name, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: https: http:; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'")


class SecurityHeaders:
    """Pure ASGI middleware (doesn't buffer the live-update stream).
    The CSP is inherited by the srcdoc iframes that show message bodies: no scripts anywhere."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("X-Frame-Options", "SAMEORIGIN")
                h.setdefault("Referrer-Policy", "no-referrer")
                h.setdefault("Content-Security-Policy", CSP)
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeaders)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse({"error": exc.message}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "That request wasn’t understood"}, status_code=400)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse({"error": "Something went wrong on the server"}, status_code=500)


# ------------------------------------------------------------------ auth helpers

def hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32, maxmem=2**26)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                              dklen=len(dk) // 2, maxmem=2**26)
        return hmac.compare_digest(calc.hex(), dk)
    except Exception:
        return False


_DUMMY_HASH = hash_password("not-a-real-password")


def start_session(response: Response, user_id: int) -> None:
    token = secrets.token_hex(32)
    db.run("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
           hash_token(token), user_id, mail.now_ms() + SESSION_MS)
    response.set_cookie("sid", token, httponly=True, samesite="lax", secure=config.cookie_secure,
                        max_age=SESSION_MS // 1000, path="/")


def require_auth(request: Request):
    token = request.cookies.get("sid")
    if token:
        row = db.one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                     "WHERE s.token_hash = ? AND s.expires_at > ?", hash_token(token), mail.now_ms())
        if row:
            return dict(row)
    raise ApiError(401, "Not signed in")


def public_user(u) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "signature": u["signature"],
            "appName": config.app_name, "domain": config.domain}


_hits: dict[str, deque] = defaultdict(deque)


def auth_limit(request: Request) -> None:
    """30 sign-in/sign-up attempts per 15 minutes per address."""
    ip = request.client.host if request.client else "?"
    if config.trust_proxy and request.headers.get("x-forwarded-for"):
        ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > 900:
        q.popleft()
    if len(q) >= 30:
        raise ApiError(429, "Too many attempts. Try again in a few minutes.")
    q.append(now)


# ------------------------------------------------------------------ auth routes

@app.get("/api/config")
def get_config():
    return {"appName": config.app_name, "domain": config.domain, "allowSignup": config.allow_signup}


@app.post("/api/auth/register")
def register(response: Response, payload: dict = Body(default={}), _=Depends(auth_limit)):
    if not config.allow_signup:
        raise ApiError(403, "Sign-ups are disabled on this server")
    username = str(payload.get("username") or "").strip().lower()
    name = str(payload.get("name") or "").strip()[:80]
    password = str(payload.get("password") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,29}", username):
        raise ApiError(400, "Username must be 3–30 characters: letters, numbers, dots, dashes or underscores")
    if username in RESERVED:
        raise ApiError(400, "That username is reserved")
    if not name:
        raise ApiError(400, "Enter your name")
    if len(password) < 8:
        raise ApiError(400, "Password must be at least 8 characters")
    if db.one("SELECT 1 FROM users WHERE username = ?", username):
        raise ApiError(409, "That address is taken")
    email = f"{username}@{config.domain}"
    cur = db.run("INSERT INTO users (username, email, name, password_hash, created_at) VALUES (?,?,?,?,?)",
                 username, email, name, hash_password(password), mail.now_ms())
    user = dict(db.one("SELECT * FROM users WHERE id = ?", cur.lastrowid))
    safe_name = re.sub(r"[<>&]", "", user["name"])
    mail.store_copy(user["id"], "inbox", {
        "message_id": mail.new_message_id(),
        "from": {"name": f"{config.app_name} Team", "address": f"postmaster@{config.domain}"},
        "to": [{"name": user["name"], "address": user["email"]}],
        "subject": f"Welcome to {config.app_name}",
        "html": (f"<p>Hi {safe_name},</p><p>Your address is <b>{user['email']}</b>. You can send and receive mail, "
                 "star and label messages, search with operators like <code>from:</code> and "
                 "<code>has:attachment</code>, and press <b>c</b> to compose.</p>"),
        "date": mail.now_ms(),
    })
    start_session(response, user["id"])
    return public_user(user)


@app.post("/api/auth/login")
def login(response: Response, payload: dict = Body(default={}), _=Depends(auth_limit)):
    ident = str(payload.get("email") or payload.get("username") or "").strip().lower()
    row = db.one("SELECT * FROM users WHERE email = ? OR username = ?", ident, ident)
    # Same work whether or not the account exists, so response time doesn't reveal accounts
    ok = verify_password(str(payload.get("password") or ""), row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise ApiError(401, "Wrong email or password")
    start_session(response, row["id"])
    return public_user(row)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("sid")
    if token:
        db.run("DELETE FROM sessions WHERE token_hash = ?", hash_token(token))
    response.delete_cookie("sid", path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(require_auth)):
    return public_user(user)


@app.put("/api/me")
def update_me(payload: dict = Body(default={}), user=Depends(require_auth)):
    name = str(payload["name"]).strip()[:80] if "name" in payload else user["name"]
    signature = str(payload["signature"])[:2000] if "signature" in payload else user["signature"]
    if not name:
        raise ApiError(400, "Name can’t be empty")
    if payload.get("newPassword"):
        if not verify_password(str(payload.get("currentPassword") or ""), user["password_hash"]):
            raise ApiError(400, "Current password is wrong")
        if len(str(payload["newPassword"])) < 8:
            raise ApiError(400, "New password must be at least 8 characters")
        db.run("UPDATE users SET password_hash = ? WHERE id = ?", hash_password(str(payload["newPassword"])), user["id"])
    db.run("UPDATE users SET name = ?, signature = ? WHERE id = ?", name, signature, user["id"])
    return public_user(db.one("SELECT * FROM users WHERE id = ?", user["id"]))


# ------------------------------------------------------------------ live updates (Server-Sent Events)

@app.get("/api/events")
async def events(user=Depends(require_auth)):
    async def stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        mail.hub.subscribe(user["id"], loop, queue)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            mail.hub.unsubscribe(user["id"], loop, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ listing & search

def like(s: str) -> str:
    return "%" + re.sub(r"([\\%_])", r"\\\1", str(s)) + "%"


_TOKEN_RE = re.compile(r'(\w+):("[^"]*"|\S+)|"([^"]*)"|(\S+)')


def build_filter(user_id: int, view: str, q: str):
    """WHERE fragment (on messages) for a folder / starred / label view or a search query."""
    conds: list[str] = []
    params: list = []
    folder_override = None
    text: list[str] = []
    operators: list[tuple[str, str]] = []

    for m in _TOKEN_RE.finditer(q or ""):
        if m.group(1):
            operators.append((m.group(1).lower(), m.group(2).strip('"')))
        else:
            text.append(m.group(3) if m.group(3) is not None else m.group(4))

    for op, val in operators:
        if op == "from":
            conds.append("(from_addr LIKE ? ESCAPE '\\' OR from_name LIKE ? ESCAPE '\\')")
            params += [like(val)] * 2
        elif op == "to":
            conds.append("(to_addrs LIKE ? ESCAPE '\\' OR cc_addrs LIKE ? ESCAPE '\\' OR bcc_addrs LIKE ? ESCAPE '\\')")
            params += [like(val)] * 3
        elif op == "subject":
            conds.append("subject LIKE ? ESCAPE '\\'")
            params.append(like(val))
        elif op == "in":
            folder_override = val.lower()
        elif op == "is":
            if val == "unread":
                conds.append("is_read = 0")
            elif val == "read":
                conds.append("is_read = 1")
            elif val == "starred":
                conds.append("is_starred = 1")
        elif op == "has":
            if val.startswith("attach"):
                conds.append("has_attachments = 1")
        elif op == "label":
            conds.append("id IN (SELECT ml.message_id FROM message_labels ml JOIN labels l ON l.id = ml.label_id "
                         "WHERE l.user_id = ? AND l.name = ? COLLATE NOCASE)")
            params += [user_id, val]
        else:
            text.append(f"{op}:{val}")

    for t in text:
        conds.append("(subject LIKE ? ESCAPE '\\' OR body_text LIKE ? ESCAPE '\\' OR from_addr LIKE ? ESCAPE '\\' "
                     "OR from_name LIKE ? ESCAPE '\\' OR to_addrs LIKE ? ESCAPE '\\')")
        params += [like(t)] * 5

    scope = folder_override or ("all" if view == "search" else view)
    if scope in REAL_FOLDERS:
        conds.append("folder = ?")
        params.append(scope)
    elif scope == "starred":
        conds.append("is_starred = 1 AND folder NOT IN ('trash','spam')")
    elif scope == "anywhere":
        pass
    elif scope.startswith("label:"):
        try:
            label_id = int(scope[6:])
        except ValueError:
            label_id = -1
        conds.append("folder NOT IN ('trash','spam') AND id IN (SELECT ml.message_id FROM message_labels ml "
                     "JOIN labels l ON l.id = ml.label_id WHERE l.user_id = ? AND l.id = ?)")
        params += [user_id, label_id]
    else:
        conds.append("folder NOT IN ('trash','spam')")
    return ("AND " + " AND ".join(conds)) if conds else "", params


def safe_json(s):
    try:
        return json.loads(s)
    except Exception:
        return []


# A conversation's count/participants cover the whole conversation (like Gmail), not just the current folder;
# Trash and Spam views only count their own messages.
THREAD_COND = """m2.owner_id = f.owner_id AND m2.thread_id = f.thread_id AND
  CASE WHEN f.folder IN ('trash','spam') THEN m2.folder = f.folder ELSE m2.folder NOT IN ('trash','spam','drafts') END"""


@app.get("/api/threads")
def list_threads(view: str = "inbox", page: int = 1, q: str = "", user=Depends(require_auth)):
    page = max(1, page)
    where, params = build_filter(user["id"], view, q)
    cte = (f"WITH f AS (SELECT *, CASE WHEN folder = 'drafts' THEN 'd' || id ELSE thread_id END AS tk "
           f"FROM messages WHERE owner_id = ? {where})")
    base = [user["id"], *params]
    total = db.one(f"{cte} SELECT COUNT(DISTINCT tk) AS n FROM f", *base)["n"]
    rows = db.all_(
        f"""{cte}
        SELECT f.id, f.tk, f.thread_id, f.folder, f.from_addr, f.from_name, f.to_addrs, f.subject, f.snippet, f.date,
          CASE WHEN f.folder = 'drafts' THEN 1 ELSE (SELECT COUNT(*) FROM messages m2 WHERE {THREAD_COND}) END AS count,
          (SELECT MAX(1 - f2.is_read) FROM f f2 WHERE f2.tk = f.tk) AS unread,
          (SELECT MAX(f2.is_starred) FROM f f2 WHERE f2.tk = f.tk) AS starred,
          (SELECT MAX(f2.has_attachments) FROM f f2 WHERE f2.tk = f.tk) AS any_attachments,
          (SELECT group_concat(label_id) FROM (SELECT DISTINCT ml.label_id FROM message_labels ml
             JOIN f f2 ON f2.id = ml.message_id WHERE f2.tk = f.tk)) AS label_ids,
          (SELECT group_concat(s, char(1)) FROM (SELECT m2.from_name || char(2) || m2.from_addr AS s, MIN(m2.date) AS d
             FROM messages m2 WHERE {THREAD_COND} GROUP BY s ORDER BY d)) AS senders
        FROM f
        WHERE f.id = (SELECT f3.id FROM f f3 WHERE f3.tk = f.tk ORDER BY f3.date DESC, f3.id DESC LIMIT 1)
        ORDER BY f.date DESC, f.id DESC
        LIMIT ? OFFSET ?""",
        *base, PAGE_SIZE, (page - 1) * PAGE_SIZE)

    threads = []
    for r in rows:
        senders = []
        for s in (r["senders"] or "").split("\x01"):
            if s:
                name, _, address = s.partition("\x02")
                senders.append({"name": name, "address": address})
        threads.append({
            "id": r["id"], "key": r["tk"], "threadId": r["thread_id"], "folder": r["folder"],
            "subject": r["subject"], "snippet": r["snippet"], "date": r["date"], "count": r["count"],
            "unread": bool(r["unread"]), "starred": bool(r["starred"]), "hasAttachments": bool(r["any_attachments"]),
            "to": safe_json(r["to_addrs"]),
            "labelIds": [int(x) for x in r["label_ids"].split(",")] if r["label_ids"] else [],
            "senders": senders,
        })
    return {"page": page, "pageSize": PAGE_SIZE, "total": total, "threads": threads}


@app.get("/api/counts")
def counts(user=Depends(require_auth)):
    uid = user["id"]

    def n(sql):
        return db.one(sql, uid)["n"]

    labels = db.all_(
        """SELECT l.id, COUNT(DISTINCT m.thread_id) AS n FROM labels l
           LEFT JOIN message_labels ml ON ml.label_id = l.id
           LEFT JOIN messages m ON m.id = ml.message_id AND m.is_read = 0 AND m.folder NOT IN ('trash','spam')
           WHERE l.user_id = ? GROUP BY l.id""", uid)
    return {
        "inbox": n("SELECT COUNT(DISTINCT thread_id) AS n FROM messages WHERE owner_id = ? AND folder = 'inbox' AND is_read = 0"),
        "drafts": n("SELECT COUNT(*) AS n FROM messages WHERE owner_id = ? AND folder = 'drafts'"),
        "spam": n("SELECT COUNT(DISTINCT thread_id) AS n FROM messages WHERE owner_id = ? AND folder = 'spam' AND is_read = 0"),
        "labels": {str(l["id"]): l["n"] for l in labels},
    }


# ------------------------------------------------------------------ reading a conversation

@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str, view: str = "", user=Depends(require_auth)):
    uid = user["id"]
    if view in ("trash", "spam"):
        rows = db.all_("SELECT * FROM messages WHERE owner_id = ? AND thread_id = ? AND folder = ? "
                       "ORDER BY date ASC, id ASC", uid, thread_id, view)
    else:
        rows = db.all_("SELECT * FROM messages WHERE owner_id = ? AND thread_id = ? AND folder NOT IN ('trash','spam') "
                       "ORDER BY date ASC, id ASC", uid, thread_id)
    if not rows:
        raise ApiError(404, "Conversation not found")

    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    atts = db.all_(f"SELECT id, message_id, filename, content_type, size, cid FROM attachments WHERE message_id IN ({marks})", *ids)
    label_rows = db.all_(f"SELECT message_id, label_id FROM message_labels WHERE message_id IN ({marks})", *ids)

    changed = db.run(f"UPDATE messages SET is_read = 1 WHERE owner_id = ? AND id IN ({marks}) "
                     "AND folder != 'drafts' AND is_read = 0", uid, *ids).rowcount
    if changed:
        mail.hub.notify(uid)  # only when something flipped, otherwise the live-update stream would loop

    messages = []
    for r in rows:
        mine = [a for a in atts if a["message_id"] == r["id"]]
        html = r["body_html"]
        for a in (x for x in mine if x["cid"]):
            html = html.replace(f"cid:{a['cid']}", f"/api/attachments/{a['id']}")
        messages.append({
            "id": r["id"], "folder": r["folder"], "messageId": r["message_id"],
            "from": {"name": r["from_name"], "address": r["from_addr"]},
            "to": safe_json(r["to_addrs"]), "cc": safe_json(r["cc_addrs"]), "bcc": safe_json(r["bcc_addrs"]),
            "subject": r["subject"], "html": html, "text": r["body_text"], "date": r["date"],
            "starred": bool(r["is_starred"]), "unread": not r["is_read"],
            "attachments": [{"id": a["id"], "filename": a["filename"], "contentType": a["content_type"], "size": a["size"]}
                            for a in mine if not a["cid"]],
        })
    return {"threadId": thread_id, "subject": rows[-1]["subject"] or "(no subject)",
            "labelIds": sorted({l["label_id"] for l in label_rows}), "messages": messages}


INLINE_SAFE = re.compile(r"^image/(png|jpeg|gif|webp)$")


@app.get("/api/attachments/{att_id}")
def get_attachment(att_id: int, download: str = "", user=Depends(require_auth)):
    a = db.one("SELECT a.* FROM attachments a JOIN messages m ON m.id = a.message_id WHERE a.id = ? AND m.owner_id = ?",
               att_id, user["id"])
    if not a:
        raise ApiError(404, "Attachment not found")
    inline = not download and bool(INLINE_SAFE.match(a["content_type"]))
    return Response(a["data"], headers={
        "Content-Type": a["content_type"] if inline else "application/octet-stream",
        "Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(a['filename'])}",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "private, max-age=86400",
    })


# ------------------------------------------------------------------ compose: send & drafts

def own_draft_id(user_id: int, raw) -> int | None:
    try:
        did = int(raw)
    except (TypeError, ValueError):
        return None
    row = db.one("SELECT id FROM messages WHERE id = ? AND owner_id = ? AND folder = 'drafts'", did, user_id)
    return row["id"] if row else None


def gather_attachments(user_id: int, draft_id, keep_json: str, files: list[UploadFile]) -> list[dict]:
    out: list[dict] = []
    if draft_id:
        try:
            keep = [int(x) for x in json.loads(keep_json or "[]")]
        except Exception:
            keep = []
        if keep:
            rows = db.all_(
                f"SELECT a.filename, a.content_type, a.data FROM attachments a JOIN messages m ON m.id = a.message_id "
                f"WHERE m.owner_id = ? AND m.id = ? AND a.id IN ({','.join('?' * len(keep))})",
                user_id, draft_id, *keep)
            out += [{"filename": r["filename"], "content_type": r["content_type"], "content": r["data"]} for r in rows]
    if len(files) > 20:
        raise ApiError(400, "Too many attachments (max 20)")
    for f in files:
        data = f.file.read(config.max_attachment_bytes + 1)
        if len(data) > config.max_attachment_bytes:
            raise ApiError(413, "That file is too large")
        out.append({"filename": f.filename or "attachment",
                    "content_type": f.content_type or "application/octet-stream", "content": data})
    if sum(len(a["content"]) for a in out) > config.max_attachment_bytes:
        raise ApiError(413, f"Attachments are over the {config.max_attachment_bytes // 1048576} MB limit")
    return out


@app.post("/api/send")
def send(to: str = Form(""), cc: str = Form(""), bcc: str = Form(""), subject: str = Form(""), html: str = Form(""),
         inReplyTo: str = Form(""), threadId: str = Form(""), draftId: str = Form(""),
         keepAttachments: str = Form("[]"), attachments: list[UploadFile] = File(default=[]),
         user=Depends(require_auth)):
    did = own_draft_id(user["id"], draftId)
    result = mail.send_message(
        user, to=mail.parse_address_list(to), cc=mail.parse_address_list(cc), bcc=mail.parse_address_list(bcc),
        subject=subject[:500], html=html, in_reply_to=inReplyTo or None, thread_id=threadId or None,
        attachments=gather_attachments(user["id"], did, keepAttachments, attachments))
    if did:
        db.run("DELETE FROM messages WHERE id = ? AND owner_id = ?", did, user["id"])
    mail.hub.notify(user["id"])
    return {"ok": True, **result}


@app.post("/api/drafts")
def save_draft(to: str = Form(""), cc: str = Form(""), bcc: str = Form(""), subject: str = Form(""), html: str = Form(""),
               inReplyTo: str = Form(""), threadId: str = Form(""), draftId: str = Form(""),
               keepAttachments: str = Form("[]"), attachments: list[UploadFile] = File(default=[]),
               user=Depends(require_auth)):
    uid = user["id"]
    did = own_draft_id(uid, draftId)
    atts = gather_attachments(uid, did, keepAttachments, attachments)  # read before the old draft is deleted
    if did:
        db.run("DELETE FROM messages WHERE id = ? AND owner_id = ?", did, uid)
    valid_thread = threadId if threadId and db.one(
        "SELECT 1 FROM messages WHERE owner_id = ? AND thread_id = ? LIMIT 1", uid, threadId) else None
    new_id = mail.store_copy(uid, "drafts", {
        "message_id": mail.new_message_id(), "in_reply_to": inReplyTo or None, "refs": None,
        "from": {"name": user["name"], "address": user["email"]},
        "to": mail.parse_address_list(to), "cc": mail.parse_address_list(cc), "subject": subject[:500],
        "html": html, "date": mail.now_ms(), "attachments": atts,
    }, is_read=1, thread_id=valid_thread, bcc=mail.parse_address_list(bcc))
    saved = db.all_("SELECT id, filename, size, content_type AS contentType FROM attachments WHERE message_id = ?", new_id)
    return {"ok": True, "id": new_id, "threadId": db.one("SELECT thread_id FROM messages WHERE id = ?", new_id)["thread_id"],
            "attachments": [dict(a) for a in saved]}


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: int, user=Depends(require_auth)):
    m = db.one("SELECT * FROM messages WHERE id = ? AND owner_id = ? AND folder = 'drafts'", draft_id, user["id"])
    if not m:
        raise ApiError(404, "Draft not found")
    atts = db.all_("SELECT id, filename, content_type, size FROM attachments WHERE message_id = ?", m["id"])
    return {"id": m["id"], "threadId": m["thread_id"], "inReplyTo": m["in_reply_to"], "subject": m["subject"],
            "html": m["body_html"], "to": safe_json(m["to_addrs"]), "cc": safe_json(m["cc_addrs"]),
            "bcc": safe_json(m["bcc_addrs"]),
            "attachments": [{"id": a["id"], "filename": a["filename"], "size": a["size"], "contentType": a["content_type"]}
                            for a in atts]}


# ------------------------------------------------------------------ actions on conversations

def resolve_ids(user_id: int, keys: list, scope: str) -> list[int]:
    ids: list[int] = []
    for k in [str(x) for x in keys][:500]:
        if re.fullmatch(r"d\d+", k):
            r = db.one("SELECT id FROM messages WHERE owner_id = ? AND id = ?", user_id, int(k[1:]))
            if r:
                ids.append(r["id"])
        elif scope in REAL_FOLDERS:
            ids += [r["id"] for r in db.all_("SELECT id FROM messages WHERE owner_id = ? AND thread_id = ? AND folder = ?",
                                             user_id, k, scope)]
        else:
            ids += [r["id"] for r in db.all_("SELECT id FROM messages WHERE owner_id = ? AND thread_id = ? "
                                             "AND folder NOT IN ('trash','spam')", user_id, k)]
    return ids


ACTION_SQL = {
    "read": "UPDATE messages SET is_read = 1 WHERE owner_id = ? AND id IN ({IDS})",
    "unread": "UPDATE messages SET is_read = 0 WHERE owner_id = ? AND id IN ({IDS}) AND folder != 'drafts'",
    "star": "UPDATE messages SET is_starred = 1 WHERE owner_id = ? AND id IN ({IDS})",
    "unstar": "UPDATE messages SET is_starred = 0 WHERE owner_id = ? AND id IN ({IDS})",
    "archive": "UPDATE messages SET folder = 'archive' WHERE owner_id = ? AND id IN ({IDS}) AND folder = 'inbox'",
    "trash": "UPDATE messages SET orig_folder = folder, folder = 'trash' WHERE owner_id = ? AND id IN ({IDS}) AND folder != 'trash'",
    "spam": "UPDATE messages SET orig_folder = folder, folder = 'spam' WHERE owner_id = ? AND id IN ({IDS}) AND folder NOT IN ('spam','drafts','sent')",
    "notspam": "UPDATE messages SET folder = 'inbox', orig_folder = NULL WHERE owner_id = ? AND id IN ({IDS}) AND folder = 'spam'",
    "restore": ("UPDATE messages SET folder = CASE WHEN orig_folder IN ('sent','drafts','archive') THEN orig_folder ELSE 'inbox' END, "
                "orig_folder = NULL WHERE owner_id = ? AND id IN ({IDS}) AND folder = 'trash'"),
    "inbox": "UPDATE messages SET folder = 'inbox' WHERE owner_id = ? AND id IN ({IDS}) AND folder = 'archive'",
    "delete": "DELETE FROM messages WHERE owner_id = ? AND id IN ({IDS}) AND folder IN ('trash','spam','drafts')",
}


@app.post("/api/threads/batch")
def batch(payload: dict = Body(default={}), user=Depends(require_auth)):
    uid = user["id"]
    action = payload.get("action")
    keys = payload.get("threads") or []
    scope = str(payload.get("scope") or "all")
    if not isinstance(keys, list):
        raise ApiError(400, "Unknown action")
    if action not in ACTION_SQL and action not in ("label", "unlabel"):
        raise ApiError(400, "Unknown action")
    ids = resolve_ids(uid, keys, scope)
    if not ids:
        return {"ok": True, "changed": 0}
    marks = ",".join("?" * len(ids))
    changed = 0
    if action in ACTION_SQL:
        changed = db.run(ACTION_SQL[action].replace("{IDS}", marks), uid, *ids).rowcount
    else:
        try:
            label_id = int(payload.get("labelId"))
        except (TypeError, ValueError):
            label_id = -1
        label = db.one("SELECT id FROM labels WHERE id = ? AND user_id = ?", label_id, uid)
        if not label:
            raise ApiError(404, "Label not found")
        if action == "label":
            with db.tx() as c:
                for i in ids:
                    changed += c.execute("INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?,?)",
                                         (i, label["id"])).rowcount
        else:
            changed = db.run(f"DELETE FROM message_labels WHERE label_id = ? AND message_id IN ({marks})",
                             label["id"], *ids).rowcount
    mail.hub.notify(uid)
    return {"ok": True, "changed": changed}


@app.post("/api/folders/{name}/empty")
def empty_folder(name: str, user=Depends(require_auth)):
    if name not in ("trash", "spam"):
        raise ApiError(400, "Only Trash and Spam can be emptied")
    n = db.run("DELETE FROM messages WHERE owner_id = ? AND folder = ?", user["id"], name).rowcount
    mail.hub.notify(user["id"])
    return {"ok": True, "deleted": n}


# ------------------------------------------------------------------ labels

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@app.get("/api/labels")
def list_labels(user=Depends(require_auth)):
    return [dict(r) for r in db.all_("SELECT id, name, color FROM labels WHERE user_id = ? ORDER BY name COLLATE NOCASE",
                                     user["id"])]


@app.post("/api/labels")
def create_label(payload: dict = Body(default={}), user=Depends(require_auth)):
    name = str(payload.get("name") or "").strip()[:40]
    color = payload.get("color") if HEX_COLOR.match(str(payload.get("color") or "")) else "#0f766e"
    if not name:
        raise ApiError(400, "Enter a label name")
    if db.one("SELECT 1 FROM labels WHERE user_id = ? AND name = ? COLLATE NOCASE", user["id"], name):
        raise ApiError(409, "You already have a label with that name")
    cur = db.run("INSERT INTO labels (user_id, name, color) VALUES (?,?,?)", user["id"], name, color)
    mail.hub.notify(user["id"])
    return {"id": cur.lastrowid, "name": name, "color": color}


@app.put("/api/labels/{label_id}")
def update_label(label_id: int, payload: dict = Body(default={}), user=Depends(require_auth)):
    label = db.one("SELECT * FROM labels WHERE id = ? AND user_id = ?", label_id, user["id"])
    if not label:
        raise ApiError(404, "Label not found")
    name = str(payload["name"]).strip()[:40] if "name" in payload else label["name"]
    color = payload["color"] if HEX_COLOR.match(str(payload.get("color") or "")) else label["color"]
    if not name:
        raise ApiError(400, "Enter a label name")
    if db.one("SELECT 1 FROM labels WHERE user_id = ? AND name = ? COLLATE NOCASE AND id != ?", user["id"], name, label_id):
        raise ApiError(409, "You already have a label with that name")
    db.run("UPDATE labels SET name = ?, color = ? WHERE id = ?", name, color, label_id)
    mail.hub.notify(user["id"])
    return {"id": label_id, "name": name, "color": color}


@app.delete("/api/labels/{label_id}")
def delete_label(label_id: int, user=Depends(require_auth)):
    db.run("DELETE FROM labels WHERE id = ? AND user_id = ?", label_id, user["id"])
    mail.hub.notify(user["id"])
    return {"ok": True}


# ------------------------------------------------------------------ contacts autocomplete

@app.get("/api/contacts")
def contacts(q: str = "", user=Depends(require_auth)):
    q = q.strip().lower()
    if not q:
        return []
    p = like(q)
    rows = db.all_(
        """SELECT from_name, from_addr, to_addrs, cc_addrs FROM messages
           WHERE owner_id = ? AND (from_addr LIKE ? ESCAPE '\\' OR from_name LIKE ? ESCAPE '\\'
             OR to_addrs LIKE ? ESCAPE '\\' OR cc_addrs LIKE ? ESCAPE '\\')
           ORDER BY date DESC LIMIT 300""", user["id"], p, p, p, p)
    seen: dict[str, dict] = {}

    def add(name, address):
        address = str(address or "").lower()
        if not address or address == user["email"] or address.startswith("mailer-daemon@"):
            return
        if q not in address and q not in str(name or "").lower():
            return
        cur = seen.setdefault(address, {"name": "", "address": address, "n": 0})
        cur["n"] += 1
        if name and not cur["name"]:
            cur["name"] = name

    for r in rows:
        add(r["from_name"], r["from_addr"])
        for a in safe_json(r["to_addrs"]) + safe_json(r["cc_addrs"]):
            add(a.get("name"), a.get("address"))
    for u in db.all_("SELECT name, email FROM users WHERE id != ? AND (email LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\') LIMIT 8",
                     user["id"], p, p):
        add(u["name"], u["email"])
    top = sorted(seen.values(), key=lambda c: -c["n"])[:8]
    return [{"name": c["name"], "address": c["address"]} for c in top]


# ------------------------------------------------------------------ fallbacks & static client

@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def api_not_found(rest: str):
    raise ApiError(404, "Not found")


app.mount("/", StaticFiles(directory=config.public_dir, html=True), name="client")
