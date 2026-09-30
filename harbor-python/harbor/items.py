"""Item tree, permissions and listing logic (files and folders)."""
import os

from . import config, db
from .util import HttpError, now_ms

SELECT = """
  SELECT i.*, u.name AS owner_name, u.email AS owner_email,
         (SELECT COUNT(*) FROM shares s WHERE s.item_id = i.id) AS share_count
  FROM items i JOIN users u ON u.id = i.owner_id"""

DESCENDANTS = """WITH RECURSIVE d(id) AS (
  SELECT id FROM items WHERE id = :id
  UNION ALL SELECT i.id FROM items i JOIN d ON i.parent_id = d.id)"""

RANK = {"viewer": 1, "editor": 2, "owner": 3}


def get_item(item_id):
    if not isinstance(item_id, int):
        return None
    return db.one(f"{SELECT} WHERE i.id = ?", (item_id,))


def get_raw(item_id):
    return db.one("SELECT * FROM items WHERE id = ?", (item_id,))


def chain(item):
    """Items from the root down to (and including) the given item."""
    out, seen, cur = [], set(), item
    while cur and cur["id"] not in seen:
        seen.add(cur["id"])
        out.insert(0, cur)
        cur = get_raw(cur["parent_id"]) if cur["parent_id"] else None
    return out


def _share(item_id, user_id):
    return db.one("SELECT role FROM shares WHERE item_id = ? AND user_id = ?", (item_id, user_id))


def access_for(user_id, item):
    """'owner' | 'editor' | 'viewer' | None. Sharing is inherited from parent folders."""
    if not item:
        return None
    if item["owner_id"] == user_id:
        return "owner"
    if item["trashed_at"]:
        return None
    role = None
    for node in chain(item):
        share = _share(node["id"], user_id)
        if share:
            if share["role"] == "editor":
                return "editor"
            role = "viewer"
    return role


def is_within(root_id, item):
    """Is `item` the public-link root, or inside it?"""
    if not item or item["trashed_at"]:
        return False
    return any(n["id"] == root_id for n in chain(item))


def require_access(user, item_id, need="viewer"):
    """Loads an item and checks the user has at least `need`. 404 hides items the user can't see."""
    item = get_item(item_id)
    access = access_for(user["id"], item)
    if not access:
        raise HttpError(404, "Item not found.")
    if RANK[access] < RANK[need]:
        raise HttpError(403, "You don't have permission to do that.")
    return item, access


def to_json(i, user_id):
    mine = i["owner_id"] == user_id
    return {
        "id": i["id"], "name": i["name"], "kind": i["kind"], "mime": i["mime"], "size": i["size"],
        "parentId": i["parent_id"], "starred": bool(i["starred"]), "trashedAt": i["trashed_at"],
        "createdAt": i["created_at"], "updatedAt": i["updated_at"], "openedAt": i["opened_at"],
        "owner": {"id": i["owner_id"], "name": i["owner_name"], "email": i["owner_email"], "me": mine},
        "shared": i["share_count"] > 0 or bool(i["share_token"]),
        "linkEnabled": bool(i["share_token"]) if mine else False,
    }


def breadcrumb(folder, user_id):
    nodes = chain(folder)
    if folder["owner_id"] != user_id:
        # Shared users only see the path from the folder that was shared with them.
        start = next((k for k, n in enumerate(nodes) if _share(n["id"], user_id)), -1)
        nodes = nodes[start:] if start >= 0 else [folder]
    return [{"id": n["id"], "name": n["name"]} for n in nodes]


SORTS = {"name": "i.name COLLATE NOCASE", "modified": "i.updated_at", "size": "i.size"}


def order_by(sort, direction):
    col = SORTS.get(sort, SORTS["name"])
    d = "DESC" if direction == "desc" else "ASC"
    return f"ORDER BY (i.kind = 'folder') DESC, {col} {d}, i.name COLLATE NOCASE ASC"


def list_children(parent_id, order, folders_only=False):
    kind = "AND i.kind = 'folder'" if folders_only else ""
    return db.all_(f"{SELECT} WHERE i.parent_id = ? AND i.trashed_at IS NULL {kind} {order}", (parent_id,))


