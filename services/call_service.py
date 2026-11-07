"""Cuoc goi thoai / video 1-1 (WebRTC). May chu chi lam signaling + luu lich su; media di thang giua 2 trinh duyet.

Trang thai song (trong bo nho): ai dang goi ai, sid cua cua so cuoc goi -> phat hien ngat ket noi, chuong goi qua han.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from db.database import db, iso, utcnow
from db.models import Call, Conversation, Message, User
from services import chat_service as cs
from services.realtime import emit_to

RING_TIMEOUT = 35            # giay


class CallError(Exception):
    pass


@dataclass
class LiveCall:
    call_id: int
    caller_id: int
    callee_id: int
    video: bool
    sids: dict[int, str] = field(default_factory=dict)   # user_id -> sid cua cua so cuoc goi
    started: float = field(default_factory=time.time)
    answered: float | None = None


_live: dict[int, LiveCall] = {}
_busy: dict[int, int] = {}                               # user_id -> call_id
_lock = threading.Lock()


def live(call_id: int) -> LiveCall | None:
    with _lock:
        return _live.get(call_id)


def busy_call(user_id: int) -> int | None:
    with _lock:
        return _busy.get(user_id)


def call_dto(call: Call, viewer_id: int) -> dict:
    other = call.callee if call.caller_id == viewer_id else call.caller
    return {"id": call.id, "conversation_id": call.conversation_id, "video": call.video, "status": call.status,
            "outgoing": call.caller_id == viewer_id, "other": cs.user_dto(other, viewer_id, with_presence=False),
            "created_at": iso(call.created_at)}


# --------------------------------------------------------------------------- #
# Vong doi cuoc goi
# --------------------------------------------------------------------------- #
def start(caller: User, conversation_id: int, video: bool, sid: str) -> Call:
    conv = cs.get_conversation(conversation_id, caller.id)
    callee_id = conv.other_user_id(caller.id)
    allowed, reason = cs.send_permission(caller.id, callee_id)
    if not allowed:
        raise CallError(reason)
    with _lock:
        if caller.id in _busy:
            raise CallError("Bạn đang trong một cuộc gọi khác.")
        if callee_id in _busy:
            raise CallError("Người này đang bận trong cuộc gọi khác.")
    call = Call(conversation_id=conv.id, caller_id=caller.id, callee_id=callee_id, video=bool(video))
    db.session.add(call)
    db.session.commit()
    lc = LiveCall(call.id, caller.id, callee_id, bool(video))
    if sid:
        lc.sids[caller.id] = sid
    with _lock:
        _live[call.id] = lc
        _busy[caller.id] = _busy[callee_id] = call.id
    emit_to(callee_id, "call:incoming", {"call": call_dto(call, callee_id)})
    t = threading.Timer(RING_TIMEOUT, _ring_timeout_cb, args=(call.id,))
    t.daemon = True
    t.start()
    return call


_app = None                                               # gan trong init (de chay ngoai request)


def init(app):
    global _app
    _app = app


def _ring_timeout_cb(call_id: int):
    if _app is None:
        return
    with _app.app_context():
        call = db.session.get(Call, call_id)
        if call is not None and call.status == "ringing":
            finish(call, "missed")


def attach(call: Call, user_id: int, sid: str):
    lc = live(call.id)
    if lc:
        lc.sids[user_id] = sid


def accept(call: Call, user: User, sid: str):
    if call.callee_id != user.id or call.status != "ringing":
        raise CallError("Cuộc gọi không còn khả dụng.")
    call.status, call.answered_at = "active", utcnow()
    db.session.commit()
    lc = live(call.id)
    if lc:
        lc.answered = time.time()
        lc.sids[user.id] = sid
    for uid in (call.caller_id, call.callee_id):
        emit_to(uid, "call:accepted", {"call_id": call.id})


def decline(call: Call, user: User):
    if user.id not in (call.caller_id, call.callee_id) or call.status != "ringing":
        return
    finish(call, "declined" if user.id == call.callee_id else "missed")


def finish(call: Call, status: str):
    """Ket thuc cuoc goi (ended | declined | missed). Ghi tin nhat ky cuoc goi vao hoi thoai."""
    if call.status in ("ended", "declined", "missed", "cut"):
        return
    was_active = call.status == "active"
    call.status = "ended" if was_active else status
    call.ended_at = utcnow()
    with _lock:
        _live.pop(call.id, None)
        for uid in (call.caller_id, call.callee_id):
            if _busy.get(uid) == call.id:
                _busy.pop(uid, None)
    secs = int((call.ended_at - call.answered_at).total_seconds()) if call.answered_at else 0
    kind = "video" if call.video else "thoại"
    if call.status == "ended":
        body = f"{'📹' if call.video else '📞'} Cuộc gọi {kind} · {_fmt_secs(secs)}"
    elif call.status == "declined":
        body = f"{'📹' if call.video else '📞'} Cuộc gọi {kind} bị từ chối"
    else:
        body = f"{'📹' if call.video else '📞'} Cuộc gọi {kind} nhỡ"
    conv = db.session.get(Conversation, call.conversation_id)
    msg = Message(conversation_id=conv.id, sender_id=call.caller_id, kind="call", body=body, call_id=call.id,
                  scan_status="off", delivered_at=utcnow())
    conv.last_message_at = msg.created_at = utcnow()
    db.session.add(msg)
    db.session.commit()
    for uid in (call.caller_id, call.callee_id):
        emit_to(uid, "call:ended", {"call_id": call.id, "status": call.status, "seconds": secs})
        emit_to(uid, "message:new", {"message": cs.message_dto(msg, uid), "conversation": cs.conversation_dto(conv, uid)})


def _fmt_secs(s: int) -> str:
    if s < 60:
        return f"{s} giây"
    return f"{s // 60} phút {s % 60:02d} giây"


def relay_signal(call: Call, user_id: int, data):
    if user_id not in (call.caller_id, call.callee_id) or call.status not in ("ringing", "active"):
        return
    other = call.callee_id if user_id == call.caller_id else call.caller_id
    emit_to(other, "call:signal", {"call_id": call.id, "data": data})


def on_disconnect(user_id: int, sid: str):
    """Cua so cuoc goi dong / mat mang -> ket thuc cuoc goi."""
    with _lock:
        ids = [c for c, lc in _live.items() if lc.sids.get(user_id) == sid]
    for cid in ids:
        call = db.session.get(Call, cid)
        if call:
            finish(call, "missed")


def get_call(call_id, user_id: int) -> Call:
    if not isinstance(call_id, int):
        raise CallError("Cuộc gọi không hợp lệ.")
    call = db.session.get(Call, call_id)
    if call is None or user_id not in (call.caller_id, call.callee_id):
        raise CallError("Không tìm thấy cuộc gọi.")
    return call


def reset():
    """Dung trong test."""
    with _lock:
        _live.clear()
        _busy.clear()
