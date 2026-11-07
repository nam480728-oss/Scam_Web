"""Bang tin: bai that cua nguoi dung (dang bai, cam xuc, binh luan, chia se) tron voi bai gia cu (chi xem)."""
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from routes import login_required_api, model_required
from services import social_service as ss
from services.view_helpers import time_ago

bp = Blueprint("feed", __name__)


def _fake_dto(fp) -> dict:
    return {"id": f"f{fp.id}", "fake": True, "author": {"name": fp.author.name, "color": fp.author.avatar_color},
            "body": fp.content, "image": f"/static/{fp.image}" if fp.image else None, "ago": time_ago(fp.created_at),
            "warn": fp.author.name == "Hội Cảnh Giác Mạng", "likes": fp.likes, "comments": fp.comments, "shares": fp.shares}


@bp.get("/feed")
@model_required
@login_required
def feed_page():
    me = current_user._get_current_object()
    items = [it["data"] if it["type"] == "post" else _fake_dto(it["data"]) for it in ss.feed(me)]
    return render_template("feed.html", items=items, suggestions=ss.suggestions(me, 5))


@bp.get("/post/<int:pid>")
@model_required
@login_required
def post_page(pid: int):
    me = current_user._get_current_object()
    return render_template("post.html", items=[ss.post_dto(ss.get_post(pid, me), me.id)])


@bp.post("/api/posts")
@login_required_api
@model_required
def create_post():
    me = current_user._get_current_object()
    p = ss.create_post(me, request.form.get("body"), request.files.get("image"))
    return jsonify(post=ss.post_dto(p, me.id)), 201


@bp.delete("/api/posts/<int:pid>")
@login_required_api
@model_required
def delete_post(pid: int):
    ss.delete_post(current_user._get_current_object(), pid)
    return jsonify(ok=True)


@bp.post("/api/posts/<int:pid>/react")
@login_required_api
@model_required
def react(pid: int):
    kind = (request.get_json(silent=True) or {}).get("kind")
    if kind is not None and not isinstance(kind, str):
        return jsonify(error="Cảm xúc không hợp lệ."), 400
    return jsonify(reactions=ss.react(current_user._get_current_object(), pid, kind))


@bp.get("/api/posts/<int:pid>/comments")
@login_required_api
@model_required
def comments(pid: int):
    return jsonify(comments=ss.list_comments(current_user._get_current_object(), pid))


@bp.post("/api/posts/<int:pid>/comments")
@login_required_api
@model_required
def add_comment(pid: int):
    body = (request.get_json(silent=True) or {}).get("body")
    if not isinstance(body, str):
        return jsonify(error="Bình luận trống."), 400
    return jsonify(comment=ss.add_comment(current_user._get_current_object(), pid, body)), 201


@bp.post("/api/posts/<int:pid>/share")
@login_required_api
@model_required
def share(pid: int):
    body = (request.get_json(silent=True) or {}).get("body")
    me = current_user._get_current_object()
    p = ss.share_post(me, pid, body if isinstance(body, str) else None)
    return jsonify(post=ss.post_dto(p, me.id)), 201
