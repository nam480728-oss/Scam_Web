"""Ham dung chung cho template Jinja (avatar, thoi gian, thong tin nguoi dang nhap)."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app
from flask_login import current_user
from markupsafe import Markup, escape


def avatar_html(user, cls: str = "") -> Markup:
    if user is None:
        return Markup("")
    if getattr(user, "avatar_path", None):
        return Markup(f'<img class="avatar {escape(cls)}" src="/static/uploads/{escape(user.avatar_path)}" alt="" loading="lazy">')
    name = getattr(user, "name", None) or getattr(user, "username", "?")
    return Markup(f'<span class="avatar {escape(cls)}" style="background:{escape(user.avatar_color)}">{escape(name[:1])}</span>')


def time_ago(dt: datetime | None) -> str:
    if dt is None:
        return ""
    secs = int((datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds())
    if secs < 60:
        return "Vừa xong"
    if secs < 3600:
        return f"{secs // 60} phút"
    if secs < 86400:
        return f"{secs // 3600} giờ"
    if secs < 86400 * 7:
        return f"{secs // 86400} ngày"
    return dt.strftime("%d/%m/%Y")


def me_dto() -> dict | None:
    if not current_user.is_authenticated:
        return None
    u = current_user
    return {"id": u.id, "username": u.username, "name": u.name, "color": u.avatar_color,
            "avatar": f"/static/uploads/{u.avatar_path}" if u.avatar_path else None,
            "dark": bool(u.dark_mode),
            "agents": {"agent3": u.agent3_enabled}}


def ice_servers() -> list[dict]:
    urls = current_app.config.get("STUN_URLS") or []
    return [{"urls": urls}] if urls else []


def register(app):
    app.jinja_env.globals.update(avatar_html=avatar_html, time_ago=time_ago, me_dto=me_dto, ice_servers=ice_servers)
