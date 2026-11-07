"""Trang ca nhan, ban be, tim kiem, thong bao."""
from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from db.database import db
from db.models import User
from routes import login_required_api
from services import chat_service as cs
from services import notify as nt
from services import profile_service as ps
from services import reputation_service as rs
from services import social_service as ss

bp = Blueprint("social", __name__)


def _me() -> User:
    return current_user._get_current_object()


def _user_by_name(username: str) -> User:
    u = User.query.filter(User.model_key == current_user.model_key, func.lower(User.username) == username.lower()).first()
    if u is None:
        abort(404)
    return u


# --------------------------------------------------------------------------- #
# Trang ca nhan
# --------------------------------------------------------------------------- #
@bp.get("/u/<username>")
@login_required
def profile_page(username: str):
    me, user = _me(), _user_by_name(username)
    rel = cs.relation(me.id, user.id) if user.id != me.id else None
    if rel and rel["blocked_me"]:
        abort(404)
    friends = User.query.filter(User.id.in_(cs.friend_ids(user.id) or {0})).order_by(User.display_name).limit(9).all()
    mutual = ss.mutual_ids(me.id, user.id) if user.id != me.id else set()
    data = {"user": {**nt.user_brief(user), "bio": user.bio, "cover": f"/static/uploads/{user.cover_path}" if user.cover_path else None,
                     "joined": user.created_at.strftime("%m/%Y"), "birth_year": user.birth_year},
            "is_me": user.id == me.id, "relation": rel, "mutual": len(mutual),
            "reputation": None if user.id == me.id else rs.badge(user, me.id),
            "posts": ss.user_posts(me, user)}
    return render_template("profile.html", user=user, friends=friends, friend_count=len(cs.friend_ids(user.id)),
                           photos=ss.user_photos(user), data=data, mutual=len(mutual), reputation=data["reputation"])


@bp.post("/api/profile")
@login_required_api
def update_profile():
    me, data = _me(), request.get_json(silent=True) or {}
    if "display_name" in data:
        name = ps.clean_name(str(data["display_name"]))
        err = ps.validate_name(name)
        if err:
            return jsonify(error=err), 400
        ps.set_display_name(me, name)
    if "bio" in data:
        bio = str(data["bio"] or "").strip()
        if len(bio) > 300:
            return jsonify(error="Giới thiệu tối đa 300 ký tự."), 400
        me.bio = bio or None
    if "birth_year" in data:
        by = data["birth_year"]
        if by in (None, ""):
            me.birth_year = None
        elif isinstance(by, int) and 1900 <= by <= 2025:
            me.birth_year = by
        else:
            return jsonify(error="Năm sinh không hợp lệ."), 400
    db.session.commit()
    return jsonify(user=nt.user_brief(me), bio=me.bio)


@bp.post("/api/profile/<kind>")
@login_required_api
def upload_profile_image(kind: str):
    if kind not in ("avatar", "cover"):
        abort(404)
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify(error="Chưa chọn ảnh."), 400
    me = _me()
    try:
        (ps.upload_avatar if kind == "avatar" else ps.upload_cover)(me, f)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db.session.commit()
    return jsonify(user=nt.user_brief(me), cover=f"/static/uploads/{me.cover_path}" if me.cover_path else None)


# --------------------------------------------------------------------------- #
# Ban be
# --------------------------------------------------------------------------- #
@bp.get("/friends")
@login_required
def friends_page():
    return render_template("friends.html")


@bp.get("/api/friends/suggestions")
@login_required_api
def friend_suggestions():
    return jsonify(users=ss.suggestions(_me()))


@bp.get("/api/users/<int:uid>/mutual")
@login_required_api
def mutual_friends(uid: int):
    cs.get_peer(current_user.id, uid)
    users = User.query.filter(User.id.in_(ss.mutual_ids(current_user.id, uid) or {0})).all()
    return jsonify(users=[nt.user_brief(u) for u in users])


# --------------------------------------------------------------------------- #
# Tim kiem
# --------------------------------------------------------------------------- #
@bp.get("/search")
@login_required
def search_page():
    q = request.args.get("q", "")
    return render_template("search.html", q=q, results=ss.search(_me(), q) if q.strip() else [])


@bp.get("/api/search")
@login_required_api
def search_api():
    return jsonify(users=ss.search(_me(), request.args.get("q", "")))


# --------------------------------------------------------------------------- #
# Thong bao
# --------------------------------------------------------------------------- #
@bp.get("/api/notifications")
@login_required_api
def notifications():
    return jsonify(nt.list_for(current_user.id))


@bp.post("/api/notifications/read")
@login_required_api
def notifications_read():
    nt.mark_all_read(current_user.id)
    return jsonify(ok=True)
