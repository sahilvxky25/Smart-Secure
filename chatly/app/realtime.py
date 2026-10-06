"""WebSocket hub: live messages, receipts, typing indicators, presence."""
import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import db
from .util import origin_allowed, session_for_token

router = APIRouter()


class Conn:
    def __init__(self, ws: WebSocket, uid: int, sess_hash: str):
        self.ws, self.uid, self.sess_hash = ws, uid, sess_hash
        self.q: asyncio.Queue = asyncio.Queue()

    async def writer(self):
        while True:
            item = await self.q.get()
            if item is None:  # session revoked -> close
                try:
                    await self.ws.close(code=4401)
                except Exception:
                    pass
                return
            try:
                await self.ws.send_text(item)
            except Exception:
                return


class Manager:
    def __init__(self):
        self.conns: dict[int, set[Conn]] = {}

    def add(self, c: Conn) -> bool:
        s = self.conns.setdefault(c.uid, set())
        s.add(c)
        return len(s) == 1

    def remove(self, c: Conn) -> bool:
        s = self.conns.get(c.uid, set())
        s.discard(c)
        if not s:
            self.conns.pop(c.uid, None)
            return True
        return False

    def is_online(self, uid: int) -> bool:
        return uid in self.conns

    def emit(self, uid: int, event: str, data):
        cs = self.conns.get(uid)
        if cs:
            payload = json.dumps({"t": event, "d": data}, separators=(",", ":"))
            for c in list(cs):
                c.q.put_nowait(payload)

    def disconnect_user(self, uid: int, keep_hash: str | None = None):
        for c in list(self.conns.get(uid, ())):
            if c.sess_hash != keep_hash:
                c.q.put_nowait(None)

    def disconnect_session(self, sess_hash: str):
        for cs in list(self.conns.values()):
            for c in list(cs):
                if c.sess_hash == sess_hash:
                    c.q.put_nowait(None)


manager = Manager()
emit = manager.emit


def now_ms() -> int:
    return int(time.time() * 1000)


def member_ids(chat_id: int) -> list[int]:
    return [r["user_id"] for r in db.all_("SELECT user_id FROM chat_members WHERE chat_id=?", (chat_id,))]


def co_member_ids(uid: int) -> list[int]:
    rows = db.all_("""SELECT DISTINCT user_id FROM chat_members
                      WHERE chat_id IN (SELECT chat_id FROM chat_members WHERE user_id=?) AND user_id!=?""", (uid, uid))
    return [r["user_id"] for r in rows]


def broadcast_presence(uid: int, online: bool):
    last_seen = now_ms()
    for other in co_member_ids(uid):
        emit(other, "presence", {"userId": uid, "online": online, "lastSeen": last_seen})


def broadcast_profile(uid: int):
    u = db.one("SELECT id,name,about FROM users WHERE id=?", (uid,))
    if u:
        for other in co_member_ids(uid) + [uid]:
            emit(other, "profile", {"id": u["id"], "name": u["name"], "about": u["about"]})


def emit_receipt(chat_id: int, uid: int):
    r = db.one("SELECT last_delivered_id d, last_read_id r FROM chat_members WHERE chat_id=? AND user_id=?", (chat_id, uid))
    if not r:
        return
    payload = {"chatId": chat_id, "userId": uid, "delivered": r["d"], "read": r["r"]}
    for m in member_ids(chat_id):
        emit(m, "receipt", payload)


def mark_all_delivered(uid: int):
    rows = db.all_("""SELECT m.chat_id, m.last_delivered_id d,
                             (SELECT MAX(id) FROM messages WHERE chat_id=m.chat_id) mx
                      FROM chat_members m WHERE m.user_id=?""", (uid,))
    for r in rows:
        if r["mx"] and r["mx"] > r["d"]:
            db.run("UPDATE chat_members SET last_delivered_id=? WHERE chat_id=? AND user_id=?", (r["mx"], r["chat_id"], uid))
            emit_receipt(r["chat_id"], uid)


def mark_read(uid: int, chat_id: int, up_to: int):
    m = db.one("SELECT last_read_id FROM chat_members WHERE chat_id=? AND user_id=?", (chat_id, uid))
    if not m:
        return
    mx = db.one("SELECT COALESCE(MAX(id),0) mx FROM messages WHERE chat_id=?", (chat_id,))["mx"]
    up_to = min(up_to, mx)
    if up_to > m["last_read_id"]:
        db.run("""UPDATE chat_members SET last_read_id=?, last_delivered_id=MAX(last_delivered_id,?)
                  WHERE chat_id=? AND user_id=?""", (up_to, up_to, chat_id, uid))
        emit_receipt(chat_id, uid)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    sess = session_for_token(ws.cookies.get("sid"))
    if not sess or not origin_allowed(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=4401)
        return
    await ws.accept()
    uid = sess["user_id"]
    conn = Conn(ws, uid, sess["token_hash"])
    first = manager.add(conn)
    writer = asyncio.create_task(conn.writer())
    try:
        if first:
            broadcast_presence(uid, True)
        mark_all_delivered(uid)
        conn.q.put_nowait(json.dumps({"t": "ready", "d": {}}))
        while True:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=90)
            if len(raw) > 2000:
                continue
            try:
                msg = json.loads(raw)
                t = msg.get("t")
                if t == "ping":
                    conn.q.put_nowait('{"t":"pong","d":{}}')
                elif t == "typing":
                    cid = int(msg.get("chatId"))
                    if db.one("SELECT 1 FROM chat_members WHERE chat_id=? AND user_id=?", (cid, uid)):
                        for m in member_ids(cid):
                            if m != uid:
                                emit(m, "typing", {"chatId": cid, "userId": uid, "typing": bool(msg.get("typing"))})
                elif t == "read":
                    mark_read(uid, int(msg.get("chatId")), int(msg.get("upTo")))
            except (ValueError, TypeError, AttributeError):
                continue
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
        pass
    finally:
        last = manager.remove(conn)
        writer.cancel()
        if last:
            db.run("UPDATE users SET last_seen=? WHERE id=?", (now_ms(), uid))
            broadcast_presence(uid, False)
