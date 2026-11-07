"""Trang Tin nhan + API hoi thoai / tin nhan / dinh kem / tin thoai / tra loi / thu hoi / cam xuc / ghim / tim kiem / kho."""
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file
from flask_login import current_user, login_required

from db.database import db
from db.models import Message
from routes import login_required_api
from services import chat_service as cs
from services.ai_client import manager

bp = Blueprint("chat", __name__)


@bp.get("/messages")
@bp.get("/messages/<int:cid>")
@login_required
def messages_page(cid: int | None = None):
    return render_template("chat.html", initial_cid=cid)


@bp.get("/api/summary")
@login_required_api
def summary():
    convs = cs.list_conversations(current_user.id)
    reqs = cs.list_requests(current_user.id)
    from services.notify import unread_count
    return jsonify(unread_total=sum(c["unread"] for c in convs), requests=len(reqs["incoming"]),
                   notifications=unread_count(current_user.id), model=manager.active_name())


@bp.get("/api/conversations")
@login_required_api
def conversations():
    return jsonify(conversations=cs.list_conversations(current_user.id))


@bp.post("/api/conversations")
@login_required_api
def open_conversation():
    data = request.get_json(silent=True) or {}
    uid = data.get("user_id")
    if not isinstance(uid, int) or isinstance(uid, bool):
        return jsonify(error="Thiếu user_id."), 400
    conv = cs.get_or_create_conversation(current_user.id, uid)
    return jsonify(conversation=cs.conversation_dto(conv, current_user.id))


@bp.get("/api/conversations/<int:cid>")
@login_required_api
def conversation_detail(cid: int):
    conv = cs.get_conversation(cid, current_user.id)
    return jsonify(conversation=cs.conversation_dto(conv, current_user.id))


@bp.get("/api/conversations/<int:cid>/messages")
@login_required_api
def conversation_messages(cid: int):
    conv = cs.get_conversation(cid, current_user.id)
    before = request.args.get("before", type=int)
    limit = min(max(request.args.get("limit", current_app.config["PAGE_SIZE"], type=int), 1), 100)
    return jsonify(cs.history(conv, current_user.id, before, limit, around=request.args.get("around", type=int)))


@bp.post("/api/conversations/<int:cid>/messages")
@login_required_api
def post_message(cid: int):
    conv = cs.get_conversation(cid, current_user.id)
    voice = duration = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        body, file, reply = data.get("body"), None, data.get("reply_to_id")
    else:
        body, file, reply = request.form.get("body"), request.files.get("file"), request.form.get("reply_to_id", type=int)
        voice, duration = request.files.get("voice"), request.form.get("duration")
    if body is not None and not isinstance(body, str):
        return jsonify(error="Nội dung không hợp lệ."), 400
    if reply is not None and (not isinstance(reply, int) or isinstance(reply, bool)):
        return jsonify(error="Tin trả lời không hợp lệ."), 400
    dto = cs.send_message(conv, current_user._get_current_object(), body, file, reply_to_id=reply, voice=voice,
                          voice_duration=duration)
    return jsonify(message=dto), 201


@bp.post("/api/messages/<int:mid>/recall")
@login_required_api
def recall(mid: int):
    return jsonify(message=cs.recall_message(cs.get_message(mid, current_user.id), current_user.id))


@bp.post("/api/messages/<int:mid>/react")
@login_required_api
def react(mid: int):
    emoji = (request.get_json(silent=True) or {}).get("emoji")
    if emoji is not None and not isinstance(emoji, str):
        return jsonify(error="Cảm xúc không hợp lệ."), 400
    return jsonify(message=cs.react(cs.get_message(mid, current_user.id), current_user.id, emoji))


@bp.post("/api/messages/<int:mid>/pin")
@login_required_api
def pin(mid: int):
    on = (request.get_json(silent=True) or {}).get("pinned", True)
    if not isinstance(on, bool):
        return jsonify(error="Giá trị không hợp lệ."), 400
    return jsonify(message=cs.pin(cs.get_message(mid, current_user.id), current_user.id, on))


@bp.get("/api/conversations/<int:cid>/search")
@login_required_api
def search(cid: int):
    conv = cs.get_conversation(cid, current_user.id)
    return jsonify(results=cs.search_messages(conv, current_user.id, request.args.get("q", "")[:100]))


@bp.get("/api/conversations/<int:cid>/media")
@login_required_api
def media(cid: int):
    conv = cs.get_conversation(cid, current_user.id)
    return jsonify(items=cs.media(conv, current_user.id, request.args.get("kind", "images")))


@bp.post("/api/conversations/<int:cid>/read")
@login_required_api
def read_conversation(cid: int):
    conv = cs.get_conversation(cid, current_user.id)
    return jsonify(cs.mark_read(conv, current_user.id))


@bp.get("/api/attachments/<int:mid>")
@login_required_api
def attachment(mid: int):
    msg = db.session.get(Message, mid)
    if msg is None or not msg.attachment_path or msg.recalled_at is not None:
        abort(404)
    if not msg.conversation.has_user(current_user.id):
        abort(404)
    if cs.attachment_blocked(msg, current_user.id):
        return jsonify(error="Vệ sĩ đã chặn tải tệp cài đặt nguy hiểm này."), 403
    path = Path(current_app.config["UPLOAD_DIR"]) / msg.attachment_path
    if not path.is_file():
        abort(404)
    inline = msg.kind in ("image", "voice")
    mime = "application/octet-stream" if cs.is_apk(msg) else (msg.attachment_mime or "application/octet-stream")
    resp = send_file(path, mimetype=mime, as_attachment=not inline,
                     download_name=msg.attachment_name, conditional=True, max_age=3600)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp
