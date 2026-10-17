"""Notion-style workspace. Run: pip install -r requirements.txt && python app.py  ->  http://localhost:5000"""
import hashlib, json, os, re, secrets, sqlite3, time, uuid
from datetime import timedelta
from html import escape
from flask import Flask, Response, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "notion.db")
app = Flask(__name__)
_kf = os.path.join(HERE, ".secret_key")
if os.environ.get("SECRET_KEY"):
    app.secret_key = os.environ["SECRET_KEY"]
else:
    if not os.path.exists(_kf):
        with open(_kf, "w") as f:
            f.write(secrets.token_hex(32))
    app.secret_key = open(_kf).read().strip()
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("HTTPS") == "1",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=30))
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
UP = os.path.join(HERE, "uploads")
COVER = re.compile(r"https?://[^\s\"'()<>]+|/uploads/[\w.\-]+|#[0-9a-fA-F]{3,8}")
FIELDS = ("cover", "title", "icon", "favorite", "trashed", "parent_id", "blocks")
TYPES = {"text", "h1", "h2", "h3", "bullet", "number", "todo", "quote", "code", "callout", "divider", "image", "table", "toggle"}


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def clean_html(s):
    """Keep <b><i><u><strike><code> and http(s) <a>; strip everything else."""
    s = re.sub(r'<a\s[^>]*?href="(https?://[^"<>\s]*)"[^>]*>', '\x00a href="\\1" target="_blank" rel="noopener"\x01', str(s))
    s = s.replace("</a>", "\x00/a\x01")
    s = re.sub(r"<(/?)(b|i|u|strike|code)(?:\s[^>]*)?>", "\x00\\1\\2\x01", s)
    s = re.sub(r"<[^>]*>", "", s)
    return s.replace("\x00", "<").replace("\x01", ">")


def clean_blocks(blocks):
    out = []
    for b in blocks:
        t = b.get("type", "text")
        t = t if t in TYPES else "text"
        nb = {"id": str(b.get("id") or uuid.uuid4().hex[:8]), "type": t,
              "text": clean_html(b.get("text", "")), "checked": bool(b.get("checked", False))}
        try:
            nb["indent"] = max(0, min(4, int(b.get("indent") or 0)))
        except (TypeError, ValueError):
            nb["indent"] = 0
        nb["open"] = b.get("open") is not False
        if t == "image":
            u = str(b.get("url", ""))
            nb["url"] = u if re.match(r"(https?://|/uploads/)", u) else ""
        if t == "table":
            rows = [[re.sub(r"<[^>]*>", "", str(c))[:500] for c in r[:10]]
                    for r in (b.get("rows") or [])[:100] if isinstance(r, list) and r]
            nb["rows"] = rows or [[""]]
        out.append(nb)
    return out


def row(r, full=False):
    d = {k: r[k] for k in ("id", "parent_id", "title", "icon", "favorite", "trashed", "updated", "cover", "share")}
    if full:
        d["blocks"] = json.loads(r["blocks"])
    return d


def owns(pid):
    return bool(pid) and db().execute("SELECT 1 FROM pages WHERE id=? AND owner=?", (pid, g.uid)).fetchone() is not None


def new_page(parent_id=None, title="", icon="📄", blocks=None):
    pid = uuid.uuid4().hex[:10]
    blocks = blocks or [{"id": uuid.uuid4().hex[:8], "type": "text", "text": "", "checked": False}]
    db().execute("INSERT INTO pages(id,parent_id,title,icon,blocks,updated,owner) VALUES(?,?,?,?,?,?,?)",
                 (pid, parent_id, title, icon, json.dumps(blocks), time.time(), g.uid))
    db().commit()
    return pid


