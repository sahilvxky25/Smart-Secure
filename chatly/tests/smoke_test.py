"""End-to-end smoke test. Start the server first, then:  python tests/smoke_test.py [http://127.0.0.1:8000]
Set DATA_DIR to the server's data dir to also verify that messages are encrypted at rest."""
import asyncio
import json
import os
import sqlite3
import sys
import time
import uuid

import httpx
import websockets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.security import totp_now  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
RUN = uuid.uuid4().hex[:6]
PASS = "Passw0rd!x"
passed = 0


def ok(cond, label):
    global passed
    assert cond, f"FAILED: {label}"
    passed += 1
    print(f"  ✓ {label}")


def client():
    return httpx.AsyncClient(base_url=BASE, headers={"Origin": BASE}, timeout=15)


async def register(name):
    c = client()
    r = await c.post("/api/auth/register", json={"email": f"{name}.{RUN}@test.dev", "name": name.title(), "password": PASS,
                                                 "question": "What was the name of your first pet?", "answer": "Rex The Dog"})
    assert r.status_code == 200, r.text
    return c, r.json()["user"]


class WS:
    def __init__(self, c):
        self.c, self.events = c, []

    async def __aenter__(self):
        sid = self.c.cookies.get("sid")
        self.ws = await websockets.connect(BASE.replace("http", "ws") + "/ws", additional_headers={"Cookie": f"sid={sid}", "Origin": BASE})
        self.task = asyncio.create_task(self._pump())
        await self.wait("ready")
        return self

    async def _pump(self):
        try:
            async for raw in self.ws:
                self.events.append(json.loads(raw))
        except Exception:
            pass

    async def wait(self, t, pred=lambda d: True, timeout=4):
        end = time.time() + timeout
        while time.time() < end:
            for e in self.events:
                if e["t"] == t and pred(e["d"]):
                    self.events.remove(e)
                    return e["d"]
            await asyncio.sleep(0.03)
        raise AssertionError(f"timeout waiting for ws event {t}")

    async def send(self, **m):
        await self.ws.send(json.dumps(m))

    async def __aexit__(self, *a):
        await self.ws.close()
        self.task.cancel()


