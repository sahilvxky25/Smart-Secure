"""SQLite access: one connection per thread, autocommit, explicit transactions."""
import sqlite3
import threading
from contextlib import contextmanager

from .config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  signature TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);

-- One row per mailbox copy: every recipient (and the sender) owns their own copy.
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  thread_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  in_reply_to TEXT,
  refs TEXT,
  folder TEXT NOT NULL DEFAULT 'inbox',      -- inbox | sent | drafts | spam | trash | archive
  orig_folder TEXT,                          -- where a trashed message goes back to
  from_addr TEXT NOT NULL,
  from_name TEXT NOT NULL DEFAULT '',
  to_addrs TEXT NOT NULL DEFAULT '[]',       -- JSON [{name,address}]
  cc_addrs TEXT NOT NULL DEFAULT '[]',
  bcc_addrs TEXT NOT NULL DEFAULT '[]',
  subject TEXT NOT NULL DEFAULT '',
  body_text TEXT NOT NULL DEFAULT '',
  body_html TEXT NOT NULL DEFAULT '',
  snippet TEXT NOT NULL DEFAULT '',
  date INTEGER NOT NULL,
  is_read INTEGER NOT NULL DEFAULT 0,
  is_starred INTEGER NOT NULL DEFAULT 0,
  has_attachments INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_owner_folder ON messages(owner_id, folder, date DESC);
CREATE INDEX IF NOT EXISTS idx_msg_owner_thread ON messages(owner_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_msg_owner_msgid ON messages(owner_id, message_id);

CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  cid TEXT,
  data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_att_msg ON attachments(message_id);

CREATE TABLE IF NOT EXISTS labels (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT '#0f766e',
  UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS message_labels (
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  label_id INTEGER NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
  PRIMARY KEY (message_id, label_id)
);
"""

_local = threading.local()


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        config.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(config.db_path, isolation_level=None, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA busy_timeout = 10000")
        _local.conn = c
    return c


def init_db() -> None:
    conn().executescript(SCHEMA)


def one(sql: str, *params):
    return conn().execute(sql, params).fetchone()


def all_(sql: str, *params):
    return conn().execute(sql, params).fetchall()


def run(sql: str, *params) -> sqlite3.Cursor:
    return conn().execute(sql, params)


@contextmanager
def tx():
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
