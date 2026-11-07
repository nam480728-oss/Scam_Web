"""Thong bao: luu CSDL + day realtime qua Socket.IO (su kien 'notify:new')."""
from __future__ import annotations

from db.database import db, iso
from db.models import Notification, User
from services.realtime import emit_to


def notification_dto(n: Notification) -> dict:
    actor = n.actor
    return {"id": n.id, "kind": n.kind, "text": n.text, "link": n.link, "level": n.level, "read": n.read_at is not None,
            "created_at": iso(n.created_at),
            "actor": None if actor is None else {"id": actor.id, "name": actor.name, "color": actor.avatar_color,
                                                 "avatar": f"/static/uploads/{actor.avatar_path}" if actor.avatar_path else None,
                                                 "username": actor.username}}


def notify(user_id: int, kind: str, text: str, link: str | None = None, actor_id: int | None = None,
           level: int = 0, commit: bool = True) -> Notification:
    n = Notification(user_id=user_id, kind=kind, text=text[:400], link=link, actor_id=actor_id, level=level)
    db.session.add(n)
    if commit:
        db.session.commit()
        emit_to(user_id, "notify:new", notification_dto(n))
    else:
        db.session.flush()
    return n


def push(n: Notification):
    """Day thong bao da luu (dung khi tao voi commit=False)."""
    emit_to(n.user_id, "notify:new", notification_dto(n))


def list_for(user_id: int, limit: int = 30) -> dict:
    rows = Notification.query.filter_by(user_id=user_id).order_by(Notification.id.desc()).limit(limit).all()
    unread = Notification.query.filter_by(user_id=user_id, read_at=None).count()
    return {"notifications": [notification_dto(n) for n in rows], "unread": unread}


def mark_all_read(user_id: int):
    from db.database import utcnow
    Notification.query.filter_by(user_id=user_id, read_at=None).update({"read_at": utcnow()})
    db.session.commit()


def unread_count(user_id: int) -> int:
    return Notification.query.filter_by(user_id=user_id, read_at=None).count()


def user_brief(u: User) -> dict:
    return {"id": u.id, "username": u.username, "name": u.name, "color": u.avatar_color,
            "avatar": f"/static/uploads/{u.avatar_path}" if u.avatar_path else None,
            "verified": bool(u.identity_verified), "phone_verified": bool(u.phone_verified)}