def init():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY, parent_id TEXT, title TEXT DEFAULT '',
                 icon TEXT DEFAULT '📄', favorite INT DEFAULT 0, trashed INT DEFAULT 0,
                 blocks TEXT DEFAULT '[]', updated REAL)""")
    for col in ("cover", "share"):
        try:
            c.execute(f"ALTER TABLE pages ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    try:
        c.execute("ALTER TABLE pages ADD COLUMN owner INTEGER")
    except sqlite3.OperationalError:
        pass
    c.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE COLLATE NOCASE, pw TEXT)")
    c.commit()
    c.close()


def seed():
    B = lambda t, x, c=False: {"id": uuid.uuid4().hex[:8], "type": t, "text": x, "checked": c}
    new_page(None, "Welcome", "👋", [B("h2", "Your workspace is ready"),
             B("text", "Type <b>/</b> for blocks, or use shortcuts like <i>#</i>, <i>-</i>, <i>1.</i>, <i>[]</i>, <i>&gt;</i> then space."),
             B("todo", "Create your first page from the sidebar", True), B("todo", "Star a page to pin it to Favorites"),
             B("callout", "Alt+↑ / Alt+↓ moves a block. Tab indents. Ctrl/Cmd+B, I, U, E format text."), B("divider", ""), B("text", "")])


def ver(h):
    return hashlib.sha256(h.encode()).hexdigest()[:16]


def sign_in(uid, pw_hash):
    session.clear()
    session.permanent = True
    session["uid"], session["v"] = uid, ver(pw_hash)


OPEN, FAILS = ("/api/login", "/api/register", "/api/me"), {}


@app.before_request
def auth():
    g.uid = None
    uid = session.get("uid")
    if uid:
        r = db().execute("SELECT pw FROM users WHERE id=?", (uid,)).fetchone()
        if r and session.get("v") == ver(r["pw"]):
            g.uid = uid
        else:
            session.clear()
    if request.path.startswith("/api/") and request.path not in OPEN and not g.uid:
        return jsonify(error="Please sign in"), 401


def creds():
    d = request.get_json(silent=True) or {}
    return str(d.get("username", "")).strip(), str(d.get("password", "")), d


def count_users():
    return db().execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


@app.get("/api/me")
def me():
    r = db().execute("SELECT username FROM users WHERE id=?", (g.uid,)).fetchone() if g.uid else None
    n = count_users()
    return jsonify(user=r["username"] if r else None, first=n == 0, signup=n == 0 or os.environ.get("ALLOW_SIGNUP", "1") != "0")


@app.post("/api/register")
def register():
    u, p, _ = creds()
    n = count_users()
    if n and os.environ.get("ALLOW_SIGNUP", "1") == "0":
        return jsonify(error="Sign-ups are disabled"), 403
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", u):
        return jsonify(error="Username: 3–32 letters, digits, . _ -"), 400
    if not 8 <= len(p) <= 200:
        return jsonify(error="Password must be at least 8 characters"), 400
    h = generate_password_hash(p)
    try:
        uid = db().execute("INSERT INTO users(username,pw) VALUES(?,?)", (u, h)).lastrowid
    except sqlite3.IntegrityError:
        return jsonify(error="That username is taken"), 409
    db().commit()
    g.uid = uid
    if n == 0 and db().execute("SELECT 1 FROM pages WHERE owner IS NULL").fetchone():
        db().execute("UPDATE pages SET owner=? WHERE owner IS NULL", (uid,))  # first account adopts pre-login pages
        db().commit()
    else:
        seed()
    sign_in(uid, h)
    return jsonify(user=u)


@app.post("/api/login")
def login():
    u, p, _ = creds()
    key, now = (request.remote_addr, u.lower()), time.time()
    FAILS[key] = [t for t in FAILS.get(key, []) if now - t < 300]
    if len(FAILS[key]) >= 5:
        return jsonify(error="Too many attempts. Try again in a few minutes."), 429
    r = db().execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
    if not r or not check_password_hash(r["pw"], p):
        FAILS[key].append(now)
        return jsonify(error="Wrong username or password"), 401
    FAILS.pop(key, None)
    sign_in(r["id"], r["pw"])
    return jsonify(user=r["username"])


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/password")
def change_password():
    d = request.get_json(silent=True) or {}
    old, new = str(d.get("old", "")), str(d.get("new", ""))
    r = db().execute("SELECT * FROM users WHERE id=?", (g.uid,)).fetchone()
    if not check_password_hash(r["pw"], old):
        return jsonify(error="Current password is wrong"), 403
    if not 8 <= len(new) <= 200:
        return jsonify(error="New password must be at least 8 characters"), 400
    if new == old:
        return jsonify(error="New password must be different"), 400
    h = generate_password_hash(new)
    db().execute("UPDATE users SET pw=? WHERE id=?", (h, g.uid))
    db().commit()
    sign_in(g.uid, h)  # keeps this device signed in; all other sessions are invalidated
    return jsonify(ok=True)


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.get("/api/pages")
def list_pages():
    return jsonify([row(r) for r in db().execute("SELECT * FROM pages WHERE owner=? ORDER BY updated", (g.uid,))])


@app.post("/api/pages")
def create_page():
    d = request.get_json(silent=True) or {}
    if d.get("parent_id") and not owns(d["parent_id"]):
        return jsonify(error="bad parent"), 400
    tpl = TEMPLATES.get(d.get("template"))
    if tpl:
        pid = new_page(d.get("parent_id"), tpl[0], tpl[1], mk(tpl[2]))
    else:
        pid = new_page(d.get("parent_id"), clean_html(d.get("title", "")), d.get("icon", "📄"))
    return jsonify(row(db().execute("SELECT * FROM pages WHERE id=? AND owner=?", (pid, g.uid)).fetchone(), True))


@app.get("/api/pages/<pid>")
def get_page(pid):
    r = db().execute("SELECT * FROM pages WHERE id=? AND owner=?", (pid, g.uid)).fetchone()
    return (jsonify(row(r, True)) if r else (jsonify(error="not found"), 404))


@app.patch("/api/pages/<pid>")
def patch_page(pid):
    d = request.get_json(silent=True) or {}
    if d.get("parent_id") and (not owns(d["parent_id"]) or d["parent_id"] == pid):
        return jsonify(error="bad parent"), 400
    sets, vals = [], []
    for k in FIELDS:
        if k in d:
            v = d[k]
            if k == "blocks":
                v = json.dumps(clean_blocks(v))
            elif k == "title":
                v = re.sub(r"<[^>]*>", "", str(v))[:300]
            elif k == "cover":
                v = v if COVER.fullmatch(str(v)) else ""
            elif k in ("favorite", "trashed"):
                v = int(bool(v))
            sets.append(f"{k}=?")
            vals.append(v)
    if sets:
        db().execute(f"UPDATE pages SET {','.join(sets)}, updated=? WHERE id=? AND owner=?", (*vals, time.time(), pid, g.uid))
        db().commit()
    return jsonify(ok=True)


@app.delete("/api/pages/<pid>")
def delete_page(pid):
    if not owns(pid):
        return jsonify(error="not found"), 404
    ids, stack = [], [pid]
    while stack:  # delete the page and all descendants
        cur = stack.pop()
        ids.append(cur)
        stack += [r["id"] for r in db().execute("SELECT id FROM pages WHERE parent_id=?", (cur,))]
    db().executemany("DELETE FROM pages WHERE id=?", [(i,) for i in ids])
    db().commit()
    return jsonify(ok=True)


def mk(items):
    out = []
    for t, x in items:
        b = {"id": uuid.uuid4().hex[:8], "type": t, "text": "" if t == "table" else x, "checked": False}
        if t == "table":
            b["rows"] = x
        out.append(b)
    return out


TEMPLATES = {
    "meeting": ("Meeting notes", "🗓️", [("h2", "Agenda"), ("bullet", ""), ("h2", "Notes"), ("text", ""), ("h2", "Action items"), ("todo", "")]),
    "weekly": ("Weekly plan", "📅", [("callout", "Top priority this week"), ("h2", "Goals"), ("todo", ""), ("h2", "Days"), ("toggle", "Monday"), ("toggle", "Tuesday"), ("toggle", "Wednesday")]),
    "project": ("Project tracker", "🚀", [("callout", "One-line goal"), ("h2", "Tasks"), ("table", [["Task", "Owner", "Status"], ["", "", ""], ["", "", ""]]), ("h2", "Notes"), ("text", "")]),
}


def md_inline(s):
    s = re.sub(r'<a href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", s)
    s = re.sub(r"</?code>", "`", s)
    s = re.sub(r"</?b>", "**", s)
    s = re.sub(r"</?i>", "*", s)
    s = re.sub(r"</?strike>", "~~", s)
    s = re.sub(r"</?u>", "", s).replace("<br>", "  \n")
    for a, b in (("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s


def to_markdown(p):
    out, n = [f"# {p['icon']} {p['title'] or 'Untitled'}", ""], 0
    for b in json.loads(p["blocks"]):
        t, x = b["type"], md_inline(b.get("text", ""))
        n = n + 1 if t == "number" else 0
        if t == "table":
            rows = b.get("rows") or [[""]]
            fmt = lambda r: "| " + " | ".join(c.replace("|", "\\|") for c in r) + " |"
            out += [fmt(rows[0]), "|" + " --- |" * len(rows[0])] + [fmt(r) for r in rows[1:]]
        elif t == "image":
            out.append(f"![]({b.get('url', '')})")
        else:
            out.append({"h1": f"## {x}", "h2": f"### {x}", "h3": f"#### {x}", "bullet": f"- {x}",
                        "number": f"{n}. {x}", "todo": f"- [{'x' if b.get('checked') else ' '}] {x}",
                        "quote": f"> {x}", "callout": f"> 💡 {x}", "divider": "---",
                        "code": f"```\n{x}\n```"}.get(t, x))
        out.append("")
    return "\n".join(out)


@app.get("/api/pages/<pid>/export.md")
def export_md(pid):
    r = db().execute("SELECT * FROM pages WHERE id=? AND owner=?", (pid, g.uid)).fetchone()
    if not r:
        return jsonify(error="not found"), 404
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", r["title"]).strip("_") or "page"
    return Response(to_markdown(r), mimetype="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{name}.md"'})


@app.post("/api/pages/<pid>/duplicate")
def duplicate(pid):
    r = db().execute("SELECT * FROM pages WHERE id=? AND owner=?", (pid, g.uid)).fetchone()
    if not r:
        return jsonify(error="not found"), 404
    blocks = json.loads(r["blocks"])
    for b in blocks:
        b["id"] = uuid.uuid4().hex[:8]
    nid = new_page(r["parent_id"], (r["title"] or "Untitled") + " (copy)", r["icon"], blocks)
    return jsonify(row(db().execute("SELECT * FROM pages WHERE id=? AND owner=?", (nid, g.uid)).fetchone(), True))


def to_html(p):
    body, n = [], 0
    for b in json.loads(p["blocks"]):
        t, x = b["type"], b.get("text", "")
        n = n + 1 if t == "number" else 0
        if t == "table":
            rows = b.get("rows") or [[""]]
            h = "".join(f"<tr>{''.join(('<th>' if y == 0 else '<td>') + escape(c) for c in r)}</tr>" for y, r in enumerate(rows))
            h = f"<table>{h}</table>"
        elif t == "image":
            h = f'<img src="{escape(b.get("url", ""))}" alt="">' if b.get("url") else ""
        else:
            h = {"h1": f"<h2>{x}</h2>", "h2": f"<h3>{x}</h3>", "h3": f"<h4>{x}</h4>", "bullet": f"<p>• {x}</p>",
                 "number": f"<p>{n}. {x}</p>", "todo": f"<p>{'☑' if b.get('checked') else '☐'} {x}</p>",
                 "quote": f"<blockquote>{x}</blockquote>", "callout": f"<aside>💡 {x}</aside>", "code": f"<pre>{x}</pre>",
                 "divider": "<hr>", "toggle": f"<p>▸ <b>{x}</b></p>"}.get(t, f"<p>{x}</p>")
        body.append(f'<div style="margin-left:{b.get("indent", 0) * 24}px">{h}</div>')
    cov = p["cover"] or ""
    cv = f'<div class="cv" style="background:{cov if cov.startswith("#") else f"url({chr(34)}{cov}{chr(34)}) center/cover"}"></div>' if cov else ""
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{escape(p['title'] or 'Untitled')}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:740px;margin:0 auto;padding:24px;background:#fff;color:#1f2328}}.cv{{height:180px;margin:-24px -24px 16px}}
img{{max-width:100%;border-radius:6px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:5px 8px;text-align:left}}
aside{{background:#eef3fd;padding:10px 12px;border-radius:6px}}blockquote{{border-left:3px solid #1f2328;margin:0;padding-left:12px}}pre{{background:#f1f3f5;padding:12px;border-radius:6px;overflow:auto}}
code{{background:#f1f3f5;padding:1px 5px;border-radius:4px}}a{{color:#2f5fd0}}@media(prefers-color-scheme:dark){{body{{background:#191b1f;color:#e6e8eb}}td,th{{border-color:#2d3138}}aside{{background:#232b3d}}pre,code{{background:#262a31}}a{{color:#7ea2f4}}}}</style>
{cv}<h1>{escape(p['icon'])} {escape(p['title'] or 'Untitled')}</h1>{''.join(body)}"""


