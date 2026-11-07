"""Socket.IO: phong rieng moi nguoi dung, hien dien (online), dang nhap, da nhan."""
from __future__ import annotations

import threading

from flask import request
from flask_login import current_user
from flask_socketio import SocketIO, emit, join_room

socketio = SocketIO()

_presence: dict[int, set[str]] = {}
_lock = threading.Lock()


def room(user_id: int) -> str:
    return f"user:{user_id}"


def is_online(user_id: int) -> bool:
    with _lock:
        return bool(_presence.get(user_id))


def emit_to(user_id: int, event: str, data: dict):
    socketio.emit(event, data, to=room(user_id))


def _register(user_id: int, sid: str) -> bool:
    """Tra ve True neu day la ket noi dau tien (vua chuyen sang online)."""
    with _lock:
        first = not _presence.get(user_id)
        _presence.setdefault(user_id, set()).add(sid)
        return first


def _unregister(user_id: int, sid: str) -> bool:
    """Tra ve True neu vua mat ket noi cuoi cung (chuyen sang offline)."""
    with _lock:
        sids = _presence.get(user_id)
        if not sids:
            return False
        sids.discard(sid)
        if not sids:
            _presence.pop(user_id, None)
            return True
        return False


def init_socket_events(app):
    from services import chat_service as cs

    @socketio.on("connect")
    def on_connect(auth=None):
        if not current_user.is_authenticated:
            return False                                   # tu choi ket noi chua dang nhap
        uid = current_user.id
        join_room(room(uid))
        if _register(uid, request.sid):
            with app.app_context():
                cs.on_user_online(uid)

    @socketio.on("disconnect")
    def on_disconnect(*args):
        uid = current_user.id if current_user.is_authenticated else None
        if uid is None:
            return
        with app.app_context():
            from services import call_service
            call_service.on_disconnect(uid, request.sid)
        if _unregister(uid, request.sid):
            with app.app_context():
                cs.on_user_offline(uid)

    @socketio.on("guardian:join")
    def guardian_join(data=None):
        """Trang /guardian va /demo nhan dong su kien Ve si cua 'the gioi' mo hinh hien tai."""
        if current_user.is_authenticated:
            join_room(f"guardian:{current_user.model_key}")
            return {"ok": True}
        return {"error": "auth"}

    # ------------------------------------------------------------------ cuoc goi (signaling WebRTC)
    def _call_handler(fn):
        def wrapper(data=None):
            if not current_user.is_authenticated or not isinstance(data, dict):
                return {"error": "Yêu cầu không hợp lệ."}
            from services import call_service
            with app.app_context():
                try:
                    return fn(current_user._get_current_object(), data, call_service) or {"ok": True}
                except call_service.CallError as e:
                    return {"error": str(e)}
                except cs.ChatError as e:
                    return {"error": e.message}
        wrapper.__name__ = fn.__name__
        return wrapper

    @socketio.on("call:start")
    @_call_handler
    def call_start(me, data, svc):
        cid = data.get("conversation_id")
        if not isinstance(cid, int):
            return {"error": "Thiếu cuộc trò chuyện."}
        call = svc.start(me, cid, bool(data.get("video")), request.sid)
        return {"ok": True, "call": svc.call_dto(call, me.id)}

    @socketio.on("call:attach")
    @_call_handler
    def call_attach(me, data, svc):
        call = svc.get_call(data.get("call_id"), me.id)
        svc.attach(call, me.id, request.sid)
        return {"ok": True, "call": svc.call_dto(call, me.id)}

    @socketio.on("call:accept")
    @_call_handler
    def call_accept(me, data, svc):
        call = svc.get_call(data.get("call_id"), me.id)
        svc.accept(call, me, request.sid)
        return {"ok": True, "call": svc.call_dto(call, me.id)}

    @socketio.on("call:decline")
    @_call_handler
    def call_decline(me, data, svc):
        svc.decline(svc.get_call(data.get("call_id"), me.id), me)

    @socketio.on("call:end")
    @_call_handler
    def call_end(me, data, svc):
        svc.finish(svc.get_call(data.get("call_id"), me.id), "ended")

    @socketio.on("call:signal")
    @_call_handler
    def call_signal(me, data, svc):
        svc.relay_signal(svc.get_call(data.get("call_id"), me.id), me.id, data.get("data"))

    @socketio.on("typing")
    def on_typing(data):
        if not current_user.is_authenticated or not isinstance(data, dict):
            return
        cs.relay_typing(current_user.id, data.get("conversation_id"), bool(data.get("is_typing")))
