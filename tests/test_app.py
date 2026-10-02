import os
import tempfile

# Configure before the app is imported
_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "test.db"), SMTP_ENABLED="false", MAIL_DOMAIN="localhost")

from email.message import EmailMessage  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, mailcore  # noqa: E402
from app.main import app  # noqa: E402

PW = "password123"


@pytest.fixture(scope="module")
def users():
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as eve:
        for c, name in ((alice, "alice"), (bob, "bob"), (eve, "eve")):
            r = c.post("/api/auth/register", json={"username": name, "name": name.title(), "password": PW})
            assert r.status_code == 200, r.text
        yield alice, bob, eve


def inbox(c, view="inbox", q=""):
    return c.get("/api/threads", params={"view": view, "q": q}).json()


def send(c, **fields):
    files = fields.pop("files", None)
    return c.post("/api/send", data=fields, files=files)


def test_auth_rules(users):
    alice, *_ = users
    anon = TestClient(app)
    assert anon.get("/api/threads").status_code == 401
    assert anon.post("/api/auth/login", json={"email": "alice", "password": "wrong"}).status_code == 401
    assert anon.post("/api/auth/register", json={"username": "alice", "name": "X", "password": PW}).status_code == 409
    assert anon.post("/api/auth/register", json={"username": "newbie", "name": "N", "password": "short"}).status_code == 400
    assert anon.post("/api/auth/register", json={"username": "admin", "name": "N", "password": PW}).status_code == 400
    assert anon.post("/api/auth/login", json={"email": "alice@localhost", "password": PW}).status_code == 200
    assert alice.get("/api/me").json()["email"] == "alice@localhost"


def test_send_receive_thread_and_attachment(users):
    alice, bob, _ = users
    r = send(alice, to="Bob <bob@localhost>", subject="Quarterly report", html="<p>Hi <b>Bob</b><script>x()</script></p>",
             files=[("attachments", ("café.txt", b"numbers", "text/plain"))])
    assert r.status_code == 200, r.text

    t = next(t for t in inbox(bob)["threads"] if t["subject"] == "Quarterly report")
    assert t["unread"] and t["hasAttachments"]
    thread = bob.get(f"/api/threads/{t['threadId']}").json()
    m = thread["messages"][0]
    assert "<script" not in m["html"] and "<b>Bob</b>" in m["html"]          # sanitised
    assert m["attachments"][0]["filename"] == "café.txt"                       # unicode filename survives
    att = bob.get(f"/api/attachments/{m['attachments'][0]['id']}?download=1")
    assert att.content == b"numbers" and att.headers["content-type"] == "application/octet-stream"
    assert not next(x for x in inbox(bob)["threads"] if x["subject"] == "Quarterly report")["unread"]  # opening marks read

    # Reply threads onto the same conversation for both people
    r = send(bob, to="alice@localhost", subject="Re: Quarterly report", html="<p>Got it</p>",
             inReplyTo=m["messageId"], threadId=t["threadId"])
    assert r.status_code == 200
    a = next(x for x in inbox(alice, "all")["threads"] if "Quarterly" in x["subject"])
    assert a["count"] == 2 and a["unread"]
    assert len(alice.get(f"/api/threads/{a['threadId']}").json()["messages"]) == 2


def test_attachments_are_private(users):
    alice, bob, eve = users
    att_id = db.one("SELECT id FROM attachments ORDER BY id LIMIT 1")["id"]
    assert eve.get(f"/api/attachments/{att_id}").status_code == 404
    assert eve.get("/api/threads", params={"view": "all"}).json()["total"] == 1  # only her welcome message


def test_search_operators(users):
    alice, bob, _ = users
    q = lambda s: alice.get("/api/threads", params={"view": "search", "q": s}).json()["total"]
    assert q("from:bob") == 1
    assert q("from:alice has:attachment") == 1
    assert q("from:bob has:attachment") == 0
    assert q("report") == 1
    assert q("subject:quarterly") == 1
    assert q("in:sent") == 1
    assert q("nonexistentword") == 0
    assert q('"100%_literal"') == 0          # LIKE wildcards are escaped, no crash


def test_bounce_for_unknown_local_user(users):
    alice, *_ = users
    assert send(alice, to="ghost@localhost", subject="Hello?", html="<p>x</p>").status_code == 200
    bounce = [t for t in inbox(alice)["threads"] if t["subject"].startswith("Delivery failed")]
    assert bounce and "mailer-daemon@localhost" == bounce[0]["senders"][0]["address"]


def test_send_validation(users):
    alice, *_ = users
    assert send(alice, to="", subject="x", html="x").status_code == 400
    r = send(alice, to="not-an-address", subject="x", html="x")
    assert r.status_code == 400 and "not a valid email" in r.json()["error"]


