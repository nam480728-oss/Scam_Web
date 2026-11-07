"""Du lieu + kich ban demo (data/scenarios.json): dung chung cho seed.py, trang /demo (Phat kich ban) va kiem thu.

- Tai khoan demo co anh dai dien sinh bang Pillow (chu cai dau tren nen mau; Thu Ha that va tai khoan gia dung CUNG anh).
- Moi buoc kich ban chay qua dung day chuyen that (tien xu ly -> AI 3 -> luat 3 lan), chi co TIN NHAN.
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from flask import current_app

from config import BASE_DIR
from db.database import db, utcnow
from db.models import (AvatarHistory, Call, Conversation, FamilyMember, Feedback, FriendRequest, GuardianEvent, LoginLog,
                       Message, NameHistory, Notification, Report, ScamCounter, User)
from services import profile_service as ps
from services.realtime import socketio

log = logging.getLogger("dangnam.demo")
_running: dict[str, bool] = {}


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads((BASE_DIR / "data" / "scenarios.json").read_text(encoding="utf-8"))


def scenario(sid: str) -> dict:
    for s in load()["scenarios"]:
        if s["id"] == sid:
            return s
    raise KeyError(sid)


def resolve(model_key: str, ref: str) -> User | None:
    if ref == "@first_normal":
        ref = load()["normal_users"][0][0]
    return User.query.filter_by(model_key=model_key, username=ref).first()


# --------------------------------------------------------------------------- #
# Anh dai dien / anh bai dang sinh bang Pillow
# --------------------------------------------------------------------------- #
def _font(size: int):
    from PIL import ImageFont
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_avatar(key: str, name: str, color: str, style: str | None = None) -> str:
    """Tra ve duong dan tuong doi trong static/uploads. Cung `key` -> cung file (tai khoan gia dung chung anh voi nguoi that)."""
    from PIL import Image, ImageDraw
    rel = f"avatars/demo_{key}.jpg"
    path = Path(current_app.config["PUBLIC_UPLOAD_DIR"]) / rel
    if path.exists():
        return rel
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (256, 256), color)
    d = ImageDraw.Draw(im)
    if style == "ha":                                     # chan dung hoat hinh co dinh cho Thu Ha (that + tai khoan gia)
        d.rectangle((0, 0, 256, 256), fill="#f3c6d8")
        d.ellipse((58, 30, 198, 190), fill="#2b2033")
        d.ellipse((76, 56, 180, 180), fill="#f6d3b8")
        d.ellipse((104, 104, 116, 116), fill="#2b2033"); d.ellipse((140, 104, 152, 116), fill="#2b2033")
        d.arc((108, 128, 148, 156), 20, 160, fill="#b23a5a", width=4)
        d.rectangle((56, 196, 200, 256), fill="#7b3fe4")
    else:
        initials = "".join(w[0] for w in name.split()[-2:]).upper() or "?"
        d.ellipse((-40, 150, 120, 310), fill=_shade(color, 0.85))
        f = _font(104 if len(initials) == 1 else 92)
        w, h = d.textbbox((0, 0), initials, font=f)[2:]
        d.text(((256 - w) / 2, (256 - h) / 2 - 12), initials, font=f, fill="white")
    im.save(path, "JPEG", quality=90)
    return rel


def _shade(hexcolor: str, k: float) -> str:
    c = hexcolor.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


def make_post_image(key: str, text: str, c1: str, c2: str) -> str:
    from PIL import Image, ImageDraw
    rel = f"posts/demo_{key}.jpg"
    path = Path(current_app.config["PUBLIC_UPLOAD_DIR"]) / rel
    if path.exists():
        return rel
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (960, 540), c1)
    d = ImageDraw.Draw(im)
    for i in range(540):
        t = i / 540
        d.line((0, i, 960, i), fill=tuple(int(int(c1[j:j + 2], 16) * (1 - t) + int(c2[j:j + 2], 16) * t) for j in (1, 3, 5)))
    f = _font(54)
    w, h = d.textbbox((0, 0), text, font=f)[2:]
    d.text(((960 - w) / 2, (540 - h) / 2), text, font=f, fill="white")
    im.save(path, "JPEG", quality=85)
    return rel


# --------------------------------------------------------------------------- #
# Tai khoan, ban be
# --------------------------------------------------------------------------- #
def ensure_user(model_key: str, username: str, name: str, *, days: int = 400, color: str = "#0f7b6c", bio: str | None = None,
                birth_year: int | None = None, verified: bool = False, phone: bool = False, style: str | None = None,
                is_demo: bool = True, avatar_key: str | None = None, old_names: list[str] | None = None,
                demo_ip: str | None = None) -> User:
    u = User.query.filter_by(model_key=model_key, username=username).first()
    if u is None:
        u = User(model_key=model_key, username=username, avatar_color=color)
        u.set_password(load()["password"])
        db.session.add(u)
    ps.set_display_name(u, name, record=False)
    u.bio, u.birth_year, u.identity_verified, u.is_demo, u.avatar_color = bio, birth_year, verified, is_demo, color
    if phone and not u.phone:
        u.phone, u.phone_verified = f"03900{random.Random(username).randint(10000, 99999)}", True
    u.created_at = utcnow() - timedelta(days=days)
    db.session.flush()
    rel = make_avatar(avatar_key or username, name, color, style)
    if u.avatar_path != rel:
        ps.set_avatar_from_path(u, rel, record=False)
        db.session.add(AvatarHistory(user_id=u.id, path=rel, changed_at=u.created_at))
    # lich su doi ten (dung cho Do uy tin): ten cu[0] -> ten cu[1] -> ... -> ten hien tai, rai deu trong tuoi tai khoan
    if old_names and not NameHistory.query.filter_by(user_id=u.id).first():
        chain = list(old_names) + [name]
        span = max(days, 1) * 24 * 60
        for i in range(len(chain) - 1):
            db.session.add(NameHistory(user_id=u.id, old_name=chain[i], new_name=chain[i + 1],
                                       changed_at=u.created_at + timedelta(minutes=span * (i + 1) / len(chain))))
    # IP demo (dai RFC 5737) cho trang truy vet cua quan tri vien
    if demo_ip and not LoginLog.query.filter_by(user_id=u.id).first():
        db.session.add(LoginLog(user_id=u.id, ip=demo_ip, user_agent="Demo browser", created_at=utcnow() - timedelta(hours=2)))
    return u


def demo_ip(username: str) -> str | None:
    return load()["actors"].get(username, {}).get("demo_ip")


def befriend(a: User, b: User, days: int = 300):
    fr = FriendRequest.query.filter(((FriendRequest.sender_id == a.id) & (FriendRequest.receiver_id == b.id)) |
                                    ((FriendRequest.sender_id == b.id) & (FriendRequest.receiver_id == a.id))).first()
    if fr is None:
        fr = FriendRequest(sender_id=a.id, receiver_id=b.id)
        db.session.add(fr)
    fr.status, fr.created_at, fr.responded_at = "accepted", utcnow() - timedelta(days=days), utcnow() - timedelta(days=days)


def conversation(a: User, b: User) -> Conversation:
    lo, hi = sorted((a.id, b.id))
    c = Conversation.query.filter_by(user_low_id=lo, user_high_id=hi).first()
    if c is None:
        c = Conversation(user_low_id=lo, user_high_id=hi)
        db.session.add(c)
        db.session.flush()
    return c


def send(sender: User, receiver: User, text: str | None, *, days_ago: float | None = None, process: bool = True,
         file_name: str | None = None, file_bytes: bytes | None = None) -> Message:
    """Gui tin nhu nguoi dung that (luu + day realtime) roi cho Ve si phan tich NGAY (dong bo, de kich ban dung thu tu)."""
    from services import chat_service as cs
    from services.realtime import emit_to
    conv = conversation(sender, receiver)
    when = utcnow() - timedelta(days=days_ago) if days_ago else utcnow()
    msg = Message(conversation_id=conv.id, sender_id=sender.id, kind="text", body=text or None,
                  created_at=when, delivered_at=when, scan_status="pending" if process else "none",
                  sender_ip=demo_ip(sender.username), sender_user_agent="Demo browser" if demo_ip(sender.username) else None)
    if file_bytes is not None:
        import uuid
        ext = file_name.rsplit(".", 1)[-1].lower()
        stored = f"{uuid.uuid4().hex}.{'bin' if ext == 'apk' else ext}"
        d = Path(current_app.config["UPLOAD_DIR"])
        d.mkdir(parents=True, exist_ok=True)
        (d / stored).write_bytes(file_bytes)
        msg.kind = "image" if ext in ("png", "jpg", "jpeg") else "file"
        msg.attachment_path, msg.attachment_name, msg.attachment_size = stored, file_name, len(file_bytes)
        msg.attachment_mime = {"png": "image/png", "jpg": "image/jpeg"}.get(ext, "application/octet-stream")
    conv.last_message_at = max(conv.last_message_at or when, when)
    db.session.add(msg)
    db.session.commit()
    for uid in (sender.id, receiver.id):
        emit_to(uid, "message:new", {"message": cs.message_dto(msg, uid), "conversation": cs.conversation_dto(conv, uid)})
    if process:
        from agents import orchestrator
        orchestrator.process_message(msg.id)
    return msg


# --------------------------------------------------------------------------- #
# Chay kich ban
# --------------------------------------------------------------------------- #
def _emit(model_key: str, event: str, data: dict):
    socketio.emit(event, data, to=f"guardian:{model_key}")


def run_step(model_key: str, step: dict) -> dict:
    t = step["type"]
    if t == "friend_request":
        from services import chat_service as cs
        a, b = resolve(model_key, step["from"]), resolve(model_key, step["to"])
        try:
            cs.send_friend_request(a.id, b.id)
        except cs.ChatError as e:
            return {"note": e.message}
        return {}
    if t in ("message", "file"):
        a, b = resolve(model_key, step["from"]), resolve(model_key, step["to"])
        if t == "message":
            m = send(a, b, step["text"], days_ago=step.get("days_ago"))
        else:
            m = send(a, b, step.get("text"), file_name=step["name"], file_bytes=b"PK\x03\x04 DEMO APK - KHONG BAO GIO THUC THI")
        return {"message_id": m.id, "level": m.warning_level}
    if t == "broadcast":
        a = resolve(model_key, step["from"])
        normals = [resolve(model_key, u) for u, _ in load()["normal_users"][:step.get("count", 20)]]
        levels = []
        for i, v in enumerate(n for n in normals if n):
            m = send(a, v, step["texts"][i % len(step["texts"])])
            levels.append(m.warning_level)
        return {"sent": len(levels), "levels": levels}
    if t == "report":
        from agents import orchestrator
        by, against = resolve(model_key, step["by"]), resolve(model_key, step["against"])
        return orchestrator.report(by, against.id, reason="Lừa đảo việc nhẹ lương cao")
    raise ValueError(t)


def run_setup(model_key: str, sc: dict, process: bool = True):
    for st in sc.get("setup", []):
        a, b = resolve(model_key, st["from"]), resolve(model_key, st["to"])
        send(a, b, st["text"], days_ago=st.get("days_ago"), process=process)


def play(app, model_key: str, sid: str, delay: float = 2.5):
    """Phat kich ban o luong nen: moi buoc cach nhau `delay` giay, bao tien do cho /demo."""
    key = f"{model_key}:{sid}"
    if _running.get(key):
        return False
    _running[key] = True
    sc = scenario(sid)

    def task():
        with app.app_context():
            try:
                _emit(model_key, "demo:start", {"scenario": sid, "steps": len(sc["steps"])})
                for i, step in enumerate(sc["steps"]):
                    _emit(model_key, "demo:step", {"scenario": sid, "index": i, "step": _public_step(model_key, step), "status": "running"})
                    res = run_step(model_key, step)
                    _emit(model_key, "demo:step", {"scenario": sid, "index": i, "step": _public_step(model_key, step), "status": "done", "result": res})
                    db.session.remove()
                    if i < len(sc["steps"]) - 1:
                        time.sleep(delay)
                _emit(model_key, "demo:done", {"scenario": sid})
            except Exception as e:  # noqa: BLE001
                log.exception("Loi phat kich ban %s", sid)
                _emit(model_key, "demo:done", {"scenario": sid, "error": str(e)})
            finally:
                _running.pop(key, None)
                db.session.remove()
    socketio.start_background_task(task)
    return True


def _public_step(model_key: str, step: dict) -> dict:
    def nm(ref):
        u = resolve(model_key, ref) if ref else None
        return u.name if u else ref
    return {"type": step["type"], "label": step.get("label"), "text": step.get("text") or step.get("name") or
            (step.get("texts") or [None])[0], "from": nm(step.get("from") or step.get("by")),
            "to": nm(step.get("to") or step.get("against")), "count": step.get("count"), "file": step.get("name"),
            "days_ago": step.get("days_ago")}


def reset(model_key: str, sid: str):
    """Xoa du lieu cua kich ban (hoi thoai, loi moi, cuoc goi, bao cao cua ke gian) roi chay lai setup."""
    sc = scenario(sid)
    victim = resolve(model_key, sc["victim"])
    people = [resolve(model_key, s) for s in sc["scammers"]]
    ids = [u.id for u in people if u]
    involved = set(ids) | ({victim.id} if victim else set())
    if sid == "khong_bao_nham":
        involved |= {u.id for u in (resolve(model_key, x) for x in ("hoanglong", "shop.mebong")) if u}
    pairs = [(resolve(model_key, a), resolve(model_key, b)) for a, b in sc.get("reset_pairs", [])]
    pairs = [(a, b) for a, b in pairs if a and b]
    from db.models import Appeal, Block
    if ids:                                                # go cac lan chan / khieu nai cu cua ke gian
        Block.query.filter(Block.blocked_id.in_(ids) | Block.blocker_id.in_(ids)).delete(synchronize_session=False)
        Appeal.query.filter(Appeal.accused_id.in_(ids) | Appeal.protected_id.in_(ids)).delete(synchronize_session=False)
    for a, b in pairs:
        Block.query.filter(((Block.blocker_id == a.id) & (Block.blocked_id == b.id))
                           | ((Block.blocker_id == b.id) & (Block.blocked_id == a.id))).delete(synchronize_session=False)
        Appeal.query.filter(((Appeal.protected_id == a.id) & (Appeal.accused_id == b.id))
                            | ((Appeal.protected_id == b.id) & (Appeal.accused_id == a.id))).delete(synchronize_session=False)
        Report.query.filter(((Report.reporter_id == a.id) & (Report.reported_id == b.id))
                            | ((Report.reporter_id == b.id) & (Report.reported_id == a.id))).delete(synchronize_session=False)
    if pairs:
        lo_hi = [tuple(sorted((a.id, b.id))) for a, b in pairs]
        convs = [c for c in (Conversation.query.filter_by(user_low_id=lo, user_high_id=hi).first() for lo, hi in lo_hi) if c]
    elif ids:
        convs = Conversation.query.filter((Conversation.user_low_id.in_(ids)) | (Conversation.user_high_id.in_(ids))).all()
        FriendRequest.query.filter(FriendRequest.sender_id.in_(ids)).delete(synchronize_session=False)
        Report.query.filter(Report.reported_id.in_(ids)).delete(synchronize_session=False)
        Notification.query.filter(Notification.actor_id.in_(ids)).delete(synchronize_session=False)
        GuardianEvent.query.filter(GuardianEvent.actor_id.in_(ids)).delete(synchronize_session=False)
        Feedback.query.filter(Feedback.target_user_id.in_(ids)).delete(synchronize_session=False)
        Call.query.filter(Call.caller_id.in_(ids)).delete(synchronize_session=False)
    else:                                                  # kich ban 7: xoa hoi thoai cua nan nhan voi ban / shop
        convs = Conversation.query.filter(Conversation.user_low_id.in_(involved), Conversation.user_high_id.in_(involved)).all()
        Call.query.filter(Call.callee_id == victim.id).delete(synchronize_session=False)
    for c in convs:
        GuardianEvent.query.filter(GuardianEvent.message_id.in_([m.id for m in c.messages])).delete(synchronize_session=False)
        ScamCounter.query.filter_by(conversation_id=c.id).delete()
        db.session.delete(c)
    db.session.commit()
    run_setup(model_key, sc)
    db.session.commit()


def demo_accounts(model_key: str) -> list[dict]:
    from services.notify import user_brief
    actors = load()["actors"]
    out = []
    for username, spec in actors.items():
        u = User.query.filter_by(model_key=model_key, username=username).first()
        if u:
            out.append({**user_brief(u), "role": spec.get("role"), "scammer": bool(spec.get("scammer"))})
    return out
