"""Nghiep vu chat: ban be, chan, hoi thoai, tin nhan, trang thai da nhan/da xem, dinh kem, tin thoai,
tra loi trich dan, thu hoi, tha cam xuc, ghim tin, tim trong hoi thoai, kho anh / tep / link."""
from __future__ import annotations

import os
import re
import uuid
from datetime import timedelta
from pathlib import Path

from flask import current_app
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from db.database import db, iso, utcnow
from db.models import Block, Conversation, FriendRequest, Message, MessageReaction, User
from services import alert_manager
from services.realtime import emit_to, is_online


class ChatError(Exception):
    """Loi nghiep vu co thong diep hien thi cho nguoi dung."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


# --------------------------------------------------------------------------- #
# Quan he giua 2 nguoi dung
# --------------------------------------------------------------------------- #
def _pair_request(a: int, b: int) -> FriendRequest | None:
    return FriendRequest.query.filter(or_(
        and_(FriendRequest.sender_id == a, FriendRequest.receiver_id == b),
        and_(FriendRequest.sender_id == b, FriendRequest.receiver_id == a))).first()


def are_friends(a: int, b: int) -> bool:
    fr = _pair_request(a, b)
    return bool(fr and fr.status == "accepted")


def block_state(me: int, other: int) -> tuple[bool, bool]:
    """(toi da chan ho, ho da chan toi)"""
    rows = Block.query.filter(or_(and_(Block.blocker_id == me, Block.blocked_id == other),
                                  and_(Block.blocker_id == other, Block.blocked_id == me))).all()
    return (any(r.blocker_id == me for r in rows), any(r.blocker_id == other for r in rows))


def friend_ids(uid: int) -> set[int]:
    rows = FriendRequest.query.filter(FriendRequest.status == "accepted",
                                      or_(FriendRequest.sender_id == uid, FriendRequest.receiver_id == uid)).all()
    return {r.receiver_id if r.sender_id == uid else r.sender_id for r in rows}


def relation(me: int, other: int) -> dict:
    i_blocked, blocked_me = block_state(me, other)
    fr = _pair_request(me, other)
    if fr and fr.status == "accepted":
        status = "friend"
    elif fr and fr.status == "pending":
        status = "sent" if fr.sender_id == me else "received"
    else:
        status = "none"
    return {"status": status, "request_id": fr.id if fr and fr.status == "pending" else None,
            "i_blocked": i_blocked, "blocked_me": blocked_me}


def get_peer(me: int, other_id: int) -> User:
    """Nguoi dung khac CUNG mo hinh AI (moi mo hinh co the gioi tai khoan rieng), neu khong thi coi nhu khong ton tai."""
    other = db.session.get(User, other_id)
    mine = db.session.get(User, me)
    if other is None or mine is None or other.model_key != mine.model_key:
        raise ChatError("Người dùng không tồn tại.", 404)
    return other


def user_dto(u: User, viewer_id: int, with_presence: bool = True) -> dict:
    d = {"id": u.id, "username": u.username, "name": u.name, "color": u.avatar_color,
         "avatar": f"/static/uploads/{u.avatar_path}" if u.avatar_path else None,
         "verified": bool(u.identity_verified), "online": False, "last_seen": None}
    if with_presence and viewer_id != u.id and are_friends(viewer_id, u.id):
        i_blocked, blocked_me = block_state(viewer_id, u.id)
        if not (i_blocked or blocked_me):                      # nguoi bi chan khong xem duoc trang thai
            d["online"] = is_online(u.id)
            d["last_seen"] = iso(u.last_seen_at)
    return d


# --------------------------------------------------------------------------- #
# Hoi thoai
# --------------------------------------------------------------------------- #
def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def get_conversation(cid: int, me: int) -> Conversation:
    conv = db.session.get(Conversation, cid)
    if conv is None or not conv.has_user(me):
        raise ChatError("Không tìm thấy cuộc trò chuyện.", 404)
    return conv


def get_or_create_conversation(me: int, other_id: int) -> Conversation:
    if other_id == me:
        raise ChatError("Không thể trò chuyện với chính mình.")
    get_peer(me, other_id)
    low, high = _pair(me, other_id)
    conv = Conversation.query.filter_by(user_low_id=low, user_high_id=high).first()
    if conv:
        return conv
    i_blocked, blocked_me = block_state(me, other_id)
    if blocked_me:
        raise ChatError("Bạn không thể nhắn tin cho người này.", 403)
    # Nguoi la van nhan duoc: tin cua ho vao hop "Tin nhan cho" cua nguoi nhan
    conv = Conversation(user_low_id=low, user_high_id=high)
    db.session.add(conv)
    try:
        db.session.commit()
    except Exception:  # dua nhau tao dong thoi -> lay ban ghi da co
        db.session.rollback()
        conv = Conversation.query.filter_by(user_low_id=low, user_high_id=high).first()
        if conv is None:
            raise
    return conv


def guardian_block(a: int, b: int) -> Block | None:
    """Lan chan do Ve si TU DONG tao (sau 3 lan phat hien lua dao) giua 2 nguoi, neu co."""
    return Block.query.filter(Block.source == "guardian", or_(and_(Block.blocker_id == a, Block.blocked_id == b),
                                                            and_(Block.blocker_id == b, Block.blocked_id == a))).first()


def send_permission(me: int, other: int) -> tuple[bool, str | None]:
    i_blocked, blocked_me = block_state(me, other)
    gb = guardian_block(me, other) if (i_blocked or blocked_me) else None
    if gb is not None and gb.blocked_id == me:
        return False, ("Hệ thống đã chặn bạn nhắn tin với người này vì phát hiện nội dung lừa đảo 3 lần. "
                       "Nếu đây là nhầm lẫn, hãy gửi Khiếu nại để xác minh danh tính.")
    if gb is not None:
        return False, "Vệ sĩ đã tự động chặn người này sau 3 lần gửi tin lừa đảo. Muốn gỡ chặn: gửi Khiếu nại."
    if i_blocked:
        return False, "Bạn đã chặn người này. Hãy bỏ chặn để nhắn tin."
    if blocked_me:
        return False, "Bạn không thể nhắn tin cho người này."
    return True, None


def _guardian_block_dto(me: int, other_id: int) -> dict | None:
    gb = guardian_block(me, other_id)
    if gb is None:
        return None
    from services.appeal_service import appeal_summary
    from services.trace_service import request_state
    protected = gb.blocker_id == me
    return {"role": "protected" if protected else "accused", "since": iso(gb.created_at),
            "appeal": appeal_summary(gb.blocker_id, gb.blocked_id, me),
            # nut "Yeu cau thong tin truy vet": CHI nan nhan (ben duoc bao ve) thay
            "trace": request_state(me, other_id) if protected else None}


def is_message_request(conv: Conversation, me: int) -> bool:
    """'Tin nhan cho': nguoi la nhan toi va toi chua tung tra loi."""
    other = conv.other_user_id(me)
    if are_friends(me, other):
        return False
    mine = Message.query.filter(Message.conversation_id == conv.id, Message.sender_id == me,
                                Message.kind != "call").first()
    return mine is None


def unread_count(conv_id: int, me: int) -> int:
    return Message.query.filter(Message.conversation_id == conv_id, Message.sender_id != me,
                                Message.read_at.is_(None)).count()


def _preview(m: Message, viewer_id: int | None = None) -> str:
    if m.recalled_at is not None:
        return "Tin nhắn đã bị thu hồi"
    if viewer_id is not None and m.sender_id != viewer_id and m.warning_level >= 2:
        return "🛡️ Tin nhắn nguy hiểm đã bị Vệ sĩ che"
    if m.kind == "call":
        return m.body or "📞 Cuộc gọi"
    if m.kind == "image":
        return "📷 Ảnh" + (f": {m.body}" if m.body else "")
    if m.kind == "voice":
        return f"🎤 Tin nhắn thoại ({_fmt_dur((m.attachment_meta or {}).get('duration'))})"
    if m.kind == "file":
        return f"📎 {m.attachment_name}"
    return m.body or ""


def _fmt_dur(sec) -> str:
    try:
        sec = int(round(float(sec)))
    except (TypeError, ValueError):
        sec = 0
    return f"{sec // 60}:{sec % 60:02d}"


def is_apk(m: Message) -> bool:
    return bool(m.attachment_name and m.attachment_name.lower().endswith(".apk"))


def attachment_blocked(m: Message, viewer_id: int) -> bool:
    """Ve si chan tai file APK tu lan phat hien lua dao thu 2 (chi phia nguoi nhan)."""
    return m.sender_id != viewer_id and is_apk(m) and m.warning_level >= 2


REACTIONS = ("❤️", "😂", "😮", "😢", "😡", "👍")
MAX_PINNED = 3
RECALL_WINDOW = timedelta(hours=24)


def _reactions(ids: list[int], viewer_id: int) -> dict[int, dict]:
    """{message_id: {"counts": {emoji: n}, "mine": emoji | None}}"""
    out: dict[int, dict] = {}
    if not ids:
        return out
    for r in MessageReaction.query.filter(MessageReaction.message_id.in_(ids)).order_by(MessageReaction.created_at):
        x = out.setdefault(r.message_id, {"counts": {}, "mine": None})
        x["counts"][r.emoji] = x["counts"].get(r.emoji, 0) + 1
        if r.user_id == viewer_id:
            x["mine"] = r.emoji
    return out


def _quote(m: Message | None, viewer_id: int) -> dict | None:
    """Tin duoc tra loi (trich dan ngan). Ton trong thu hoi + che tin nguy hiem voi nguoi xem."""
    if m is None:
        return {"id": None, "preview": "Tin nhắn không còn tồn tại", "mine": False}
    return {"id": m.id, "sender_id": m.sender_id, "mine": m.sender_id == viewer_id, "kind": m.kind,
            "preview": _preview(m, viewer_id)[:160]}


def message_dto(m: Message, viewer_id: int, guards: dict | None = None, reactions: dict | None = None) -> dict:
    recalled = m.recalled_at is not None
    d = {"id": m.id, "conversation_id": m.conversation_id, "sender_id": m.sender_id, "mine": m.sender_id == viewer_id,
         "kind": m.kind, "body": None if recalled else m.body, "created_at": iso(m.created_at),
         "delivered_at": iso(m.delivered_at), "read_at": iso(m.read_at), "attachment": None, "warning_level": 0,
         "call_id": m.call_id, "recalled": recalled, "pinned": m.pinned_at is not None,
         "can_recall": m.sender_id == viewer_id and not recalled and m.kind != "call"
                       and utcnow() - m.created_at <= RECALL_WINDOW}
    if m.kind in ("image", "file", "voice") and not recalled:
        meta = m.attachment_meta or {}
        d["attachment"] = {"url": f"/api/attachments/{m.id}", "name": m.attachment_name, "mime": m.attachment_mime,
                           "size": m.attachment_size, "is_image": m.kind == "image", "is_apk": is_apk(m),
                           "blocked": attachment_blocked(m, viewer_id)}
        if m.kind == "voice":
            d["attachment"].update(duration=meta.get("duration"), masked=bool(meta.get("masked")) and m.sender_id != viewer_id)
    if m.reply_to_id:
        d["reply_to"] = _quote(m.reply_to, viewer_id)
    if reactions is None:
        reactions = _reactions([m.id], viewer_id)
    d["reactions"] = reactions.get(m.id, {"counts": {}, "mine": None})
    # Ket qua Ve si CHI gui cho NGUOI NHAN. Nguoi gui khong bao gio thay co cua chinh minh qua API.
    if m.sender_id != viewer_id and m.kind != "call":
        d["warning_level"] = m.warning_level
        d["scan"] = m.scan_status
        if guards is None:
            from services.guard_view import message_guards
            guards = message_guards([m.id], viewer_id)
        d["guard"] = guards.get(m.id)
    return d


def conversation_dto(conv: Conversation, me: int) -> dict:
    other_id = conv.other_user_id(me)
    other = db.session.get(User, other_id)
    last = conv.messages.order_by(Message.id.desc()).first()
    allowed, reason = send_permission(me, other_id)
    state = alert_manager.conversation_state(conv.id, me, other_id)
    i_blocked, blocked_me = block_state(me, other_id)
    friend = are_friends(me, other_id)
    preview = None
    if last is not None:
        preview = {"preview": _preview(last, me), "mine": last.sender_id == me, "created_at": iso(last.created_at)}
    return {"id": conv.id, "other": user_dto(other, me), "unread": unread_count(conv.id, me),
            "last_message": preview, "last_message_at": iso(conv.last_message_at), "can_send": allowed,
            "send_block_reason": reason, "i_blocked": i_blocked, "blocked_me": blocked_me,
            "is_friend": friend, "request": not friend and is_message_request(conv, me),
            "guardian_block": _guardian_block_dto(me, other_id), "pinned": pinned_messages(conv, me),
            "mutual": len(friend_ids(me) & friend_ids(other_id)),
            "reputation": None if friend else _reputation_badge(other, me), **state}


def _reputation_badge(other: User, me: int) -> dict:
    from services.reputation_service import badge
    return badge(other, me)


def list_conversations(me: int) -> list[dict]:
    convs = (Conversation.query.filter(or_(Conversation.user_low_id == me, Conversation.user_high_id == me),
                                       Conversation.last_message_at.isnot(None))
             .order_by(Conversation.last_message_at.desc()).all())
    return [conversation_dto(c, me) for c in convs]


def _dtos(rows: list[Message], me: int) -> list[dict]:
    from services.guard_view import message_guards
    guards = message_guards([m.id for m in rows if m.sender_id != me], me)
    reacts = _reactions([m.id for m in rows], me)
    return [message_dto(m, me, guards, reacts) for m in rows]


def history(conv: Conversation, me: int, before: int | None, limit: int, around: int | None = None) -> dict:
    """Trang tin nhan. around: nhay toi 1 tin (ket qua tim kiem / tin ghim / tin duoc trich dan) -> tai tu ~15 tin
    truoc tin do den tin moi nhat."""
    q = conv.messages
    if around:
        older = (conv.messages.filter(Message.id < around).order_by(Message.id.desc()).limit(15).all())
        start = older[-1].id if older else around
        rows = q.filter(Message.id >= start).order_by(Message.id.asc()).limit(500).all()
        has_more = conv.messages.filter(Message.id < start).first() is not None
        return {"messages": _dtos(rows, me), "has_more": has_more}
    if before:
        q = q.filter(Message.id < before)
    rows = q.order_by(Message.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = list(reversed(rows[:limit]))
    return {"messages": _dtos(rows, me), "has_more": has_more}


# --------------------------------------------------------------------------- #
# Gui tin nhan + AI trong tai
# --------------------------------------------------------------------------- #
def _store_attachment(file_storage, voice: bool = False) -> dict:
    cfg = current_app.config
    original = (file_storage.filename or "").strip()
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if voice:
        if ext not in cfg["VOICE_EXTS"]:
            raise ChatError("Định dạng ghi âm không được hỗ trợ.")
    elif ext not in cfg["IMAGE_EXTS"] | cfg["FILE_EXTS"] | cfg["APK_EXTS"]:
        raise ChatError("Loại tệp này không được hỗ trợ (ảnh png/jpg/gif/webp hoặc pdf, doc, xls, txt, zip, apk...).")
    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        raise ChatError("Tệp rỗng.")
    limit = cfg["MAX_VOICE_BYTES"] if voice else cfg["MAX_UPLOAD_BYTES"]
    if size > limit:
        raise ChatError(f"Tệp quá lớn (tối đa {limit // 2**20} MB).")
    # Ten ngau nhien, KHONG giu duoi .apk tren dia: file khong bao gio duoc mo hay thuc thi
    stored = f"{uuid.uuid4().hex}.{'bin' if ext in cfg['APK_EXTS'] else ext}"
    Path(cfg["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    file_storage.save(Path(cfg["UPLOAD_DIR"]) / stored)
    display = secure_filename(original) or f"tep.{ext}"
    if original:                                         # giu ten co dau de hien thi, bo ky tu nguy hiem
        display = "".join(c for c in original if c not in '\\/:*?"<>|\r\n\x00')[:200] or display
    kind = "voice" if voice else ("image" if ext in cfg["IMAGE_EXTS"] else "file")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
            "webm": "audio/webm", "ogg": "audio/ogg", "m4a": "audio/mp4", "mp3": "audio/mpeg", "wav": "audio/wav",
            }.get(ext, "application/octet-stream")
    return {"kind": kind, "path": stored, "name": display, "size": size, "mime": mime}


def send_message(conv: Conversation, sender: User, body: str | None, file_storage=None, reply_to_id: int | None = None,
                 voice=None, voice_duration=None) -> dict:
    cfg = current_app.config
    other_id = conv.other_user_id(sender.id)
    allowed, reason = send_permission(sender.id, other_id)
    if not allowed:
        raise ChatError(reason, 403)
    body = (body or "").strip()
    if len(body) > cfg["MAX_MESSAGE_LEN"]:
        raise ChatError(f"Tin nhắn quá dài (tối đa {cfg['MAX_MESSAGE_LEN']} ký tự).")
    has_voice = voice is not None and bool(voice.filename)
    has_file = not has_voice and file_storage is not None and bool(file_storage.filename)
    if not body and not has_file and not has_voice:
        raise ChatError("Tin nhắn trống.")
    if has_voice:
        body = ""                                         # tin thoai khong kem chu
        try:
            dur = float(voice_duration)
        except (TypeError, ValueError):
            dur = 0.0
        if not 0.5 <= dur <= cfg["MAX_VOICE_SECONDS"] + 1:
            raise ChatError(f"Tin nhắn thoại phải dài từ 1 giây đến {cfg['MAX_VOICE_SECONDS'] // 60} phút.")
    reply = None
    if reply_to_id:
        reply = db.session.get(Message, reply_to_id)
        if reply is None or reply.conversation_id != conv.id or reply.kind == "call":
            raise ChatError("Tin nhắn được trả lời không tồn tại.", 404)

    att = _store_attachment(voice, voice=True) if has_voice else (_store_attachment(file_storage) if has_file else None)
    try:
        msg = Message(conversation_id=conv.id, sender_id=sender.id, kind=att["kind"] if att else "text",
                      body=body or None, reply_to_id=reply.id if reply else None)
        from services.trace_service import request_meta
        msg.sender_ip, msg.sender_user_agent = request_meta()   # truy vet: CHI quan tri vien xem
        if att:
            msg.attachment_path, msg.attachment_name = att["path"], att["name"]
            msg.attachment_mime, msg.attachment_size = att["mime"], att["size"]
            if has_voice:
                msg.attachment_meta = {"duration": round(dur, 1)}
        # ---- Ve si phan tich NEN sau khi tin da den nguoi nhan (khong lam cham chat) ----
        msg.scan_status = "pending"
        recipient_online = is_online(other_id)
        if recipient_online:
            msg.delivered_at = utcnow()
        conv.last_message_at = msg.created_at = utcnow()
        db.session.add(msg)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if att:
            try:
                (Path(cfg["UPLOAD_DIR"]) / att["path"]).unlink(missing_ok=True)
            except OSError:
                pass
        raise

    for viewer_id in (sender.id, other_id):
        emit_to(viewer_id, "message:new", {"message": message_dto(msg, viewer_id),
                                           "conversation": conversation_dto(conv, viewer_id)})
    dto = message_dto(msg, sender.id)
    from agents import orchestrator
    orchestrator.on_message(msg.id)                      # Ve si: tien xu ly -> AI 3 -> luat 3 lan
    return dto


# --------------------------------------------------------------------------- #
# Thu hoi / tha cam xuc / ghim / tim kiem / kho media
# --------------------------------------------------------------------------- #
def get_message(mid: int, me: int) -> Message:
    m = db.session.get(Message, mid)
    if m is None or not m.conversation.has_user(me) or m.kind == "call":
        raise ChatError("Không tìm thấy tin nhắn.", 404)
    return m


def _push_update(m: Message):
    """Ca 2 ben cap nhat lai tin (moi ben 1 ban rieng: canh bao chi nguoi nhan thay)."""
    conv = m.conversation
    for uid in (conv.user_low_id, conv.user_high_id):
        emit_to(uid, "message:update", {"message": message_dto(m, uid), "conversation": conversation_dto(conv, uid)})


def recall_message(m: Message, me: int) -> dict:
    """Thu hoi: noi dung an voi CA 2 ben. Tin lua dao bi thu hoi VAN tinh lan canh bao (Ve si da ghi nhan luc nhan),
    nguoi nhan van thay huy hieu canh bao. Noi dung van luu o may chu cho nhat ky Ve si / bao cao."""
    if m.sender_id != me:
        raise ChatError("Bạn chỉ thu hồi được tin của chính mình.", 403)
    if m.recalled_at is not None:
        return message_dto(m, me)
    if utcnow() - m.created_at > RECALL_WINDOW:
        raise ChatError("Chỉ thu hồi được tin nhắn trong vòng 24 giờ.")
    m.recalled_at, m.pinned_at, m.pinned_by_id = utcnow(), None, None
    db.session.commit()
    _push_update(m)
    return message_dto(m, me)


def react(m: Message, me: int, emoji: str | None) -> dict:
    """Tha / doi / go cam xuc (bam lai cung cam xuc = go)."""
    if m.recalled_at is not None:
        raise ChatError("Tin nhắn đã bị thu hồi.")
    allowed, reason = send_permission(me, m.conversation.other_user_id(me))
    if not allowed:
        raise ChatError(reason, 403)
    if emoji is not None and emoji not in REACTIONS:
        raise ChatError("Cảm xúc không hợp lệ.")
    row = db.session.get(MessageReaction, (m.id, me))
    if emoji is None or (row is not None and row.emoji == emoji):
        if row is not None:
            db.session.delete(row)
    elif row is None:
        db.session.add(MessageReaction(message_id=m.id, user_id=me, emoji=emoji))
    else:
        row.emoji, row.created_at = emoji, utcnow()
    db.session.commit()
    _push_update(m)
    return message_dto(m, me)


def pinned_messages(conv: Conversation, me: int) -> list[dict]:
    rows = (conv.messages.filter(Message.pinned_at.isnot(None), Message.recalled_at.is_(None))
            .order_by(Message.pinned_at.desc()).limit(MAX_PINNED).all())
    return [{"id": m.id, "preview": _preview(m, me)[:160], "mine": m.sender_id == me, "kind": m.kind,
             "pinned_at": iso(m.pinned_at)} for m in rows]


def pin(m: Message, me: int, on: bool) -> dict:
    if on:
        if m.recalled_at is not None:
            raise ChatError("Không ghim được tin đã thu hồi.")
        if m.pinned_at is None:
            n = m.conversation.messages.filter(Message.pinned_at.isnot(None), Message.recalled_at.is_(None)).count()
            if n >= MAX_PINNED:
                raise ChatError(f"Mỗi cuộc trò chuyện ghim tối đa {MAX_PINNED} tin. Hãy bỏ ghim bớt.")
            m.pinned_at, m.pinned_by_id = utcnow(), me
    else:
        m.pinned_at, m.pinned_by_id = None, None
    db.session.commit()
    _push_update(m)
    return message_dto(m, me)


def search_messages(conv: Conversation, me: int, q: str, limit: int = 30) -> list[dict]:
    q = (q or "").strip()
    if len(q) < 2:
        return []
    esc = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    rows = (conv.messages.filter(Message.recalled_at.is_(None), Message.kind.in_(("text", "image", "file")),
                                 Message.body.like(f"%{esc}%", escape="\\"))
            .order_by(Message.id.desc()).limit(limit).all())
    return [{"id": m.id, "mine": m.sender_id == me, "created_at": iso(m.created_at), "preview": _preview(m, me)[:200]}
            for m in rows]


LINK_RE = re.compile(r"(https?://[^\s<]+|www\.[^\s<]+)", re.IGNORECASE)


def media(conv: Conversation, me: int, kind: str) -> list[dict]:
    """Kho anh / tep / link da gui trong cuoc chat (moi nhat truoc). Tin bi Ve si che van hien la 'da bi che'."""
    base = conv.messages.filter(Message.recalled_at.is_(None))
    out = []
    if kind == "images":
        for m in base.filter(Message.kind == "image").order_by(Message.id.desc()).limit(120):
            hidden = m.sender_id != me and m.warning_level >= 2
            out.append({"id": m.id, "url": None if hidden else f"/api/attachments/{m.id}", "hidden": hidden,
                        "mine": m.sender_id == me, "created_at": iso(m.created_at)})
    elif kind == "files":
        for m in base.filter(Message.kind.in_(("file", "voice"))).order_by(Message.id.desc()).limit(120):
            out.append({"id": m.id, "name": m.attachment_name if m.kind == "file" else _preview(m, me), "kind": m.kind,
                        "size": m.attachment_size, "is_apk": is_apk(m), "blocked": attachment_blocked(m, me),
                        "mine": m.sender_id == me, "created_at": iso(m.created_at)})
    elif kind == "links":
        for m in base.filter(Message.body.like("%http%") | Message.body.like("%www.%")).order_by(Message.id.desc()).limit(200):
            danger = m.sender_id != me and m.warning_level >= 1
            for u in LINK_RE.findall(m.body or ""):
                out.append({"id": m.id, "url": u.rstrip(".,;:!?)"), "danger": danger, "mine": m.sender_id == me,
                            "created_at": iso(m.created_at)})
    else:
        raise ChatError("Loại không hợp lệ.")
    return out


def mark_read(conv: Conversation, me: int) -> dict:
    now = utcnow()
    rows = Message.query.filter(Message.conversation_id == conv.id, Message.sender_id != me,
                                Message.read_at.is_(None)).all()
    ids = [m.id for m in rows]
    for m in rows:
        m.read_at = now
        if m.delivered_at is None:
            m.delivered_at = now
    db.session.commit()
    other_id = conv.other_user_id(me)
    if ids:
        emit_to(other_id, "message:status", {"conversation_id": conv.id, "message_ids": ids, "status": "seen",
                                             "at": iso(now)})
    emit_to(me, "conversation:read", {"conversation_id": conv.id})        # dong bo cac tab khac cua toi
    return {"marked": len(ids)}


def relay_typing(me: int, cid, is_typing: bool):
    if not isinstance(cid, int):
        return
    conv = db.session.get(Conversation, cid)
    if conv is None or not conv.has_user(me):
        return
    other = conv.other_user_id(me)
    if send_permission(me, other)[0] and not block_state(me, other)[1]:
        emit_to(other, "typing", {"conversation_id": cid, "user_id": me, "is_typing": bool(is_typing)})


# --------------------------------------------------------------------------- #
# Hien dien
# --------------------------------------------------------------------------- #
def _notify_presence(uid: int, online: bool):
    user = db.session.get(User, uid)
    for fid in friend_ids(uid):
        i_blocked, blocked_me = block_state(uid, fid)
        if i_blocked or blocked_me:
            continue
        emit_to(fid, "presence", {"user_id": uid, "online": online, "last_seen": iso(user.last_seen_at) if user else None})


def on_user_online(uid: int):
    """Danh dau cac tin gui cho toi la 'da nhan' va bao cho nguoi gui; thong bao ban be."""
    now = utcnow()
    pending = (Message.query.join(Conversation, Message.conversation_id == Conversation.id)
               .filter(Message.sender_id != uid, Message.delivered_at.is_(None),
                       or_(Conversation.user_low_id == uid, Conversation.user_high_id == uid)).all())
    by_conv: dict[tuple[int, int], list[int]] = {}
    for m in pending:
        m.delivered_at = now
        by_conv.setdefault((m.conversation_id, m.sender_id), []).append(m.id)
    db.session.commit()
    for (cid, sender_id), ids in by_conv.items():
        emit_to(sender_id, "message:status", {"conversation_id": cid, "message_ids": ids, "status": "delivered",
                                              "at": iso(now)})
    _notify_presence(uid, True)


def on_user_offline(uid: int):
    user = db.session.get(User, uid)
    if user:
        user.last_seen_at = utcnow()
        db.session.commit()
    _notify_presence(uid, False)


# --------------------------------------------------------------------------- #
# Ket ban / chan
# --------------------------------------------------------------------------- #
def search_users(me: int, q: str, limit: int = 20) -> list[dict]:
    from services.profile_service import fold
    q = fold(q.strip().lstrip("@"))
    if not q:
        return []
    esc = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    model_key = db.session.get(User, me).model_key
    users = (User.query.filter(User.id != me, User.model_key == model_key, User.search_name.like(f"%{esc}%", escape="\\"))
             .order_by(User.display_name).limit(limit * 2).all())
    out = []
    for u in users:
        rel = relation(me, u.id)
        if rel["blocked_me"]:
            continue                                       # nguoi da chan toi: an khoi tim kiem
        out.append({**user_dto(u, me), "relation": rel["status"], "request_id": rel["request_id"],
                    "i_blocked": rel["i_blocked"]})
        if len(out) >= limit:
            break
    return out


def list_friends(me: int) -> list[dict]:
    users = User.query.filter(User.id.in_(friend_ids(me) or {0})).order_by(User.username).all()
    out = []
    for u in users:
        rel = relation(me, u.id)
        out.append({**user_dto(u, me), "i_blocked": rel["i_blocked"], "blocked_me": rel["blocked_me"]})
    return out


def list_requests(me: int) -> dict:
    inc = FriendRequest.query.filter_by(receiver_id=me, status="pending").order_by(FriendRequest.id.desc()).all()
    out = FriendRequest.query.filter_by(sender_id=me, status="pending").order_by(FriendRequest.id.desc()).all()
    mine = friend_ids(me)
    from services.reputation_service import badge
    return {"incoming": [{"id": r.id, "user": user_dto(r.sender, me, False), "created_at": iso(r.created_at),
                          "mutual": len(mine & friend_ids(r.sender_id)), "reputation": badge(r.sender, me)}
                         for r in inc if not block_state(me, r.sender_id)[1]],
            "outgoing": [{"id": r.id, "user": user_dto(r.receiver, me, False), "created_at": iso(r.created_at)}
                         for r in out]}


def _notify_accept(me: int, other_id: int):
    from services.notify import notify
    u = db.session.get(User, me)
    notify(other_id, "friend_accept", f"{u.name} đã chấp nhận lời mời kết bạn. Hai bạn đã là bạn bè!",
           link=f"/u/{u.username}", actor_id=me)


def _notify_friend_change(a: int, b: int, kind: str):
    for uid in (a, b):
        emit_to(uid, "friend:update", {"kind": kind})


def send_friend_request(me: int, other_id: int) -> dict:
    if other_id == me:
        raise ChatError("Không thể tự kết bạn với chính mình.")
    get_peer(me, other_id)
    i_blocked, blocked_me = block_state(me, other_id)
    if blocked_me:
        raise ChatError("Không thể gửi lời mời cho người này.", 403)
    if i_blocked:
        raise ChatError("Bạn đã chặn người này. Hãy bỏ chặn trước.", 403)
    fr = _pair_request(me, other_id)
    if fr:
        if fr.status == "accepted":
            raise ChatError("Hai bạn đã là bạn bè.")
        if fr.status == "pending":
            if fr.sender_id == me:
                raise ChatError("Bạn đã gửi lời mời rồi.")
            fr.status, fr.responded_at = "accepted", utcnow()            # ho da moi minh -> tu dong chap nhan
            db.session.commit()
            _notify_friend_change(me, other_id, "accepted")
            _notify_accept(me, other_id)
            return {"status": "friend"}
        # da bi tu choi truoc do: cho phep moi lai (dao chieu ban ghi cu neu can)
        fr.sender_id, fr.receiver_id, fr.status, fr.responded_at, fr.created_at = me, other_id, "pending", None, utcnow()
    else:
        db.session.add(FriendRequest(sender_id=me, receiver_id=other_id))
    try:
        db.session.commit()
    except IntegrityError:                                   # hai nguoi gui dong thoi -> coi nhu da gui
        db.session.rollback()
        raise ChatError("Lời mời đã tồn tại, hãy tải lại danh sách.", 409)
    _notify_friend_change(me, other_id, "request")
    sender = db.session.get(User, me)
    from services.notify import notify
    notify(other_id, "friend_request", f"{sender.name} đã gửi cho bạn lời mời kết bạn.", link="/friends", actor_id=me)
    return {"status": "sent"}


def respond_friend_request(me: int, request_id: int, accept: bool) -> dict:
    fr = db.session.get(FriendRequest, request_id)
    if fr is None or fr.receiver_id != me or fr.status != "pending":
        raise ChatError("Lời mời không tồn tại hoặc đã được xử lý.", 404)
    if block_state(me, fr.sender_id)[1]:
        raise ChatError("Không thể xử lý lời mời này.", 403)
    fr.status, fr.responded_at = ("accepted" if accept else "declined"), utcnow()
    db.session.commit()
    _notify_friend_change(me, fr.sender_id, "accepted" if accept else "declined")
    if accept:
        _notify_accept(me, fr.sender_id)
    return {"status": fr.status}


def cancel_friend_request(me: int, request_id: int) -> dict:
    fr = db.session.get(FriendRequest, request_id)
    if fr is None or fr.sender_id != me or fr.status != "pending":
        raise ChatError("Lời mời không tồn tại hoặc đã được xử lý.", 404)
    other = fr.receiver_id
    db.session.delete(fr)
    db.session.commit()
    _notify_friend_change(me, other, "cancelled")
    return {"status": "none"}


def unfriend(me: int, other_id: int) -> dict:
    fr = _pair_request(me, other_id)
    if not fr or fr.status != "accepted":
        raise ChatError("Hai bạn chưa là bạn bè.", 404)
    db.session.delete(fr)
    db.session.commit()
    _notify_friend_change(me, other_id, "unfriended")
    return {"status": "none"}


def block_user(me: int, other_id: int) -> dict:
    if other_id == me:
        raise ChatError("Không thể tự chặn chính mình.")
    get_peer(me, other_id)
    if not Block.query.filter_by(blocker_id=me, blocked_id=other_id).first():
        db.session.add(Block(blocker_id=me, blocked_id=other_id))
        db.session.commit()
    _notify_block_change(me, other_id)
    return {"i_blocked": True}


def unblock_user(me: int, other_id: int) -> dict:
    row = Block.query.filter_by(blocker_id=me, blocked_id=other_id).first()
    if row is not None and row.source == "guardian":
        raise ChatError("Vệ sĩ đã tự động chặn người này sau 3 lần gửi tin lừa đảo. Chỉ gỡ được qua Khiếu nại "
                        "(hai bên chụp ảnh trực tiếp và xác nhận nhau).", 403)
    if row:
        db.session.delete(row)
        db.session.commit()
    _notify_block_change(me, other_id)
    return {"i_blocked": False}


def _notify_block_change(me: int, other_id: int):
    emit_to(me, "block:update", {"user_id": other_id})
    emit_to(other_id, "block:update", {"user_id": me})
    # cap nhat lai hien dien hai chieu theo trang thai chan moi
    i_blocked, blocked_me = block_state(me, other_id)
    visible = are_friends(me, other_id) and not (i_blocked or blocked_me)
    for a, b in ((me, other_id), (other_id, me)):
        user = db.session.get(User, a)
        emit_to(b, "presence", {"user_id": a, "online": bool(visible and is_online(a)),
                                "last_seen": iso(user.last_seen_at) if user and visible else None})


def list_blocked(me: int) -> list[dict]:
    rows = Block.query.filter_by(blocker_id=me).order_by(Block.id.desc()).all()
    from services.trace_service import request_state
    return [{**user_dto(r.blocked, me, False), "block_source": r.source,
             "trace": request_state(me, r.blocked_id) if r.source == "guardian" else None} for r in rows]
