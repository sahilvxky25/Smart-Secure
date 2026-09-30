import os
import secrets

from flask import Blueprint, g, jsonify, request

from . import config, db, items
from .files import send_item
from .security import json_body, require_user
from .util import HttpError, clean_name, mime_for, now_ms, to_int

bp = Blueprint("items", __name__, url_prefix="/api/items")
VIEWS = {"drive", "shared", "recent", "starred", "trash", "search"}


@bp.before_request
def _auth():
    require_user()


# ---------------------------------------------------------------- listing
@bp.get("")
@bp.get("/")
def list_items():
    view = request.args.get("view", "drive")
    if view not in VIEWS:
        raise HttpError(400, "Unknown view.")
    parent = None
    if request.args.get("parent"):
        parent = to_int(request.args["parent"])
        if parent is None:
            raise HttpError(400, "Bad folder id.")
    return jsonify(items.list_items(
        g.user, view=view, parent=parent, q=request.args.get("q"), sort=request.args.get("sort"),
        direction=request.args.get("dir"), folders_only=request.args.get("kind") == "folder"))


# ---------------------------------------------------------------- create
@bp.post("/folder")
def create_folder():
    body = json_body()
    name = clean_name(body.get("name"))
    if not name:
        raise HttpError(400, "Enter a valid folder name.")
    owner_id, parent_id = g.user["id"], None
    if body.get("parentId"):
        item, _ = items.require_access(g.user, to_int(body["parentId"]), "editor")
        if item["kind"] != "folder":
            raise HttpError(400, "Choose a folder to create this in.")
        owner_id, parent_id = item["owner_id"], item["id"]
    resp = jsonify({"item": items.to_json(items.create_folder(owner_id, parent_id, name), g.user["id"])})
    resp.status_code = 201
    return resp


@bp.post("/upload")
def upload():
    owner_id, parent_id = g.user["id"], None
    raw = request.args.get("parentId")
    if raw and raw != "root":
        item, _ = items.require_access(g.user, to_int(raw), "editor")
        if item["kind"] != "folder":
            raise HttpError(400, "Choose a folder to upload into.")
        owner_id, parent_id = item["owner_id"], item["id"]
    declared = request.content_length or 0
    if items.used_bytes(owner_id) + declared > config.QUOTA_BYTES:
        raise HttpError(413, "Not enough storage space for this upload.")

    files = request.files.getlist("files")
    if len(files) > config.MAX_FILES_PER_UPLOAD:
        _discard(files)
        raise HttpError(413, "Too many files in one upload.")

    user_dir = config.UPLOAD_DIR / str(owner_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    used = items.used_bytes(owner_id)
    created, rejected = [], []
    try:
        for f in files:
            name = clean_name(f.filename or "") or "Untitled"
            tmp = f.stream
            tmp.flush()
            size = os.path.getsize(tmp.name)
            if used + size > config.QUOTA_BYTES:
                rejected.append(name)
                continue
            key = secrets.token_hex(16)
            os.replace(tmp.name, user_dir / key)
            used += size
            record = items.create_file(owner_id, parent_id, name, mime_for(name, f.mimetype), size, f"{owner_id}/{key}")
            created.append(items.to_json(record, g.user["id"]))
    finally:
        _discard(files)
    if not created and rejected:
        raise HttpError(413, "Not enough storage space for this upload.")
    resp = jsonify({"items": created, "rejected": rejected})
    resp.status_code = 201
    return resp


def _discard(files):
    """Close upload streams and remove any temp files that weren't moved into place."""
    for f in files:
        try:
            f.stream.close()
        except Exception:
            pass
        try:
            os.unlink(f.stream.name)
        except (OSError, AttributeError):
            pass


# ---------------------------------------------------------------- read
@bp.get("/<int:item_id>/download")
def download(item_id):
    item, access = items.require_access(g.user, item_id, "viewer")
    if access == "owner" and item["kind"] == "file":
        db.run("UPDATE items SET opened_at = ? WHERE id = ?", (now_ms(), item["id"]))
    return send_item(item, inline=request.args.get("inline") == "1")


# ---------------------------------------------------------------- update
@bp.patch("/<int:item_id>")
def update(item_id):
    item, access = items.require_access(g.user, item_id, "editor")
    if item["trashed_at"]:
        raise HttpError(409, "Restore this item before changing it.")
    body = json_body()
    if ("starred" in body or "parentId" in body) and access != "owner":
        raise HttpError(403, "Only the owner can do that.")

    if "name" in body:
        clean = clean_name(body["name"])
        if not clean:
            raise HttpError(400, "Enter a valid name.")
        db.run("UPDATE items SET name = ?, updated_at = ? WHERE id = ?", (clean, now_ms(), item["id"]))
    if "starred" in body:
        db.run("UPDATE items SET starred = ? WHERE id = ?", (1 if body["starred"] else 0, item["id"]))
    if "parentId" in body:
        target = None
        if body["parentId"] is not None:
            target = items.get_item(to_int(body["parentId"]))
            if (not target or target["owner_id"] != g.user["id"] or target["kind"] != "folder" or target["trashed_at"]):
                raise HttpError(400, "Choose a folder in My Drive.")
            if target["id"] == item["id"] or items.is_descendant(item["id"], target):
                raise HttpError(400, "A folder can't be moved into itself.")
        db.run("UPDATE items SET parent_id = ? WHERE id = ?", (target["id"] if target else None, item["id"]))
    return jsonify({"item": items.to_json(items.get_item(item["id"]), g.user["id"])})


# ---------------------------------------------------------------- trash
@bp.post("/empty-trash")
def empty_trash():
    roots = items.trash_roots(g.user["id"])
    for item_id in roots:
        items.purge(item_id)
    return jsonify({"removed": len(roots)})


@bp.post("/<int:item_id>/restore")
def restore(item_id):
    item, _ = items.require_access(g.user, item_id, "owner")
    if not item["trashed_at"]:
        raise HttpError(409, "This item isn't in the trash.")
    items.restore(item)
    return jsonify({"item": items.to_json(items.get_item(item["id"]), g.user["id"])})


@bp.delete("/<int:item_id>")
def delete(item_id):
    item, _ = items.require_access(g.user, item_id, "owner")
    if request.args.get("permanent") == "1":
        if not item["trashed_at"]:
            raise HttpError(409, "Move this item to the trash first.")
        items.purge(item["id"])
    elif not item["trashed_at"]:
        items.trash(item["id"])
    return jsonify({"ok": True})
