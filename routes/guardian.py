"""Ve si: API Bao cao / Phan hoi / Hoi Ve si / Vi sao? / Mat ma gia dinh + Bang dieu khien (/guardian) + Trinh dien (/demo)."""
from datetime import timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from agents import orchestrator
from db.database import db, utcnow
from db.models import Appeal, Block, Feedback, GuardianEvent, Message, User
from routes import login_required_api
from services import chat_service as cs
from services import guard_view

bp = Blueprint("guardian", __name__)
FEEDBACK_LABELS = {"not_scam", "acquaintance"}


def _me() -> User:
    return current_user._get_current_object()


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


# --------------------------------------------------------------------------- #
# Bao cao lua dao / Khong phai lua dao / Vi sao? / Hoi Ve si
# --------------------------------------------------------------------------- #
@bp.post("/api/guardian/report")
@login_required_api
def report():
    """Bao cao lua dao: CHI luu lai lam nhan train (khong canh bao nguoi khac, khong danh sach den)."""
    data = request.get_json(silent=True) or {}
    uid, mid = _int(data.get("user_id")), _int(data.get("message_id"))
    if mid:
        m = db.session.get(Message, mid)
        if m is None or not m.conversation.has_user(current_user.id) or m.sender_id == current_user.id:
            return jsonify(error="Không tìm thấy tin nhắn."), 404
        uid = m.sender_id
    if not uid or uid == current_user.id:
        return jsonify(error="Thiếu người cần báo cáo."), 400
    cs.get_peer(current_user.id, uid)
    res = orchestrator.report(_me(), uid, message_id=mid, reason=str(data.get("reason") or "Người dùng báo cáo lừa đảo")[:300])
    return jsonify(ok=True, **res)


@bp.post("/api/guardian/feedback")
@login_required_api
def feedback():
    data = request.get_json(silent=True) or {}
    label, mid = data.get("label"), _int(data.get("message_id"))
    if label not in FEEDBACK_LABELS:
        return jsonify(error="Nhãn không hợp lệ."), 400
    target = _int(data.get("user_id"))
    if mid:
        m = db.session.get(Message, mid)
        if m is None or not m.conversation.has_user(current_user.id) or m.sender_id == current_user.id:
            return jsonify(error="Không tìm thấy tin nhắn."), 404
        target = m.sender_id
    orchestrator.feedback(_me(), label, message_id=mid, target_user_id=target)
    return jsonify(ok=True)


@bp.get("/api/guardian/messages/<int:mid>")
@login_required_api
def why(mid: int):
    d = guard_view.message_detail(mid, current_user.id)
    if d is None:
        return jsonify(error="Không có kết quả phân tích cho tin này."), 404
    return jsonify(event=d)


@bp.post("/api/guardian/ask")
@login_required_api
def ask():
    data = request.get_json(silent=True) or {}
    text, cid = data.get("text"), _int(data.get("conversation_id"))
    if text is not None and not isinstance(text, str):
        return jsonify(error="Nội dung không hợp lệ."), 400
    return jsonify(orchestrator.ask(_me(), text=text, conversation_id=cid))


@bp.post("/api/guardian/family-check")
@login_required_api
def family_check():
    """Kiem tra cau tra loi Mat ma gia dinh cua doi phuong (tin moi nhat cua ho) - so voi dap an da ma hoa."""
    from werkzeug.security import check_password_hash
    from routes.settings import family_answer_key
    me, cid = _me(), _int((request.get_json(silent=True) or {}).get("conversation_id"))
    if not me.family_answer_hash:
        return jsonify(error="Bạn chưa đặt Mật mã gia đình trong Cài đặt."), 400
    conv = cs.get_conversation(cid, me.id) if cid else None
    if conv is None:
        return jsonify(error="Thiếu cuộc trò chuyện."), 400
    last = conv.messages.filter(Message.sender_id != me.id, Message.kind == "text").order_by(Message.id.desc()).first()
    if last is None:
        return jsonify(result="waiting")
    ok = check_password_hash(me.family_answer_hash, family_answer_key(last.body or ""))
    return jsonify(result="match" if ok else "mismatch")


# --------------------------------------------------------------------------- #
# Bang dieu khien Ve si
# --------------------------------------------------------------------------- #
@bp.get("/guardian")
@login_required
def dashboard():
    return render_template("guardian.html")


@bp.get("/api/guardian/events")
@login_required_api
def events():
    limit = min(max(request.args.get("limit", 40, type=int), 1), 200)
    rows = (GuardianEvent.query.filter_by(model_key=current_user.model_key).order_by(GuardianEvent.id.desc())
            .limit(limit).all())
    return jsonify(events=[orchestrator.event_dto(e) for e in rows])