@app.post("/api/pages/<pid>/share")
def share(pid):
    r = db().execute("SELECT share FROM pages WHERE id=? AND owner=?", (pid, g.uid)).fetchone()
    if not r:
        return jsonify(error="not found"), 404
    tok = "" if r["share"] else secrets.token_urlsafe(8)
    db().execute("UPDATE pages SET share=? WHERE id=? AND owner=?", (tok, pid, g.uid))
    db().commit()
    return jsonify(share=tok)


@app.get("/s/<tok>")
def public(tok):
    r = db().execute("SELECT * FROM pages WHERE share=? AND share!='' AND trashed=0", (tok,)).fetchone()
    return Response(to_html(r), mimetype="text/html") if r else ("Not found", 404)


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    ext = os.path.splitext(f.filename or "")[1].lower() if f else ""
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return jsonify(error="Only png, jpg, gif or webp images are supported"), 400
    os.makedirs(UP, exist_ok=True)
    name = uuid.uuid4().hex + ext
    f.save(os.path.join(UP, name))
    return jsonify(url="/uploads/" + name)


@app.get("/uploads/<path:n>")
def uploads(n):
    return send_from_directory(UP, n)


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    like = f"%{q}%"
    rs = db().execute("SELECT * FROM pages WHERE owner=? AND trashed=0 AND (title LIKE ? OR blocks LIKE ?) LIMIT 30", (g.uid, like, like))
    return jsonify([row(r) for r in rs])


init()
if __name__ == "__main__":
    app.run(debug=True, port=5000)