def list_items(user, view="drive", parent=None, q=None, sort=None, direction=None, folders_only=False):
    uid = user["id"]
    order = order_by(sort, direction)
    rows, folder, access, crumbs = [], None, "owner", []

    if view in ("drive", "shared") and parent:
        item, access = require_access(user, parent, "viewer")
        if item["kind"] != "folder" or item["trashed_at"]:
            raise HttpError(404, "Folder not found.")
        rows = list_children(item["id"], order, folders_only)
        folder = {"id": item["id"], "name": item["name"], "parentId": item["parent_id"]}
        crumbs = breadcrumb(item, uid)
    elif view == "drive":
        kind = "AND i.kind = 'folder'" if folders_only else ""
        rows = db.all_(f"{SELECT} WHERE i.owner_id = ? AND i.parent_id IS NULL AND i.trashed_at IS NULL {kind} {order}", (uid,))
    elif view == "shared":
        rows = db.all_(f"{SELECT} JOIN shares s ON s.item_id = i.id WHERE s.user_id = ? AND i.trashed_at IS NULL {order}", (uid,))
        access = "viewer"
    elif view == "recent":
        rows = db.all_(f"""{SELECT} WHERE i.owner_id = ? AND i.kind = 'file' AND i.trashed_at IS NULL
                           ORDER BY COALESCE(i.opened_at, i.updated_at) DESC LIMIT 60""", (uid,))
    elif view == "starred":
        rows = db.all_(f"{SELECT} WHERE i.owner_id = ? AND i.starred = 1 AND i.trashed_at IS NULL {order}", (uid,))
    elif view == "trash":
        rows = db.all_(f"""{SELECT} WHERE i.owner_id = ? AND i.trashed_at IS NOT NULL
                           AND NOT EXISTS (SELECT 1 FROM items p WHERE p.id = i.parent_id AND p.trashed_at = i.trashed_at)
                           ORDER BY i.trashed_at DESC""", (uid,))
    elif view == "search":
        term = str(q or "").strip()
        if term:
            like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = db.all_(f"""{SELECT} WHERE i.owner_id = ? AND i.trashed_at IS NULL AND i.name LIKE ? ESCAPE '\\'
                               {order} LIMIT 200""", (uid, like))
    else:
        raise HttpError(400, "Unknown view.")
    return {"items": [to_json(r, uid) for r in rows], "folder": folder, "path": crumbs, "access": access}


# ---------------------------------------------------------------- mutations

def create_folder(owner_id, parent_id, name):
    ts = now_ms()
    cur = db.run("""INSERT INTO items (owner_id, parent_id, name, kind, size, created_at, updated_at)
                    VALUES (?, ?, ?, 'folder', 0, ?, ?)""", (owner_id, parent_id, name, ts, ts))
    return get_item(cur.lastrowid)


def create_file(owner_id, parent_id, name, mime, size, storage_key):
    ts = now_ms()
    cur = db.run("""INSERT INTO items (owner_id, parent_id, name, kind, mime, size, storage_key, created_at, updated_at)
                    VALUES (?, ?, ?, 'file', ?, ?, ?, ?, ?)""", (owner_id, parent_id, name, mime, size, storage_key, ts, ts))
    return get_item(cur.lastrowid)


def trash(item_id):
    db.run(f"{DESCENDANTS} UPDATE items SET trashed_at = :ts WHERE id IN (SELECT id FROM d)",
           {"id": item_id, "ts": now_ms()})


def restore(item):
    parent = get_raw(item["parent_id"]) if item["parent_id"] else None
    parent_id = parent["id"] if parent and not parent["trashed_at"] else None
    c = db.conn()
    c.execute("BEGIN")
    try:
        c.execute(f"{DESCENDANTS} UPDATE items SET trashed_at = NULL WHERE id IN (SELECT id FROM d) AND trashed_at = :ts",
                  {"id": item["id"], "ts": item["trashed_at"]})
        c.execute("UPDATE items SET parent_id = ?, updated_at = ? WHERE id = ?", (parent_id, now_ms(), item["id"]))
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise


def purge(item_id):
    """Deletes an item, everything inside it, and the stored bytes."""
    keys = [r["storage_key"] for r in db.all_(
        f"{DESCENDANTS} SELECT storage_key FROM items WHERE id IN (SELECT id FROM d) AND storage_key IS NOT NULL",
        {"id": item_id})]
    db.run("DELETE FROM items WHERE id = ?", (item_id,))
    for key in keys:
        try:
            os.unlink(config.UPLOAD_DIR / key)
        except OSError:
            pass


def trash_roots(owner_id, older_than=None):
    cutoff = older_than if older_than is not None else 2**62
    return [r["id"] for r in db.all_("""SELECT i.id FROM items i WHERE i.owner_id = ? AND i.trashed_at IS NOT NULL
        AND i.trashed_at < ?
        AND NOT EXISTS (SELECT 1 FROM items p WHERE p.id = i.parent_id AND p.trashed_at = i.trashed_at)""",
        (owner_id, cutoff))]


def purge_expired_trash(days):
    cutoff = now_ms() - days * 86_400_000
    owners = db.all_("SELECT DISTINCT owner_id FROM items WHERE trashed_at IS NOT NULL AND trashed_at < ?", (cutoff,))
    n = 0
    for o in owners:
        for item_id in trash_roots(o["owner_id"], cutoff):
            purge(item_id)
            n += 1
    return n


def is_descendant(ancestor_id, item):
    return any(n["id"] == ancestor_id for n in chain(item))


def used_bytes(owner_id):
    return db.one("SELECT COALESCE(SUM(size), 0) AS used FROM items WHERE owner_id = ? AND kind = 'file'", (owner_id,))["used"]
