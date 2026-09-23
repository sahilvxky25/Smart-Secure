"""
Feedback Database — Arduino UNO Q (Linux side)
------------------------------------------------
A tiny Flask app that:
  - Serves a public web form (name, email, message)
  - Writes submissions to a local SQLite database
  - Shows a list of past submissions
  - Includes basic anti-spam: honeypot field + simple rate limiting

Run with:  python3 app.py
Then visit http://<device-ip>:5000  (or your tunnel URL)
"""

import sqlite3
import time
import re
from pathlib import Path
from flask import Flask, request, redirect, url_for, render_template, g, abort

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "feedback.db"
RATE_LIMIT_SECONDS = 30      # min seconds between submissions from same IP
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__)

# very simple in-memory rate limiter: {ip: last_submit_timestamp}
_last_submit = {}


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    rows = db.execute(
        "SELECT name, email, message, created_at FROM entries ORDER BY id DESC LIMIT 100"
    ).fetchall()
    return render_template("index.html", entries=rows, error=None)


@app.route("/submit", methods=["POST"])
def submit():
    db = get_db()

    # --- Honeypot: real users never fill this hidden field ---
    if request.form.get("website"):
        return redirect(url_for("index"))

    # --- Rate limit per IP ---
    ip = request.remote_addr or "unknown"
    now = time.time()
    last = _last_submit.get(ip, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return render_error("You're submitting too fast. Please wait a bit and try again.")
    _last_submit[ip] = now

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    message = (request.form.get("message") or "").strip()

    if not name or not email or not message:
        return render_error("All fields are required.")
    if len(name) > 100 or len(email) > 150 or len(message) > 2000:
        return render_error("One of your fields is too long.")
    if not EMAIL_RE.match(email):
        return render_error("Please enter a valid email address.")

    db.execute(
        "INSERT INTO entries (name, email, message) VALUES (?, ?, ?)",
        (name, email, message),
    )
    db.commit()
    return redirect(url_for("index"))


def render_error(msg):
    db = get_db()
    rows = db.execute(
        "SELECT name, email, message, created_at FROM entries ORDER BY id DESC LIMIT 100"
    ).fetchall()
    return render_template("index.html", entries=rows, error=msg), 400


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    # 0.0.0.0 so it's reachable from other devices / the tunnel
    app.run(host="0.0.0.0", port=5000)
