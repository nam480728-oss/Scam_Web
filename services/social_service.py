"""Mang xa hoi: ban chung, goi y ket ban, tim kiem, bai dang / cam xuc / binh luan / chia se.

Bai dang va binh luan KHONG bi he thong chong lua dao quet (pham vi chi o loi moi ket ban, tin nhan, cuoc goi).
"""
from __future__ import annotations

from sqlalchemy import func, or_

from db.database import db, iso
from db.models import FeedPost, FriendRequest, Post, PostComment, PostReaction, User
from services import profile_service as ps
from services.chat_service import ChatError, block_state, friend_ids, relation
from services.notify import notify, user_brief

REACTIONS = {"like": "👍", "love": "❤️", "haha": "😆", "sad": "😢", "angry": "😡"}
REACTION_LABELS = {"like": "Thích", "love": "Yêu thích", "haha": "Haha", "sad": "Buồn", "angry": "Phẫn nộ"}
MAX_POST_LEN = 5000
MAX_COMMENT_LEN = 1000


# --------------------------------------------------------------------------- #
# Ban be
# --------------------------------------------------------------------------- #
def mutual_ids(a: int, b: int) -> set[int]:
    return friend_ids(a) & friend_ids(b)


def _pending_ids(uid: int) -> set[int]:
    rows = FriendRequest.query.filter(FriendRequest.status == "pending",
                                      or_(FriendRequest.sender_id == uid, FriendRequest.receiver_id == uid)).all()
    return {r.receiver_id if r.sender_id == uid else r.sender_id for r in rows}


def suggestions(me: User, limit: int = 12) -> list[dict]:
    """Ban cua ban (xep theo so ban chung), sau do la nguoi moi trong cung the gioi."""
    mine, pending = friend_ids(me.id), _pending_ids(me.id)
    scores: dict[int, int] = {}
    for f in mine:
        for ff in friend_ids(f):
            if ff != me.id and ff not in mine and ff not in pending:
                scores[ff] = scores.get(ff, 0) + 1
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    users = {u.id: u for u in User.query.filter(User.id.in_([k for k, _ in ranked] or [0]))}
    out = []
    for uid, n in ranked:
        u = users.get(uid)
        if u and u.model_key == me.model_key and not any(block_state(me.id, uid)):
            out.append({**user_brief(u), "mutual": n})
        if len(out) >= limit:
            return out
    extra = (User.query.filter(User.model_key == me.model_key, User.id != me.id,
                               User.id.notin_(mine | pending | set(scores) | {0}))
             .order_by(User.created_at.desc()).limit(limit * 2).all())
    for u in extra:
        if not any(block_state(me.id, u.id)):
            out.append({**user_brief(u), "mutual": 0})
        if len(out) >= limit:
            break
    return out


def search(me: User, q: str, limit: int = 30) -> list[dict]:
    q = ps.fold(q.strip().lstrip("@"))
    if not q:
        return []
    esc = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    rows = (User.query.filter(User.model_key == me.model_key, User.id != me.id,
                              User.search_name.like(f"%{esc}%", escape="\\"))
            .order_by(func.length(User.display_name)).limit(limit * 2).all())
    out = []
    for u in rows:
        rel = relation(me.id, u.id)
        if rel["blocked_me"]:
            continue
        out.append({**user_brief(u), "relation": rel["status"], "request_id": rel["request_id"],
                    "i_blocked": rel["i_blocked"], "mutual": len(mutual_ids(me.id, u.id))})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- #
# Bai dang
# --------------------------------------------------------------------------- #
def _reaction_summary(post_id: int, me_id: int) -> dict:
    rows = (db.session.query(PostReaction.kind, func.count()).filter(PostReaction.post_id == post_id)
            .group_by(PostReaction.kind).all())
    counts = {k: n for k, n in rows}
    mine = db.session.get(PostReaction, (post_id, me_id))
    top = [REACTIONS[k] for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:3]]
    return {"total": sum(counts.values()), "top": top, "mine": mine.kind if mine else None}


def post_dto(p: Post, me_id: int, depth: int = 0) -> dict:
    d = {"id": p.id, "author": user_brief(p.author), "body": p.body,
         "image": f"/static/uploads/{p.image_path}" if p.image_path else None,
         "created_at": iso(p.created_at), "mine": p.user_id == me_id,
         "reactions": _reaction_summary(p.id, me_id),
         "comments": PostComment.query.filter_by(post_id=p.id).count(),
         "shares": Post.query.filter_by(shared_post_id=p.id).count(), "shared": None}
    if p.shared_post_id and depth == 0:
        orig = db.session.get(Post, p.shared_post_id)
        d["shared"] = post_dto(orig, me_id, 1) if orig else {"deleted": True}
    return d


