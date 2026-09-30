import secrets

from flask import Blueprint, g, jsonify

from . import db, items
from .security import json_body, require_user
from .util import HttpError, now_ms

bp = Blueprint("sharing", __name__, url_prefix="/api/items")


@bp.before_request
def _auth():
    require_user()


def sharing_state(item):
    people = db.all_("""SELECT u.id AS userId, u.name, u.email, s.role FROM shares s
        JOIN users u ON u.id = s.user_id WHERE s.item_id = ? ORDER BY u.name COLLATE NOCASE""", (item["id"],))
    return {
        "owner": {"id": item["owner_id"], "name": item["owner_name"], "email": item["owner_email"]},
        "people": people,
        "link": {"enabled": bool(item["share_token"]), "token": item["share_token"] or None},
    }


@bp.get("/<int:item_id>/sharing")
def get_sharing(item_id):
    item, _ = items.require_access(g.user, item_id, "owner")
    return jsonify(sharing_state(item))


@bp.post("/<int:item_id>/shares")
def share_with_person(item_id):
    """Share with a person (or change their role)."""
    item, _ = items.require_access(g.user, item_id, "owner")
    if item["trashed_at"]:
        raise HttpError(409, "Restore this item before sharing it.")
    body = json_body()
    email = str(body.get("email") or "").strip().lower()
    role = "editor" if body.get("role") == "editor" else "viewer"
    person = db.one("SELECT id FROM users WHERE email = ?", (email,))
    if not person:
        raise HttpError(404, "No Harbor account uses that email address.")
    if person["id"] == g.user["id"]:
        raise HttpError(400, "You already own this item.")
    db.run("""INSERT INTO shares (item_id, user_id, role, created_at) VALUES (?, ?, ?, ?)
              ON CONFLICT(item_id, user_id) DO UPDATE SET role = excluded.role""",
           (item["id"], person["id"], role, now_ms()))
    return jsonify(sharing_state(items.get_item(item["id"])))


@bp.delete("/<int:item_id>/shares/<int:user_id>")
def remove_share(item_id, user_id):
    """The owner can remove anyone; a person can always remove themselves."""
    item = items.get_item(item_id)
    if not item:
        raise HttpError(404, "Item not found.")
    if item["owner_id"] != g.user["id"] and user_id != g.user["id"]:
        raise HttpError(403, "Only the owner can do that.")
    db.run("DELETE FROM shares WHERE item_id = ? AND user_id = ?", (item_id, user_id))
    return jsonify(sharing_state(items.get_item(item_id)) if item["owner_id"] == g.user["id"] else {"ok": True})


@bp.post("/<int:item_id>/link")
def toggle_link(item_id):
    """Turn the public "anyone with the link" view on or off."""
    item, _ = items.require_access(g.user, item_id, "owner")
    if item["trashed_at"]:
        raise HttpError(409, "Restore this item before sharing it.")
    token = (item["share_token"] or secrets.token_urlsafe(18)) if json_body().get("enabled") else None
    db.run("UPDATE items SET share_token = ? WHERE id = ?", (token, item["id"]))
    return jsonify(sharing_state(items.get_item(item["id"])))
