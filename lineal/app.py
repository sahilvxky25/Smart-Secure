"""Lineal backend – Flask + SQLite. Accounts, sessions, change password, issues API."""
import json, os, re, sqlite3, time, uuid
from collections import defaultdict
from functools import wraps

import jwt
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

SECRET = os.environ.get("JWT_SECRET", "")
if len(SECRET) < 16:
    raise SystemExit("Set JWT_SECRET to a random string of 16+ characters")
PROD = os.environ.get("APP_ENV") == "production"      # enables Secure cookies (needs HTTPS)
INVITE = os.environ.get("INVITE_CODE")                # if set, sign-up requires it
DB_PATH = os.environ.get("DB_PATH", "lineal.db")
DUMMY_HASH = generate_password_hash("not-a-real-password")

app = Flask(__name__, static_folder="public", static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)   # correct client IP behind Render/Railway
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024

# ---------- database ----------
def init_db():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, hash TEXT, tv INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS issues(id TEXT PRIMARY KEY, num INTEGER, data TEXT);""")
    c.commit(); c.close()
init_db()

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10)   # autocommit; BEGIN explicit
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

# ---------- helpers ----------
def body():
    b = request.get_json(silent=True)
    return b if isinstance(b, dict) else {}

def pub(u):
    return {"id": str(u["id"]), "name": u["name"], "email": u["email"]}

def err(msg, code=400):
    return jsonify(error=msg), code

def ok_password(p):
    return isinstance(p, str) and 8 <= len(p) <= 128

_tries = defaultdict(list)
def limited(f):
    """10 attempts per 15 minutes per IP (in-memory; run gunicorn with 1 worker)."""
    @wraps(f)
    def wrapper(*a, **k):
        now, ip = time.time(), request.remote_addr
        _tries[ip] = t = [x for x in _tries[ip] if now - x < 900]
        if len(t) >= 10:
            return err("Too many attempts. Try again in 15 minutes.", 429)
        t.append(now)
        return f(*a, **k)
    return wrapper

def start_session(resp, uid, tv):
    token = jwt.encode({"uid": uid, "tv": tv, "exp": int(time.time()) + 7 * 86400}, SECRET, algorithm="HS256")
    resp.set_cookie("tk", token, httponly=True, samesite="Lax", secure=PROD, max_age=7 * 86400)
    return resp

def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        try:
            p = jwt.decode(request.cookies.get("tk", ""), SECRET, algorithms=["HS256"])
            u = db().execute("SELECT * FROM users WHERE id=?", (p["uid"],)).fetchone()
            if not u or u["tv"] != p["tv"]:      # tv changes on password change → old sessions die
                raise ValueError
        except Exception:
            return err("auth", 401)
        g.user = u
        return f(*a, **k)
    return wrapper

# ---------- auth ----------
@app.post("/api/register")
@limited
def register():
    b = body()
    if INVITE and b.get("invite") != INVITE:
        return err("Invalid invite code", 403)
    name, email = str(b.get("name") or "").strip()[:60], str(b.get("email") or "").strip().lower()
    if not name or not re.fullmatch(r"\S+@\S+\.\S+", email):
        return err("Enter your name and a valid email")
    if not ok_password(b.get("password")):
        return err("Password must be 8–128 characters")
    try:
        cur = db().execute("INSERT INTO users(name,email,hash) VALUES(?,?,?)",
                           (name, email, generate_password_hash(b["password"])))
    except sqlite3.IntegrityError:
        return err("Email already registered", 409)
    u = db().execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return start_session(jsonify(pub(u)), u["id"], u["tv"])

@app.post("/api/login")
@limited
def login():
    b = body()
    u = db().execute("SELECT * FROM users WHERE email=?", (str(b.get("email") or "").strip().lower(),)).fetchone()
    good = check_password_hash(u["hash"] if u else DUMMY_HASH, str(b.get("password") or ""))  # constant-ish time
    if not u or not good:
        return err("Wrong email or password", 401)
    return start_session(jsonify(pub(u)), u["id"], u["tv"])

@app.post("/api/logout")
def logout():
    resp = jsonify(ok=True)
    resp.delete_cookie("tk")
    return resp

@app.get("/api/me")
@login_required
def me():
    return jsonify(pub(g.user))

@app.post("/api/change-password")
@login_required
@limited
def change_password():
    b, u = body(), g.user
    cur, new = str(b.get("current") or ""), b.get("next")
    if not check_password_hash(u["hash"], cur):
        return err("Current password is incorrect")
    if not ok_password(new):
        return err("New password must be 8–128 characters")
    if new == cur:
        return err("New password must differ from the current one")
    db().execute("UPDATE users SET hash=?, tv=tv+1 WHERE id=?", (generate_password_hash(new), u["id"]))
    return start_session(jsonify(ok=True), u["id"], u["tv"] + 1)   # this device stays signed in

@app.get("/api/users")
@login_required
def users():
    return jsonify([pub(r) for r in db().execute("SELECT id,name,email FROM users")])

# ---------- issues ----------
def clean(b):
    def s(k, n, d=""):
        return str(b.get(k) or d)[:n]
    def i(k, d=0):
        try: return int(b.get(k) or d)
        except (TypeError, ValueError): return d
    comments = b.get("comments") if isinstance(b.get("comments"), list) else []
    return {
        "title": s("title", 300), "desc": s("desc", 20000), "status": s("status", 20, "todo"),
        "priority": min(4, max(0, i("priority"))), "label": s("label", 40), "project": s("project", 40),
        "assignee": s("assignee", 20), "created": i("created") or int(time.time() * 1000),
        "comments": [{"t": str(c.get("t") or "")[:5000], "by": str(c.get("by") or "")[:20],
                      "at": int(c.get("at") or time.time() * 1000)}
                     for c in comments[-500:] if isinstance(c, dict)],
    }

@app.get("/api/issues")
@login_required
def list_issues():
    return jsonify([{"id": r["id"], "num": r["num"], **json.loads(r["data"])}
                    for r in db().execute("SELECT * FROM issues")])

@app.post("/api/issues")
@login_required
def create_issue():
    b = body()
    iid = b.get("id") if re.fullmatch(r"[\w-]{1,40}", str(b.get("id") or "")) else str(uuid.uuid4())
    c = db()
    c.execute("BEGIN IMMEDIATE")                       # serialise numbering so LIN-numbers never collide
    num = (c.execute("SELECT MAX(num) FROM issues").fetchone()[0] or 0) + 1
    c.execute("INSERT OR IGNORE INTO issues(id,num,data) VALUES(?,?,?)", (iid, num, json.dumps(clean(b))))
    c.execute("COMMIT")
    return jsonify(id=iid, num=c.execute("SELECT num FROM issues WHERE id=?", (iid,)).fetchone()[0])

@app.put("/api/issues/<iid>")
@login_required
def update_issue(iid):
    db().execute("UPDATE issues SET data=? WHERE id=?", (json.dumps(clean(body())), iid))
    return jsonify(ok=True)

@app.delete("/api/issues/<iid>")
@login_required
def delete_issue(iid):
    db().execute("DELETE FROM issues WHERE id=?", (iid,))
    return jsonify(ok=True)

@app.get("/")
def index():
    return send_from_directory("public", "index.html")

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 8000)))
