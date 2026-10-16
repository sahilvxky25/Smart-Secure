"""Google Tasks clone: Flask + SQLite. Run: python app.py  ->  http://localhost:5000"""
import os, re, secrets, sqlite3
from datetime import date, timedelta
from functools import wraps
from flask import Flask, g, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "tasks.db")
KEY = os.path.join(BASE, ".secret_key")
if not os.path.exists(KEY):
    open(KEY, "w").write(secrets.token_hex(32))

app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="")
app.secret_key = open(KEY).read()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lists(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, pos REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, list_id INTEGER NOT NULL,
  parent_id INTEGER, title TEXT NOT NULL, details TEXT DEFAULT '', due TEXT, starred INTEGER DEFAULT 0,
  done INTEGER DEFAULT 0, repeat TEXT DEFAULT '', pos REAL DEFAULT 0, completed_at TEXT);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def init():
    with sqlite3.connect(DB) as c: c.executescript(SCHEMA)

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session: return jsonify(error="Not signed in"), 401
        return f(*a, **k)
    return w

def err(msg, code=400): return jsonify(error=msg), code
def rows(q, *a): return [dict(r) for r in db().execute(q, a).fetchall()]
def one(q, *a): return db().execute(q, a).fetchone()

# ---------- auth ----------
def valid_pw(p): return isinstance(p, str) and len(p) >= 8

@app.post("/api/register")
def register():
    d = request.get_json(force=True); email = (d.get("email") or "").strip().lower(); pw = d.get("password")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email): return err("Enter a valid email address")
    if not valid_pw(pw): return err("Password must be at least 8 characters")
    if one("SELECT 1 FROM users WHERE email=?", email): return err("That email is already registered", 409)
    cur = db().execute("INSERT INTO users(email,pw) VALUES(?,?)", (email, generate_password_hash(pw)))
    db().execute("INSERT INTO lists(user_id,title) VALUES(?,?)", (cur.lastrowid, "My Tasks"))
    db().commit()
    session.clear(); session["uid"] = cur.lastrowid; session["email"] = email
    return jsonify(email=email)

@app.post("/api/login")
def login():
    d = request.get_json(force=True); email = (d.get("email") or "").strip().lower()
    u = one("SELECT * FROM users WHERE email=?", email)
    if not u or not check_password_hash(u["pw"], d.get("password") or ""): return err("Wrong email or password", 401)
    session.clear(); session["uid"] = u["id"]; session["email"] = email
    return jsonify(email=email)

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=True)

@app.get("/api/me")
def me(): return jsonify(email=session.get("email")) if "uid" in session else err("Not signed in", 401)

@app.post("/api/password")
@login_required
def change_password():
    d = request.get_json(force=True); u = one("SELECT * FROM users WHERE id=?", session["uid"])
    if not check_password_hash(u["pw"], d.get("old") or ""): return err("Current password is incorrect", 403)
    if not valid_pw(d.get("new")): return err("New password must be at least 8 characters")
    if d["new"] == d["old"]: return err("New password must differ from the current one")
    db().execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(d["new"]), u["id"])); db().commit()
    return jsonify(ok=True)

# ---------- lists ----------
@app.get("/api/lists")
@login_required
def get_lists():
    return jsonify(rows("SELECT * FROM lists WHERE user_id=? ORDER BY pos,id", session["uid"]))

@app.post("/api/lists")
@login_required
def add_list():
    t = (request.get_json(force=True).get("title") or "").strip()
    if not t: return err("List name is required")
    cur = db().execute("INSERT INTO lists(user_id,title,pos) VALUES(?,?,(SELECT IFNULL(MAX(pos),0)+1 FROM lists WHERE user_id=?))", (session["uid"], t, session["uid"]))
    db().commit()
    return jsonify(dict(one("SELECT * FROM lists WHERE id=?", cur.lastrowid)))

def own_list(i): return one("SELECT * FROM lists WHERE id=? AND user_id=?", i, session["uid"])

@app.patch("/api/lists/<int:i>")
@login_required
def rename_list(i):
    t = (request.get_json(force=True).get("title") or "").strip()
    if not own_list(i): return err("Not found", 404)
    if not t: return err("List name is required")
    db().execute("UPDATE lists SET title=? WHERE id=?", (t, i)); db().commit(); return jsonify(ok=True)

@app.delete("/api/lists/<int:i>")
@login_required
def del_list(i):
    if not own_list(i): return err("Not found", 404)
    if one("SELECT COUNT(*) c FROM lists WHERE user_id=?", session["uid"])["c"] <= 1: return err("You need at least one list")
    db().execute("DELETE FROM tasks WHERE list_id=?", (i,)); db().execute("DELETE FROM lists WHERE id=?", (i,)); db().commit()
    return jsonify(ok=True)

@app.post("/api/lists/<int:i>/clear")
@login_required
def clear_done(i):
    if not own_list(i): return err("Not found", 404)
    db().execute("DELETE FROM tasks WHERE list_id=? AND done=1", (i,)); db().commit(); return jsonify(ok=True)

