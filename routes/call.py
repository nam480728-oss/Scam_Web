"""Cua so cuoc goi (WebRTC). Goi di: /call/new?conv=<id>&video=1. Nghe may: /call/<id>."""
from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required

from db.database import db
from db.models import Call
from services import chat_service as cs

bp = Blueprint("call", __name__)


@bp.get("/call/new")
@login_required
def new_call():
    cid = request.args.get("conv", type=int)
    if not cid:
        abort(404)
    conv = cs.get_conversation(cid, current_user.id)
    other = cs.user_dto(db.session.get(type(current_user._get_current_object()), conv.other_user_id(current_user.id)),
                        current_user.id, with_presence=False)
    return render_template("call.html", hide_nav=True, mode="outgoing", conv_id=conv.id, call_id=None, other=other,
                           video=request.args.get("video", "1") == "1")


@bp.get("/call/<int:call_id>")
@login_required
def answer_call(call_id: int):
    call = db.session.get(Call, call_id)
    if call is None or current_user.id not in (call.caller_id, call.callee_id):
        abort(404)
    other = call.caller if call.callee_id == current_user.id else call.callee
    return render_template("call.html", hide_nav=True, mode="incoming", conv_id=call.conversation_id, call_id=call.id,
                           other=cs.user_dto(other, current_user.id, with_presence=False), video=call.video)