def test_labels_star_trash_restore_delete(users):
    alice, *_ = users
    label = alice.post("/api/labels", json={"name": "Work", "color": "#112233"}).json()
    assert alice.post("/api/labels", json={"name": "work"}).status_code == 409   # case-insensitive duplicate
    t = next(t for t in inbox(alice)["threads"] if "Quarterly" in t["subject"])
    key = [t["threadId"]]
    B = lambda action, **kw: alice.post("/api/threads/batch", json={"action": action, "threads": key, "scope": "all", **kw})

    assert B("label", labelId=label["id"]).json()["changed"] >= 1
    assert B("star").status_code == 200
    assert inbox(alice, f"label:{label['id']}")["total"] == 1
    assert inbox(alice, "starred")["total"] == 1
    assert alice.get("/api/counts").json()["labels"][str(label["id"])] >= 0

    B("trash")
    assert inbox(alice, "trash")["total"] == 1 and not any("Quarterly" in x["subject"] for x in inbox(alice, "all")["threads"])
    B_trash = lambda action: alice.post("/api/threads/batch", json={"action": action, "threads": key, "scope": "trash"})
    B_trash("restore")
    assert inbox(alice, "trash")["total"] == 0
    # sent copy returns to Sent, received copy to Inbox
    assert inbox(alice, "sent")["total"] >= 1 and any("Quarterly" in x["subject"] for x in inbox(alice)["threads"])

    B("trash")
    B_trash("delete")
    assert inbox(alice, "trash")["total"] == 0
    assert alice.post("/api/threads/batch", json={"action": "explode", "threads": key}).status_code == 400
    assert alice.post("/api/threads/batch", json={"action": "label", "threads": key, "labelId": 99999}).status_code in (200, 404)


def test_drafts_roundtrip(users):
    _, bob, _ = users
    r = bob.post("/api/drafts", data={"to": "alice@localhost", "subject": "WIP", "html": "<p>draft</p>"},
                 files=[("attachments", ("a.txt", b"hello", "text/plain"))]).json()
    d = bob.get(f"/api/drafts/{r['id']}").json()
    assert d["subject"] == "WIP" and d["attachments"][0]["filename"] == "a.txt"
    assert bob.get("/api/counts").json()["drafts"] == 1
    # re-saving replaces the draft but keeps its attachment
    r2 = bob.post("/api/drafts", data={"draftId": str(r["id"]), "to": "alice@localhost", "subject": "WIP 2", "html": "<p>more</p>",
                                       "keepAttachments": f"[{d['attachments'][0]['id']}]"}).json()
    assert bob.get("/api/counts").json()["drafts"] == 1 and r2["attachments"][0]["filename"] == "a.txt"
    # sending a draft removes it
    assert send(bob, draftId=str(r2["id"]), to="alice@localhost", subject="WIP 2", html="<p>more</p>",
                keepAttachments=f"[{r2['attachments'][0]['id']}]").status_code == 200
    assert bob.get("/api/counts").json()["drafts"] == 0
    assert bob.get(f"/api/drafts/{r2['id']}").status_code == 404


def test_inbound_parsing_inline_and_attachments(users):
    alice, *_ = users
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "Carol <carol@example.com>", "alice@localhost", "Rich mail ✓"
    m["Message-ID"] = "<abc@example.com>"
    m.set_content("plain version")
    m.add_alternative('<p>See <img src="cid:logo1"> <a href="javascript:alert(1)">bad</a> '
                      '<a href="https://ok.example">ok</a><img src="https://t.example/p.gif"></p>', subtype="html")
    m.get_payload()[1].add_related(b"\x89PNG fake", "image", "png", cid="<logo1>", filename="logo.png")
    m.add_attachment(b"%PDF fake", maintype="application", subtype="pdf", filename="invoice.pdf")
    mailcore.deliver_inbound(m.as_bytes(), ["alice@localhost", "alice@localhost", "nobody@localhost"])

    t = next(t for t in inbox(alice)["threads"] if t["subject"] == "Rich mail ✓")
    msgs = alice.get(f"/api/threads/{t['threadId']}").json()["messages"]
    assert len(msgs) == 1                                                  # duplicate recipient -> single copy
    body = msgs[0]
    assert [a["filename"] for a in body["attachments"]] == ["invoice.pdf"]  # inline logo is not listed as an attachment
    assert "/api/attachments/" in body["html"] and "cid:" not in body["html"]
    assert "javascript:" not in body["html"] and 'href="https://ok.example"' in body["html"]
    assert "noopener" in body["html"]


def test_spam_heuristic_and_empty(users):
    alice, *_ = users
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "x@spam.example", "alice@localhost", "You have won a prize"
    m.set_content("claim your prize now")
    mailcore.deliver_inbound(m.as_bytes(), ["alice@localhost"])
    assert inbox(alice, "spam")["total"] == 1
    assert alice.post("/api/folders/spam/empty").json()["deleted"] == 1
    assert alice.post("/api/folders/inbox/empty").status_code == 400


def test_settings_and_password_change(users):
    _, _, eve = users
    assert eve.put("/api/me", json={"name": "Eve E", "signature": "Cheers, Eve"}).json()["signature"] == "Cheers, Eve"
    assert eve.put("/api/me", json={"newPassword": "newpassword1", "currentPassword": "bad"}).status_code == 400
    assert eve.put("/api/me", json={"newPassword": "newpassword1", "currentPassword": PW}).status_code == 200
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"email": "eve", "password": PW}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": "eve", "password": "newpassword1"}).status_code == 200


def test_logout_invalidates_session(users):
    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "bob", "password": PW})
    assert c.get("/api/me").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/me").status_code == 401


def test_html_sanitiser_unit():
    dirty = ('<div style="color:red;position:fixed;background:url(http://x/y)">hi</div>'
             '<img src="/api/threads" onerror="x()"><iframe src="//evil"></iframe><style>*{}</style><a href="data:text/html,x">d</a>')
    clean = mailcore.clean_html(dirty)
    assert "position" not in clean and "url(" not in clean and "onerror" not in clean
    assert "<iframe" not in clean and "<style" not in clean and "data:text" not in clean and 'src="/api' not in clean
    assert "color: red" in clean or "color:red" in clean