# ---------- tasks ----------
@app.get("/api/tasks")
@login_required
def get_tasks():
    q, a = "SELECT * FROM tasks WHERE user_id=?", [session["uid"]]
    if request.args.get("list"): q += " AND list_id=?"; a.append(int(request.args["list"]))
    if request.args.get("starred"): q += " AND starred=1"
    return jsonify(rows(q + " ORDER BY pos,id", *a))

@app.post("/api/tasks")
@login_required
def add_task():
    d = request.get_json(force=True); t = (d.get("title") or "").strip()
    if not t: return err("Title is required")
    if not own_list(d.get("list_id")): return err("List not found", 404)
    pid = d.get("parent_id")
    if pid:
        p = one("SELECT * FROM tasks WHERE id=? AND user_id=?", pid, session["uid"])
        if not p or p["parent_id"]: return err("Subtasks can only be one level deep")
    cur = db().execute("""INSERT INTO tasks(user_id,list_id,parent_id,title,details,due,starred,repeat,pos)
      VALUES(?,?,?,?,?,?,?,?,(SELECT IFNULL(MAX(pos),0)+1 FROM tasks WHERE list_id=?))""",
      (session["uid"], d["list_id"], pid, t, d.get("details", ""), d.get("due") or None, int(bool(d.get("starred"))), d.get("repeat", ""), d["list_id"]))
    db().commit()
    return jsonify(dict(one("SELECT * FROM tasks WHERE id=?", cur.lastrowid)))

def advance(due, rule):
    d = date.fromisoformat(due) if due else date.today()
    if rule == "daily": return d + timedelta(days=1)
    if rule == "weekly": return d + timedelta(weeks=1)
    y, m = (d.year + (rule == "yearly"), d.month + (rule == "monthly"))
    if m > 12: y, m = y + 1, 1
    while True:
        try: return d.replace(year=y, month=m)
        except ValueError: d -= timedelta(days=1)

@app.patch("/api/tasks/<int:i>")
@login_required
def patch_task(i):
    t = one("SELECT * FROM tasks WHERE id=? AND user_id=?", i, session["uid"])
    if not t: return err("Not found", 404)
    d = request.get_json(force=True); sets, vals = [], []
    for k in ("title", "details", "due", "starred", "done", "repeat"):
        if k in d:
            v = d[k]
            if k == "title": v = (v or "").strip(); 
            if k == "title" and not v: return err("Title is required")
            if k in ("starred", "done"): v = int(bool(v))
            if k == "due": v = v or None
            sets.append(f"{k}=?"); vals.append(v)
    if "done" in d:
        sets.append("completed_at=?"); vals.append(date.today().isoformat() if d["done"] else None)
    if "list_id" in d and d["list_id"] != t["list_id"]:
        if not own_list(d["list_id"]): return err("List not found", 404)
        for tid in [i] + [r["id"] for r in rows("SELECT id FROM tasks WHERE parent_id=?", i)]:
            db().execute("UPDATE tasks SET list_id=? WHERE id=?", (d["list_id"], tid))
        if t["parent_id"]: sets.append("parent_id=NULL")
    if sets: db().execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals + [i])
    # completing a parent completes its subtasks; repeating tasks spawn the next occurrence
    if d.get("done") and not t["done"]:
        db().execute("UPDATE tasks SET done=1, completed_at=? WHERE parent_id=?", (date.today().isoformat(), i))
        if t["repeat"] and not t["parent_id"]:
            db().execute("""INSERT INTO tasks(user_id,list_id,title,details,due,starred,repeat,pos)
              VALUES(?,?,?,?,?,?,?,?)""", (t["user_id"], t["list_id"], t["title"], t["details"], advance(t["due"], t["repeat"]).isoformat(), t["starred"], t["repeat"], t["pos"]))
    db().commit()
    return jsonify(ok=True)

@app.delete("/api/tasks/<int:i>")
@login_required
def del_task(i):
    db().execute("DELETE FROM tasks WHERE (id=? OR parent_id=?) AND user_id=?", (i, i, session["uid"])); db().commit()
    return jsonify(ok=True)

@app.post("/api/tasks/reorder")
@login_required
def reorder():
    for n, i in enumerate(request.get_json(force=True).get("ids", [])):
        db().execute("UPDATE tasks SET pos=? WHERE id=? AND user_id=?", (n, i, session["uid"]))
    db().commit(); return jsonify(ok=True)

@app.get("/")
def index():
    # Works whether index.html is in ./static/ (recommended) or next to app.py
    for folder in (os.path.join(BASE, "static"), BASE):
        if os.path.exists(os.path.join(folder, "index.html")):
            return send_from_directory(folder, "index.html")
    return "index.html not found. Put it in a 'static' folder next to app.py.", 404

init()
if __name__ == "__main__":
    app.run(debug=False, port=5000)