@bp.get("/api/guardian/stats")
@login_required_api
def stats():
    mk = current_user.model_key
    msg_q = GuardianEvent.query.filter(GuardianEvent.model_key == mk, GuardianEvent.kind == "message")
    by_kind = dict(db.session.query(GuardianEvent.kind, func.count()).filter(GuardianEvent.model_key == mk)
                   .group_by(GuardianEvent.kind).all())
    by_level = dict(db.session.query(GuardianEvent.level, func.count()).filter(GuardianEvent.model_key == mk,
                                                                              GuardianEvent.kind == "message")
                    .group_by(GuardianEvent.level).all())
    world = db.session.query(User.id).filter(User.model_key == mk)
    blocks = Block.query.filter(Block.source == "guardian", Block.blocker_id.in_(world)).count()
    appeals = dict(db.session.query(Appeal.status, func.count()).filter(Appeal.protected_id.in_(world))
                   .group_by(Appeal.status).all())
    labels = dict(db.session.query(Feedback.label, func.count()).filter(Feedback.user_id.in_(world))
                  .group_by(Feedback.label).all())
    since = utcnow() - timedelta(hours=24)
    hourly = [0] * 24
    for (ts,) in db.session.query(GuardianEvent.created_at).filter(GuardianEvent.model_key == mk,
                                                                   GuardianEvent.created_at >= since).all():
        hourly[min(23, int((ts - since).total_seconds() // 3600))] += 1
    lat = [e.timings.get("agent3") for e in msg_q.order_by(GuardianEvent.id.desc()).limit(100)
           if e.timings and e.timings.get("agent3") is not None]
    from agents.agent3_adapter import reader
    from services.ai_client import manager
    return jsonify(modes={"agent3": reader.backend, "agent3_model": manager.active_name()}, by_kind=by_kind,
                   by_level={str(k): v for k, v in by_level.items()}, messages=by_kind.get("message", 0),
                   flagged=sum(v for k, v in by_level.items() if k), auto_blocks=blocks, appeals=appeals,
                   labels=labels, hourly=hourly, agent3_avg_ms=round(sum(lat) / len(lat), 1) if lat else None)


# --------------------------------------------------------------------------- #
# Trinh dien
# --------------------------------------------------------------------------- #
@bp.get("/demo")
@login_required
def demo_page():
    from services import demo_service as ds
    return render_template("demo.html", accounts=ds.demo_accounts(current_user.model_key))


def _scenario_dto(sc: dict) -> dict:
    from services import demo_service as ds
    mk = current_user.model_key
    v = ds.resolve(mk, sc["victim"])
    from services.notify import user_brief
    return {"id": sc["id"], "no": sc["no"], "title": sc["title"], "summary": sc["summary"], "expect": sc.get("expect"),
            "victim": {**user_brief(v), "agents": {"agent3": v.agent3_enabled}} if v else None,
            "scammers": [user_brief(u) for u in (ds.resolve(mk, s) for s in sc["scammers"]) if u],
            "steps": [ds._public_step(mk, st) for st in sc["steps"]]}


@bp.get("/api/demo/scenarios")
@login_required_api
def demo_scenarios():
    from services import demo_service as ds
    seeded = ds.resolve(current_user.model_key, "balan") is not None
    return jsonify(seeded=seeded, scenarios=[_scenario_dto(s) for s in ds.load()["scenarios"]] if seeded else [])


@bp.post("/api/demo/play/<sid>")
@login_required_api
def demo_play(sid: str):
    from flask import current_app
    from services import demo_service as ds
    try:
        ds.scenario(sid)
    except KeyError:
        return jsonify(error="Kịch bản không tồn tại."), 404
    if ds.resolve(current_user.model_key, "balan") is None:
        return jsonify(error="Chưa có dữ liệu demo. Hãy chạy: python seed.py"), 400
    delay = min(max(float((request.get_json(silent=True) or {}).get("delay", 2.5)), 1.0), 6.0)
    if not ds.play(current_app._get_current_object(), current_user.model_key, sid, delay):
        return jsonify(error="Kịch bản này đang phát."), 409
    return jsonify(ok=True)


@bp.post("/api/demo/reset/<sid>")
@login_required_api
def demo_reset(sid: str):
    from services import demo_service as ds
    try:
        ds.reset(current_user.model_key, sid)
    except KeyError:
        return jsonify(error="Kịch bản không tồn tại."), 404
    return jsonify(ok=True)


@bp.post("/api/demo/agents/<sid>")
@login_required_api
def demo_agents(sid: str):
    """Cong tac bat/tat AI 3 cua NAN NHAN trong kich ban (so sanh truoc / sau)."""
    from services import demo_service as ds
    data = request.get_json(silent=True) or {}
    try:
        v = ds.resolve(current_user.model_key, ds.scenario(sid)["victim"])
    except KeyError:
        return jsonify(error="Kịch bản không tồn tại."), 404
    if isinstance(data.get("agent3"), bool):
        v.agent3_enabled = data["agent3"]
    db.session.commit()
    return jsonify(agents={"agent3": v.agent3_enabled})


@bp.post("/demo/login/<username>")
def demo_login(username: str):
    """Dang nhap nhanh vao tai khoan DEMO (chi tai khoan is_demo cua the gioi mo hinh hien tai)."""
    from flask import current_app, redirect, url_for
    from flask_login import login_user

    from services.ai_client import manager
    if not current_app.config.get("DEMO_QUICK_LOGIN", True):
        return jsonify(error="Đăng nhập nhanh đã tắt."), 403
    u = User.query.filter_by(model_key=manager.active, username=username, is_demo=True).first()
    if u is None:
        return jsonify(error="Không phải tài khoản demo."), 404
    login_user(u, remember=True)
    nxt = request.args.get("next") or ""
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("feed.feed_page"))
