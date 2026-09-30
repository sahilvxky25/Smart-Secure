from flask import Blueprint, jsonify, request

from . import db, items
from .files import send_item
from .util import HttpError, to_int

bp = Blueprint("public", __name__, url_prefix="/api/public")

SELECT_BY_TOKEN = """
  SELECT i.*, u.name AS owner_name, u.email AS owner_email, 0 AS share_count
  FROM items i JOIN users u ON u.id = i.owner_id WHERE i.share_token = ? AND i.trashed_at IS NULL"""


def root_for(token):
    root = db.one(SELECT_BY_TOKEN, (token,))
    if not root:
        raise HttpError(404, "This link doesn't work. It may have been turned off or the item deleted.")
    return root


def pub(i):
    return {"id": i["id"], "name": i["name"], "kind": i["kind"], "mime": i["mime"], "size": i["size"],
            "updatedAt": i["updated_at"]}


@bp.get("/<token>")
def view(token):
    root = root_for(token)
    current = root
    folder = request.args.get("folder")
    if folder and to_int(folder) != root["id"]:
        candidate = items.get_item(to_int(folder))
        if not candidate or candidate["kind"] != "folder" or not items.is_within(root["id"], candidate):
            raise HttpError(404, "Folder not found.")
        current = candidate
    nodes = items.chain(current)
    start = next(k for k, n in enumerate(nodes) if n["id"] == root["id"])
    path = [{"id": n["id"], "name": n["name"]} for n in nodes[start:]]
    children = (items.list_children(current["id"], "ORDER BY (i.kind = 'folder') DESC, i.name COLLATE NOCASE")
                if current["kind"] == "folder" else [])
    return jsonify({"root": pub(root), "sharedBy": root["owner_name"], "path": path, "items": [pub(c) for c in children]})


@bp.get("/<token>/download/<int:item_id>")
def download(token, item_id):
    root = root_for(token)
    item = items.get_item(item_id)
    if not item or not items.is_within(root["id"], item):
        raise HttpError(404, "Item not found.")
    return send_item(item, inline=request.args.get("inline") == "1")