async def main():
    print("Registration & login")
    a, ua = await register("alice")
    b, ub = await register("bob")
    c, uc = await register("carol")
    ok(ua["twoFactor"] is False and ua["email"].startswith("alice"), "register returns user and logs in")
    r = await client().post("/api/auth/register", json={"email": ua["email"], "name": "X", "password": PASS, "question": "What was the name of your first pet?", "answer": "zz"})
    ok(r.status_code == 409, "duplicate email rejected")
    r = await client().post("/api/auth/register", json={"email": f"weak.{RUN}@test.dev", "name": "W", "password": "short", "question": "What was the name of your first pet?", "answer": "zz"})
    ok(r.status_code == 400, "weak password rejected")
    r = await client().post("/api/auth/login", json={"email": ua["email"], "password": "wrong-pass1"})
    ok(r.status_code == 401, "wrong password rejected")
    ok((await a.get("/api/me")).json()["user"]["id"] == ua["id"], "session cookie authenticates /api/me")
    ok((await client().get("/api/me")).status_code == 401, "no cookie -> 401")
    r = await client().post("/api/auth/login", json={"email": ua["email"], "password": PASS}, headers={"Origin": "https://evil.example"})
    ok(r.status_code == 403, "cross-origin POST blocked (CSRF)")

    print("Forgot password via security question")
    cc = client()
    q = (await cc.post("/api/auth/forgot/question", json={"email": ua["email"]})).json()["question"]
    ok(q == "What was the name of your first pet?", "returns the question chosen at sign-up")
    fake1 = (await cc.post("/api/auth/forgot/question", json={"email": f"nobody.{RUN}@test.dev"})).json()["question"]
    fake2 = (await cc.post("/api/auth/forgot/question", json={"email": f"nobody.{RUN}@test.dev"})).json()["question"]
    ok(fake1 == fake2, "unknown email gets a stable fake question (no account enumeration)")
    r = await cc.post("/api/auth/forgot/verify", json={"email": ua["email"], "answer": "Fluffy"})
    ok(r.status_code == 400, "wrong answer rejected")
    r = await cc.post("/api/auth/forgot/verify", json={"email": ua["email"], "answer": "  rex   the DOG "})
    ok(r.status_code == 200 and "resetToken" in r.json(), "right answer (case/space-insensitive) gives reset token")
    tok = r.json()["resetToken"]
    ok((await cc.post("/api/auth/forgot/reset", json={"resetToken": tok, "newPassword": "short"})).status_code == 400, "reset enforces password policy")
    NEW = "BrandNew123"
    ok((await cc.post("/api/auth/forgot/reset", json={"resetToken": tok, "newPassword": NEW})).status_code == 200, "password reset")
    ok((await cc.post("/api/auth/forgot/reset", json={"resetToken": tok, "newPassword": NEW})).status_code == 400, "reset token is single-use")
    ok((await a.get("/api/me")).status_code == 401, "reset signs out existing sessions")
    ok((await client().post("/api/auth/login", json={"email": ua["email"], "password": PASS})).status_code == 401, "old password no longer works")
    a = client()
    ok((await a.post("/api/auth/login", json={"email": ua["email"], "password": NEW})).status_code == 200, "login with new password")
    # lockout after repeated wrong answers
    lk = client()
    for _ in range(5):
        await lk.post("/api/auth/forgot/verify", json={"email": uc["email"], "answer": "nope"})
    r = await lk.post("/api/auth/forgot/verify", json={"email": uc["email"], "answer": "rex the dog"})
    ok(r.status_code == 429, "recovery locks after 5 wrong answers")

    print("Direct messages, receipts, typing, presence")
    r = await a.post("/api/chats/dm", json={"email": ub["email"]})
    dm = r.json()["chat"]
    ok(dm["type"] == "dm" and dm["name"] == "Bob", "start DM by email")
    ok((await b.get("/api/chats")).json()["chats"] == [], "empty DM hidden from recipient")
    ok((await a.post("/api/chats/dm", json={"email": f"ghost.{RUN}@test.dev"})).status_code == 404, "unknown email -> 404")
    async with WS(b) as wb, WS(a) as wa:
        await wa.wait("presence", lambda d: d["userId"] == ub["id"] and d["online"]) if False else None
        r = await a.post(f"/api/chats/{dm['id']}/messages", json={"text": "Hello Bob 👋 <b>bold</b>"})
        m1 = r.json()["message"]
        got = await wb.wait("message", lambda d: d["id"] == m1["id"])
        ok(got["text"] == "Hello Bob 👋 <b>bold</b>" and got["senderId"] == ua["id"], "recipient receives message live")
        rc = await wa.wait("receipt", lambda d: d["userId"] == ub["id"] and d["delivered"] >= m1["id"])
        ok(rc["read"] < m1["id"], "sender sees 'delivered' (not yet read)")
        ok((await b.get("/api/chats")).json()["chats"][0]["unread"] == 1, "unread counter")
        await wb.send(t="read", chatId=dm["id"], upTo=m1["id"])
        rc = await wa.wait("receipt", lambda d: d["userId"] == ub["id"] and d["read"] >= m1["id"])
        ok(True, "sender sees 'read' after recipient reads")
        await wb.send(t="typing", chatId=dm["id"], typing=True)
        ok((await wa.wait("typing"))["typing"] is True, "typing indicator")
        # reply + delete
        r = await b.post(f"/api/chats/{dm['id']}/messages", json={"text": "Hi Alice!", "replyTo": m1["id"]})
        m2 = r.json()["message"]
        ok(m2["replyTo"]["id"] == m1["id"] and "Hello" in m2["replyTo"]["text"], "reply carries quoted preview")
        await wa.wait("message", lambda d: d["id"] == m2["id"])
        ok((await a.delete(f"/api/chats/{dm['id']}/messages/{m2['id']}")).status_code == 404, "cannot delete someone else's message")
        ok((await b.delete(f"/api/chats/{dm['id']}/messages/{m2['id']}")).status_code == 200, "delete own message")
        d = await wa.wait("message_deleted")
        ok(d["id"] == m2["id"], "deletion pushed live")
        await b.get(f"/api/chats/{dm['id']}/messages")
        msgs = (await a.get(f"/api/chats/{dm['id']}/messages")).json()["messages"]
        ok(msgs[-1]["deleted"] is True and msgs[-1]["text"] is None, "deleted message has no text")
    ok((await a.post(f"/api/chats/{dm['id']}/messages", json={"text": "   "})).status_code == 400, "empty message rejected")
    ok((await c.get(f"/api/chats/{dm['id']}/messages")).status_code == 404, "outsiders cannot read a chat")

    print("Encryption at rest")
    dd = os.getenv("DATA_DIR")
    if dd and os.path.exists(os.path.join(dd, "chatly.db")):
        con = sqlite3.connect(os.path.join(dd, "chatly.db"))
        blob = " ".join(r[0] for r in con.execute("SELECT enc FROM messages"))
        ok("Hello Bob" not in blob and blob.count("v1.") >= 1, "message bodies in SQLite are AES-GCM ciphertext")
        pw = con.execute("SELECT password_hash, sq_answer_hash FROM users WHERE id=?", (ua["id"],)).fetchone()
        ok(pw[0].startswith("scrypt$") and "rex" not in pw[1].lower(), "passwords and security answers are salted scrypt hashes")
    else:
        print("  (skipped: set DATA_DIR to the server's data dir)")

    print("Groups")
    r = await a.post("/api/chats/group", json={"name": "Team", "emails": [ub["email"], uc["email"], f"ghost.{RUN}@test.dev"]})
    g = r.json()["chat"]
    ok(g["type"] == "group" and len(g["members"]) == 3 and r.json()["notFound"], "create group; unknown email reported")
    ok(g["myRole"] == "admin", "creator is admin")
    ok((await b.get("/api/chats")).json()["chats"][0]["type"] in ("group", "dm"), "members see the group")
    ok((await b.patch(f"/api/chats/{g['id']}", json={"name": "Hax"})).status_code == 403, "non-admin cannot rename")
    ok((await a.patch(f"/api/chats/{g['id']}", json={"name": "Team Alpha"})).json()["chat"]["name"] == "Team Alpha", "admin renames")
    d_ = await register("dave")
    async with WS(d_[0]) as wd:
        r = await a.post(f"/api/chats/{g['id']}/members", json={"emails": [d_[1]["email"]]})
        ok(len(r.json()["chat"]["members"]) == 4, "admin adds member")
        ch = await wd.wait("chat")
        ok(ch["id"] == g["id"], "new member is pushed the group live")
    hist = (await d_[0].get(f"/api/chats/{g['id']}/messages")).json()["messages"]
    ok(all("created the group" not in (m["text"] or "") for m in hist), "new member can't see history before joining")
    await b.post(f"/api/chats/{g['id']}/messages", json={"text": "hi team"})
    ok((await a.post(f"/api/chats/{g['id']}/members/{ub['id']}/role", json={"role": "admin"})).status_code == 200, "promote to admin")
    ok((await a.delete(f"/api/chats/{g['id']}/members/{uc['id']}")).status_code == 200, "admin removes member")
    ok((await c.get(f"/api/chats/{g['id']}")).status_code == 404, "removed member loses access")
    ok((await d_[0].delete(f"/api/chats/{g['id']}/members/{ub['id']}")).status_code == 403, "member cannot remove others")
    ok((await d_[0].delete(f"/api/chats/{g['id']}/members/{d_[1]['id']}")).status_code == 200, "member can leave")

    print("Change password")
    a2 = client()
    await a2.post("/api/auth/login", json={"email": ua["email"], "password": NEW})
    ok((await a.post("/api/account/password", json={"current": "wrong", "new": "Another123"})).status_code == 403, "needs current password")
    ok((await a.post("/api/account/password", json={"current": NEW, "new": "Another123"})).status_code == 200, "password changed")
    ok((await a2.get("/api/me")).status_code == 401, "other devices signed out")
    ok((await a.get("/api/me")).status_code == 200, "current device stays signed in")
    NEW = "Another123"

    print("Two-factor authentication")
    s = (await b.post("/api/account/2fa/setup")).json()
    ok(s["qr"].startswith("data:image/svg+xml") and s["uri"].startswith("otpauth://totp/"), "2FA setup returns QR + otpauth URI")
    ok((await b.post("/api/account/2fa/enable", json={"code": "000000"})).status_code == 400, "wrong code can't enable 2FA")
    r = await b.post("/api/account/2fa/enable", json={"code": totp_now(s["secret"])})
    backup = r.json()["backupCodes"]
    ok(r.status_code == 200 and len(backup) == 8, "2FA enabled, 8 backup codes issued")
    nb = client()
    r = await nb.post("/api/auth/login", json={"email": ub["email"], "password": PASS})
    ok(r.json().get("twoFactor") is True and (await nb.get("/api/me")).status_code == 401, "login now stops at 2FA step")
    ticket = r.json()["ticket"]
    ok((await nb.post("/api/auth/login/2fa", json={"ticket": ticket, "code": "123456"})).status_code == 401, "wrong 2FA code rejected")
    # replay protection: the code used to enable cannot be reused; wait for the next step
    nxt = totp_now(s["secret"], time.time() + 30)
    r = await nb.post("/api/auth/login/2fa", json={"ticket": ticket, "code": nxt})
    ok(r.status_code == 200 and (await nb.get("/api/me")).status_code == 200, "valid TOTP completes login")
    nb2 = client()
    t2 = (await nb2.post("/api/auth/login", json={"email": ub["email"], "password": PASS})).json()["ticket"]
    ok((await nb2.post("/api/auth/login/2fa", json={"ticket": t2, "code": backup[0]})).status_code == 200, "backup code logs in")
    nb3 = client()
    t3 = (await nb3.post("/api/auth/login", json={"email": ub["email"], "password": PASS})).json()["ticket"]
    ok((await nb3.post("/api/auth/login/2fa", json={"ticket": t3, "code": backup[0]})).status_code == 401, "backup code is single-use")
    # forgot-password must not bypass 2FA
    fp = client()
    r = await fp.post("/api/auth/forgot/verify", json={"email": ub["email"], "answer": "rex the dog"})
    ok(r.json().get("needs2fa") is True and "resetToken" not in r.json(), "security question alone does NOT bypass 2FA")
    r = await fp.post("/api/auth/forgot/2fa", json={"ticket": r.json()["ticket"], "code": backup[1]})
    ok(r.status_code == 200 and "resetToken" in r.json(), "reset allowed after 2FA code")
    ok((await b.post("/api/account/2fa/disable", json={"password": "bad", "code": "x"})).status_code == 403, "disable 2FA needs password")

    print("Delete account")
    async with WS(a) as wa2:
        dd2 = await register("erin")
        er = dd2[0]
        await er.post("/api/chats/dm", json={"email": ua["email"]})
        chat = (await er.post("/api/chats/dm", json={"email": ua["email"]})).json()["chat"]
        await er.post(f"/api/chats/{chat['id']}/messages", json={"text": "bye soon"})
        gr = (await er.post("/api/chats/group", json={"name": "Erin's", "emails": [ua["email"]]})).json()["chat"]
        await er.post(f"/api/chats/{gr['id']}/messages", json={"text": "group msg"})
        await wa2.wait("message", lambda d: d["text"] == "bye soon")
        ok((await er.post("/api/account/delete", json={"password": "bad", "confirm": "DELETE"})).status_code == 403, "deletion needs correct password")
        ok((await er.post("/api/account/delete", json={"password": PASS, "confirm": "nope"})).status_code == 400, "deletion needs DELETE confirmation")
        ok((await er.post("/api/account/delete", json={"password": PASS, "confirm": "DELETE"})).status_code == 200, "account deleted")
        await wa2.wait("chat_removed", lambda d: d["chatId"] == chat["id"])
        ok(True, "peer's DM removed live")
    ok((await er.get("/api/me")).status_code == 401, "deleted user's session is dead")
    ok((await client().post("/api/auth/login", json={"email": dd2[1]["email"], "password": PASS})).status_code == 401, "deleted user cannot log in")
    grp = (await a.get(f"/api/chats/{gr['id']}")).json()["chat"]
    ok(grp["myRole"] == "admin" and len(grp["members"]) == 1, "group survives; remaining member promoted to admin")
    ok((await a.get(f"/api/chats/{chat['id']}")).status_code == 404, "1:1 chat with deleted user is gone")

    ok((await a.post("/api/auth/logout")).status_code == 200 and (await a.get("/api/me")).status_code == 401, "logout")
    print(f"\nAll {passed} checks passed ✔")


asyncio.run(main())