def get_post(post_id: int, me: User) -> Post:
    p = db.session.get(Post, post_id)
    if p is None or p.author.model_key != me.model_key:
        raise ChatError("Bài viết không tồn tại.", 404)
    return p


def create_post(me: User, body: str | None, image=None, shared_post_id: int | None = None) -> Post:
    body = (body or "").strip()
    if len(body) > MAX_POST_LEN:
        raise ChatError(f"Bài viết quá dài (tối đa {MAX_POST_LEN} ký tự).")
    has_image = image is not None and bool(image.filename)
    if not body and not has_image and not shared_post_id:
        raise ChatError("Bài viết trống.")
    path = None
    if has_image:
        try:
            path = ps.save_post_image(image)
        except ValueError as e:
            raise ChatError(str(e))
    p = Post(user_id=me.id, body=body or None, image_path=path, shared_post_id=shared_post_id)
    db.session.add(p)
    db.session.commit()
    return p


def share_post(me: User, post_id: int, body: str | None) -> Post:
    orig = get_post(post_id, me)
    if orig.shared_post_id:                                   # chia se bai goc, khong long nhieu tang
        orig = db.session.get(Post, orig.shared_post_id) or orig
    p = create_post(me, body, shared_post_id=orig.id)
    if orig.user_id != me.id:
        notify(orig.user_id, "share", f"{me.name} đã chia sẻ bài viết của bạn.", link=f"/post/{orig.id}", actor_id=me.id)
    return p


def delete_post(me: User, post_id: int):
    p = get_post(post_id, me)
    if p.user_id != me.id:
        raise ChatError("Bạn chỉ xóa được bài của mình.", 403)
    db.session.delete(p)
    db.session.commit()


def react(me: User, post_id: int, kind: str | None) -> dict:
    p = get_post(post_id, me)
    row = db.session.get(PostReaction, (p.id, me.id))
    is_new = False
    if kind is None:
        if row:
            db.session.delete(row)
    else:
        if kind not in REACTIONS:
            raise ChatError("Cảm xúc không hợp lệ.")
        if row:
            row.kind = kind
        else:
            is_new = True
            db.session.add(PostReaction(post_id=p.id, user_id=me.id, kind=kind))
    db.session.commit()
    if is_new and p.user_id != me.id:
        notify(p.user_id, "reaction", f"{me.name} đã bày tỏ cảm xúc {REACTIONS[kind]} về bài viết của bạn.",
               link=f"/post/{p.id}", actor_id=me.id)
    return _reaction_summary(p.id, me.id)


def comment_dto(c: PostComment, me_id: int) -> dict:
    return {"id": c.id, "author": user_brief(c.author), "body": c.body, "created_at": iso(c.created_at),
            "mine": c.user_id == me_id}


def list_comments(me: User, post_id: int) -> list[dict]:
    p = get_post(post_id, me)
    return [comment_dto(c, me.id) for c in PostComment.query.filter_by(post_id=p.id).order_by(PostComment.id).all()]


def add_comment(me: User, post_id: int, body: str) -> dict:
    p = get_post(post_id, me)
    body = (body or "").strip()
    if not body:
        raise ChatError("Bình luận trống.")
    if len(body) > MAX_COMMENT_LEN:
        raise ChatError(f"Bình luận quá dài (tối đa {MAX_COMMENT_LEN} ký tự).")
    c = PostComment(post_id=p.id, user_id=me.id, body=body)
    db.session.add(c)
    db.session.commit()
    if p.user_id != me.id:
        notify(p.user_id, "comment", f"{me.name} đã bình luận về bài viết của bạn: “{body[:60]}”",
               link=f"/post/{p.id}", actor_id=me.id)
    return comment_dto(c, me.id)


def feed(me: User, limit: int = 40) -> list[dict]:
    """Bai that cua nguoi dung (cung the gioi) tron voi bai gia cu, xep theo thoi gian."""
    posts = (Post.query.join(User, Post.user_id == User.id).filter(User.model_key == me.model_key)
             .order_by(Post.created_at.desc(), Post.id.desc()).limit(limit).all())
    items = [{"type": "post", "at": p.created_at, "data": post_dto(p, me.id)} for p in posts]
    for fp in FeedPost.query.order_by(FeedPost.created_at.desc()).limit(limit).all():
        items.append({"type": "fake", "at": fp.created_at, "data": fp})
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


def user_posts(viewer: User, user: User, limit: int = 30) -> list[dict]:
    rows = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).limit(limit).all()
    return [post_dto(p, viewer.id) for p in rows]


def user_photos(user: User, limit: int = 9) -> list[str]:
    rows = (Post.query.filter(Post.user_id == user.id, Post.image_path.isnot(None))
            .order_by(Post.created_at.desc()).limit(limit).all())
    return [f"/static/uploads/{p.image_path}" for p in rows]
