"""SQLite access: one connection per thread, autocommit, WAL."""
import sqlite3
import threading

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT    NOT NULL,
  email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT    NOT NULL,
  created_at    INTEGER NOT NULL,
  totp_secret   TEXT,
  totp_enabled  INTEGER NOT NULL DEFAULT 0,
  totp_last_step INTEGER,
  session_version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recovery_codes (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash TEXT    NOT NULL,
  used_at   INTEGER,
  UNIQUE (user_id, code_hash)
);

CREATE TABLE IF NOT EXISTS items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parent_id   INTEGER REFERENCES items(id) ON DELETE CASCADE,
  name        TEXT    NOT NULL,
  kind        TEXT    NOT NULL CHECK (kind IN ('file', 'folder')),
  mime        TEXT,
  size        INTEGER NOT NULL DEFAULT 0,
  storage_key TEXT,
  starred     INTEGER NOT NULL DEFAULT 0,
  trashed_at  INTEGER,
  share_token TEXT UNIQUE,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL,
  opened_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_items_parent ON items(parent_id);
CREATE INDEX IF NOT EXISTS idx_items_owner  ON items(owner_id, trashed_at);

CREATE TABLE IF NOT EXISTS shares (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role       TEXT    NOT NULL CHECK (role IN ('viewer', 'editor')),
  created_at INTEGER NOT NULL,
  UNIQUE (item_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_shares_user ON shares(user_id);
"""


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(config.DATA_DIR / "harbor.db", timeout=15, isolation_level=None)
        c.row_factory = _dict_factory
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA foreign_keys = ON")
        _local.conn = c
    return c


def one(sql, params=()):
    return conn().execute(sql, params).fetchone()


def all_(sql, params=()):
    return conn().execute(sql, params).fetchall()


def run(sql, params=()):
    return conn().execute(sql, params)


MIGRATIONS = {  # columns added after the first release: added to older databases on startup
    "totp_secret": "TEXT",
    "totp_enabled": "INTEGER NOT NULL DEFAULT 0",
    "totp_last_step": "INTEGER",
    "session_version": "INTEGER NOT NULL DEFAULT 0",
}


def init():
    c = conn()
    c.executescript(SCHEMA)
    have = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    for col, decl in MIGRATIONS.items():
        if col not in have:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
